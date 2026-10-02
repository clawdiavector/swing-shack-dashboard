"""Review draft actions — regenerate / recompose / swap (P4 API)."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_caption_keep_lock = threading.Lock()

from _lib.jobs.layer1._io import atomic_write


def _data_dir() -> Path:
    import os

    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def _normalize_draft_item_id(draft_id: str) -> str:
    raw = (draft_id or "").strip()
    if not raw:
        raise ValueError("draft id required")
    if raw.startswith("draft_asset:"):
        return raw
    if ":" in raw:
        return f"draft_asset:{raw}"
    raise ValueError("draft id must be draft_asset:<campaign>:<asset>")


def _load_sidecar(asset_id: str) -> dict[str, Any]:
    path = _data_dir() / "draft-assets" / f"{asset_id}.json"
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _save_sidecar(asset_id: str, sidecar: dict[str, Any]) -> None:
    atomic_write(f"draft-assets/{asset_id}.json", sidecar)


def resolve_draft(draft_id: str) -> dict[str, Any]:
    """Resolve draft_asset context from URL id."""
    from _lib import unified_inbox as ui

    item_id = _normalize_draft_item_id(draft_id)
    item_type, key = ui._parse_item_id(item_id)  # noqa: SLF001
    if item_type != "draft_asset":
        raise ValueError("not a draft_asset")
    campaign_id, asset_id = key.split(":", 1)
    data = ui._load_campaign_data()  # noqa: SLF001
    campaign = (data.get("campaigns") or {}).get(campaign_id)
    if not isinstance(campaign, dict):
        raise LookupError("campaign not found")
    asset = (campaign.get("assets") or {}).get(asset_id)
    if not isinstance(asset, dict):
        raise LookupError("asset not found")
    sidecar = _load_sidecar(asset_id)
    item = ui.find_item(item_id)
    brand_id = str((item or {}).get("brand_id") or sidecar.get("brand_id") or "")
    if not brand_id:
        brand_id = str(campaign.get("identity", {}).get("brand") or "")
    moment_id = str(sidecar.get("source_inbox_item_id") or "")
    return {
        "item_id": item_id,
        "campaign_id": campaign_id,
        "asset_id": asset_id,
        "brand_id": brand_id,
        "asset": asset,
        "sidecar": sidecar,
        "moment_id": moment_id,
    }


# Default real-venue files for SS template compose (not stand-ins).
_SS_TEMPLATE_VENUE_REL: dict[str, str] = {
    "ss-service-promo": "templates/service-promo/photos/venue-taildrop-service-promo.png",
    "ss-did-you-know": "templates/did-you-know/photos/venue-taildrop-coaching.png",
    "ss-fitting-headline": "templates/fitting-headline/photos/venue-taildrop-fitting.png",
}


def _load_brand_rel_photo(brand_id: str, rel: str) -> bytes | None:
    from _lib.brand_overlay import _candidate_brand_dirs

    rel_path = rel.strip().strip("/")
    for root in _candidate_brand_dirs(brand_id):
        path = root / rel_path
        if path.is_file():
            return path.read_bytes()
    return None


def _first_library_photo_bytes(brand_id: str, library_rel: str) -> bytes | None:
    from _lib.brand_overlay import _candidate_brand_dirs

    rel_dir = library_rel.strip().strip("/")
    if not rel_dir:
        return None
    suffixes = (".jpg", ".jpeg", ".png", ".webp")
    for root in _candidate_brand_dirs(brand_id):
        base = root / rel_dir
        if not base.is_dir():
            continue
        files = sorted(p for p in base.iterdir() if p.is_file() and p.suffix.lower() in suffixes)
        if files:
            return files[0].read_bytes()
    return None


def _default_template_venue_bytes(brand_id: str, archetype_id: str) -> bytes | None:
    rel = _SS_TEMPLATE_VENUE_REL.get(archetype_id or "")
    if rel:
        return _load_brand_rel_photo(brand_id, rel)
    from _lib.archetypes import archetype_by_id

    arch = archetype_by_id(brand_id, archetype_id) or {}
    bg = arch.get("background") if isinstance(arch.get("background"), dict) else {}
    if bg.get("kind") == "photo_full_bleed" and bg.get("library"):
        return _first_library_photo_bytes(brand_id, str(bg.get("library") or ""))
    return None


def resolve_compose_photo_bytes(
    brand_id: str,
    archetype_id: str,
    sidecar: dict[str, Any],
) -> bytes | None:
    """Explicit sidecar venue / candidates, then known Taildrop, then pack default."""
    explicit = _photo_bytes_for_sidecar(sidecar)
    if explicit:
        return explicit
    if brand_id == "swing-shack" and archetype_id == "ss-service-promo":
        legacy = _data_dir() / "draft-assets" / "images" / "swing-shack" / "ss-venue-draft-5f71e71f280b.png"
        if legacy.is_file():
            return legacy.read_bytes()
    return _default_template_venue_bytes(brand_id, archetype_id)


def _photo_bytes_for_sidecar(sidecar: dict[str, Any]) -> bytes | None:
    venue = sidecar.get("venue_photo")
    if venue:
        path = Path(str(venue))
        if not path.is_file():
            alt = _data_dir() / str(venue).lstrip("/")
            path = alt if alt.is_file() else path
        if path.is_file():
            return path.read_bytes()
    qc = sidecar.get("qc") if isinstance(sidecar.get("qc"), dict) else {}
    candidates = sidecar.get("photo_candidates") if isinstance(sidecar.get("photo_candidates"), list) else []
    if not candidates:
        return None
    sel = qc.get("selected")
    idx = int(sel if sel is not None else 0)
    if idx < 0 or idx >= len(candidates):
        idx = 0
    path = Path(str(candidates[idx].get("path") or ""))
    if not path.is_file():
        alt = _data_dir() / str(candidates[idx].get("path") or "").lstrip("/")
        path = alt if alt.is_file() else path
    if not path.is_file():
        return None
    return path.read_bytes()


def _fields_for_compose(
    *,
    brand_id: str,
    asset: dict[str, Any],
    sidecar: dict[str, Any],
    archetype: dict[str, Any] | None = None,
    headline: str | None = None,
    cta: str | None = None,
) -> dict[str, str]:
    from _lib.archetype_compose import caption_fields_from_text
    from _lib.compose_visual_copy import visual_copy_for_archetype

    caption = str(asset.get("caption") or "")
    moment_id = str(sidecar.get("source_inbox_item_id") or "")
    asset_title = str(asset.get("name") or asset.get("title") or sidecar.get("title") or "")
    applies = archetype.get("applies_to") if isinstance(archetype, dict) else {}
    compose_only = isinstance(applies, dict) and applies.get("needs_photo") is False
    if archetype and (moment_id or compose_only):
        content = visual_copy_for_archetype(
            brand_id=brand_id,
            moment_id=moment_id,
            caption=caption,
            archetype=archetype,
            asset_title=asset_title or None,
            sidecar=sidecar,
        )
    elif moment_id:
        from _lib.jobs.layer5.create_photo_compose import _content_from_caption, build_image_draft_context

        ctx = build_image_draft_context(brand_id, moment_id)
        content = _content_from_caption(caption, ctx)
    else:
        content = caption_fields_from_text(caption)
    if headline is not None and str(headline).strip():
        content["caption_hook"] = str(headline).strip()
    if cta is not None and str(cta).strip():
        content["cta"] = str(cta).strip()
    return {k: str(v) for k, v in content.items()}


def _archetype_for_draft(
    *,
    brand_id: str,
    moment_id: str,
    sidecar: dict[str, Any],
    archetype_id: str | None,
) -> dict[str, Any]:
    from _lib.archetypes_v2 import archetype_by_id, select_archetype

    if archetype_id:
        found = archetype_by_id(brand_id, archetype_id)
        if not found:
            raise ValueError(f"unknown archetype_id: {archetype_id}")
        return found
    existing = sidecar.get("archetype") if isinstance(sidecar.get("archetype"), dict) else {}
    eid = str(existing.get("id") or "").strip()
    if eid:
        found = archetype_by_id(brand_id, eid)
        if found:
            return found
    if moment_id:
        return select_archetype(brand_id, moment_id)
    return select_archetype(brand_id, "")


def recompose_draft(
    draft_id: str,
    *,
    headline: str | None = None,
    cta: str | None = None,
    service_label: str | None = None,
    archetype_id: str | None = None,
    candidate_index: int | None = None,
    venue_photo: str | None = None,
) -> dict[str, Any]:
    """Synchronous compose_post only — returns composed URL map."""
    from _lib.archetype_compose import compose_post_for_channels
    from _lib.jobs.layer5.image_draft_context import image_url_for, primary_channel_for_item
    from _lib.publish_sandbox import intended_publish_channels
    from _lib import unified_inbox as ui

    ctx = resolve_draft(draft_id)
    brand_id = ctx["brand_id"]
    asset_id = ctx["asset_id"]
    asset = ctx["asset"]
    sidecar = dict(ctx["sidecar"])
    moment_id = ctx["moment_id"]

    if venue_photo and str(venue_photo).strip():
        sidecar["venue_photo"] = str(venue_photo).strip()

    if candidate_index is not None:
        qc = sidecar.get("qc") if isinstance(sidecar.get("qc"), dict) else {}
        qc = dict(qc)
        qc["selected"] = int(candidate_index)
        sidecar["qc"] = qc

    archetype = _archetype_for_draft(
        brand_id=brand_id,
        moment_id=moment_id,
        sidecar=sidecar,
        archetype_id=archetype_id,
    )
    if archetype_id:
        sidecar["archetype"] = {
            "id": str(archetype.get("id") or archetype_id),
            "canvas": archetype.get("canvas"),
            "schema": "https://campaign-os/brand-directory/visual-archetypes/v2",
        }
    if service_label is not None and str(service_label).strip():
        sidecar["compose_service_label"] = str(service_label).strip()

    needs_photo = archetype.get("applies_to", {}).get("needs_photo", True)
    archetype_id_resolved = str(archetype.get("id") or archetype_id or "")
    photo_bytes: bytes | None = resolve_compose_photo_bytes(
        brand_id, archetype_id_resolved, sidecar
    )
    if needs_photo and photo_bytes is None:
        return {"ok": False, "error": "no photo candidate available for compose"}

    fields = _fields_for_compose(
        brand_id=brand_id,
        asset=asset,
        sidecar=sidecar,
        archetype=archetype,
        headline=headline,
        cta=cta,
    )
    channels = list(intended_publish_channels(brand_id))
    composed = compose_post_for_channels(
        brand_id=brand_id,
        archetype=archetype,
        channels=channels,
        fields=fields,
        photo_bytes=photo_bytes,
    )
    if not composed:
        return {"ok": False, "error": "compose produced no outputs"}

    out_dir = _data_dir() / "draft-assets" / "images" / brand_id
    out_dir.mkdir(parents=True, exist_ok=True)
    composed_urls: dict[str, str] = {}
    from _lib.publish_image import publish_jpeg_name_for_png, write_publish_jpeg_from_png_bytes

    for ch, png in composed.items():
        dest = out_dir / f"composed-{asset_id}-{ch}.png"
        dest.write_bytes(png)
        write_publish_jpeg_from_png_bytes(png, out_dir / publish_jpeg_name_for_png(dest.name))
        composed_urls[ch] = image_url_for(brand_id, str(dest))

    primary = primary_channel_for_item(brand_id, moment_id, fallback="instagram")
    primary_url = composed_urls.get(primary) or next(iter(composed_urls.values()), "")

    data = ui._load_campaign_data()  # noqa: SLF001
    for campaign in (data.get("campaigns") or {}).values():
        row = (campaign.get("assets") or {}).get(asset_id)
        if isinstance(row, dict):
            row["image_url"] = primary_url
            row["composed"] = composed_urls
            break
    ui._write_campaign_data(data)  # noqa: SLF001

    sidecar["composed"] = composed_urls
    sidecar["action"] = "compose_post"
    _save_sidecar(asset_id, sidecar)

    return {
        "ok": True,
        "asset_id": asset_id,
        "composed": composed_urls,
        "primary_channel": primary,
    }


def regenerate_photo(draft_id: str, *, note: str) -> dict[str, Any]:
    """Enqueue draft_photo (+ compose_post) for the same calendar moment."""
    from _lib import ops_agents, ops_layers

    note_s = (note or "").strip()
    if not note_s:
        return {"ok": False, "error": "note is required"}

    ctx = resolve_draft(draft_id)
    brand_id = ctx["brand_id"]
    asset_id = ctx["asset_id"]
    moment_id = ctx["moment_id"]
    if not moment_id:
        return {"ok": False, "error": "draft has no source moment"}

    cap_info = ops_layers.brand_images_today(brand_id)
    from _lib.marketing_calendar import render_mode_for_record  # noqa: PLC0415
    from _lib.unified_inbox import _calendar_record_for_key  # noqa: PLC0415

    cal_record: dict | None = None
    if moment_id.startswith("calendar_candidate:"):
        parts = moment_id.split(":", 2)
        if len(parts) >= 3:
            cal_record = _calendar_record_for_key(brand_id, parts[2])
    is_oneshot = render_mode_for_record(cal_record or {}) == "oneshot"

    if cap_info.get("at_cap"):
        return {
            "ok": False,
            "error": f"Daily image cap reached for {brand_id}",
            "at_cap": True,
            "brand_id": brand_id,
            **cap_info,
        }
    if (
        is_oneshot
        and cap_info.get("at_oneshot_cap")
        and str(ctx["sidecar"].get("action") or "") != "draft_oneshot"
    ):
        return {
            "ok": False,
            "error": f"One-shot cap reached for {brand_id}",
            "at_cap": True,
            "brand_id": brand_id,
            **cap_info,
        }

    sidecar = dict(ctx["sidecar"])
    sidecar["review_regenerate_note"] = note_s
    sidecar.pop("composed", None)
    _save_sidecar(asset_id, sidecar)

    data_dir = _data_dir()
    from _lib import unified_inbox as ui

    data = ui._load_campaign_data()  # noqa: SLF001
    campaign = (data.get("campaigns") or {}).get(ctx["campaign_id"])
    if isinstance(campaign, dict):
        row = (campaign.get("assets") or {}).get(asset_id)
        if isinstance(row, dict):
            row.pop("composed", None)
    ui._write_campaign_data(data)  # noqa: SLF001

    from _lib.template_recipe import load_recipe_for_moment  # noqa: PLC0415

    if is_oneshot:
        photo_actions: tuple[str, ...] = ("draft_oneshot",)
    else:
        recipe = load_recipe_for_moment(brand_id, moment_id)
        gen_slots = recipe.get("gen_slots") if isinstance(recipe, dict) else None
        photo_action = "draft_gen_slots" if isinstance(gen_slots, list) and gen_slots else "draft_photo"
        photo_actions = (photo_action, "compose_post")

    item_hash = hashlib.sha1(moment_id.encode()).hexdigest()[:12]
    enqueued: list[str] = []
    for action in photo_actions:
        row = ops_agents.normalise_enqueue(
            {
                "agent": "cos-image",
                "brand": brand_id,
                "reason": "review-regenerate",
                "action": action,
                "payload_ref": f"inbox/{moment_id}",
                "dedupe_key": f"{action}-review-{item_hash}-{hashlib.sha1(note_s.encode()).hexdigest()[:8]}",
            }
        )
        ops_agents.append_enqueue_row(data_dir, row)
        enqueued.append(action)

    return {
        "ok": True,
        "brand_id": brand_id,
        "moment_id": moment_id,
        "enqueued": enqueued,
        **cap_info,
    }


def retire_caption_drafts_for_moment(moment_id: str) -> list[str]:
    """Clear caption drafts so draft_assets will rerun P11 for this moment."""
    from _lib import unified_inbox as ui

    moment_id = (moment_id or "").strip()
    if not moment_id:
        return []

    draft_dir = _data_dir() / "draft-assets"
    if not draft_dir.is_dir():
        return []

    data = ui._load_campaign_data()  # noqa: SLF001
    retired: list[str] = []
    now = datetime.now(timezone.utc).isoformat()

    for path in sorted(draft_dir.glob("*.json")):
        try:
            sidecar = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(sidecar, dict):
            continue
        if str(sidecar.get("source_inbox_item_id") or "") != moment_id:
            continue
        if str(sidecar.get("action") or "") == "superseded_caption":
            continue
        asset_id = str(sidecar.get("asset_id") or path.stem)
        for campaign in (data.get("campaigns") or {}).values():
            if not isinstance(campaign, dict):
                continue
            asset = (campaign.get("assets") or {}).get(asset_id)
            if isinstance(asset, dict):
                asset["caption"] = ""
                asset.pop("copy_package", None)
                asset.pop("composed", None)
        sidecar.pop("composed", None)
        sidecar["action"] = "superseded_caption"
        sidecar["superseded_at"] = now
        sidecar["superseded_for_moment"] = moment_id
        _save_sidecar(asset_id, sidecar)
        retired.append(asset_id)

    if retired:
        ui._write_campaign_data(data)  # noqa: SLF001
    return retired


def clear_caption_keep_image(asset_id: str) -> bool:
    """Blank caption text on one draft. Leave the poster, image, and sidecar link."""
    from _lib import unified_inbox as ui

    asset_id = (asset_id or "").strip()
    if not asset_id:
        return False
    sidecar = _load_sidecar(asset_id)
    if not sidecar:
        return False
    data = ui._load_campaign_data()  # noqa: SLF001
    found = False
    for campaign in (data.get("campaigns") or {}).values():
        if not isinstance(campaign, dict):
            continue
        asset = (campaign.get("assets") or {}).get(asset_id)
        if isinstance(asset, dict):
            asset["caption"] = ""
            asset.pop("copy_package", None)
            found = True
    if not found:
        return False
    ui._write_campaign_data(data)  # noqa: SLF001
    for key in ("copy_package", "compose_headline", "compose_cta", "compose_body"):
        sidecar.pop(key, None)
    _save_sidecar(asset_id, sidecar)
    return True


def restore_poster_from_publish(
    draft_id: str,
    *,
    detach_asset_id: str | None = None,
    event_date: str | None = None,
) -> dict[str, Any]:
    """Put the queued publish image and caption back on this draft."""
    from _lib.publish_sandbox import _queue_path, _read_jsonl  # noqa: SLF001
    from _lib import unified_inbox as ui

    ctx = resolve_draft(draft_id)
    asset_id = str(ctx["asset_id"])
    asset = ctx["asset"]
    sidecar = dict(ctx["sidecar"])
    prefix = f"qc-{asset_id}-"
    rows = [
        row for row in _read_jsonl(_queue_path())
        if str(row.get("idempotency_key") or "").startswith(prefix)
    ]
    if not rows:
        return {"ok": False, "error": "no publish row for this draft"}

    composed: dict[str, str] = {}
    image_url = ""
    image_path = ""
    caption = ""
    for row in rows:
        platform = str(row.get("platform") or "").strip()
        url = str(row.get("image_url") or "").strip()
        if platform and url:
            composed[platform] = url
        if platform == "instagram" or not image_url:
            image_url = url or image_url
            image_path = str(row.get("image_path") or image_path)
            caption = str(row.get("caption_preview") or caption)
    if not composed or not caption:
        return {"ok": False, "error": "publish row is missing the image or caption"}

    now = datetime.now(timezone.utc).isoformat()
    asset["caption"] = caption
    asset["image_url"] = image_url
    asset["image_path"] = image_path
    asset["composed"] = composed
    asset["updatedAt"] = now
    asset.pop("copy_package", None)
    ui._write_campaign_data(_campaign_data_with_asset(ctx, asset))  # noqa: SLF001

    sidecar["composed"] = composed
    sidecar["action"] = "compose_post"
    sidecar.pop("superseded_at", None)
    sidecar.pop("superseded_for_moment", None)
    sidecar["restored_at"] = now
    _save_sidecar(asset_id, sidecar)

    moved_date = ""
    day = (event_date or "").strip()[:10]
    source = str(sidecar.get("source_inbox_item_id") or "")
    if day and source.startswith("calendar_candidate:"):
        parts = source.split(":", 2)
        if len(parts) == 3 and parts[1] and parts[2]:
            from _lib.marketing_calendar import set_fields  # noqa: PLC0415

            updated = set_fields(
                parts[1],
                parts[2],
                {"event_date": day},
                reason="restore poster onto this day",
            )
            if updated:
                moved_date = str(updated.get("event_date") or day)

    detached = ""
    detach_id = (detach_asset_id or "").strip()
    if detach_id and detach_id != asset_id:
        other = _load_sidecar(detach_id)
        if other:
            other["action"] = "superseded_caption"
            other["source_inbox_item_id"] = ""
            other["superseded_at"] = now
            _save_sidecar(detach_id, other)
            detached = detach_id

    return {
        "ok": True,
        "asset_id": asset_id,
        "image_url": image_url,
        "detached_asset_id": detached,
        "event_date": moved_date,
    }


def _campaign_data_with_asset(ctx: dict[str, Any], asset: dict[str, Any]) -> dict[str, Any]:
    from _lib import unified_inbox as ui

    data = ui._load_campaign_data()  # noqa: SLF001
    campaign = (data.get("campaigns") or {}).get(ctx["campaign_id"])
    if not isinstance(campaign, dict):
        raise LookupError("campaign not found")
    assets = campaign.setdefault("assets", {})
    assets[ctx["asset_id"]] = asset
    return data


def _kick_caption_keep(moment_id: str, brand_id: str) -> dict[str, Any]:
    """Write the queued caption now, for this moment only. Other queue rows stay pending."""
    if not _caption_keep_lock.acquire(blocking=False):
        return {"ok": False, "error": "caption writer busy", "started": False}
    previous = os.environ.get("CAMPAIGN_OS_L5_ONLY_ITEM")
    os.environ["CAMPAIGN_OS_L5_ONLY_ITEM"] = moment_id
    try:
        from _lib.jobs.layer5.draft_assets import run

        result = run(brand=brand_id)
        if not isinstance(result, dict):
            result = {"ok": True}
        result["started"] = True
        return result
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:240], "started": True}
    finally:
        if previous is None:
            os.environ.pop("CAMPAIGN_OS_L5_ONLY_ITEM", None)
        else:
            os.environ["CAMPAIGN_OS_L5_ONLY_ITEM"] = previous
        _caption_keep_lock.release()


def regenerate_caption(
    *,
    moment_id: str | None = None,
    draft_id: str | None = None,
    reason: str = "regenerate-caption",
    recompose: bool = False,
    run_now: bool = True,
) -> dict[str, Any]:
    """Rewrite caption text on the open draft. recompose=True retires the poster and rebuilds it."""
    from _lib import ops_agents
    from _lib.l5_create_enqueue import create_actions_for_moment

    resolved_moment = (moment_id or "").strip()
    brand_id = ""
    asset_id = ""
    if draft_id:
        ctx = resolve_draft(draft_id)
        brand_id = str(ctx["brand_id"] or "")
        asset_id = str(ctx["asset_id"] or "")
        resolved_moment = str(ctx["moment_id"] or resolved_moment)
    if not resolved_moment:
        return {"ok": False, "error": "moment_id required (or draft with source moment)"}
    if not brand_id:
        from _lib import unified_inbox as ui

        item_type, key = ui._parse_item_id(resolved_moment)  # noqa: SLF001
        if item_type == "calendar_candidate":
            brand_id = key.split(":", 1)[0]

    if not brand_id:
        return {"ok": False, "error": "could not resolve brand_id"}

    if not recompose and not asset_id:
        return {"ok": False, "error": "draft_id required to rewrite a caption in place"}

    retired: list[str] = []
    if recompose:
        retired = retire_caption_drafts_for_moment(resolved_moment)
    elif not clear_caption_keep_image(asset_id):
        return {"ok": False, "error": "could not clear caption on this draft"}
    reason_s = (reason or "regenerate-caption").strip()[:64]
    stamp = hashlib.sha1(f"{reason_s}:{resolved_moment}".encode()).hexdigest()[:10]
    item_hash = hashlib.sha1(resolved_moment.encode()).hexdigest()[:12]
    data_dir = _data_dir()
    enqueued: list[str] = []

    cap_row = ops_agents.normalise_enqueue(
        {
            "agent": "cos-caption",
            "brand": brand_id,
            "reason": reason_s,
            "action": "draft_caption",
            "payload_ref": f"inbox/{resolved_moment}",
            "dedupe_key": (
                f"cap-regen-{stamp}-{item_hash}" if recompose else f"cap-keep-{asset_id}"
            ),
        }
    )
    ops_agents.append_enqueue_row(data_dir, cap_row)
    enqueued.append("draft_caption")

    if recompose:
        compose_row = ops_agents.normalise_enqueue(
            {
                "agent": "cos-image",
                "brand": brand_id,
                "reason": reason_s,
                "action": "compose_post",
                "payload_ref": f"inbox/{resolved_moment}",
                "dedupe_key": f"compose-regen-{stamp}-{item_hash}",
            }
        )
        ops_agents.append_enqueue_row(data_dir, compose_row)
        enqueued.append("compose_post")

        # Lodge-only extras (gbp) when rebuilding the poster — skip draft_photo.
        for action in create_actions_for_moment(brand_id, resolved_moment, phase="lodge"):
            if action in enqueued or action == "draft_caption":
                continue
            row = ops_agents.normalise_enqueue(
                {
                    "agent": "cos-caption" if action == "draft_gbp" else "cos-image",
                    "brand": brand_id,
                    "reason": reason_s,
                    "action": action,
                    "payload_ref": f"inbox/{resolved_moment}",
                    "dedupe_key": f"{action}-regen-{stamp}-{item_hash}",
                }
            )
            ops_agents.append_enqueue_row(data_dir, row)
            enqueued.append(action)

    writer: dict[str, Any] = {}
    if not recompose and run_now:
        writer = _kick_caption_keep(resolved_moment, brand_id)

    return {
        "ok": True,
        "brand_id": brand_id,
        "moment_id": resolved_moment,
        "retired_asset_ids": retired,
        "enqueued": enqueued,
        "started": bool(writer.get("started")),
        "drafted": writer.get("drafted"),
        "writer_error": writer.get("error"),
    }


def enqueue_recompose_after_caption_edit(
    *,
    brand_id: str,
    asset_id: str,
    reason: str = "caption-edit",
) -> dict[str, Any]:
    """Queue compose_post when an already-composed draft caption changes."""
    try:
        sidecar = _load_sidecar(asset_id)
        if not sidecar:
            return {"ok": True, "enqueued": False, "reason": "no_sidecar"}
        moment_id = str(sidecar.get("source_inbox_item_id") or "").strip()
        if not moment_id:
            return {"ok": True, "enqueued": False, "reason": "no_moment"}

        from _lib.jobs.layer5 import draft_assets  # noqa: PLC0415

        if not draft_assets._moment_has_composed(brand_id, moment_id):
            return {"ok": True, "enqueued": False, "reason": "not_composed"}

        src = str(sidecar.get("_poster_copy_source") or sidecar.get("poster_copy_mode") or "")
        if src in ("llm_hook", "caption_fallback", "from_llm_hook"):
            sidecar.pop("compose_headline", None)
            sidecar["_poster_copy_source"] = "caption_fallback"
            _save_sidecar(asset_id, sidecar)

        from _lib.l5_create_enqueue import enqueue_compose_post_for_moment  # noqa: PLC0415

        enqueued = enqueue_compose_post_for_moment(
            item_id=moment_id,
            brand_id=brand_id,
            reason=reason,
        )
        return {"ok": True, "enqueued": bool(enqueued), "reason": reason if enqueued else "already_queued"}
    except Exception as exc:
        return {"ok": False, "enqueued": False, "reason": str(exc)[:120]}


def swap_candidate(draft_id: str, *, candidate_index: int) -> dict[str, Any]:
    sidecar = resolve_draft(draft_id)["sidecar"]
    candidates = sidecar.get("photo_candidates") if isinstance(sidecar.get("photo_candidates"), list) else []
    idx = int(candidate_index)
    if idx not in (0, 1) or idx >= len(candidates):
        return {"ok": False, "error": "candidate_index must be 0 or 1 for this draft"}
    return recompose_draft(draft_id, candidate_index=idx)


def record_draft_reject_feedback(
    *,
    brand_id: str,
    asset_id: str,
    reason: str,
    sidecar: dict[str, Any],
) -> None:
    from _lib.feedback_loop import add_record

    qc = sidecar.get("qc") if isinstance(sidecar.get("qc"), dict) else {}
    signal = {
        "verdict": "rejected",
        "reason": reason,
        "qc_verdict": qc.get("verdict"),
        "qc_reasons": qc.get("candidates") or qc.get("reasons"),
        "qc_snapshot": qc,
    }
    add_record(
        brand_id,
        image_id=asset_id,
        kind="generated",
        source="manual",
        captured_signal=signal,
        dna_snapshot={"sidecar_action": sidecar.get("action")},
        notes=reason,
    )
