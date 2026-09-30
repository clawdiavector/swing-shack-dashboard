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
        if brand_id == "stick":
            return "Fit first. Buy second."
        return "Equipment matched to the player."
    if "equipment" in pillar or "brands" in cap or "retail" in cap:
        return "Curated brands selected for quality, value, and relevance."
    if "apparel" in pillar or "clothing" in cap:
        return "Style that belongs."
    if brand_id == "stick":
        return "Better Begins Here."
    return "Real Golf, Indoors."


def _derive_service_label(*, brand_id: str, moment_id: str, caption: str, sidecar: dict[str, Any]) -> str:
    """Label before the `@` logo on ss-service-promo (e.g. CLUB FITTING)."""
    explicit = str(sidecar.get("compose_service_label") or "").strip()
    if explicit:
        return explicit.upper()
    return _service_carousel_headline(
        brand_id=brand_id,
        moment_id=moment_id,
        caption=caption,
    )


def _service_carousel_headline(*, brand_id: str, moment_id: str, caption: str) -> str:
    ctx = build_image_draft_context(brand_id, moment_id or f"proposal:{brand_id}:compose")
    pillar = _pillar_id_from_context(ctx).lower()
    cap = (caption or "").lower()
    if "fitting" in pillar or "fitting" in cap or "club fitting" in cap or "club assessment" in cap:
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


def _default_cta_from_bible(brand_id: str) -> str:
    from _lib.brand_bible import bible_copy_slice  # noqa: PLC0415

    cs = (bible_copy_slice(brand_id, "poster") or {}).get("copy_system") or {}
    ctas = cs.get("approved_ctas") or []
    if ctas and isinstance(ctas[0], str):
        return ctas[0]
    if brand_id == "swing-shack":
        return "Book your session"
    return "Book a fitting"


def _service_cta(*, brand_id: str, moment_id: str, caption: str) -> str:
    ctx = build_image_draft_context(brand_id, moment_id)
    pillar = _pillar_id_from_context(ctx).lower()
    cap = (caption or "").lower()
    if "fitting" in pillar or "club assessment" in cap or "club fitting" in cap:
        if brand_id == "swing-shack":
            return "Book your club assessment"
        return "Book a fitting"
    if "coaching" in pillar or "trackman" in cap or "swing assessment" in cap:
        if brand_id == "swing-shack":
            return "Book your swing assessment"
        return "Book your swing assessment"
    return _default_cta_from_bible(brand_id)


def _gate_poster_fields(brand_id: str, base: dict[str, str]) -> dict[str, str]:
    from _lib.caption_copy_contract import gate_text  # noqa: PLC0415

    for field in (
        "caption_hook",
        "cta",
        "qualifier",
        "service_lockup",
        "service_label",
        "kicker",
    ):
        val = base.get(field)
        if val and not gate_text(brand_id, str(val))["passed"]:
            base[field] = ""
            blocked = str(base.get("_poster_gate_blocked") or "").strip()
            base["_poster_gate_blocked"] = f"{blocked} {field}".strip()
    return {k: str(v) for k, v in base.items()}


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

    from _lib.poster_copy import resolve_poster_cta, resolve_poster_hook  # noqa: PLC0415

    if archetype_id == "stick-service-end":
        mid = moment_id or f"proposal:{brand_id}:compose"
        ctx = build_image_draft_context(brand_id, mid)
        base = _content_from_caption(caption, ctx)
        headline, src = resolve_poster_hook(
            brand_id=brand_id,
            moment_id=mid,
            caption=caption,
            archetype=archetype,
            sidecar=sidecar,
            asset_title=asset_title,
        )
        tagline = str(sidecar.get("compose_qualifier") or "").strip()
        if not headline:
            headline = _service_carousel_headline(brand_id=brand_id, moment_id=mid, caption=caption)
            src = "caption_fallback"
        if headline == "CLUB FITTING":
            headline = "FITTINGS"
        if not tagline:
            tagline = _service_end_tagline(brand_id=brand_id, moment_id=mid, caption=caption)
        base["caption_hook"] = headline
        base["qualifier"] = tagline
        base["_poster_copy_source"] = src
        return _gate_poster_fields(brand_id, base)

    if needs_photo and archetype_id in ("stick-service-start", "stick-shop-corner"):
        mid = moment_id or f"proposal:{brand_id}:compose"
        headline, src = resolve_poster_hook(
            brand_id=brand_id,
            moment_id=mid,
            caption=caption,
            archetype=archetype,
            sidecar=sidecar,
            asset_title=asset_title,
        )
        lockup = str(sidecar.get("compose_cta") or "").strip() or "@ stick"
        if not headline:
            headline = _service_carousel_headline(brand_id=brand_id, moment_id=mid, caption=caption)
            src = "caption_fallback"
        ctx = build_image_draft_context(brand_id, mid)
        base = _content_from_caption(caption, ctx)
        base["caption_hook"] = headline
        base["cta"] = lockup
        base["_poster_copy_source"] = src
        return _gate_poster_fields(brand_id, base)

    if needs_photo and archetype_id == "stick-coach-profile":
        mid = moment_id or f"proposal:{brand_id}:compose"
        name, src = resolve_poster_hook(
            brand_id=brand_id,
            moment_id=mid,
            caption=caption,
            archetype=archetype,
            sidecar=sidecar,
            asset_title=asset_title,
        )
        body = str(sidecar.get("compose_body") or "").strip()
        ctx = build_image_draft_context(brand_id, mid)
        base = _content_from_caption(caption, ctx)
        if not name:
            name = str(base.get("caption_hook") or "").strip()
            src = "caption_fallback"
        if not body:
            body = str(base.get("caption_body") or "").strip()
        base["caption_hook"] = name
        base["_poster_copy_source"] = src
        return _gate_poster_fields(brand_id, _coach_profile_fields(base, body))
    if needs_photo:
        ctx = build_image_draft_context(brand_id, moment_id or "proposal:stick:local")
        base = _content_from_caption(caption, ctx)
        return _gate_poster_fields(brand_id, base)

    mid = moment_id or f"proposal:{brand_id}:compose"
    headline, src = resolve_poster_hook(
        brand_id=brand_id,
        moment_id=mid,
        caption=caption,
        archetype=archetype,
        sidecar=sidecar,
        asset_title=asset_title,
    )
    cta = resolve_poster_cta(
        brand_id=brand_id,
        moment_id=mid,
        caption=caption,
        sidecar=sidecar,
    )
    qualifier = str(sidecar.get("compose_qualifier") or "").strip()
    price = str(sidecar.get("compose_price") or "").strip()
    price_period = str(sidecar.get("compose_price_period") or "").strip()
    price_labels = str(sidecar.get("compose_price_labels") or "").strip()
    price_values = str(sidecar.get("compose_price_values") or "").strip()
    accent = str(sidecar.get("compose_accent") or "").strip()

    subject = str(sidecar.get("compose_subject") or "").strip()
    expiry = str(sidecar.get("compose_expiry") or "").strip()

    ctx = build_image_draft_context(brand_id, mid)
    base = _content_from_caption(caption, ctx)
    base["caption_hook"] = headline
    base["cta"] = cta
    base["_poster_copy_source"] = src
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
    if archetype_id == "ss-service-promo":
        base["service_label"] = _derive_service_label(
            brand_id=brand_id,
            moment_id=mid,
            caption=caption,
            sidecar=sidecar,
        )
    return _gate_poster_fields(brand_id, base)
