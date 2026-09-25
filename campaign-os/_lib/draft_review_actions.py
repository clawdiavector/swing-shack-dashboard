"""Review draft actions — regenerate / recompose / swap (P4 API)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

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


def _photo_bytes_for_sidecar(sidecar: dict[str, Any]) -> bytes | None:
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
    headline: str | None = None,
    cta: str | None = None,
) -> dict[str, str]:
    from _lib.archetype_compose import caption_fields_from_text
    from _lib.jobs.layer5.create_photo_compose import _content_from_caption, build_image_draft_context

    caption = str(asset.get("caption") or "")
    moment_id = str(sidecar.get("source_inbox_item_id") or "")
    if moment_id:
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
    archetype_id: str | None = None,
    candidate_index: int | None = None,
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

    needs_photo = archetype.get("applies_to", {}).get("needs_photo", True)
    photo_bytes: bytes | None = None
    if needs_photo:
        photo_bytes = _photo_bytes_for_sidecar(sidecar)
        if photo_bytes is None:
            return {"ok": False, "error": "no photo candidate available for compose"}

    fields = _fields_for_compose(
        brand_id=brand_id,
        asset=asset,
        sidecar=sidecar,
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
    for ch, png in composed.items():
        dest = out_dir / f"composed-{asset_id}-{ch}.png"
        dest.write_bytes(png)
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
    if cap_info.get("at_cap"):
        return {
            "ok": False,
            "error": f"Daily image cap reached for {brand_id}",
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

    item_hash = hashlib.sha1(moment_id.encode()).hexdigest()[:12]
    enqueued: list[str] = []
    for action in ("draft_photo", "compose_post"):
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
