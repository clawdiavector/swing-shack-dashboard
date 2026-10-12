"""Render calendar records that carry a `render_spec`, deterministically.

Why this job exists
-------------------
`compose_post_for_channels()` writes its output to `$DATA_DIR/draft-assets/`.
In production that is the Railway volume, so a post rendered on a laptop can
never reach the live Review queue — the bytes are on the wrong disk. Until this
job existed the only route was `railway ssh` from the one machine with the
Railway CLI, which made scheduling a post a two-person operation.

The calendar is already writable with a bearer token
(`/api/calendar/v2/upsert` is in `DUAL_AUTH_PATHS`), and `upsert_event` keeps
fields it does not recognise. So an operator attaches the render spec to the
calendar record, and this job — also bearer-triggerable, via
`POST /api/jobs/run/render_batch` — composes it where the volume is.

Deterministic throughout: same archetype plus same fields produce byte-identical
output, no model, no credits, ~200ms per channel. The post lands as
`review/planned`. `POST /api/posts/lodge` (`_lib/post_lodge.py`) drives this
job for one record and can approve it straight onto the shelf.

Record contract
---------------
    render_spec: {
      "archetype": "ss-fitting-headline",   # this, or `image` — not both
      "image":     "swing-shack/x.jpg",     # a finished image, relative to
                                            #   $DATA_DIR/operator-uploads/
      "slug":      "spoon-wrong-clubs",     # required — filenames and asset id
      "channels":  ["instagram"],           # optional — archetype default, or
                                            #   the brand's publish channels
      "fields":    {...},                   # the archetype's text zones
      "photo":     "data/.../photo.jpg",    # optional — pack default
      "caption":   "...",                   # required — a post needs copy
      "date":      "2026-10-06"             # optional — else the event date
    }

`image` is the pass-through: a picture that is already finished (type baked
in by a model or a designer) is sized to each channel and placed as-is. Nothing
is composed on top. `post_lodge.save_upload()` is how it gets onto the volume.

Joining the week
----------------
A post only shows on This week when a draft sidecar names its calendar moment
(`unified_inbox._index_draft_sidecars`). The moment's `calendar_id` is a
revision id and changes whenever the record is edited, so a latched record
still gets its sidecar checked, and rewritten when it points at a stale id.

Idempotency
-----------
The latch is `$DATA_DIR/render-batch-latch.json`, mapping event_key to a hash of
the render_spec it was last composed from. The calendar itself cannot hold the
latch: `upsert_event` only persists a new revision when a field in its
MATERIAL_FIELDS list changes, so a status flag written back would silently
no-op. Hashing the spec also gives the behaviour an operator expects — edit the
spec and it re-renders, leave it alone and a re-run costs nothing.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"

_ACTIVE_BRANDS = ("swing-shack", "stick", "bag-drop")
_LATCH_NAME = "render-batch-latch.json"
UPLOADS_DIR = "operator-uploads"
_CAMPAIGN_BATCH = "calendar"

# Instagram's feed accepts 4:5 (portrait) to 1.91:1 (landscape). An image
# inside that range keeps its own shape; outside it is centre-cropped to the
# nearest edge, and the crop is reported because it can clip baked-in type.
_FEED_ASPECT = (4 / 5, 1.91)
_STORY_ASPECT = 9 / 16
_OUT_WIDTH = 1080


def _spec_fingerprint(spec: dict[str, Any]) -> str:
    """Stable hash of a render_spec — sorted keys so field order cannot matter."""
    return hashlib.sha256(
        json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


def _latch_path():
    # schedule_posts owns the DATA_DIR resolution the rest of this flow uses;
    # resolving it a second way here is how the two drift apart.
    return _scripts_module("schedule_posts").runtime_data_dir() / _LATCH_NAME


def _load_latch() -> dict[str, str]:
    p = _latch_path()
    if not p.is_file():
        return {}
    try:
        got = json.loads(p.read_text())
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        # A corrupt latch must not block rendering; worst case is a re-render.
        return {}


def _save_latch(latch: dict[str, str]) -> None:
    p = _latch_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(latch, indent=2, sort_keys=True) + "\n")


def _scripts_module(name: str):
    """Import a helper from campaign-os/scripts/ (it ships in the image).

    schedule_posts.py owns the asset shape the Review queue reads, and
    render_post.py owns photo selection and where published bytes land.
    Importing them keeps one definition of each rather than a second copy here
    that drifts the first time either changes.
    """
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    return __import__(name)


def uploads_root() -> Path:
    return _scripts_module("schedule_posts").runtime_data_dir() / UPLOADS_DIR


def resolve_upload(rel: str) -> Path:
    """Map a render_spec `image` to a file under operator-uploads/, or refuse.

    The calendar is bearer-writable, so `image` is untrusted input: anything
    that resolves outside the uploads directory is rejected rather than read.
    """
    root = uploads_root().resolve()
    path = (root / str(rel)).resolve()
    if root not in path.parents:
        raise ValueError(f"image must be a path inside {UPLOADS_DIR}/, got {rel!r}")
    if not path.is_file():
        raise ValueError(f"image not found on the volume: {UPLOADS_DIR}/{rel}")
    return path


def default_channels(brand: str) -> list[str]:
    """Where a pass-through post goes when the spec does not say."""
    from _lib.publish_sandbox import compose_publish_channels  # noqa: PLC0415

    return compose_publish_channels(brand) or ["instagram"]


def fit_for_channel(src, channel: str):
    """Size a finished image for one channel. Returns (PNG bytes, note or None)."""
    from PIL import Image  # noqa: PLC0415

    im = src.convert("RGB")
    w, h = im.size
    aspect = w / h
    if "story" in channel or "reel" in channel:
        target = _STORY_ASPECT
    else:
        target = min(max(aspect, _FEED_ASPECT[0]), _FEED_ASPECT[1])
    note = None
    if abs(target - aspect) > 0.005:
        if aspect > target:  # too wide — trim the sides
            nw = round(h * target)
            left = (w - nw) // 2
            im = im.crop((left, 0, left + nw, h))
        else:  # too tall — trim top and bottom
            nh = round(w / target)
            top = (h - nh) // 2
            im = im.crop((0, top, w, top + nh))
        note = (f"{channel}: cropped {w}x{h} to {target:.3f}:1 — check no "
                f"type was cut off")
    out_h = round(_OUT_WIDTH * im.size[1] / im.size[0])
    im = im.resize((_OUT_WIDTH, out_h), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG", compress_level=6)
    return buf.getvalue(), note


def _passthrough_one(brand: str, spec: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """Place a finished image as a post, one size per channel, nothing on top."""
    from PIL import Image  # noqa: PLC0415

    render_post = _scripts_module("render_post")
    src = resolve_upload(spec["image"])
    channels = spec.get("channels") or default_channels(brand)
    placed: dict[str, str] = {}
    notes: list[str] = []
    with Image.open(src) as im:
        for channel in channels:
            png, note = fit_for_channel(im, channel)
            out = render_post.publish_into_campaign_os(brand, spec["slug"], channel, png)
            placed[channel] = out["url"]
            if note:
                notes.append(note)
    return placed, notes


def _render_one(brand: str, spec: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """Compose one record's images and place them where the app serves them."""
    if spec.get("image"):
        return _passthrough_one(brand, spec)

    render_post = _scripts_module("render_post")
    from _lib.archetype_compose import compose_post_for_channels  # noqa: PLC0415

    try:
        arc = render_post._get(brand, spec["archetype"])
        photo = render_post._pick_photo(brand, arc, spec.get("photo"), None)
    except SystemExit as e:
        # render_post is a CLI and exits on a bad archetype or photo path.
        # SystemExit is not an Exception, so left alone it would end the whole
        # batch instead of skipping this one record.
        raise ValueError(str(e)) from None
    applies = arc.get("applies_to") or {}
    channels = spec.get("channels") or applies.get("channels") or ["instagram"]
    if applies.get("needs_photo") and photo is None:
        raise ValueError(
            f"{brand}/{spec['archetype']} needs a photo and its pack has none"
        )

    composed = compose_post_for_channels(
        brand_id=brand, archetype=arc, channels=list(channels),
        fields=dict(spec.get("fields") or {}), photo_bytes=photo,
    )
    if not composed:
        raise ValueError(
            f"{brand}/{spec['archetype']} produced nothing for channels {channels}"
        )

    placed: dict[str, str] = {}
    for channel, png in composed.items():
        out = render_post.publish_into_campaign_os(brand, spec["slug"], channel, png)
        placed[channel] = out["url"]
    return placed, []


def _sidecar_path(asset_id: str) -> Path:
    return (_scripts_module("schedule_posts").runtime_data_dir()
            / "draft-assets" / f"{asset_id}.json")


def _repair_sidecar(brand: str, slug: str, cal_id: str, campaigns: dict) -> bool:
    """Re-point a latched post's sidecar at the moment's current revision.

    Returns True when it rewrote one. A post rendered before sidecars were
    written, or whose record was edited since, would otherwise sit in Review
    and never show on This week.
    """
    schedule_posts = _scripts_module("schedule_posts")
    cid = schedule_posts._campaign_id_for(brand, _CAMPAIGN_BATCH)
    aid = schedule_posts._asset_id_for(brand, slug)
    asset = ((campaigns.get(cid) or {}).get("assets") or {}).get(aid)
    if not isinstance(asset, dict):
        return False
    want = f"calendar_candidate:{brand}:{cal_id}"
    path = _sidecar_path(aid)
    if path.is_file():
        try:
            if json.loads(path.read_text()).get("source_inbox_item_id") == want:
                return False
        except (OSError, ValueError):
            pass
    composed = asset.get("composed") if isinstance(asset.get("composed"), dict) else None
    schedule_posts.write_draft_sidecar(
        {"brand": brand, "slug": slug, "channels": list(composed or {}) or None},
        cid, aid, cal_id, composed=composed,
        created_by="campaign-os/render_batch",
    )
    # Queued publish rows name the moment too; re-point them (and a moved date)
    # or Release finds nothing for the new revision.
    from _lib.publish_sandbox import sync_queue_rows_for_asset  # noqa: PLC0415

    sync_queue_rows_for_asset(brand_id=brand, asset_id=aid, asset=asset)
    return True


def run(brand: str | None = None, event_key: str | None = None) -> dict[str, Any]:
    """Compose every pending render_spec on the brand's calendar.

    `event_key` narrows the sweep to one record, which is how post_lodge renders
    the post it just wrote without reporting on everything else in the calendar.
    """
    from _lib import marketing_calendar as mc  # noqa: PLC0415

    schedule_posts = _scripts_module("schedule_posts")
    brands = [brand] if brand else list(_ACTIVE_BRANDS)
    latch = _load_latch()

    rendered: list[dict[str, Any]] = []
    skipped: list[str] = []
    rejoined: list[str] = []

    cd_path = schedule_posts.campaign_data_path()
    if not cd_path.is_file():
        # Not created here: unified_inbox falls back to the bundled copy when
        # the volume has none, and a fresh file would silently shadow it.
        return {"ok": False, "error": f"no campaign-data.json at {cd_path}",
                "rendered": 0, "skipped": 0, "rejoined": [], "posts": [],
                "problems": [f"no campaign-data.json at {cd_path}"]}
    data = json.loads(cd_path.read_text())
    campaigns = data.setdefault("campaigns", {})
    dirty = False

    for b in brands:
        for record in mc.canonical_records(b):
            rs = record.get("render_spec")
            if not isinstance(rs, dict):
                continue
            slug = rs.get("slug")
            key = record.get("event_key") or slug or "<no key>"
            if event_key and key != event_key:
                continue
            cal_id = str(record.get("calendar_id") or key)
            fingerprint = _spec_fingerprint(rs)
            if latch.get(key) == fingerprint:
                # Already composed from exactly this spec — but the moment may
                # have a new revision id since, so keep the week join current.
                if slug and _repair_sidecar(b, slug, cal_id, campaigns):
                    rejoined.append(key)
                continue
            if not slug:
                skipped.append(f"{key}: render_spec needs a slug")
                continue
            if bool(rs.get("archetype")) == bool(rs.get("image")):
                skipped.append(
                    f"{key}: render_spec needs exactly one of archetype "
                    f"(compose from a template) or image (a finished picture)")
                continue
            caption = rs.get("caption") or ""
            if not caption:
                # Same rule schedule_posts enforces: a post without copy is not
                # a post, and would sit in Review as an un-approvable stub.
                skipped.append(f"{key}: no caption -- a post needs copy")
                continue

            spec = {
                "brand": b,
                "archetype": rs.get("archetype"),
                "image": rs.get("image"),
                "slug": slug,
                "channels": rs.get("channels"),
                "fields": rs.get("fields") or {},
                "photo": rs.get("photo"),
                "caption": caption,
                "date": rs.get("date") or record.get("event_date"),
            }
            try:
                placed, notes = _render_one(b, spec)
            except Exception as e:  # noqa: BLE001 — one bad record must not stop the batch
                skipped.append(f"{key}: {e}")
                continue

            # build_asset takes its primary channel from the spec; for a
            # pass-through that is whatever default_channels() resolved.
            spec["channels"] = list(placed)
            cid, aid, asset = schedule_posts.build_asset(
                spec, _CAMPAIGN_BATCH, approval="review", publish="planned")
            asset["composed"] = dict(placed)
            if spec["image"]:
                asset["renderMode"] = "operator-image"
                asset["history"][0]["note"] = (
                    f"finished image placed as-is for {spec['date']}; "
                    f"awaiting human approval")
            campaign = campaigns.setdefault(cid, {
                "identity": {"name": f"{b} — calendar"},
                "brand_id": b,
                "assets": {},
            })
            assets = campaign.setdefault("assets", {})
            existing = assets.get(aid)
            if isinstance(existing, dict):
                asset["createdAt"] = existing.get("createdAt", asset["createdAt"])
                asset["history"] = (existing.get("history") or []) + asset["history"]
            assets[aid] = asset
            dirty = True

            schedule_posts.write_draft_sidecar(
                spec, cid, aid, cal_id, composed=placed,
                created_by="campaign-os/render_batch")
            # Review hides campaigns the brand does not own in brands.json.
            if problem := schedule_posts.register_campaign_ownership(b, cid):
                notes.append(problem)

            latch[key] = fingerprint
            rendered.append({"brand": b, "event_key": key, "asset_id": aid,
                             "campaign_id": cid, "calendar_id": cal_id,
                             "channels": placed, "notes": notes})

    if dirty:
        data["updatedAt"] = schedule_posts._now()
        cd_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    if rendered:
        _save_latch(latch)

    return {
        "ok": not skipped,
        "rendered": len(rendered),
        "skipped": len(skipped),
        "rejoined": rejoined,
        "posts": rendered,
        "problems": skipped,
        "note": "Posts land as review/planned. Approving stays a human action.",
    }
