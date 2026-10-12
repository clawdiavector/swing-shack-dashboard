"""draft_photo and compose_post row handlers (P3 two-stage create)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Optional

from ..layer1._io import atomic_write
from .draft_assets import (
    IMAGE_EST_USD,
    _ROUTER_SELF_RECORDING_PROVIDERS,
    _data_dir,
    _event_key_from_calendar,
    _find_caption_draft_for_item,
    _utc_now_iso,
    _write_draft,
    _write_image_brief,
)
from .image_draft_context import ImageDraftContext, build_image_draft_context, image_url_for, primary_channel_for_item
from .visual_qc import build_edit_instruction, visual_check


def _content_from_caption(caption: str, ctx: ImageDraftContext) -> dict[str, Any]:
    lines = [ln.strip() for ln in (caption or "").split("\n") if ln.strip()]
    hook = lines[0] if lines else caption
    body = lines[1] if len(lines) > 1 else ""
    products = ctx.products or []
    product_name = ""
    vendor_name = ""
    if products and isinstance(products[0], dict):
        product_name = str(products[0].get("name") or products[0].get("title") or "")
        vendor_name = str(products[0].get("vendor") or products[0].get("brand") or "")
    return {
        "caption_hook": hook,
        "caption_body": body,
        "cta": "Book now",
        "product_name": product_name,
        "vendor_name": vendor_name,
        "brand_tagline": "Stick Golf",
    }


def _sidecar_for_item(item_id: str) -> tuple[str | None, dict[str, Any] | None]:
    draft_dir = _data_dir() / "draft-assets"
    if not draft_dir.is_dir():
        return None, None
    for path in sorted(draft_dir.glob("*.json"), reverse=True):
        if path.name.endswith(".brief.json") or path.name.endswith(".qc.json"):
            continue
        try:
            sidecar = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(sidecar, dict):
            continue
        if sidecar.get("source_inbox_item_id") != item_id:
            continue
        if str(sidecar.get("action") or "") in (
            "draft_photo",
            "draft_image",
            "draft_caption",
            "draft_gen_slots",
        ):
            return str(sidecar.get("asset_id") or ""), sidecar
    return None, None


def process_draft_photo_row(
    row: dict[str, Any],
    *,
    item_id: str,
    brand_id: str,
    draft_ctx: ImageDraftContext | None = None,
    action_label: str = "draft_photo",
) -> tuple[Optional[str], Optional[str]]:
    from _lib.archetypes_v2 import select_archetype  # noqa: PLC0415
    from _lib.visual_gate import decide, list_trusted_library_photos  # noqa: PLC0415

    decision = decide(brand_id, item_id)
    if decision.is_gap():
        return None, f"gap:{decision.reason}"

    ctx = draft_ctx or build_image_draft_context(brand_id, item_id)
    calendar = ctx.lineage.get("calendar") if isinstance(ctx.lineage.get("calendar"), dict) else {}
    event_key = _event_key_from_calendar(calendar)

    archetype = select_archetype(brand_id, item_id)
    archetype_id = str(archetype.get("id") or "")
    needs_photo = archetype.get("applies_to", {}).get("needs_photo", True)
    if not needs_photo:
        caption_asset_id, _caption_text = _find_caption_draft_for_item(item_id)
        if not caption_asset_id:
            return None, "compose-only archetype requires caption draft first"
        sidecar_path = _data_dir() / "draft-assets" / f"{caption_asset_id}.json"
        merged: dict[str, Any] = {}
        if sidecar_path.is_file():
            try:
                loaded = json.loads(sidecar_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    merged = loaded
            except (OSError, json.JSONDecodeError):
                merged = {}
        merged.update(
            {
                "action": action_label,
                "asset_id": caption_asset_id,
                "brand_id": brand_id,
                "source_inbox_item_id": item_id,
                "archetype": {
                    "id": archetype_id,
                    "schema": "https://campaign-os/brand-directory/visual-archetypes/v2",
                },
                "qc": {
                    "verdict": "pass",
                    "checked_at": _utc_now_iso(),
                    "candidates": [],
                    "selected": None,
                    "compose_only": True,
                },
            }
        )
        atomic_write(f"draft-assets/{caption_asset_id}.json", merged)
        from _lib import post_cost  # noqa: PLC0415

        post_cost.record_line(
            usd=0.0,
            brand_id=brand_id,
            kind="image",
            route="job:draft_assets/photo",
            inbox_item_id=item_id,
            action="compose_post",
            cost_source="estimate",
            draft_asset_id=caption_asset_id,
            event_key=event_key,
            queue_row_id=str(row.get("id") or "") or None,
        )
        return process_compose_post_row(
            row,
            item_id=item_id,
            brand_id=brand_id,
        )

    caption_asset_id, _caption_text = _find_caption_draft_for_item(item_id)
    if not caption_asset_id:
        return None, "compose-only archetype requires caption draft first"

    photo_src = decision.photo
    if photo_src is None:
        return None, "gap:no_real_photo"

    photo_path = Path(photo_src.path)
    if not photo_path.is_file():
        return None, "gap:no_real_photo"

    regen_sidecar = _sidecar_for_item(item_id)[1] or {}
    regen_note = str(regen_sidecar.get("review_regenerate_note") or "").strip()
    if regen_note and photo_src.kind == "library":
        bg = archetype.get("background") if isinstance(archetype.get("background"), dict) else {}
        library = str(bg.get("library") or "")
        trusted = list_trusted_library_photos(brand_id, library)
        if len(trusted) > 1:
            seed = f"{item_id}:{regen_note}"
            import zlib

            photo_path = trusted[zlib.crc32(seed.encode("utf-8")) % len(trusted)]

    sidecar_path = _data_dir() / "draft-assets" / f"{caption_asset_id}.json"
    merged: dict[str, Any] = {}
    if sidecar_path.is_file():
        try:
            loaded = json.loads(sidecar_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                merged = loaded
        except (OSError, json.JSONDecodeError):
            merged = {}

    photo_source = "operator" if photo_src.kind in ("sidecar", "render_spec") else "library"
    merged.update(
        {
            "action": action_label,
            "asset_id": caption_asset_id,
            "brand_id": brand_id,
            "source_inbox_item_id": item_id,
            "venue_photo": str(photo_path),
            "photo_source": photo_source,
            "archetype": {
                "id": archetype_id,
                "canvas": archetype.get("canvas"),
                "schema": "https://campaign-os/brand-directory/visual-archetypes/v2",
            },
            "qc": {
                "verdict": "pass",
                "checked_at": _utc_now_iso(),
                "candidates": [{"index": 0, "path": str(photo_path), "verdict": "pass", "reasons": []}],
                "selected": 0,
            },
            "photo_candidates": [
                {
                    "index": 0,
                    "path": str(photo_path),
                    "url": image_url_for(brand_id, str(photo_path)),
                }
            ],
        }
    )
    merged.pop("review_regenerate_note", None)
    merged.pop("composed", None)
    atomic_write(f"draft-assets/{caption_asset_id}.json", merged)
    from _lib import post_cost  # noqa: PLC0415

    post_cost.record_line(
        usd=0.0,
        brand_id=brand_id,
        kind="image",
        route="job:draft_assets/photo",
        inbox_item_id=item_id,
        action="compose_post",
        cost_source="estimate",
        draft_asset_id=caption_asset_id,
        event_key=event_key,
        queue_row_id=str(row.get("id") or "") or None,
    )
    return caption_asset_id, None


def process_compose_post_row(
    row: dict[str, Any],
    *,
    item_id: str,
    brand_id: str,
) -> tuple[Optional[str], Optional[str]]:
    from _lib.archetype_compose import ComposeError, compose_post_for_channels  # noqa: PLC0415
    from _lib.archetypes_v2 import select_archetype  # noqa: PLC0415
    from _lib.publish_sandbox import intended_publish_channels  # noqa: PLC0415
    from _lib.visual_gate import decide  # noqa: PLC0415

    gate = decide(brand_id, item_id)
    if gate.is_gap():
        return None, f"gap:{gate.reason}"

    asset_id, sidecar = _sidecar_for_item(item_id)
    if not sidecar:
        return None, None
    archetype = select_archetype(brand_id, item_id)
    archetype_id = str(archetype.get("id") or "")
    needs_photo = archetype.get("applies_to", {}).get("needs_photo", True)
    qc = sidecar.get("qc") if isinstance(sidecar.get("qc"), dict) else {}
    candidates = sidecar.get("photo_candidates") if isinstance(sidecar.get("photo_candidates"), list) else []
    photo_bytes: bytes | None = None
    if needs_photo:
        gen_slots = sidecar.get("gen_slots") if isinstance(sidecar.get("gen_slots"), dict) else {}
        bg_path = gen_slots.get("background") or (next(iter(gen_slots.values()), None) if gen_slots else None)
        if bg_path:
            path = Path(str(bg_path))
            if not path.is_file():
                alt = _data_dir() / str(bg_path).lstrip("/")
                path = alt if alt.is_file() else path
            if path.is_file():
                photo_bytes = path.read_bytes()
        if photo_bytes is None:
            if qc.get("verdict") not in ("pass",) and qc.get("selected") is None:
                return None, None
            sel = qc.get("selected")
            if sel is None and candidates:
                return None, None
            if candidates:
                idx = int(sel if sel is not None else 0)
                path = Path(candidates[idx]["path"])
                if path.is_file():
                    photo_bytes = path.read_bytes()
                else:
                    return None, None
    if photo_bytes is None and gate.photo is not None:
        path = Path(gate.photo.path)
        if path.is_file():
            photo_bytes = path.read_bytes()

    _, caption_text = _find_caption_draft_for_item(item_id)
    if not caption_text and asset_id:
        from _lib.unified_inbox import _load_campaign_data  # noqa: PLC0415

        data = _load_campaign_data()
        for campaign in (data.get("campaigns") or {}).values():
            asset = (campaign.get("assets") or {}).get(asset_id or "")
            if isinstance(asset, dict):
                caption_text = str(asset.get("caption") or "") or caption_text
                break
    from _lib.compose_visual_copy import visual_copy_for_archetype  # noqa: PLC0415

    asset_title = str(sidecar.get("title") or "")
    content = visual_copy_for_archetype(
        brand_id=brand_id,
        moment_id=item_id,
        caption=caption_text or "",
        archetype=archetype,
        asset_title=asset_title or None,
        sidecar=sidecar,
    )
    channels = [c for c in intended_publish_channels(brand_id) if c != "gbp"]
    try:
        composed = compose_post_for_channels(
            brand_id=brand_id,
            archetype=archetype,
            channels=channels,
            content=content,
            photo_bytes=photo_bytes,
        )
    except ComposeError as exc:
        if "missing background photo" in str(exc).lower():
            return None, "gap:no_real_photo"
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)

    if not composed:
        return None, "no composed outputs"

    out_dir = _data_dir() / "draft-assets" / "images" / brand_id
    out_dir.mkdir(parents=True, exist_ok=True)
    composed_urls: dict[str, str] = {}
    from _lib.publish_image import publish_jpeg_name_for_png, write_publish_jpeg_from_png_bytes

    for ch, png in composed.items():
        fname = f"composed-{asset_id}-{ch}.png" if asset_id else f"composed-{ch}.png"
        dest = out_dir / fname
        dest.write_bytes(png)
        write_publish_jpeg_from_png_bytes(png, out_dir / publish_jpeg_name_for_png(dest.name))
        composed_urls[ch] = image_url_for(brand_id, str(dest))

    primary = primary_channel_for_item(brand_id, item_id, fallback="instagram")
    primary_path = composed_urls.get(primary) or next(iter(composed_urls.values()), "")
    from _lib.unified_inbox import _load_campaign_data, _write_campaign_data  # noqa: PLC0415

    data = _load_campaign_data()
    for campaign in (data.get("campaigns") or {}).values():
        asset = (campaign.get("assets") or {}).get(asset_id or "")
        if isinstance(asset, dict):
            asset["image_url"] = primary_path
            primary_fname = (
                f"composed-{asset_id}-{primary}.png" if asset_id else f"composed-{primary}.png"
            )
            asset["image_path"] = str(out_dir / primary_fname)
            asset["composed"] = composed_urls
            break
    _write_campaign_data(data)

    archetype_meta: dict[str, Any] = {
        "id": archetype_id,
        "canvas": archetype.get("canvas"),
        "schema": "https://campaign-os/brand-directory/visual-archetypes/v2",
    }
    from _lib.archetypes import _moment_context  # noqa: PLC0415

    template_id = str(_moment_context(brand_id, item_id).get("template_id") or "")
    if template_id:
        archetype_meta["template_id"] = template_id

    sidecar["composed"] = composed_urls
    sidecar["action"] = "compose_post"
    sidecar["archetype"] = archetype_meta
    atomic_write(f"draft-assets/{asset_id}.json", sidecar)
    from _lib import post_cost  # noqa: PLC0415

    cal = sidecar.get("calendar") if isinstance(sidecar.get("calendar"), dict) else {}
    ek = str(sidecar.get("event_key") or cal.get("event_key") or "").strip() or None
    post_cost.record_line(
        usd=0.0,
        brand_id=brand_id,
        kind="image",
        route="job:draft_assets/compose",
        inbox_item_id=item_id,
        action="compose_post",
        cost_source="estimate",
        draft_asset_id=str(asset_id or "") or None,
        event_key=ek,
        queue_row_id=str(row.get("id") or "") or None,
    )
    return asset_id, None
