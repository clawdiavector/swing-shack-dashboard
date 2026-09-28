"""L5 draft_gen_slots — generative recipe slot runner with pack cache."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from ..layer1._io import atomic_write
from _lib.template_recipe import (
    cache_bucket_key,
    cache_file_path,
    cache_is_fresh,
    load_recipe_for_moment,
    write_cache_entry,
)

from .create_photo_compose import _sidecar_for_item
from .draft_assets import (
    _data_dir,
    _find_caption_draft_for_item,
    _utc_now_iso,
    _write_draft,
    _write_image_brief,
)
from .image_draft_context import (
    ImageDraftContext,
    background_plate_scene_prompt,
    build_image_draft_context,
    image_url_for,
    primary_channel_for_item,
)
from .visual_qc import visual_check


def _resolve_prompt(template: str, ctx: ImageDraftContext, *, brand_id: str, item_id: str) -> str:
    scene = background_plate_scene_prompt(brand_id, item_id, ctx)
    calendar = ctx.lineage.get("calendar") if isinstance(ctx.lineage.get("calendar"), dict) else {}
    pillar = str(calendar.get("pillar") or calendar.get("pillar_id") or "coaching")
    pillars = calendar.get("pillars")
    if isinstance(pillars, list) and pillars:
        pillar = str(pillars[0] or pillar)
    title = scene
    out = (
        template.replace("{scene}", scene)
        .replace("{title}", title)
        .replace("{pillar}", pillar)
        .replace("{brand_id}", brand_id)
    )
    return out.strip()


def process_draft_gen_slots_row(
    row: dict[str, Any],
    *,
    item_id: str,
    brand_id: str,
    draft_ctx: ImageDraftContext | None = None,
) -> tuple[Optional[str], Optional[str]]:
    from _lib.archetypes import select_archetype  # noqa: PLC0415
    from _lib.image_gen_router import ImageGenAuthError, generate_image_with_persistence  # noqa: PLC0415
    from _lib import llm_spend  # noqa: PLC0415
    from _lib.image_submit_quota import check_brand_image_submit, record_brand_image_submit  # noqa: PLC0415

    recipe = load_recipe_for_moment(brand_id, item_id)
    if not recipe:
        return None, "no template recipe for moment"
    slots = recipe.get("gen_slots")
    if not isinstance(slots, list) or not slots:
        return None, "recipe has no gen_slots"

    archetype = select_archetype(brand_id, item_id)
    archetype_id = str(archetype.get("id") or recipe.get("archetype_id") or "")
    template_pack = str(archetype.get("template_pack") or "")
    ctx = draft_ctx or build_image_draft_context(brand_id, item_id)
    size = ctx.aspect
    est = llm_spend.modelled_image_cost(size)
    allowed, reason = llm_spend.check("image", est)
    if not allowed:
        return None, "daily LLM spend cap reached" if "cap" in reason.lower() else reason

    seed_bump = 0
    _, existing_sidecar = _sidecar_for_item(item_id)
    if isinstance(existing_sidecar, dict):
        try:
            seed_bump = int(existing_sidecar.get("gen_seed_bump") or 0)
        except (TypeError, ValueError):
            seed_bump = 0

    policy_key = str(recipe.get("cache_policy") or "coaching_service_7d")
    bucket_hash = cache_bucket_key(
        brand_id=brand_id,
        recipe=recipe,
        item_id=item_id,
        seed_bump=seed_bump,
    )

    gen_paths: dict[str, str] = {}
    gen_prompt_used = background_plate_scene_prompt(brand_id, item_id, ctx)
    output_base = str(_data_dir() / "draft-assets" / "images")

    for slot in slots:
        if not isinstance(slot, dict):
            continue
        slot_id = str(slot.get("id") or "").strip()
        if not slot_id:
            continue
        optional = bool(slot.get("optional"))
        cache_path = cache_file_path(
            brand_id=brand_id,
            template_pack=template_pack,
            slot_id=slot_id,
            bucket_hash=bucket_hash,
        )
        if cache_is_fresh(cache_path, policy_key=policy_key):
            gen_paths[slot_id] = str(cache_path)
            continue

        img_ok, img_reason = check_brand_image_submit(brand_id)
        if not img_ok:
            if optional:
                continue
            return None, "cap_reached" if "cap" in img_reason.lower() else img_reason

        prompt_template = str(slot.get("prompt_template") or "{scene}")
        prompt = _resolve_prompt(prompt_template, ctx, brand_id=brand_id, item_id=item_id)
        gen_prompt_used = prompt
        negative = slot.get("negative")
        negative_s = ", ".join(str(x) for x in negative) if isinstance(negative, list) else ""

        record_brand_image_submit(brand_id)
        llm_spend.write_approval_receipt(route="job:draft_gen_slots", estimate_usd=est, brand_id=brand_id)

        gen_kwargs: dict[str, Any] = {
            "brand_id": brand_id,
            "prompt": prompt,
            "size": size,
            "output_base": output_base,
            "background_plate": True,
            "negative_prompt": negative_s,
            "inbox_item_id": item_id,
            "cost_action": "draft_gen_slots",
        }

        try:
            result = generate_image_with_persistence(**gen_kwargs)
        except ImageGenAuthError:
            return None, "missing OPENAI_API_KEY"
        except Exception as exc:  # noqa: BLE001
            if optional:
                continue
            return None, str(exc)

        pj = getattr(result, "provider_job_id", None)
        raw_bytes = getattr(result, "bytes", b"") or b""
        if pj and not raw_bytes:
            from . import image_jobs_state  # noqa: PLC0415

            image_jobs_state.upsert_submit(
                item_id,
                job_id=str(pj),
                brand=brand_id,
                size=size,
                est_usd=est,
                retry_count=0,
            )
            row["status"] = "waiting"
            return None, None

        path = getattr(result, "saved_path", None) or getattr(result, "path", None)
        if not path and raw_bytes:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(raw_bytes)
            path = cache_path
        elif path:
            src = Path(path)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(src.read_bytes())
            path = cache_path

        if not path or not Path(path).is_file():
            if optional:
                continue
            return None, "gen slot produced no image"

        qc = visual_check(Path(path), brand_id=brand_id, archetype_id=archetype_id)
        verdict = str(qc.get("verdict") or "")
        reasons = qc.get("reasons") if isinstance(qc.get("reasons"), list) else []
        if verdict in ("fail", "needs_human"):
            if optional:
                continue
            reason_s = ", ".join(str(r) for r in reasons[:4]) or verdict
            return None, f"gen slot {slot_id} QC {verdict}: {reason_s}"

        write_cache_entry(
            Path(path),
            brand_id=brand_id,
            slot_id=slot_id,
            bucket_hash=bucket_hash,
            prompt_used=prompt,
        )
        gen_paths[slot_id] = str(path)

    if not gen_paths:
        return None, "no gen slots materialized"

    bg_path = gen_paths.get("background") or next(iter(gen_paths.values()))
    photo_candidates = [
        {
            "index": 0,
            "path": bg_path,
            "url": image_url_for(brand_id, bg_path),
            "provider": "gen_recipe",
            "model": "recipe",
            "cost_usd": est,
            "size": size,
        }
    ]
    last_qc = visual_check(Path(bg_path), brand_id=brand_id, archetype_id=archetype_id)
    qc_payload = {
        "verdict": str(last_qc.get("verdict") or "pass"),
        "checked_at": last_qc.get("checked_at") or _utc_now_iso(),
        "reasons": last_qc.get("reasons") or [],
        "candidates": [
            {
                "index": 0,
                "path": bg_path,
                "verdict": str(last_qc.get("verdict") or "pass"),
                "reasons": last_qc.get("reasons") or [],
            }
        ],
        "selected": 0,
        "edit_attempted": False,
        "human_reason": None,
        "gen_recipe": True,
    }

    caption_asset_id, caption_text = _find_caption_draft_for_item(item_id)
    caption = caption_text or ctx.job
    primary_platform = primary_channel_for_item(brand_id, item_id, fallback="instagram")

    asset_id = caption_asset_id
    if not asset_id:
        asset_id = _write_draft(
            brand_id=brand_id,
            caption=caption,
            platform=primary_platform,
            source_item_id=item_id,
            sidecar={"action": "draft_gen_slots", "queue_row_id": row.get("id")},
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
    merged.update(
        {
            "action": "draft_gen_slots",
            "gen_slots": gen_paths,
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
            "recipe_id": recipe.get("id"),
            "text_policy": recipe.get("text_policy") or "compose_only",
            "calendar": calendar,
            "prompt": ctx.job,
            "gen_prompt": gen_prompt_used,
            "image_size": size,
        }
    )
    atomic_write(f"draft-assets/{asset_id}.json", merged)
    atomic_write(f"draft-assets/{asset_id}.qc.json", qc_payload)

    from _lib.campaigns import read_create_payload  # noqa: PLC0415

    cd = ctx.lineage.get("creative_director") if isinstance(ctx.lineage.get("creative_director"), dict) else {}
    _write_image_brief(
        asset_id,
        sections=list(cd.get("sections") or []),
        platform_spec=dict(ctx.platform_spec or {}),
        reference_id=None,
        product_id=None,
        provenance=read_create_payload(item_id),
    )
    return asset_id, None
