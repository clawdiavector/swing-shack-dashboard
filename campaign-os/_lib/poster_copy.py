"""Poster headline / CTA resolution for compose (caption coherence v1)."""

from __future__ import annotations

import re
from typing import Any

from _lib.jobs.layer5.image_draft_context import build_image_draft_context, calendar_title_for_item

_DEFAULT_HOOK_CAP = 72
_DEFAULT_CTA_CAP = 48
_VALID_MODES = frozenset(
    {"from_llm_hook", "from_lodge_title", "fixed", "from_caption_fallback"}
)


def poster_copy_mode_for_archetype(archetype: dict[str, Any] | None) -> str:
    if not isinstance(archetype, dict):
        return "from_llm_hook"
    mode = str(archetype.get("poster_copy_mode") or "from_llm_hook").strip()
    return mode if mode in _VALID_MODES else "from_llm_hook"


def _zone_cap(archetype: dict[str, Any] | None, zone_name: str, *, default: int) -> int:
    if not isinstance(archetype, dict):
        return default
    zones = archetype.get("zones") if isinstance(archetype.get("zones"), dict) else {}
    zone = zones.get(zone_name) if isinstance(zones.get(zone_name), dict) else {}
    if not zone:
        return default
    max_lines = int(zone.get("max_lines") or 0)
    max_chars = int(zone.get("max_chars_per_line") or 0)
    if max_lines > 0 and max_chars > 0:
        return max_lines * max_chars
    return default


def poster_hook_cap(archetype: dict[str, Any] | None) -> int:
    return _zone_cap(archetype, "headline", default=_DEFAULT_HOOK_CAP)


def poster_cta_cap(archetype: dict[str, Any] | None) -> int:
    cap = _zone_cap(archetype, "cta", default=0)
    if cap <= 0:
        cap = _zone_cap(archetype, "subhead", default=0)
    return cap if cap > 0 else _DEFAULT_CTA_CAP


def _trim_hook(text: str, *, max_chars: int) -> str:
    s = (text or "").strip()
    if not s or len(s) <= max_chars:
        return s
    cut = s[:max_chars]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip() or s[:max_chars].strip()


def resolve_poster_hook(
    *,
    brand_id: str,
    moment_id: str,
    caption: str,
    archetype: dict[str, Any] | None,
    sidecar: dict[str, Any] | None = None,
    asset_title: str | None = None,
) -> tuple[str, str]:
    """Returns (headline, source_label)."""
    sidecar = sidecar or {}
    cap = poster_hook_cap(archetype)
    mode = poster_copy_mode_for_archetype(archetype)

    explicit = str(sidecar.get("compose_headline") or "").strip()
    if explicit:
        return _trim_hook(explicit, max_chars=cap), "sidecar"

    if mode == "fixed":
        pc = archetype.get("poster_copy") if isinstance(archetype, dict) else {}
        fixed = ""
        if isinstance(pc, dict):
            fixed = str(pc.get("fixed_headline") or "").strip()
        if fixed:
            return _trim_hook(fixed, max_chars=cap), "fixed"

    if mode == "from_lodge_title":
        lodge = str(sidecar.get("lodge_title") or "").strip()
        if not lodge and moment_id:
            lodge = calendar_title_for_item(brand_id, moment_id)
        if not lodge and moment_id:
            ctx = build_image_draft_context(brand_id, moment_id)
            cal = ctx.lineage.get("calendar") if isinstance(ctx.lineage.get("calendar"), dict) else {}
            lodge = str(cal.get("title") or "").strip()
        if lodge:
            return _trim_hook(lodge, max_chars=cap), "lodge_title"

    if mode == "from_llm_hook":
        pkg = sidecar.get("copy_package") if isinstance(sidecar.get("copy_package"), dict) else {}
        hook = str(pkg.get("poster_hook") or "").strip()
        if hook:
            return _trim_hook(hook, max_chars=cap), "llm_hook"

    from _lib.compose_visual_copy import _hook_from_caption  # noqa: PLC0415

    hook = _hook_from_caption(caption, max_chars=cap)
    if hook:
        return hook, "caption_fallback"

    if asset_title:
        t = str(asset_title).strip()
        if t:
            return _trim_hook(t, max_chars=cap), "caption_fallback"

    if moment_id:
        ctx = build_image_draft_context(brand_id, moment_id)
        cal = ctx.lineage.get("calendar") if isinstance(ctx.lineage.get("calendar"), dict) else {}
        angle = str(cal.get("angle") or cal.get("suggested_angles") or "").strip()
        if angle and len(angle) <= cap:
            return angle, "caption_fallback"

    return "", "caption_fallback"


def resolve_poster_cta(
    *,
    brand_id: str,
    moment_id: str,
    caption: str,
    sidecar: dict[str, Any] | None = None,
) -> str:
    sidecar = sidecar or {}
    explicit = str(sidecar.get("compose_cta") or "").strip()
    if explicit:
        return explicit
    pkg = sidecar.get("copy_package") if isinstance(sidecar.get("copy_package"), dict) else {}
    line = str(pkg.get("cta_line") or "").strip()
    if line:
        return line
    from _lib.compose_visual_copy import _service_cta  # noqa: PLC0415

    return _service_cta(brand_id=brand_id, moment_id=moment_id or f"proposal:{brand_id}:compose", caption=caption)


def compose_fields_from_copy_package(
    *,
    brand_id: str,
    moment_id: str,
    caption: str,
    archetype: dict[str, Any] | None,
    copy_package: dict[str, Any],
    cal_title: str,
) -> tuple[str, str, str, str, str]:
    """Returns compose_headline, compose_cta, compose_body, poster_copy_mode, source."""
    mode = poster_copy_mode_for_archetype(archetype)
    sidecar_preview = {
        "lodge_title": cal_title,
        "copy_package": copy_package,
    }
    headline, src = resolve_poster_hook(
        brand_id=brand_id,
        moment_id=moment_id,
        caption=caption,
        archetype=archetype,
        sidecar=sidecar_preview,
    )
    cta = resolve_poster_cta(
        brand_id=brand_id,
        moment_id=moment_id,
        caption=caption,
        sidecar={"copy_package": copy_package},
    )
    body = str(copy_package.get("caption_body") or "").strip()
    return headline, cta, body, mode, src


def hook_grounded_in_caption(hook: str, caption: str) -> bool:
    hook_words = {w.lower() for w in re.findall(r"[a-zA-Z]{4,}", hook or "")}
    cap_words = {w.lower() for w in re.findall(r"[a-zA-Z]{4,}", caption or "")}
    if not hook_words:
        return True
    return bool(hook_words & cap_words)
