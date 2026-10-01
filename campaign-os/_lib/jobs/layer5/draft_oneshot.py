"""L5 draft_oneshot — model-rendered text line for calendar one-shot cards."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .draft_assets import (
    _ROUTER_SELF_RECORDING_PROVIDERS,
    _data_dir,
    _event_key_from_calendar,
    _find_caption_draft_for_item,
    _sidecar_for_moment,
    _write_draft,
)
from .image_draft_context import (
    ImageDraftContext,
    background_plate_scene_prompt,
    build_image_draft_context,
    image_url_for,
    primary_channel_for_item,
)

ONESHOT_SIZE = "1024x1280"
_DEFAULT_TEXT_PLACEMENT = (
    "Upper third, generous overlay-safe margins, high contrast against the plate, "
    "single line unless it wraps naturally. Leave the bottom-right corner clear for a logo lockup."
)
_LOGO_DRIFT_WARNING = (
    "AI-rendered logo. The mark will drift from the brand asset — proportions, spacing "
    "and letterforms are not reproducible. Check it before approving."
)


class OneshotCopyMissing(Exception):
    """No resolvable literal line on the card."""


def literal_line_for_card(brand_id: str, item_id: str, record: dict) -> tuple[str, str]:
    """Return (line, source). Raises OneshotCopyMissing when empty."""
    del brand_id, item_id
    process = str(record.get("process") or "").strip().lower()
    origin = str(record.get("origin") or "").strip().lower()
    if process == "humour" or origin == "meme_lord":
        line = str(record.get("meme_line") or "").strip()
        flavour = str(record.get("meme_flavour") or "").strip().lower()
        if line and flavour:
            return line, f"meme_lord:{flavour}"
        raise OneshotCopyMissing("humour card missing meme_line / meme_flavour")

    headline = str(record.get("headline") or "").strip()
    title = str(record.get("title") or "").strip()
    cta = str(record.get("cta") or "").strip()
    if headline:
        line = f"{headline}\n{cta}".strip() if cta else headline
        return line, "card:headline"
    if title:
        line = f"{title}\n{cta}".strip() if cta else title
        return line, "card:title"
    raise OneshotCopyMissing("no headline or title on card")


def oneshot_scene_prompt(brand_id: str, item_id: str, ctx: ImageDraftContext) -> str:
    """Scene plate without the no-text background suffix."""
    from .image_draft_context import _BACKGROUND_PLATE_SUFFIX  # noqa: PLC0415

    base = background_plate_scene_prompt(brand_id, item_id, ctx)
    return base.replace(_BACKGROUND_PLATE_SUFFIX, "").strip()


def _calendar_record(brand_id: str, item_id: str) -> dict[str, Any]:
    if not item_id.startswith("calendar_candidate:"):
        return {}
    parts = item_id.split(":", 2)
    if len(parts) < 3:
        return {}
    cal_id = parts[2]
    from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

    for record in canonical_records(brand_id):
        rid = str(record.get("calendar_id") or record.get("event_key") or "")
        if rid == cal_id:
            return record if isinstance(record, dict) else {}
    return {}


def process_draft_oneshot_row(
    row: dict[str, Any],
    *,
    item_id: str,
    brand_id: str,
    draft_ctx: ImageDraftContext | None = None,
) -> tuple[Optional[str], Optional[str]]:
    from _lib import llm_spend  # noqa: PLC0415
    from _lib.creative_director import compose_prompt, pick_model  # noqa: PLC0415
    from _lib.image_gen_router import ImageGenAuthError, generate_image_with_persistence  # noqa: PLC0415
    from _lib.image_submit_quota import (  # noqa: PLC0415
        check_brand_image_submit,
        check_brand_oneshot_submit,
        record_brand_image_submit,
        record_brand_oneshot_submit,
    )
    from _lib.marketing_calendar import render_mode_for_record  # noqa: PLC0415

    record = _calendar_record(brand_id, item_id)
    if render_mode_for_record(record) != "oneshot":
        row["status"] = "skipped"
        row["note"] = "not a one-shot card"
        return None, "not_oneshot"

    try:
        literal_text, literal_source = literal_line_for_card(brand_id, item_id, record)
    except OneshotCopyMissing as exc:
        row["status"] = "error"
        row["note"] = str(exc)[:240]
        return None, str(exc)

    ctx = draft_ctx or build_image_draft_context(brand_id, item_id)
    calendar = ctx.lineage.get("calendar") if isinstance(ctx.lineage.get("calendar"), dict) else {}
    if not record and calendar:
        record = calendar

    ai_logo = bool(record.get("oneshot_ai_logo"))
    scene = oneshot_scene_prompt(brand_id, item_id, ctx)
    text_placement = _DEFAULT_TEXT_PLACEMENT if not ai_logo else (
        f"{_DEFAULT_TEXT_PLACEMENT} Include the brand logo lockup as described in brand guidelines."
    )
    cd = compose_prompt(
        brand_id=brand_id,
        job=scene,
        literal_text=literal_text,
        text_placement=text_placement,
        render_text=True,
        ai_rendered_logo=ai_logo,
        format_aspect="4:5",
    )
    wire = cd["wire_prompt"]
    negative = cd["negative_prompt"]

    size = ONESHOT_SIZE
    est = llm_spend.modelled_image_cost(size)
    allowed, reason = llm_spend.check("image", est)
    if not allowed:
        return None, "daily LLM spend cap reached" if "cap" in reason.lower() else reason

    img_ok, img_reason = check_brand_image_submit(brand_id)
    if not img_ok:
        return None, "cap_reached" if "cap" in img_reason.lower() else img_reason

    os_ok, os_reason = check_brand_oneshot_submit(brand_id)
    if not os_ok:
        return None, os_reason

    requested = str(record.get("oneshot_model") or "").strip() or None
    routing = pick_model(
        {"needs_reference": False, "photoreal": False, "typography": True, "edit": False},
        requested_model=requested,
    )

    existing = _sidecar_for_moment(item_id)
    reuse_id: str | None = None
    regen_count = 0
    prev_paths: list[str] = []
    if existing and str(existing.get("action") or "") == "draft_oneshot":
        reuse_id = str(existing.get("asset_id") or "") or None
        try:
            regen_count = max(0, int(existing.get("regen_count") or 0))
        except (TypeError, ValueError):
            regen_count = 0
        old_path = str(existing.get("router_sidecar_path") or "").strip()
        if old_path:
            prev_paths = list(existing.get("previous_router_sidecar_paths") or [])
            if old_path not in prev_paths:
                prev_paths.append(old_path)
        regen_count += 1

    pending_asset_id = reuse_id or f"draft-{uuid.uuid4().hex[:12]}"
    event_key = _event_key_from_calendar(calendar)
    output_base = str(_data_dir() / "draft-assets" / "images")

    llm_spend.write_approval_receipt(route="job:draft_oneshot", estimate_usd=est, brand_id=brand_id)
    record_brand_image_submit(brand_id)
    record_brand_oneshot_submit(brand_id)

    try:
        result = generate_image_with_persistence(
            brand_id=brand_id,
            prompt=wire,
            negative_prompt=negative,
            size=size,
            output_base=output_base,
            provider=routing.get("provider"),
            model=routing.get("model"),
            inbox_item_id=item_id,
            event_key=event_key,
            draft_asset_id=pending_asset_id,
            cost_action="draft_oneshot",
        )
    except ImageGenAuthError:
        return None, "missing OPENAI_API_KEY"
    except Exception as exc:  # noqa: BLE001
        from .draft_assets import _record_error  # noqa: PLC0415

        return None, _record_error(
            exc,
            context={"brand": brand_id, "item": item_id, "step": "draft_oneshot_generate"},
        )

    raw_bytes = getattr(result, "bytes", b"") or b""
    if not raw_bytes:
        return None, "no image bytes"

    logo_source = "missing"
    logo_asset_path: str | None = None
    logo_drift_warning: str | None = None
    if ai_logo:
        logo_source = "ai"
        logo_drift_warning = _LOGO_DRIFT_WARNING
        final_bytes = raw_bytes
    else:
        from _lib.brand_overlay import _find_logo, overlay_logo_only  # noqa: PLC0415

        logo_path = _find_logo(brand_id)
        if logo_path:
            logo_source = "asset"
            logo_asset_path = str(logo_path)
        final_bytes = overlay_logo_only(raw_bytes, brand_id, position="bottom-right")
        image_path_str = getattr(result, "saved_path", None)
        if image_path_str and isinstance(final_bytes, (bytes, bytearray)):
            try:
                Path(str(image_path_str)).write_bytes(final_bytes)
            except OSError:
                pass

    image_path_str = str(getattr(result, "saved_path", None) or "")
    image_url = image_url_for(brand_id, image_path_str) if image_path_str else None

    caption_asset_id, caption_text = _find_caption_draft_for_item(item_id)
    title = str(calendar.get("title") or "")
    angle = str(calendar.get("angle") or "")
    if caption_text:
        caption = caption_text
    elif title and angle:
        caption = f"{title} — {angle}"
    elif title:
        caption = title
    else:
        caption = f"One-shot draft for {item_id}"

    def _as_float(val: object) -> float | None:
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            return float(val)
        return None

    billed = _as_float(getattr(result, "cost_usd", None))
    if billed is None:
        billed = _as_float(getattr(result, "cost_estimate_usd", None))
    if billed is None:
        billed = est
    cost_source = str(getattr(result, "cost_source", "") or "estimate")
    provider_name = str(getattr(result, "provider", "") or "")
    if provider_name not in _ROUTER_SELF_RECORDING_PROVIDERS:
        from _lib import post_cost  # noqa: PLC0415

        post_cost.record_spend_and_line(
            float(billed),
            route="job:draft_oneshot/image",
            model=getattr(result, "model", None),
            kind="image",
            brand_id=brand_id,
            inbox_item_id=item_id,
            draft_asset_id=pending_asset_id,
            event_key=event_key,
            action="draft_oneshot",
            cost_source=cost_source,
            queue_row_id=str(row.get("id") or "") or None,
            provider_job_id=None,
        )

    model_routing = {"pick_model": routing}
    replaced_at = None
    if regen_count > 0:
        replaced_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    sidecar: dict[str, Any] = {
        "action": "draft_oneshot",
        "route": "job:draft_oneshot",
        "model": getattr(result, "model", None),
        "provider": getattr(result, "provider", None),
        "image_path": image_path_str,
        "image_url": image_url,
        "image_size": size,
        "cost_estimate_usd": billed,
        "cost_usd": billed,
        "source": cost_source,
        "queue_row_id": row.get("id"),
        "event_key": event_key,
        "title": title or None,
        "prompt_used": getattr(result, "prompt_used", None) or wire,
        "master_prompt": cd.get("master_prompt"),
        "negative_prompt": negative,
        "literal_text": literal_text,
        "literal_text_source": literal_source,
        "sections": cd.get("sections") or [],
        "model_routing": model_routing,
        "router_sidecar_path": getattr(result, "saved_sidecar_path", None),
        "logo_source": logo_source,
        "logo_drift_warning": logo_drift_warning,
        "logo_asset_path": logo_asset_path,
        "regen_count": regen_count,
        "replaced_at": replaced_at,
        "previous_router_sidecar_paths": prev_paths,
        "caption_asset_id": caption_asset_id,
        "calendar": calendar,
    }

    asset_id = _write_draft(
        brand_id=brand_id,
        caption=caption,
        platform=primary_channel_for_item(brand_id, item_id, fallback="instagram"),
        source_item_id=item_id,
        image_path=image_path_str,
        image_url=image_url,
        asset_id=pending_asset_id,
        sidecar=sidecar,
    )
    return asset_id, None
