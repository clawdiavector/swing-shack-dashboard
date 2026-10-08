"""Lodge one finished post onto the live calendar, ready to release.

The flow a person runs from Claude Code on any machine, with only a
COS_JOB_TOKEN:

    POST /api/posts/lodge   image + caption + date  ->  On the shelf

One call does what used to take three and a Railway shell:

  1. the image (if any) is written to $DATA_DIR/operator-uploads/ on the volume
  2. a calendar moment is booked for the date, carrying a render_spec
  3. render_batch places it (pass-through) or composes it (archetype) and
     writes the sidecar that joins it to This week
  4. unless approve=False, the draft is approved through the same
     unified_inbox.approve_item the Review button calls, which queues one
     publish row per channel

It then sits on the shelf as `scheduled` until someone clicks Release now.
Release stays the human gate; nothing here posts.

Lodging the same slug again replaces the post (new image or caption, same
calendar slot). A post that has already been released or posted is refused,
because editing it here would not reach what is already queued to go out.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
_TZ = ZoneInfo("Africa/Johannesburg")
_IMAGE_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
MAX_IMAGE_BYTES = 20 * 1024 * 1024
_CAPTION_MAX = 2200  # Instagram's limit; Facebook's is far higher
_LOCKED_STATES = ("released", "posted")


class LodgeError(ValueError):
    """A request this module refuses, with the HTTP status that fits it."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _render_batch():
    from _lib.jobs.layer5 import render_batch  # noqa: PLC0415

    return render_batch


def save_upload(brand: str, slug: str, image_bytes: bytes) -> tuple[str, dict[str, Any]]:
    """Validate an image and write it under operator-uploads/. Returns (rel, info).

    The filename carries a content hash, so a new picture under the same slug
    changes the render_spec and re-renders, and the same picture lodged twice
    is a no-op.
    """
    from PIL import Image, UnidentifiedImageError  # noqa: PLC0415

    if not image_bytes:
        raise LodgeError("image is empty")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise LodgeError(
            f"image is {len(image_bytes) // (1024 * 1024)} MB; the limit is "
            f"{MAX_IMAGE_BYTES // (1024 * 1024)} MB", 413)
    try:
        with Image.open(io.BytesIO(image_bytes)) as im:
            fmt = im.format
            size = im.size
            im.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as e:
        raise LodgeError(f"image could not be read: {e}") from None
    ext = _IMAGE_FORMATS.get(str(fmt))
    if not ext:
        raise LodgeError(f"image is {fmt}; send JPEG, PNG or WebP")

    digest = hashlib.sha256(image_bytes).hexdigest()[:12]
    rel = f"{brand}/{slug}-{digest}.{ext}"
    path = _render_batch().uploads_root() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_bytes(image_bytes)
    info = {"stored_as": f"{_render_batch().UPLOADS_DIR}/{rel}",
            "format": fmt, "width": size[0], "height": size[1]}
    return rel, info


def _current_record(brand: str, event_key: str) -> dict[str, Any] | None:
    from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

    for rec in canonical_records(brand):
        if rec.get("event_key") == event_key:
            return rec
    return None


def _campaign_asset(campaign_id: str, asset_id: str) -> dict[str, Any]:
    rb = _render_batch()
    path = rb._scripts_module("schedule_posts").campaign_data_path()
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return ((data.get("campaigns") or {}).get(campaign_id) or {}).get(
        "assets", {}).get(asset_id) or {}


def _validate(brand: str, slug: str, date_s: str, caption: str,
              channels: list[str] | None) -> date:
    from _lib.marketing_calendar import VALID_BRAND_IDS  # noqa: PLC0415

    if brand not in VALID_BRAND_IDS:
        raise LodgeError(f"brand must be one of {sorted(VALID_BRAND_IDS)}, got {brand!r}")
    if not _SLUG.match(slug or ""):
        raise LodgeError(
            "slug must be 2-64 characters of lowercase letters, digits and "
            f"hyphens, got {slug!r}")
    try:
        day = date.fromisoformat(str(date_s or ""))
    except ValueError:
        raise LodgeError(f"date must be YYYY-MM-DD, got {date_s!r}") from None
    today = datetime.now(_TZ).date()
    if day < today:
        raise LodgeError(f"date {day} is in the past (today is {today} in Johannesburg)")
    if not (caption or "").strip():
        raise LodgeError("caption is required -- a post needs copy")
    if len(caption) > _CAPTION_MAX:
        raise LodgeError(f"caption is {len(caption)} characters; Instagram allows {_CAPTION_MAX}")
    if channels is not None and (not isinstance(channels, list)
                                 or not all(isinstance(c, str) and c for c in channels)):
        raise LodgeError("channels must be a list of channel names")
    return day


def lodge_post(
    *,
    brand: str,
    slug: str,
    date: str,
    caption: str,
    image_bytes: bytes | None = None,
    archetype: str | None = None,
    fields: dict[str, Any] | None = None,
    photo: str | None = None,
    channels: list[str] | None = None,
    title: str | None = None,
    created_by: str = "operator",
    approve: bool = True,
) -> dict[str, Any]:
    """Book, render and (by default) approve one post. Raises LodgeError."""
    from _lib import unified_inbox  # noqa: PLC0415
    from _lib.marketing_calendar import transition_status, upsert_event  # noqa: PLC0415

    caption = (caption or "").replace("\r\n", "\n").strip()
    day = _validate(brand, slug, date, caption, channels)
    if bool(image_bytes) == bool(archetype):
        raise LodgeError(
            "send exactly one of image (a finished picture) or archetype "
            "(compose from a template)")

    rb = _render_batch()
    schedule_posts = rb._scripts_module("schedule_posts")
    event_key = f"{brand}:{slug}"

    prior = _current_record(brand, event_key)
    if prior is not None:
        state = unified_inbox.post_state(
            prior, index=unified_inbox.build_post_index(brand_id=brand)).get("state")
        if state in _LOCKED_STATES:
            raise LodgeError(
                f"{event_key} is already {state}; lodge it under a new slug or "
                f"change it in Campaign OS", 409)

    render_spec: dict[str, Any] = {"slug": slug, "caption": caption, "date": day.isoformat()}
    upload: dict[str, Any] | None = None
    if image_bytes:
        render_spec["image"], upload = save_upload(brand, slug, image_bytes)
    else:
        render_spec["archetype"] = archetype
        if fields:
            render_spec["fields"] = dict(fields)
        if photo:
            render_spec["photo"] = photo
    if channels:
        render_spec["channels"] = list(channels)

    primary = (channels or rb.default_channels(brand))[0]
    record = {
        "event_key": event_key,
        "brand_id": brand,
        "type": "moment",
        # week_board only shows moments whose status is approved/candidate/
        # active/completed; "approved" books the slot. Whether the POST may go
        # out is the asset's own approval and the Release click.
        "status": "approved",
        "title": (title or caption.split("\n", 1)[0]).strip()[:72] or slug,
        "event_date": day.isoformat(),
        "event_start": day.isoformat(),
        "event_end": day.isoformat(),
        "source_type": "operator",
        "source_origin": "internal_strategy",
        "created_by": created_by or "operator",
        "primary_channel": primary,
        "post_type": archetype or "operator-image",
        # render_mode is deliberately unset: "oneshot" would queue a paid
        # model draft for this moment on top of the image we already have.
        "render_spec": render_spec,
    }
    try:
        upsert = upsert_event(brand, record)
    except (ValueError, PermissionError) as e:
        raise LodgeError(f"calendar refused the record: {e}") from None
    rec = upsert.get("record") or {}
    if str(rec.get("status") or "") != "approved":
        transition_status(brand, str(rec.get("calendar_id") or event_key), "approved",
                          reason=f"lodged by {created_by}")

    batch = rb.run(brand, event_key=event_key)
    if batch.get("problems"):
        raise LodgeError("render failed: " + "; ".join(batch["problems"]), 422)
    posts = batch.get("posts") or []
    rendered = posts[0] if posts else None

    cid = schedule_posts._campaign_id_for(brand, rb._CAMPAIGN_BATCH)
    aid = schedule_posts._asset_id_for(brand, slug)
    approval = None
    if approve and str(_campaign_asset(cid, aid).get("approvalStatus") or "") != "approved":
        approval = unified_inbox.approve_item(
            f"draft_asset:{cid}:{aid}", editor=created_by or "operator",
            reason="lodged ready for release")
        if not approval.get("ok"):
            raise LodgeError(f"rendered, but approval failed: {approval.get('error')}", 500)

    current = _current_record(brand, event_key) or rec
    cal_id = str(current.get("calendar_id") or event_key)
    state = unified_inbox.post_state_for(brand, cal_id) or {}
    asset = _campaign_asset(cid, aid)

    return {
        "ok": True,
        "brand": brand,
        "event_key": event_key,
        "calendar_id": cal_id,
        "asset_id": aid,
        "go_live_date": day.isoformat(),
        "state": state.get("state"),
        "next_action": state.get("next_action"),
        "calendar_action": upsert.get("action"),
        "rendered": bool(rendered),
        "images": dict(asset.get("composed") or {}),
        "publish_queue_rows": (approval or {}).get("publish_queue_rows"),
        "upload": upload,
        "notes": (rendered or {}).get("notes") or [],
        "links": {
            "shelf": "/app/shelf",
            "week": "/app/week",
            "review": f"/app/review/{state.get('inbox_item_id')}" if state.get("inbox_item_id") else "/app/review",
        },
    }
