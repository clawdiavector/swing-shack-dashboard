"""L5 draft_oneshot — model-rendered text line for calendar one-shot cards."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
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
from .oneshot_art_direction import OneshotArtDirection, build_art_direction
from .image_draft_context import (
    ImageDraftContext,
    background_plate_scene_prompt,
    build_image_draft_context,
    image_url_for,
    primary_channel_for_item,
)

ONESHOT_SIZE = "1024x1280"
# Default one-shot model. Ideogram 4 is the text-rendering upgrade over 3 and is
# live on Krea (web slug `ideogram-v4`), but the exact MCP model string has not
# been confirmed with a real call from here — `_MODEL_CAPABILITIES` still marks
# it `verified: False` for that reason. `_ONESHOT_FALLBACK_MODEL` covers the
# case where Krea's upstream rejects the id, the way it already does for models
# that `list_models` advertises but will not run (see creative_director's note
# on google/gemini-3-pro-image). Operators override per card with
# `oneshot_model` — recraft/recraft-v4 is the pick for collage cards.
# Verified against Krea list_models on 2026-10-05: there is no
# "ideogram/ideogram-4". The 4.x line ships as 4.5 and 4.5-precise, so the
# old id could only ever 422. Keep this in step with verify_specs.py.
ONESHOT_DEFAULT_MODEL = "ideogram/ideogram-4.5"
_ONESHOT_FALLBACK_MODEL = "ideogram/ideogram-3"
_LOGO_DRIFT_WARNING = (
    "AI-rendered logo. The mark will drift from the brand asset — proportions, spacing "
    "and letterforms are not reproducible. Check it before approving."
)
# Swapped in for _BACKGROUND_PLATE_SUFFIX on render-text jobs. The background
# suffix bans "no text, no letters, no logos, no typography" outright, which
# is wrong here — we want exactly one line rendered. But stripping it to
# nothing (the old behaviour) also threw away "no UI overlays, no
# infographic elements", leaving nothing to stop the model treating a
# mentioned screen/monitor as a second surface to put text on. Evidence
# (2026-10-02): the hardcoded "TrackMan launch monitor glow" scene string
# produced garbled UI-looking text on the monitor and on an overhead
# fixture in testing. Keep the non-text safety, replace the text ban with
# an explicit "screens are dark" instruction instead of silence.
_RENDER_TEXT_SCENE_SUFFIX = (
    " Single unified photograph, not a collage, not split panels, not a poster or "
    "brochure layout. No people required. Any monitor, screen, or illuminated sign "
    "visible in the shot is dark or shows only a soft unreadable glow, not legible "
    "content. No infographic elements."
)


_MODEL_REJECTION_MARKERS = ("unsupported", "unknown model", "invalid model", "no such model")


def _is_model_rejection(exc: Exception) -> bool:
    """True when a Krea upstream error looks like 'this model id is not callable'."""
    msg = str(exc).lower()
    return any(marker in msg for marker in _MODEL_REJECTION_MARKERS) and "model" in msg


class OneshotCopyMissing(Exception):
    """No resolvable literal line on the card."""


@dataclass
class _OneshotBundle:
    literal_text: str
    literal_source: str
    cd: dict[str, Any]
    wire: str
    negative: str
    calendar: dict[str, Any]
    record: dict[str, Any]
    ai_logo: bool
    routing: dict[str, str]
    pending_asset_id: str
    regen_count: int
    prev_paths: list[str]
    event_key: str | None
    size: str
    est: float
    art: OneshotArtDirection


def _origin_kind(record: dict) -> str:
    origin = record.get("origin")
    if isinstance(origin, dict):
        return str(origin.get("kind") or "").strip().lower()
    return str(origin or "").strip().lower()


@dataclass
class OneshotCopy:
    """The lines the model is asked to paint, and where they came from."""

    headline: str
    kicker: str
    source: str

    @property
    def literal_text(self) -> str:
        return f"{self.headline}\n{self.kicker}".strip() if self.kicker else self.headline


def _normalise_label(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


def _caption_draft_sidecar(item_id: str) -> dict[str, Any]:
    """The draft_caption sidecar for this moment, if the caption job has run.

    `compose_headline` / `compose_cta` are the approved poster copy the
    template path overlays (written by `poster_copy.compose_fields_from_copy_package`).
    One-shot used to ignore them and read the calendar record only — which is
    why cards with no `headline` fell through to the card title.
    """
    draft_dir = _data_dir() / "draft-assets"
    if not draft_dir.is_dir():
        return {}
    newest: dict[str, Any] = {}
    newest_at = ""
    for path in sorted(draft_dir.glob("*.json")):
        try:
            sidecar = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(sidecar, dict):
            continue
        if sidecar.get("source_inbox_item_id") != item_id:
            continue
        if sidecar.get("action") != "draft_caption":
            continue
        created = str(sidecar.get("created_at") or "")
        if created >= newest_at:
            newest, newest_at = sidecar, created
    return newest


def literal_line_for_card(brand_id: str, item_id: str, record: dict) -> tuple[str, str]:
    """Back-compat wrapper — (line, source). Prefer `oneshot_copy_for_card`."""
    copy = oneshot_copy_for_card(brand_id, item_id, record)
    return copy.literal_text, copy.source


def oneshot_copy_for_card(brand_id: str, item_id: str, record: dict) -> OneshotCopy:
    """Resolve the real headline (+ kicker) for a one-shot card.

    Refuses rather than falling back to the calendar card's `title`. The title
    is a planning label — "Coaching promo — one-shot" — and painting it onto a
    poster is exactly the failure in the 2 Oct review card. A one-shot with no
    approved copy is a card that is not ready to render, not a card to render
    with its own filename on it.
    """
    del brand_id
    process = str(record.get("process") or "").strip().lower()
    if process == "humour" or _origin_kind(record) == "meme_lord":
        meme = record.get("meme")
        if not isinstance(meme, dict):
            raise OneshotCopyMissing("humour card missing meme object")
        line = str(meme.get("caption") or "").strip()
        flavour = str(meme.get("flavour") or "").strip().lower()
        if not line:
            raise OneshotCopyMissing("humour card missing meme.caption")
        source = f"meme_lord:{flavour}" if flavour else "meme_lord:unknown"
        return OneshotCopy(headline=line, kicker="", source=source)

    headline = str(record.get("headline") or "").strip()
    kicker = str(record.get("cta") or "").strip()
    source = "card:headline"
    if not headline:
        sidecar = _caption_draft_sidecar(item_id)
        headline = str(sidecar.get("compose_headline") or "").strip()
        kicker = str(sidecar.get("compose_cta") or "").strip()
        source = "caption_draft:compose_headline"
    if not headline:
        raise OneshotCopyMissing(
            "no approved headline for this card — run draft_caption first, or set "
            "headline on the calendar record. One-shot will not paint the card title."
        )

    title = str(record.get("title") or "").strip()
    if title and _normalise_label(headline) == _normalise_label(title):
        raise OneshotCopyMissing(
            f"resolved headline is the card label ({title!r}) — needs real poster copy"
        )
    if _normalise_label(kicker) == _normalise_label(headline):
        kicker = ""
    return OneshotCopy(headline=headline, kicker=kicker, source=source)


def oneshot_scene_prompt(brand_id: str, item_id: str, ctx: ImageDraftContext) -> str:
    """Scene plate with the no-text background suffix swapped for a render-text-safe one."""
    from .image_draft_context import _BACKGROUND_PLATE_SUFFIX  # noqa: PLC0415

    base = background_plate_scene_prompt(brand_id, item_id, ctx)
    return base.replace(_BACKGROUND_PLATE_SUFFIX, _RENDER_TEXT_SCENE_SUFFIX).strip()


def _brand_palette(brand_id: str) -> dict[str, Any]:
    """Role-keyed palette (primary/accent/neutral_light) for art direction."""
    from _lib.creative_director import _load_brand_context  # noqa: PLC0415

    palette = _load_brand_context(brand_id).get("palette")
    return palette if isinstance(palette, dict) else {}


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


def _prepare_oneshot_bundle(
    brand_id: str,
    item_id: str,
    *,
    draft_ctx: ImageDraftContext | None = None,
    row: dict[str, Any] | None = None,
) -> tuple[Optional[_OneshotBundle], Optional[str]]:
    from _lib import llm_spend  # noqa: PLC0415
    from _lib.creative_director import compose_prompt, pick_model  # noqa: PLC0415
    from _lib.marketing_calendar import render_mode_for_record  # noqa: PLC0415

    record = _calendar_record(brand_id, item_id)
    if render_mode_for_record(record) != "oneshot":
        if row is not None:
            row["status"] = "skipped"
            row["note"] = "not a one-shot card"
        return None, "not_oneshot"

    ctx = draft_ctx or build_image_draft_context(brand_id, item_id)
    calendar = ctx.lineage.get("calendar") if isinstance(ctx.lineage.get("calendar"), dict) else {}
    if not record and calendar:
        record = calendar

    # Copy first — a card with no approved headline never reaches the model.
    try:
        copy = oneshot_copy_for_card(brand_id, item_id, record)
    except OneshotCopyMissing as exc:
        # "copy:" prefix is load-bearing — draft_assets routes a one-shot error
        # to row status "error" (not "skipped") on that word, and a copy
        # problem is a card that needs attention, not one to pass over.
        note = f"copy: {exc}"
        if row is not None:
            row["status"] = "error"
            row["note"] = note[:240]
        return None, note
    literal_text = copy.literal_text
    literal_source = copy.source

    ai_logo = bool(record.get("oneshot_ai_logo"))
    post_type = str(record.get("post_type") or calendar.get("post_type") or "").strip().lower()
    art = build_art_direction(
        brand_id=brand_id,
        post_type=post_type,
        headline=copy.headline,
        kicker=copy.kicker,
        ai_logo=ai_logo,
        palette=_brand_palette(brand_id),
        fallback_scene=oneshot_scene_prompt(brand_id, item_id, ctx),
    )
    type_spec = art.type_spec
    if ai_logo:
        type_spec = (
            f"{type_spec} Include the brand logo lockup in the bottom-right corner as "
            "described in brand guidelines."
        )
    cd = compose_prompt(
        brand_id=brand_id,
        job=art.scene,
        literal_text=literal_text,
        literal_text_spec=type_spec,
        brand_colours_inline=True,
        output_style=art.output_style,
        render_text=True,
        ai_rendered_logo=ai_logo,
        format_aspect="4:5",
    )
    wire = cd["wire_prompt"]
    negative = cd["negative_prompt"]

    size = ONESHOT_SIZE
    est = llm_spend.modelled_image_cost(size)

    requested = str(record.get("oneshot_model") or "").strip() or None
    routing = pick_model(
        {"needs_reference": False, "photoreal": False, "typography": True, "edit": False},
        requested_model=requested or ONESHOT_DEFAULT_MODEL,
    )
    if not requested:
        # pick_model's requested-model path words its reason as an operator
        # choice. This one is the route default, so say so — the sidecar is
        # what gets read back when a gen is reviewed.
        routing = dict(routing)
        routing["reason"] = (
            f"one-shot default ({ONESHOT_DEFAULT_MODEL}) — unverified, no live Krea run yet; "
            f"falls back to {_ONESHOT_FALLBACK_MODEL} if upstream rejects the id"
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

    return (
        _OneshotBundle(
            literal_text=literal_text,
            literal_source=literal_source,
            cd=cd,
            wire=wire,
            negative=negative,
            calendar=calendar,
            record=record,
            ai_logo=ai_logo,
            routing=routing,
            pending_asset_id=pending_asset_id,
            regen_count=regen_count,
            prev_paths=prev_paths,
            event_key=event_key,
            size=size,
            est=est,
            art=art,
        ),
        None,
    )


def _logo_sidecar_fields(brand_id: str, *, ai_logo: bool) -> tuple[str, str | None, str | None]:
    if ai_logo:
        return "ai", None, _LOGO_DRIFT_WARNING
    from _lib.brand_overlay import _find_logo  # noqa: PLC0415

    logo_path = _find_logo(brand_id)
    if logo_path:
        return "asset", str(logo_path), None
    return "missing", None, None


def _overlay_logo_on_file(
    raw_bytes: bytes,
    brand_id: str,
    *,
    ai_logo: bool,
    image_path_str: str | None,
) -> bytes:
    # Logo stamp paused. The volume asset is an opaque white plate and was
    # painting a white square over the poster. Re-enable when logo.png is a
    # transparent mark.
    del brand_id, ai_logo, image_path_str
    return raw_bytes


def _write_oneshot_draft_from_image(
    row: dict[str, Any],
    *,
    brand_id: str,
    item_id: str,
    bundle: _OneshotBundle,
    image_path_str: str,
    image_url: str | None,
    result: Any,
    record_sync_post_cost: bool,
) -> str:
    caption_asset_id, caption_text = _find_caption_draft_for_item(item_id)
    calendar = bundle.calendar
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
        billed = bundle.est
    cost_source = str(getattr(result, "cost_source", "") or "estimate")
    provider_name = str(getattr(result, "provider", "") or "")
    pj_raw = getattr(result, "provider_job_id", None)
    provider_job_id = pj_raw.strip() if isinstance(pj_raw, str) and pj_raw.strip() else None

    if record_sync_post_cost and provider_name not in _ROUTER_SELF_RECORDING_PROVIDERS:
        from _lib import post_cost  # noqa: PLC0415

        post_cost.record_spend_and_line(
            float(billed),
            route="job:draft_oneshot/image",
            model=getattr(result, "model", None),
            kind="image",
            brand_id=brand_id,
            inbox_item_id=item_id,
            draft_asset_id=bundle.pending_asset_id,
            event_key=bundle.event_key,
            action="draft_oneshot",
            cost_source=cost_source,
            queue_row_id=str(row.get("id") or "") or None,
            provider_job_id=provider_job_id,
        )

    cd = bundle.cd
    routing = bundle.routing
    model_routing = {"pick_model": routing}
    replaced_at = None
    if bundle.regen_count > 0:
        replaced_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    logo_source, logo_asset_path, logo_drift_warning = _logo_sidecar_fields(
        brand_id,
        ai_logo=bundle.ai_logo,
    )

    sidecar: dict[str, Any] = {
        "action": "draft_oneshot",
        "route": "job:draft_oneshot",
        "model": getattr(result, "model", None),
        "provider": getattr(result, "provider", None),
        "image_path": image_path_str,
        "image_url": image_url,
        "image_size": bundle.size,
        "cost_estimate_usd": billed,
        "cost_usd": billed,
        "source": cost_source,
        "queue_row_id": row.get("id"),
        "event_key": bundle.event_key,
        "title": title or None,
        "prompt_used": getattr(result, "prompt_used", None) or bundle.wire,
        "master_prompt": cd.get("master_prompt"),
        "negative_prompt": bundle.negative,
        "literal_text": bundle.literal_text,
        "literal_text_source": bundle.literal_source,
        "art_direction": {
            "treatment": bundle.art.treatment,
            "post_type": bundle.art.post_type,
            "scene_source": bundle.art.scene_source,
            "type_spec": bundle.art.type_spec,
        },
        "sections": cd.get("sections") or [],
        "model_routing": model_routing,
        "router_sidecar_path": getattr(result, "saved_sidecar_path", None),
        "logo_source": logo_source,
        "logo_drift_warning": logo_drift_warning,
        "logo_asset_path": logo_asset_path,
        "regen_count": bundle.regen_count,
        "replaced_at": replaced_at,
        "previous_router_sidecar_paths": bundle.prev_paths,
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
        asset_id=bundle.pending_asset_id,
        sidecar=sidecar,
    )
    return asset_id


def finalize_draft_oneshot_from_krea_poll(
    row: dict[str, Any],
    *,
    item_id: str,
    brand_id: str,
    png_path: Path,
    job_entry: dict[str, Any],
) -> Optional[str]:
    """Complete draft_oneshot after krea_poll downloaded the async Krea PNG."""
    bundle, err = _prepare_oneshot_bundle(brand_id, item_id, row=row)
    if err or bundle is None:
        return None

    raw_bytes = png_path.read_bytes()
    if not raw_bytes:
        return None

    image_path_str = str(png_path)
    _overlay_logo_on_file(
        raw_bytes,
        brand_id,
        ai_logo=bundle.ai_logo,
        image_path_str=image_path_str,
    )

    image_url = image_url_for(brand_id, image_path_str)
    meta_path = png_path.with_suffix(".png.meta.json")
    router_sidecar = str(meta_path) if meta_path.is_file() else None
    job_id = str(job_entry.get("job_id") or "")
    est = float(job_entry.get("est_usd") or bundle.est)

    class _PollResult:
        pass

    poll_result = _PollResult()
    poll_result.model = bundle.routing.get("model")
    poll_result.provider = "krea"
    poll_result.cost_usd = est
    poll_result.cost_estimate_usd = est
    poll_result.cost_source = "krea"
    poll_result.provider_job_id = job_id
    poll_result.prompt_used = bundle.wire
    poll_result.saved_sidecar_path = router_sidecar

    return _write_oneshot_draft_from_image(
        row,
        brand_id=brand_id,
        item_id=item_id,
        bundle=bundle,
        image_path_str=image_path_str,
        image_url=image_url,
        result=poll_result,
        record_sync_post_cost=False,
    )


def process_draft_oneshot_row(
    row: dict[str, Any],
    *,
    item_id: str,
    brand_id: str,
    draft_ctx: ImageDraftContext | None = None,
) -> tuple[Optional[str], Optional[str]]:
    from _lib import llm_spend  # noqa: PLC0415
    from _lib.image_gen_router import (  # noqa: PLC0415
        ImageGenAuthError,
        ImageGenUpstreamError,
        generate_image_with_persistence,
    )
    from _lib.image_submit_quota import (  # noqa: PLC0415
        check_brand_image_submit,
        check_brand_oneshot_submit,
        record_brand_image_submit,
        record_brand_oneshot_submit,
    )

    bundle, err = _prepare_oneshot_bundle(brand_id, item_id, draft_ctx=draft_ctx, row=row)
    if err or bundle is None:
        return None, err

    allowed, reason = llm_spend.check("image", bundle.est)
    if not allowed:
        return None, "daily LLM spend cap reached" if "cap" in reason.lower() else reason

    img_ok, img_reason = check_brand_image_submit(brand_id)
    if not img_ok:
        return None, "cap_reached" if "cap" in img_reason.lower() else img_reason

    is_regen = bundle.regen_count > 0
    if not is_regen:
        os_ok, os_reason = check_brand_oneshot_submit(brand_id)
        if not os_ok:
            return None, os_reason

    output_base = str(_data_dir() / "draft-assets" / "images")

    llm_spend.write_approval_receipt(route="job:draft_oneshot", estimate_usd=bundle.est, brand_id=brand_id)
    record_brand_image_submit(brand_id)
    if not is_regen:
        record_brand_oneshot_submit(brand_id)

    def _generate(model: str | None):
        return generate_image_with_persistence(
            brand_id=brand_id,
            prompt=bundle.wire,
            # Krea folds negatives into the prompt as "Avoid: …". That essay
            # was not in the Krea UI paste that matched the art direction.
            negative_prompt=None,
            size=bundle.size,
            output_base=output_base,
            provider=bundle.routing.get("provider"),
            model=model,
            inbox_item_id=item_id,
            event_key=bundle.event_key,
            draft_asset_id=bundle.pending_asset_id,
            cost_action="draft_oneshot",
            background_plate=True,
        )

    try:
        try:
            result = _generate(bundle.routing.get("model"))
        except ImageGenUpstreamError as exc:
            # Krea's upstream rejects model ids its own list_models advertises
            # (verified for google/gemini-3-pro-image). The one-shot default is
            # marked unverified for exactly this reason — take one shot at the
            # known-good id rather than failing the card. Quota and spend were
            # already recorded above and are not re-charged.
            current = str(bundle.routing.get("model") or "")
            if not _is_model_rejection(exc) or current == _ONESHOT_FALLBACK_MODEL:
                raise
            bundle.routing = dict(bundle.routing)
            bundle.routing["model"] = _ONESHOT_FALLBACK_MODEL
            bundle.routing["reason"] = (
                f"{current} rejected by Krea upstream — fell back to "
                f"{_ONESHOT_FALLBACK_MODEL}"
            )
            bundle.routing["fallback_from"] = current
            result = _generate(_ONESHOT_FALLBACK_MODEL)
    except ImageGenAuthError:
        return None, "missing OPENAI_API_KEY"
    except Exception as exc:  # noqa: BLE001
        from .draft_assets import _record_error  # noqa: PLC0415

        return None, _record_error(
            exc,
            context={"brand": brand_id, "item": item_id, "step": "draft_oneshot_generate"},
        )

    pj = getattr(result, "provider_job_id", None)
    raw_bytes = getattr(result, "bytes", b"") or b""
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
            size=bundle.size,
            est_usd=bundle.est,
            retry_count=rc,
        )
        row["status"] = "waiting"
        return None, None

    if not raw_bytes:
        image_path_str = str(getattr(result, "saved_path", None) or "")
        if image_path_str:
            try:
                raw_bytes = Path(image_path_str).read_bytes()
            except OSError:
                raw_bytes = b""
    if not raw_bytes:
        return None, "no image bytes"

    image_path_str = str(getattr(result, "saved_path", None) or "")
    if raw_bytes:
        _overlay_logo_on_file(
            raw_bytes,
            brand_id,
            ai_logo=bundle.ai_logo,
            image_path_str=image_path_str or None,
        )
    image_url = image_url_for(brand_id, image_path_str) if image_path_str else None

    asset_id = _write_oneshot_draft_from_image(
        row,
        brand_id=brand_id,
        item_id=item_id,
        bundle=bundle,
        image_path_str=image_path_str,
        image_url=image_url,
        result=result,
        record_sync_post_cost=True,
    )
    return asset_id, None
