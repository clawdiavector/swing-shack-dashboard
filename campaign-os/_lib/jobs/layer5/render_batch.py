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
`review/planned`; approving it stays a human action behind a session login.

Record contract
---------------
    render_spec: {
      "archetype": "ss-fitting-headline",   # required
      "slug":      "spoon-wrong-clubs",     # required — filenames and asset id
      "channels":  ["instagram"],           # optional — archetype default
      "fields":    {...},                   # the archetype's text zones
      "photo":     "data/.../photo.jpg",    # optional — pack default
      "caption":   "...",                   # required — a post needs copy
      "date":      "2026-10-06"             # optional — else the event date
    }

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
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"

_ACTIVE_BRANDS = ("swing-shack", "stick", "bag-drop")
_LATCH_NAME = "render-batch-latch.json"


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


def _render_one(brand: str, spec: dict[str, Any]) -> dict[str, str]:
    """Compose one record's images and place them where the app serves them."""
    render_post = _scripts_module("render_post")
    from _lib.archetype_compose import compose_post_for_channels  # noqa: PLC0415

    arc = render_post._get(brand, spec["archetype"])
    applies = arc.get("applies_to") or {}
    channels = spec.get("channels") or applies.get("channels") or ["instagram"]
    photo = render_post._pick_photo(brand, arc, spec.get("photo"), None)
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
    return placed


def run(brand: str | None = None) -> dict[str, Any]:
    """Compose every pending render_spec on the brand's calendar."""
    from _lib import marketing_calendar as mc  # noqa: PLC0415

    schedule_posts = _scripts_module("schedule_posts")
    brands = [brand] if brand else list(_ACTIVE_BRANDS)
    latch = _load_latch()

    rendered: list[dict[str, Any]] = []
    skipped: list[str] = []

    cd_path = schedule_posts.campaign_data_path()
    if not cd_path.is_file():
        return {"ok": False, "error": f"no campaign-data.json at {cd_path}",
                "rendered": 0, "skipped": 0}
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
            fingerprint = _spec_fingerprint(rs)
            if latch.get(key) == fingerprint:
                continue  # already composed from exactly this spec
            if not rs.get("archetype") or not slug:
                skipped.append(f"{key}: render_spec needs archetype and slug")
                continue
            caption = rs.get("caption") or ""
            if not caption:
                # Same rule schedule_posts enforces: a post without copy is not
                # a post, and would sit in Review as an un-approvable stub.
                skipped.append(f"{key}: no caption -- a post needs copy")
                continue

            spec = {
                "brand": b,
                "archetype": rs["archetype"],
                "slug": slug,
                "channels": rs.get("channels"),
                "fields": rs.get("fields") or {},
                "photo": rs.get("photo"),
                "caption": caption,
                "date": rs.get("date") or record.get("event_date"),
            }
            try:
                placed = _render_one(b, spec)
            except Exception as e:  # noqa: BLE001 — one bad record must not stop the batch
                skipped.append(f"{key}: {e}")
                continue

            cid, aid, asset = schedule_posts.build_asset(
                spec, "calendar", approval="review", publish="planned")
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

            latch[key] = fingerprint
            rendered.append({"brand": b, "event_key": key, "asset_id": aid,
                             "channels": placed})

    if dirty:
        data["updatedAt"] = schedule_posts._now()
        cd_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    if rendered:
        _save_latch(latch)

    return {
        "ok": not skipped,
        "rendered": len(rendered),
        "skipped": len(skipped),
        "posts": rendered,
        "problems": skipped,
        "note": "Posts land as review/planned. Approving stays a human action.",
    }
