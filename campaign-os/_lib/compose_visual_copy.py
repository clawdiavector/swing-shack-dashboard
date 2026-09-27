"""Derive poster headline + CTA for deterministic compose (service-frame templates)."""

from __future__ import annotations

import re
from typing import Any

from _lib.jobs.layer5.create_photo_compose import _content_from_caption
from _lib.jobs.layer5.image_draft_context import build_image_draft_context

_SS_SERVICE_LABELS = {
    "ss-fitting": "CLUB FITTING",
    "fitting": "CLUB FITTING",
    "ss-coaching": "COACHING",
    "coaching": "COACHING",
    "ss-membership": "MEMBERSHIP",
    "membership": "MEMBERSHIP",
}


def _service_label(*, brand_id: str, moment_id: str) -> str:
    if brand_id != "swing-shack":
        return ""
    ctx = build_image_draft_context(brand_id, moment_id or f"proposal:{brand_id}:compose")
    pillar = _pillar_id_from_context(ctx).lower()
    for key, label in _SS_SERVICE_LABELS.items():
        if key in pillar or pillar == key:
            return label
    return ""


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        s = line.strip()
        if s:
            return s
    return ""


def _hook_from_caption(caption: str, *, max_chars: int = 72) -> str:
    """Short visual hook — matches Review default, then tightens long captions."""
    text = (caption or "").strip()
    if not text:
        return ""
    q = text.find("?")
    if 0 <= q <= max_chars + 24:
        return text[: q + 1].strip()
    line = _first_line(text)
    if not line:
        return ""
    if len(line) <= max_chars:
        return line
    q = line.find("?")
    if 0 <= q < max_chars + 20:
        return line[: q + 1].strip()
    m = re.match(r"^(.{10,}?[.?!])", line)
    if m and len(m.group(1)) <= max_chars:
        return m.group(1).strip()
    words = line.split()
    out: list[str] = []
    n = 0
    for w in words:
        if n + len(w) + (1 if out else 0) > max_chars:
            break
        out.append(w)
        n += len(w) + (1 if len(out) > 1 else 0)
    trimmed = " ".join(out).strip() or line[:max_chars].strip()
    # Service-frame zones: 3×24 chars — keep hooks short even before uppercase wrap.
    short = trimmed.split()
    if len(short) > 8:
        trimmed = " ".join(short[:8])
    return trimmed


def _pillar_id_from_context(ctx) -> str:
    cal = ctx.lineage.get("calendar") if isinstance(ctx.lineage.get("calendar"), dict) else {}
    for key in ("pillar", "pillar_id", "pillars"):
        val = cal.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, list) and val and isinstance(val[0], str):
            return val[0].strip()
    prov = ctx.lineage.get("provenance") if isinstance(ctx.lineage.get("provenance"), dict) else {}
    pid = prov.get("pillar_id")
    return str(pid).strip() if pid else ""


def _service_cta(*, brand_id: str, moment_id: str, caption: str) -> str:
    ctx = build_image_draft_context(brand_id, moment_id)
    pillar = _pillar_id_from_context(ctx).lower()
    cap = (caption or "").lower()
    if "fitting" in pillar or "club assessment" in cap or "club fitting" in cap:
        return "Book your free club assessment"
    if "coaching" in pillar or "trackman" in cap or "swing assessment" in cap:
        return "Book your free swing assessment"
    return "Book your free assessment"


def visual_copy_for_archetype(
    *,
    brand_id: str,
    moment_id: str,
    caption: str,
    archetype: dict[str, Any],
    asset_title: str | None = None,
    sidecar: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Fill compose fields for text-on-template archetypes (no photo)."""
    sidecar = sidecar or {}
    applies = archetype.get("applies_to") if isinstance(archetype.get("applies_to"), dict) else {}
    needs_photo = applies.get("needs_photo", True)
    if needs_photo:
        ctx = build_image_draft_context(brand_id, moment_id or "proposal:stick:local")
        base = _content_from_caption(caption, ctx)
        return {k: str(v) for k, v in base.items()}

    mid = moment_id or f"proposal:{brand_id}:compose"
    headline = str(sidecar.get("compose_headline") or "").strip()
    cta = str(sidecar.get("compose_cta") or "").strip()
    if not headline:
        headline = _hook_from_caption(caption)
    if not headline and asset_title:
        headline = str(asset_title).strip()
    if not headline:
        ctx = build_image_draft_context(brand_id, moment_id)
        cal = ctx.lineage.get("calendar") if isinstance(ctx.lineage.get("calendar"), dict) else {}
        angle = str(cal.get("angle") or cal.get("suggested_angles") or "").strip()
        if angle and len(angle) <= 72:
            headline = angle
    if not cta:
        cta = _service_cta(brand_id=brand_id, moment_id=mid, caption=caption)

    ctx = build_image_draft_context(brand_id, mid)
    base = _content_from_caption(caption, ctx)
    base["caption_hook"] = headline
    if str(archetype.get("id") or "") == "ss-service-promo":
        lines = [ln.strip() for ln in (caption or "").splitlines() if ln.strip()]
        subhead = lines[1] if len(lines) > 1 else cta
        base["cta"] = subhead
        base["service_label"] = _service_label(brand_id=brand_id, moment_id=mid)
    else:
        base["cta"] = cta
    return {k: str(v) for k, v in base.items()}
