"""Deterministic archetype renderer (compose_post stage)."""

from __future__ import annotations

import io
from typing import Any

from _lib import archetypes_v2 as archetypes
from _lib.brand_overlay import _find_color_palette, _find_fonts, _find_logo, _hex_to_rgba, _load_font, _load_image

try:
    from PIL import Image, ImageDraw
except Exception:  # noqa: BLE001
    Image = ImageDraw = None  # type: ignore


class ComposeError(RuntimeError):
    """Non-recoverable compose failure (missing assets, overflow)."""


def _palette_colour(token: str, brand_id: str) -> tuple[int, int, int, int]:
    if token.startswith("#"):
        return _hex_to_rgba(token, 255)
    palette_doc = _find_color_palette(brand_id)
    palette = palette_doc.get("palette") if isinstance(palette_doc, dict) else {}
    entry = palette.get(token) if isinstance(palette, dict) else None
    if isinstance(entry, dict) and entry.get("hex"):
        return _hex_to_rgba(str(entry["hex"]), 255)
    if token == "white":
        return (255, 255, 255, 255)
    return (255, 255, 255, 255)


def _font_size_for_role(brand_id: str, role: str, zone_h_px: int) -> int:
    fonts = _find_fonts(brand_id)
    scale = fonts.get("scale") if isinstance(fonts, dict) else []
    size = 32
    if isinstance(scale, list):
        for row in scale:
            if isinstance(row, dict) and str(row.get("name") or "") == role:
                size = int(row.get("size_px") or size)
                break
    return max(12, min(size, zone_h_px))


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


def _wrap_text(text: str, font, max_width: int, max_lines: int, max_chars: int) -> list[str]:
    words = (text or "").strip().split()
    lines: list[str] = []
    current = ""
    for word in words:
        chunk = f"{current} {word}".strip() if current else word
        if len(chunk) > max_chars and current:
            lines.append(current)
            current = word[:max_chars]
        else:
            current = chunk[:max_chars]
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) > max_lines:
        raise ComposeError("text overflow")
    return lines


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
    rect = zone.get("rect") if isinstance(zone.get("rect"), dict) else {}
    x0, y0, x1, y1 = _rect_px(rect, canvas_w, canvas_h)
    role = str(zone.get("font_role") or "body")
    min_px = int(zone.get("min_font_px") or 12)
    if base_canvas_h > 0 and canvas_h < base_canvas_h:
        min_px = max(10, int(min_px * canvas_h / base_canvas_h))
    max_lines = int(zone.get("max_lines") or 1)
    max_chars = int(zone.get("max_chars_per_line") or 40)
    colour = _palette_colour(str(zone.get("colour") or "white"), brand_id)
    zone_h_px = y1 - y0
    size = _font_size_for_role(brand_id, role, zone_h_px)
    if size < min_px:
        if min_px <= zone_h_px:
            size = min_px
        else:
            raise ComposeError("font below min_font_px")
    font = _load_font(None, size)
    lines = _wrap_text(text, font, x1 - x0, max_lines, max_chars)
    if not lines:
        if zone.get("optional"):
            return
        raise ComposeError("missing text")
    lh = float(zone.get("line_height") or 1.2)
    y = y0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        align = str(zone.get("align") or "left")
        if align == "center":
            x = x0 + (x1 - x0 - tw) // 2
        elif align == "right":
            x = x1 - tw
        else:
            x = x0
        draw.text((x, y), line, font=font, fill=colour[:3])
        y += int(size * lh)


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


def _background(base, archetype: dict[str, Any], brand_id: str) -> None:
    bg = archetype.get("background") if isinstance(archetype.get("background"), dict) else {}
    kind = str(bg.get("kind") or "solid")
    draw = ImageDraw.Draw(base)
    w, h = base.size
    if kind == "gradient":
        grad = bg.get("gradient") if isinstance(bg.get("gradient"), dict) else {}
        c0 = _hex_to_rgba(str(grad.get("from") or "#000000"), 255)
        c1 = _hex_to_rgba(str(grad.get("to") or "#FFFFFF"), 255)
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
        elif kind == "image" and str(zone.get("source") or "") == "photo":
            rect = zone.get("rect") if isinstance(zone.get("rect"), dict) else {}
            if photo_bytes:
                _paste_photo(base, photo_bytes, rect)
            elif not zone.get("optional"):
                raise ComposeError("missing photo")
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
        "brand_tagline": "Stick Golf",
    }
