"""Derive poster headline + CTA for deterministic compose (service-frame templates)."""

from __future__ import annotations

import re
import zlib
from typing import Any

from _lib.jobs.layer5.create_photo_compose import _content_from_caption
from _lib.jobs.layer5.image_draft_context import build_image_draft_context


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


def _service_end_tagline(*, brand_id: str, moment_id: str, caption: str) -> str:
    ctx = build_image_draft_context(brand_id, moment_id or f"proposal:{brand_id}:compose")
    pillar = _pillar_id_from_context(ctx).lower()
    cap = (caption or "").lower()
    if "coaching" in pillar or "trackman" in cap or "swing" in cap:
        return "Coaching sessions that guide players toward better, more enjoyable golf."
    if "fitting" in pillar or "club assessment" in cap:
        return "Brand-agnostic fittings guided by data and science."
    if "equipment" in pillar or "brands" in cap or "retail" in cap:
        return "Curated brands selected for quality, value, and relevance."
    if "apparel" in pillar or "clothing" in cap:
        return "Style that belongs."
    return "Golf, made simpler."


def _service_carousel_headline(*, brand_id: str, moment_id: str, caption: str) -> str:
    ctx = build_image_draft_context(brand_id, moment_id or f"proposal:{brand_id}:compose")
    pillar = _pillar_id_from_context(ctx).lower()
    cap = (caption or "").lower()
    if "fitting" in pillar or "club fitting" in cap or "club assessment" in cap:
        return "CLUB FITTING"
    if "equipment" in pillar or "equipment" in cap:
        return "EQUIPMENT"
    if "apparel" in pillar or "apparel" in cap:
        return "APPAREL"
    if "coaching" in pillar or "trackman" in cap or "swing" in cap:
        return "COACHING"
    hook = _hook_from_caption(caption, max_chars=24).upper()
    return hook or "COACHING"


def _derive_service_lockup(
    *,
    brand_id: str,
    moment_id: str,
    caption: str,
    sidecar: dict[str, Any],
    headline: str,
) -> str:
    lock = str(sidecar.get("compose_service_lockup") or "").strip()
    if lock:
        return lock
    ctx = build_image_draft_context(brand_id, moment_id)
    cal = ctx.lineage.get("calendar") if isinstance(ctx.lineage.get("calendar"), dict) else {}
    subject = str(cal.get("subject") or cal.get("service") or cal.get("angle") or "").strip()
    if subject and len(subject) <= 32:
        return subject.upper()
    cap = (caption or "").lower()
    pillar = _pillar_id_from_context(ctx).lower()
    if "putter" in pillar or "putter" in cap:
        return "PUTTER FITTING"
    if "iron" in pillar or "iron" in cap or "fitting" in pillar:
        return "IRON FITTING"
    words = (headline or caption or "").upper().split()
    if len(words) >= 2:
        return " ".join(words[-2:])
    return words[-1] if words else "CLUB FITTING"


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
    archetype_id = str(archetype.get("id") or "")

    def _coach_profile_fields(base: dict[str, str], body: str) -> dict[str, str]:
        lines = [ln.strip() for ln in (body or "").splitlines() if ln.strip()]
        if lines:
            base["kicker"] = lines[0]
        for idx, line in enumerate(lines[1:4], start=1):
            base[f"bio_{idx}"] = line
        return {k: str(v) for k, v in base.items()}

    if archetype_id == "stick-service-end":
        mid = moment_id or f"proposal:{brand_id}:compose"
        ctx = build_image_draft_context(brand_id, mid)
        base = _content_from_caption(caption, ctx)
        headline = str(sidecar.get("compose_headline") or "").strip()
        tagline = str(sidecar.get("compose_qualifier") or "").strip()
        if not headline:
            headline = _service_carousel_headline(brand_id=brand_id, moment_id=mid, caption=caption)
        if headline == "CLUB FITTING":
            headline = "FITTINGS"
        if not tagline:
            tagline = _service_end_tagline(brand_id=brand_id, moment_id=mid, caption=caption)
        base["caption_hook"] = headline
        base["qualifier"] = tagline
        return {k: str(v) for k, v in base.items()}

    if needs_photo and archetype_id in ("stick-service-start", "stick-shop-corner"):
        mid = moment_id or f"proposal:{brand_id}:compose"
        headline = str(sidecar.get("compose_headline") or "").strip()
        lockup = str(sidecar.get("compose_cta") or "").strip()
        if not headline:
            headline = _service_carousel_headline(brand_id=brand_id, moment_id=mid, caption=caption)
        if not lockup:
            lockup = "@ stick"
        ctx = build_image_draft_context(brand_id, mid)
        base = _content_from_caption(caption, ctx)
        base["caption_hook"] = headline
        base["cta"] = lockup
        return {k: str(v) for k, v in base.items()}

    if needs_photo and archetype_id == "stick-coach-profile":
        mid = moment_id or f"proposal:{brand_id}:compose"
        name = str(sidecar.get("compose_headline") or "").strip()
        body = str(sidecar.get("compose_body") or "").strip()
        ctx = build_image_draft_context(brand_id, mid)
        base = _content_from_caption(caption, ctx)
        if not name:
            name = str(base.get("caption_hook") or "").strip()
        if not body:
            body = str(base.get("caption_body") or "").strip()
        base["caption_hook"] = name
        return _coach_profile_fields(base, body)
    if needs_photo:
        ctx = build_image_draft_context(brand_id, moment_id or "proposal:stick:local")
        base = _content_from_caption(caption, ctx)
        return {k: str(v) for k, v in base.items()}

    mid = moment_id or f"proposal:{brand_id}:compose"
    headline = str(sidecar.get("compose_headline") or "").strip()
    cta = str(sidecar.get("compose_cta") or "").strip()
    qualifier = str(sidecar.get("compose_qualifier") or "").strip()
    price = str(sidecar.get("compose_price") or "").strip()
    price_period = str(sidecar.get("compose_price_period") or "").strip()
    price_labels = str(sidecar.get("compose_price_labels") or "").strip()
    price_values = str(sidecar.get("compose_price_values") or "").strip()
    accent = str(sidecar.get("compose_accent") or "").strip()
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

    subject = str(sidecar.get("compose_subject") or "").strip()
    expiry = str(sidecar.get("compose_expiry") or "").strip()

    ctx = build_image_draft_context(brand_id, mid)
    base = _content_from_caption(caption, ctx)
    base["caption_hook"] = headline
    base["cta"] = cta
    if qualifier:
        base["qualifier"] = qualifier
    if price:
        base["price"] = price
    if price_period:
        base["price_period"] = price_period
    if price_labels:
        base["price_labels"] = price_labels
    if price_values:
        base["price_values"] = price_values
    if not accent and headline:
        opts = ("ss_green", "ss_orange", "ss_blue", "ss_purple")
        accent = opts[zlib.crc32(headline.upper().encode("utf-8")) % len(opts)]
    if accent:
        base["accent"] = accent
    if subject:
        base["offer_subject"] = subject
    if expiry:
        base["offer_expiry"] = expiry
    base["service_lockup"] = _derive_service_lockup(
        brand_id=brand_id,
        moment_id=mid,
        caption=caption,
        sidecar=sidecar,
        headline=headline,
    )
    return {k: str(v) for k, v in base.items()}
