"""Deterministic archetype renderer (compose_post stage)."""

from __future__ import annotations

import io
from typing import Any

from _lib import archetypes_v2 as archetypes
from _lib.brand_overlay import (
    _brand_dir,
    _find_color_palette,
    _find_fonts,
    _find_logo,
    _hex_to_rgba,
    _load_brand_font,
    _load_image,
)

try:
    from PIL import Image, ImageDraw, ImageFont, features
except Exception:  # noqa: BLE001
    Image = ImageDraw = ImageFont = features = None  # type: ignore


class ComposeError(RuntimeError):
    """Non-recoverable compose failure (missing assets, overflow)."""


def _require_raqm() -> None:
    if features is None or not features.check("raqm"):
        raise ComposeError("PIL raqm layout engine required for text compose")


def _palette_colour(token: str, brand_id: str) -> tuple[int, int, int, int]:
    if token.startswith("#"):
        return _hex_to_rgba(token, 255)
    palette_doc = _find_color_palette(brand_id)
    tokens = palette_doc.get("tokens") if isinstance(palette_doc.get("tokens"), dict) else {}
    raw_token = tokens.get(token) if isinstance(tokens, dict) else None
    if isinstance(raw_token, str) and raw_token.startswith("#"):
        return _hex_to_rgba(raw_token, 255)
    palette = palette_doc.get("palette") if isinstance(palette_doc, dict) else {}
    entry = palette.get(token) if isinstance(palette, dict) else None
    if isinstance(entry, dict) and entry.get("hex"):
        return _hex_to_rgba(str(entry["hex"]), 255)
    if token == "white":
        return (255, 255, 255, 255)
    return (255, 255, 255, 255)


def _font_nominal_size(brand_id: str, role: str, zone_h_px: int) -> int:
    fonts = _find_fonts(brand_id)
    size = 32
    roles = fonts.get("roles") if isinstance(fonts, dict) else None
    if isinstance(roles, dict) and role in roles:
        entry = roles.get(role)
        if isinstance(entry, dict) and entry.get("size_px"):
            size = int(entry["size_px"])
    scale = fonts.get("scale") if isinstance(fonts, dict) else []
    if isinstance(scale, list):
        for row in scale:
            if isinstance(row, dict) and str(row.get("name") or "") == role:
                size = int(row.get("size_px") or size)
                break
    return max(12, min(size, zone_h_px))


def _emphasis_role(zone: dict[str, Any]) -> str:
    return str(zone.get("emphasis_font_role") or "cta_emphasis")


def _tracking_px(zone: dict[str, Any], font_size: int) -> float:
    em = zone.get("tracking_em")
    if em is None:
        return 0.0
    try:
        return float(em) * font_size
    except (TypeError, ValueError):
        return 0.0


def _emphasis_words(zone: dict[str, Any]) -> set[str]:
    raw = zone.get("emphasis_words")
    if not isinstance(raw, list):
        return set()
    return {str(w).upper() for w in raw if str(w).strip()}


def _apply_text_transform(text: str, zone: dict[str, Any]) -> str:
    transform = str(zone.get("text_transform") or zone.get("transform") or "").lower()
    if transform == "uppercase":
        return text.upper()
    return text


def _rect_px(rect: dict[str, float], w: int, h: int) -> tuple[int, int, int, int]:
    x0 = int(rect["x0"] * w)
    y0 = int(rect["y0"] * h)
    x1 = int(rect["x1"] * w)
    y1 = int(rect["y1"] * h)
    return x0, y0, max(x1, x0 + 1), max(y1, y0 + 1)


def _shift_rect_anchor(
    rect: dict[str, float],
    *,
    block_anchor: str,
    base_h: int,
    target_h: int,
) -> dict[str, float]:
    if block_anchor != "center" or target_h <= base_h:
        return dict(rect)
    delta = (target_h - base_h) / 2 / target_h
    return {
        "x0": rect["x0"],
        "x1": rect["x1"],
        "y0": rect["y0"] + delta,
        "y1": rect["y1"] + delta,
    }


def _zones_for_canvas(archetype: dict[str, Any], canvas_id: str, base_canvas_id: str, base_h: int, target_h: int) -> dict[str, Any]:
    zones = dict(archetype.get("zones") or {})
    overrides = archetype.get("canvas_overrides") if isinstance(archetype.get("canvas_overrides"), dict) else {}
    if canvas_id in overrides and isinstance(overrides[canvas_id], dict):
        merged = dict(zones)
        merged.update(overrides[canvas_id])
        return merged
    if canvas_id == base_canvas_id:
        return zones
    anchor = str(archetype.get("block_anchor") or "center")
    out: dict[str, Any] = {}
    for zid, zspec in zones.items():
        if not isinstance(zspec, dict):
            continue
        rect = zspec.get("rect") if isinstance(zspec.get("rect"), dict) else {}
        zcopy = dict(zspec)
        zcopy["rect"] = _shift_rect_anchor(rect, block_anchor=anchor, base_h=base_h, target_h=target_h)
        out[zid] = zcopy
    return out


def _run_length(text: str, font, tracking_px: float) -> float:
    if not text:
        return 0.0
    base = float(font.getlength(text))
    if tracking_px and len(text) > 1:
        base += tracking_px * (len(text) - 1)
    return base


def _word_font(word: str, body_font, emph_font, emphasis: set[str]):
    if emph_font and word.upper() in emphasis:
        return emph_font
    return body_font


def _line_width(words: list[str], body_font, emph_font, emphasis: set[str], tracking_px: float) -> float:
    if not words:
        return 0.0
    total = 0.0
    for i, word in enumerate(words):
        font = _word_font(word, body_font, emph_font, emphasis)
        total += _run_length(word, font, tracking_px)
        if i < len(words) - 1:
            total += _run_length(" ", body_font, 0.0)
    return total


def _wrap_text(
    text: str,
    body_font,
    emph_font,
    max_width: int,
    max_lines: int,
    max_chars: int,
    emphasis: set[str],
    tracking_px: float,
) -> list[str]:
    words = (text or "").strip().split()
    if not words:
        return []
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        if len(word) > max_chars:
            word = word[:max_chars]
        trial = current + [word]
        trial_text = " ".join(trial)
        if len(trial_text) > max_chars * max_lines and current:
            lines.append(" ".join(current))
            current = [word]
        elif _line_width(trial, body_font, emph_font, emphasis, tracking_px) <= max_width or not current:
            current = trial
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    if len(lines) > max_lines:
        raise ComposeError("text overflow")
    return lines


def _cap_height(font) -> int:
    bbox = font.getbbox("H")
    return max(1, bbox[3] - bbox[1])


def _block_height(num_lines: int, font_size: int, line_height: float, font) -> int:
    if num_lines <= 0:
        return 0
    pitch = int(font_size * line_height)
    return (num_lines - 1) * pitch + _cap_height(font)


def _fit_font_size(
    *,
    brand_id: str,
    role: str,
    zone: dict[str, Any],
    text: str,
    zone_w: int,
    zone_h: int,
    min_px: int,
) -> tuple[int, list[str], Any, Any]:
    emph_role = _emphasis_role(zone)
    emphasis = _emphasis_words(zone)
    lh = float(zone.get("line_height") or 1.2)
    max_lines = int(zone.get("max_lines") or 1)
    max_chars = int(zone.get("max_chars_per_line") or 80)
    nominal = _font_nominal_size(brand_id, role, zone_h)
    lo, hi = min_px, nominal
    best_size = min_px
    best_lines: list[str] = []
    best_body = None
    best_emph = None
    while lo <= hi:
        mid = (lo + hi) // 2
        body = _load_brand_font(brand_id, role, mid)
        if body is None:
            raise ComposeError(f"unresolved font role {role}")
        emph = _load_brand_font(brand_id, emph_role, mid) if emphasis else None
        track = _tracking_px(zone, mid)
        try:
            lines = _wrap_text(text, body, emph, zone_w, max_lines, max_chars, emphasis, track)
        except ComposeError:
            hi = mid - 1
            continue
        if not lines:
            hi = mid - 1
            continue
        too_wide = any(
            _line_width(ln.split(), body, emph, emphasis, track) > zone_w for ln in lines
        )
        too_tall = _block_height(len(lines), mid, lh, body) > zone_h
        if not too_wide and not too_tall:
            best_size = mid
            best_lines = lines
            best_body = body
            best_emph = emph
            lo = mid + 1
        else:
            hi = mid - 1
    if not best_lines or best_body is None:
        raise ComposeError("text overflow")
    return best_size, best_lines, best_body, best_emph


def _draw_tracked_run(
    draw,
    x: float,
    baseline: float,
    text: str,
    font,
    fill,
    tracking_px: float,
) -> float:
    if not text:
        return x
    if tracking_px <= 0:
        draw.text((x, baseline), text, font=font, fill=fill, anchor="ls")
        return x + _run_length(text, font, 0.0)
    cx = x
    for i, ch in enumerate(text):
        draw.text((cx, baseline), ch, font=font, fill=fill, anchor="ls")
        cx += font.getlength(ch) + (tracking_px if i < len(text) - 1 else 0.0)
    return cx


def _draw_line_mixed(
    draw,
    x0: float,
    baseline: float,
    line: str,
    body_font,
    emph_font,
    emphasis: set[str],
    fill,
    tracking_px: float,
    align: str,
    zone_x0: int,
    zone_x1: int,
) -> None:
    words = line.split()
    line_w = _line_width(words, body_font, emph_font, emphasis, tracking_px)
    if align == "center":
        x = zone_x0 + (zone_x1 - zone_x0 - line_w) / 2
    elif align == "right":
        x = zone_x1 - line_w
    else:
        x = float(x0)
    for wi, word in enumerate(words):
        font = _word_font(word, body_font, emph_font, emphasis)
        x = _draw_tracked_run(draw, x, baseline, word, font, fill, tracking_px)
        if wi < len(words) - 1:
            x = _draw_tracked_run(draw, x, baseline, " ", body_font, fill, 0.0)


def _draw_text_zone(
    draw,
    *,
    zone: dict[str, Any],
    text: str,
    brand_id: str,
    canvas_w: int,
    canvas_h: int,
    base_canvas_h: int = 1350,
) -> None:
    _require_raqm()
    rect = zone.get("rect") if isinstance(zone.get("rect"), dict) else {}
    x0, y0, x1, y1 = _rect_px(rect, canvas_w, canvas_h)
    role = str(zone.get("font_role") or "body")
    min_px = int(zone.get("min_font_px") or 12)
    if base_canvas_h > 0 and canvas_h < base_canvas_h:
        min_px = max(10, int(min_px * canvas_h / base_canvas_h))
    text = _apply_text_transform(text, zone)
    colour = _palette_colour(str(zone.get("colour") or "white"), brand_id)
    zone_w = x1 - x0
    zone_h = y1 - y0
    origin_x = float(zone.get("text_origin_x") or x0)
    wrap_x1 = zone.get("wrap_x1")
    if wrap_x1 is not None:
        wrap_w = max(zone_w, int(float(wrap_x1) * canvas_w) - int(origin_x))
    else:
        wrap_w = zone_w
    size, lines, body_font, emph_font = _fit_font_size(
        brand_id=brand_id,
        role=role,
        zone=zone,
        text=text,
        zone_w=wrap_w,
        zone_h=zone_h,
        min_px=min_px,
    )
    lh = float(zone.get("line_height") or 1.2)
    pitch = int(size * lh)
    valign = str(zone.get("valign") or "top").lower()
    cap = _cap_height(body_font)
    block_h = (len(lines) - 1) * pitch + cap
    y_base = y0
    if valign == "center":
        y_base = y0 + (zone_h - block_h) // 2
    tracking_px = _tracking_px(zone, size)
    emphasis = _emphasis_words(zone)
    for i, line in enumerate(lines):
        baseline = y_base + cap + i * pitch
        _draw_line_mixed(
            draw,
            origin_x,
            baseline,
            line,
            body_font,
            emph_font,
            emphasis,
            colour[:3],
            tracking_px,
            str(zone.get("align") or "left"),
            x0,
            x1,
        )


def _paste_photo(base, photo_bytes: bytes | None, rect: dict[str, float]) -> None:
    if not photo_bytes:
        return
    from _lib.brand_overlay import _load_image_from_bytes

    photo = _load_image_from_bytes(photo_bytes)
    if photo is None:
        return
    x0, y0, x1, y1 = _rect_px(rect, base.width, base.height)
    target = photo.resize((x1 - x0, y1 - y0), Image.LANCZOS)
    base.paste(target, (x0, y0))


def _paste_logo(base, brand_id: str, rect: dict[str, float]) -> None:
    logo_path = _find_logo(brand_id)
    if not logo_path:
        raise ComposeError("missing brand logo")
    logo = _load_image(logo_path)
    if logo is None:
        raise ComposeError("missing brand logo")
    x0, y0, x1, y1 = _rect_px(rect, base.width, base.height)
    target_h = y1 - y0
    aspect = logo.width / max(1, logo.height)
    target_w = int(target_h * aspect)
    logo = logo.resize((target_w, target_h), Image.LANCZOS)
    base.paste(logo, (x0, y0), logo if logo.mode == "RGBA" else None)


def _paste_brand_asset(base, brand_id: str, zone: dict[str, Any]) -> None:
    rel = zone.get("asset")
    if not isinstance(rel, str) or not rel.strip():
        raise ComposeError("missing zone asset")
    base_dir = _brand_dir(brand_id)
    if not base_dir:
        raise ComposeError("missing brand directory")
    path = base_dir / rel
    if not path.exists():
        raise ComposeError(f"missing asset {rel}")
    img = _load_image(path)
    if img is None:
        raise ComposeError(f"missing asset {rel}")
    rect = zone.get("rect") if isinstance(zone.get("rect"), dict) else {}
    x0, y0, x1, y1 = _rect_px(rect, base.width, base.height)
    zone_w = x1 - x0
    zone_h = y1 - y0
    fit = str(zone.get("fit") or "aspect_fit").lower()
    align = str(zone.get("align") or "left").lower()
    if fit == "aspect_fit":
        scale = min(zone_w / max(1, img.width), zone_h / max(1, img.height))
        tw = max(1, int(img.width * scale))
        th = max(1, int(img.height * scale))
        img = img.resize((tw, th), Image.LANCZOS)
    else:
        tw, th = zone_w, zone_h
        img = img.resize((tw, th), Image.LANCZOS)
    if align == "right":
        px = x1 - tw
    elif align == "center":
        px = x0 + (zone_w - tw) // 2
    else:
        px = x0
    valign = str(zone.get("valign") or "center").lower()
    if valign == "bottom":
        py = y1 - th
    elif valign == "top":
        py = y0
    else:
        py = y0 + (zone_h - th) // 2
    base.paste(img, (px, py), img if img.mode == "RGBA" else None)


def _background(base, archetype: dict[str, Any], brand_id: str) -> None:
    bg = archetype.get("background") if isinstance(archetype.get("background"), dict) else {}
    kind = str(bg.get("kind") or "solid")
    draw = ImageDraw.Draw(base)
    w, h = base.size
    if kind == "gradient":
        grad = bg.get("gradient") if isinstance(bg.get("gradient"), dict) else {}
        direction = str(grad.get("direction") or bg.get("direction") or "vertical").lower()
        c0 = _hex_to_rgba(str(grad.get("from") or "#000000"), 255)
        c1 = _hex_to_rgba(str(grad.get("to") or "#FFFFFF"), 255)
        if direction == "horizontal":
            for x in range(w):
                t = x / max(1, w - 1)
                r = int(c0[0] * (1 - t) + c1[0] * t)
                g = int(c0[1] * (1 - t) + c1[1] * t)
                b = int(c0[2] * (1 - t) + c1[2] * t)
                draw.line([(x, 0), (x, h)], fill=(r, g, b))
        else:
            for y in range(h):
                t = y / max(1, h - 1)
                r = int(c0[0] * (1 - t) + c1[0] * t)
                g = int(c0[1] * (1 - t) + c1[1] * t)
                b = int(c0[2] * (1 - t) + c1[2] * t)
                draw.line([(0, y), (w, y)], fill=(r, g, b))
    elif kind in ("solid", "photo_band"):
        fill = _palette_colour(str(bg.get("fill") or "navy_deep"), brand_id)
        draw.rectangle([0, 0, w, h], fill=fill[:3])


def _content_for_source(source: str, fields: dict[str, str], zone: dict[str, Any]) -> str:
    if source == "static":
        return str(zone.get("text") or "")
    val = fields.get(source) or ""
    return str(val)


def compose_to_canvas(
    *,
    brand_id: str,
    archetype: dict[str, Any],
    doc: dict[str, Any],
    canvas_id: str,
    fields: dict[str, str],
    photo_bytes: bytes | None,
) -> bytes:
    if Image is None:
        raise ComposeError("PIL unavailable")
    canvases = doc.get("canvases") if isinstance(doc.get("canvases"), dict) else {}
    spec = canvases.get(canvas_id)
    if not isinstance(spec, dict):
        raise ComposeError(f"unknown canvas {canvas_id}")
    w = int(spec.get("w") or 1080)
    h = int(spec.get("h") or 1350)
    base_canvas_id = str(archetype.get("canvas") or "ig_post")
    base_spec = canvases.get(base_canvas_id) if isinstance(canvases.get(base_canvas_id), dict) else spec
    base_h = int(base_spec.get("h") or h)
    zones = _zones_for_canvas(archetype, canvas_id, base_canvas_id, base_h, h)
    base = Image.new("RGB", (w, h), (7, 60, 82))
    bg_kind = str((archetype.get("background") or {}).get("kind") or "")
    if bg_kind != "photo_full_bleed" or not photo_bytes:
        _background(base, archetype, brand_id)
    draw = ImageDraw.Draw(base)
    for zid, zone in zones.items():
        if not isinstance(zone, dict):
            continue
        kind = str(zone.get("kind") or "")
        if kind == "band":
            rect = zone.get("rect") if isinstance(zone.get("rect"), dict) else {}
            x0, y0, x1, y1 = _rect_px(rect, w, h)
            fill = _palette_colour(str(zone.get("fill") or "teal"), brand_id)
            draw.rectangle([x0, y0, x1, y1], fill=fill[:3])
        elif kind == "image":
            source = str(zone.get("source") or "")
            rect = zone.get("rect") if isinstance(zone.get("rect"), dict) else {}
            if source == "photo":
                if photo_bytes:
                    _paste_photo(base, photo_bytes, rect)
                elif not zone.get("optional"):
                    raise ComposeError("missing photo")
            elif source == "asset":
                try:
                    _paste_brand_asset(base, brand_id, zone)
                except ComposeError:
                    if zone.get("optional"):
                        continue
                    raise
            elif not zone.get("optional"):
                raise ComposeError("unknown image source")
        elif kind == "logo":
            rect = zone.get("rect") if isinstance(zone.get("rect"), dict) else {}
            try:
                _paste_logo(base, brand_id, rect)
            except ComposeError:
                if zone.get("optional"):
                    continue
                raise
        elif kind == "text":
            source = str(zone.get("source") or "")
            text = _content_for_source(source, fields, zone)
            if not text.strip():
                if zone.get("optional"):
                    continue
                raise ComposeError("missing text")
            _draw_text_zone(
                draw,
                zone=zone,
                text=text,
                brand_id=brand_id,
                canvas_w=w,
                canvas_h=h,
                base_canvas_h=base_h,
            )
    buf = io.BytesIO()
    base.save(buf, format="PNG", compress_level=6)
    return buf.getvalue()


def compose_post_for_channels(
    *,
    brand_id: str,
    archetype: dict[str, Any],
    channels: list[str],
    fields: dict[str, str] | None = None,
    content: dict[str, str] | None = None,
    photo_bytes: bytes | None,
) -> dict[str, bytes]:
    fields = fields or content or {}
    doc = archetypes.load_archetypes_doc(brand_id)
    out: dict[str, bytes] = {}
    for channel in channels:
        mapped = archetypes.canvas_for_channel(doc, channel)
        if not mapped:
            continue
        canvas_id, _spec = mapped
        out[channel] = compose_to_canvas(
            brand_id=brand_id,
            archetype=archetype,
            doc=doc,
            canvas_id=canvas_id,
            fields=fields,
            photo_bytes=photo_bytes,
        )
    if not out:
        raise ComposeError("no channels composed")
    return out


def caption_fields_from_text(caption: str) -> dict[str, str]:
    lines = [ln.strip() for ln in (caption or "").splitlines() if ln.strip()]
    hook = lines[0] if lines else ""
    body = "\n".join(lines[1:3]) if len(lines) > 1 else ""
    return {
        "caption_hook": hook,
        "caption_body": body,
        "cta": lines[-1] if lines else "Learn more",
        "product_name": hook[:22],
        "vendor_name": "",
    }
