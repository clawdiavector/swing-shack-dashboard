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
        if str(sidecar.get("action") or "") in ("draft_photo", "draft_image", "draft_caption"):
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
    from _lib import llm_spend  # noqa: PLC0415
    from _lib.archetypes_v2 import select_archetype  # noqa: PLC0415
    from _lib.image_gen_router import ImageGenAuthError, edit_image, generate_image_with_persistence  # noqa: PLC0415
    from _lib.image_submit_quota import check_brand_image_submit, record_brand_image_submit  # noqa: PLC0415

    ctx = draft_ctx or build_image_draft_context(brand_id, item_id)
    regen_asset_id, regen_sidecar = _sidecar_for_item(item_id)
    regen_note = str((regen_sidecar or {}).get("review_regenerate_note") or "").strip()
    if regen_note and regen_sidecar and regen_sidecar.get("photo_candidates"):
        candidates = regen_sidecar.get("photo_candidates") if isinstance(regen_sidecar.get("photo_candidates"), list) else []
        qc = regen_sidecar.get("qc") if isinstance(regen_sidecar.get("qc"), dict) else {}
        sel = qc.get("selected")
        idx = int(sel if sel is not None else 0)
        if candidates and 0 <= idx < len(candidates):
            src_path = Path(str(candidates[idx].get("path") or ""))
            if not src_path.is_file():
                alt = _data_dir() / str(candidates[idx].get("path") or "").lstrip("/")
                src_path = alt if alt.is_file() else src_path
            if src_path.is_file():
                instruction = f"{regen_note.strip()}. Do not add text, logos, or watermarks."
                try:
                    edited = edit_image(src_path.read_bytes(), instruction, brand_id=brand_id)
                except Exception:
                    edited = None
                if edited and getattr(edited, "bytes", None):
                    edit_path = src_path.with_name(src_path.stem + "-review-edit.png")
                    edit_path.write_bytes(edited.bytes)
                    regen_sidecar = dict(regen_sidecar)
                    regen_sidecar.pop("review_regenerate_note", None)
                    regen_sidecar.pop("composed", None)
                    regen_sidecar["photo_candidates"] = [
                        {
                            **dict(candidates[idx]),
                            "index": 0,
                            "path": str(edit_path),
                            "url": image_url_for(brand_id, str(edit_path)),
                        }
                    ]
                    regen_sidecar["qc"] = {
                        "verdict": "pass",
                        "checked_at": _utc_now_iso(),
                        "candidates": [{"index": 0, "path": str(edit_path), "verdict": "pass", "reasons": []}],
                        "selected": 0,
                        "edit_attempted": True,
                        "human_reason": None,
                    }
                    aid = str(regen_asset_id or regen_sidecar.get("asset_id") or "")
                    if aid:
                        atomic_write(f"draft-assets/{aid}.json", regen_sidecar)
                        return aid, None

    archetype = select_archetype(brand_id, item_id)
    archetype_id = str(archetype.get("id") or "")
    size = ctx.aspect
    est = llm_spend.modelled_image_cost(size)
    allowed, reason = llm_spend.check("image", est * 2)
    if not allowed:
        return None, "daily LLM spend cap reached" if "cap" in reason.lower() else reason

    img_ok, img_reason = check_brand_image_submit(brand_id)
    if not img_ok:
        return None, "cap_reached" if "cap" in img_reason.lower() else img_reason

    from _lib.creative_director import pick_model  # noqa: PLC0415

    calendar = ctx.lineage.get("calendar") if isinstance(ctx.lineage.get("calendar"), dict) else {}
    record_type = str(calendar.get("type") or "").lower()
    routing = pick_model(
        {
            "needs_reference": bool(ctx.reference_bytes),
            "photoreal": record_type == "moment",
            "typography": False,
            "edit": False,
        }
    )
    output_base = str(_data_dir() / "draft-assets" / "images")
    gen_kwargs: dict[str, Any] = {
        "brand_id": brand_id,
        "prompt": ctx.job,
        "size": size,
        "output_base": output_base,
        "provider": routing.get("provider"),
        "model": routing.get("model"),
    }
    if ctx.refs:
        gen_kwargs["reference_dnas"] = ctx.refs
    if ctx.reference_bytes:
        gen_kwargs["reference_bytes"] = ctx.reference_bytes
    if ctx.products:
        gen_kwargs["product_service_items"] = ctx.products

    candidates: list[dict[str, Any]] = []
    paths: list[Path] = []
    for _ in range(2):
        img_ok, _ = check_brand_image_submit(brand_id)
        if not img_ok:
            break
        record_brand_image_submit(brand_id)
        llm_spend.write_approval_receipt(route="job:draft_assets/photo", estimate_usd=est, brand_id=brand_id)
        try:
            result = generate_image_with_persistence(**gen_kwargs)
        except ImageGenAuthError:
            return None, "missing OPENAI_API_KEY"
        except Exception as exc:  # noqa: BLE001
            return None, str(exc)
        pj = getattr(result, "provider_job_id", None)
        raw_bytes = getattr(result, "bytes", b"")
        if pj and not raw_bytes:
            from . import image_jobs_state  # noqa: PLC0415

            row_fallback = row.get("image_retry_count")
            try:
                rc = max(0, int(row_fallback or 0))
            except (TypeError, ValueError):
                rc = 0
            image_jobs_state.upsert_submit(
                item_id,
                job_id=str(pj),
                brand=brand_id,
                size=size,
                est_usd=est,
                retry_count=rc,
            )
            row["status"] = "waiting"
            return None, None
        path = getattr(result, "saved_path", None) or getattr(result, "path", None)
        if path:
            paths.append(Path(path))
        provider = str(getattr(result, "provider", "") or "")
        if provider not in _ROUTER_SELF_RECORDING_PROVIDERS:
            llm_spend.record(est, route="job:draft_assets/photo", kind="image", brand_id=brand_id)

    if not paths:
        return None, None

    qc_entries: list[dict[str, Any]] = []
    for idx, p in enumerate(paths):
        qc = visual_check(p, brand_id=brand_id, archetype_id=archetype_id)
        qc_entries.append({"index": idx, "path": str(p), "verdict": qc["verdict"], "reasons": qc.get("reasons") or [], "scores": qc.get("scores") or {}})

    edit_attempted = False
    if all(e["verdict"] != "pass" for e in qc_entries):
        best = min(qc_entries, key=lambda e: len(e.get("reasons") or []))
        if best["verdict"] in ("fail", "soft_fail"):
            edit_attempted = True
            instruction = build_edit_instruction(failed=best.get("reasons") or [], brand_id=brand_id)
            src = Path(best["path"])
            try:
                edited = edit_image(src.read_bytes(), instruction, brand_id=brand_id)
            except Exception:
                edited = None
            if edited and getattr(edited, "bytes", None):
                edit_path = src.with_name(src.stem + "-edit.png")
                edit_path.write_bytes(edited.bytes)
                qc2 = visual_check(edit_path, brand_id=brand_id, archetype_id=archetype_id)
                best["edit_attempted"] = True
                best["edit_instruction"] = instruction
                if qc2["verdict"] != "pass":
                    for e in qc_entries:
                        e["verdict"] = "needs_human"

    selected = next((e["index"] for e in qc_entries if e["verdict"] == "pass"), None)
    caption_asset_id, caption_text = _find_caption_draft_for_item(item_id)
    caption = caption_text or ctx.job
    primary_platform = primary_channel_for_item(brand_id, item_id, fallback="instagram")
    photo_candidates = []
    for idx, p in enumerate(paths):
        photo_candidates.append(
            {
                "index": idx,
                "path": str(p),
                "url": image_url_for(brand_id, str(p)),
                "provider": routing.get("provider"),
                "model": routing.get("model"),
                "cost_usd": est,
                "size": size,
            }
        )

    cd = ctx.lineage.get("creative_director") if isinstance(ctx.lineage.get("creative_director"), dict) else {}
    qc_payload = {
        "verdict": "pass" if selected is not None else "needs_human",
        "checked_at": _utc_now_iso(),
        "ocr_available": any(
            visual_check(paths[0], brand_id=brand_id, archetype_id=archetype_id).get("ocr_available") for _ in [0]
        ),
        "candidates": qc_entries,
        "selected": selected,
        "edit_attempted": edit_attempted,
        "human_reason": None if selected is not None else "QC did not pass after edit",
    }

    asset_id = caption_asset_id
    if not asset_id:
        asset_id = _write_draft(
            brand_id=brand_id,
            caption=caption,
            platform=primary_platform,
            source_item_id=item_id,
            sidecar={"action": action_label, "queue_row_id": row.get("id")},
        )

    sidecar_path = _data_dir() / "draft-assets" / f"{asset_id}.json"
    merged: dict[str, Any] = {}
    if sidecar_path.is_file():
        try:
            loaded = json.loads(sidecar_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                merged = loaded
        except (OSError, json.JSONDecodeError):
            merged = {}
    calendar = ctx.lineage.get("calendar") if isinstance(ctx.lineage.get("calendar"), dict) else {}
    model_routing = dict(cd.get("model_routing") or {})
    model_routing["pick_model"] = routing
    merged.update(
        {
            "action": action_label,
            "photo_candidates": photo_candidates,
            "qc": qc_payload,
            "archetype": {
                "id": archetype_id,
                "canvas": archetype.get("canvas"),
                "schema": "https://campaign-os/brand-directory/visual-archetypes/v2",
            },
            "asset_id": asset_id,
            "brand_id": brand_id,
            "source_inbox_item_id": item_id,
            "caption_asset_id": caption_asset_id,
            "sections": cd.get("sections") or [],
            "negative_prompt": cd.get("negative_prompt") or "",
            "model_routing": model_routing,
            "reference_dnas": ctx.lineage.get("reference_meta") or [],
            "product_service_items": ctx.lineage.get("product_meta") or [],
            "brand_bible": ctx.lineage.get("brand_bible") or {},
            "calendar": calendar,
            "context_degraded": ctx.lineage.get("degraded") or [],
            "image_size": size,
            "prompt": ctx.job,
        }
    )
    atomic_write(f"draft-assets/{asset_id}.json", merged)
    atomic_write(f"draft-assets/{asset_id}.qc.json", qc_payload)
    _write_image_brief(
        asset_id,
        sections=list(cd.get("sections") or []),
        platform_spec=dict(ctx.platform_spec or {}),
        reference_id=None,
        product_id=None,
    )
    return asset_id, None


def process_compose_post_row(
    row: dict[str, Any],
    *,
    item_id: str,
    brand_id: str,
) -> tuple[Optional[str], Optional[str]]:
    from _lib.archetype_compose import compose_post_for_channels  # noqa: PLC0415
    from _lib.archetypes_v2 import select_archetype  # noqa: PLC0415
    from _lib.publish_sandbox import intended_publish_channels  # noqa: PLC0415

    asset_id, sidecar = _sidecar_for_item(item_id)
    if not sidecar:
        return None, None
    archetype = select_archetype(brand_id, item_id)
    needs_photo = archetype.get("applies_to", {}).get("needs_photo", True)
    qc = sidecar.get("qc") if isinstance(sidecar.get("qc"), dict) else {}
    candidates = sidecar.get("photo_candidates") if isinstance(sidecar.get("photo_candidates"), list) else []
    photo_bytes: bytes | None = None
    if needs_photo:
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

    _, caption_text = _find_caption_draft_for_item(item_id)
    if not caption_text and asset_id:
        from _lib.unified_inbox import _load_campaign_data  # noqa: PLC0415

        data = _load_campaign_data()
        for campaign in (data.get("campaigns") or {}).values():
            asset = (campaign.get("assets") or {}).get(asset_id or "")
            if isinstance(asset, dict):
                caption_text = str(asset.get("caption") or "") or caption_text
                break
    ctx = build_image_draft_context(brand_id, item_id)
    content = _content_from_caption(caption_text or "", ctx)
    channels = [c for c in intended_publish_channels(brand_id) if c != "gbp"]
    try:
        composed = compose_post_for_channels(
            brand_id=brand_id,
            archetype=archetype,
            channels=channels,
            content=content,
            photo_bytes=photo_bytes,
        )
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)

    if not composed:
        return None, "no composed outputs"

    out_dir = _data_dir() / "draft-assets" / "images" / brand_id
    out_dir.mkdir(parents=True, exist_ok=True)
    composed_urls: dict[str, str] = {}
    for ch, png in composed.items():
        fname = f"composed-{ch}.png"
        dest = out_dir / fname
        dest.write_bytes(png)
        composed_urls[ch] = image_url_for(brand_id, str(dest))

    primary = primary_channel_for_item(brand_id, item_id, fallback="instagram")
    primary_path = composed_urls.get(primary) or next(iter(composed_urls.values()), "")
    from _lib.unified_inbox import _load_campaign_data, _write_campaign_data  # noqa: PLC0415

    data = _load_campaign_data()
    for campaign in (data.get("campaigns") or {}).values():
        asset = (campaign.get("assets") or {}).get(asset_id or "")
        if isinstance(asset, dict):
            asset["image_url"] = primary_path
            asset["image_path"] = str(out_dir / f"composed-{primary}.png")
            asset["composed"] = composed_urls
            break
    _write_campaign_data(data)

    sidecar["composed"] = composed_urls
    sidecar["action"] = "compose_post"
    atomic_write(f"draft-assets/{asset_id}.json", sidecar)
    return asset_id, None
