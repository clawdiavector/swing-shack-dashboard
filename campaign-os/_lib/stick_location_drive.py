"""Deterministic renderer for stick-location-drive (map-photo + route-line styles)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from _lib.brand_overlay import _brand_dir, _load_brand_font, _load_image

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # noqa: BLE001
    Image = ImageDraw = ImageFont = None  # type: ignore

NAVY = (11, 67, 114)
ACCENT = (62, 224, 137)
WHITE = (255, 255, 255)


def _rect_px(rect: dict[str, Any], w: int, h: int) -> tuple[int, int, int, int]:
    return (
        int(float(rect.get("x0", 0)) * w),
        int(float(rect.get("y0", 0)) * h),
        int(float(rect.get("x1", 1)) * w),
        int(float(rect.get("y1", 1)) * h),
    )


def _style(fields: dict[str, str], archetype: dict[str, Any]) -> str:
    raw = str(fields.get("style") or "").strip()
    if raw in ("map-photo", "route-line"):
        return raw
    style = archetype.get("style") if isinstance(archetype.get("style"), dict) else {}
    return str(style.get("default") or "map-photo")


def _pack_dir(brand_id: str) -> Path:
    return _brand_dir(brand_id) / "templates" / "location-drive"


def _default_map_photo(brand_id: str) -> bytes | None:
    ref = _pack_dir(brand_id) / "references" / "ref-01.jpg"
    if not ref.is_file():
        return None
    img = Image.open(ref).convert("RGB")
    w, h = img.size
    x0, y0, x1, y1 = _rect_px({"x0": 0.06, "y0": 0.07, "x1": 0.52, "y1": 0.85}, w, h)
    crop = img.crop((x0, y0, x1, y1))
    buf = io.BytesIO()
    crop.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _paste_cover(base: Image.Image, photo: Image.Image, rect: dict[str, Any]) -> None:
    w, h = base.size
    x0, y0, x1, y1 = _rect_px(rect, w, h)
    tw, th = max(1, x1 - x0), max(1, y1 - y0)
    src = photo.convert("RGB")
    sw, sh = src.size
    scale = max(tw / sw, th / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)
    cx, cy = (nw - tw) // 2, (nh - th) // 2
    base.paste(resized.crop((cx, cy, cx + tw, cy + th)), (x0, y0))


def _draw_pin(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, fill: tuple[int, int, int]) -> None:
    r = size // 3
    draw.ellipse([cx - r, cy - r - size // 6, cx + r, cy + r - size // 6], fill=fill)
    tri = [(cx, cy + size // 2), (cx - r, cy), (cx + r, cy)]
    draw.polygon(tri, fill=fill)
    draw.ellipse([cx - r // 3, cy - r - size // 8, cx + r // 3, cy - size // 12], fill=NAVY)


def _rounded_pill(
    base: Image.Image,
    rect: dict[str, Any],
    *,
    fill: tuple[int, int, int],
    radius_frac: float,
    icon: str | None = None,
    label: str = "",
    font: ImageFont.FreeTypeFont | None = None,
) -> None:
    w, h = base.size
    x0, y0, x1, y1 = _rect_px(rect, w, h)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    rad = max(4, int(min(x1 - x0, y1 - y0) * radius_frac))
    draw.rounded_rectangle([x0, y0, x1, y1], radius=rad, fill=fill + (255,))
    if icon == "pin":
        _draw_pin(draw, x0 + rad + 8, (y0 + y1) // 2, min(y1 - y0, 48), WHITE)
    if label and font is not None:
        tw = font.getlength(label.upper())
        tx = x0 + (x1 - x0 - int(tw)) // 2 + (12 if icon else 0)
        ty = y0 + (y1 - y0 - font.size) // 2
        draw.text((tx, ty), label.upper(), fill=WHITE, font=font)
    base.paste(layer, (0, 0), layer)


def _wrap_upper(text: str, font: ImageFont.FreeTypeFont, max_w: int, max_lines: int) -> list[str]:
    words = text.upper().split()
    lines: list[str] = []
    cur: list[str] = []
    for word in words:
        trial = " ".join(cur + [word])
        if font.getlength(trial) <= max_w or not cur:
            cur.append(word)
        else:
            lines.append(" ".join(cur))
            cur = [word]
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(" ".join(cur))
    return lines[:max_lines]


def _draw_text_block(
    draw: ImageDraw.ImageDraw,
    rect: dict[str, Any],
    text: str,
    font: ImageFont.FreeTypeFont,
    *,
    canvas_w: int,
    canvas_h: int,
    colour: tuple[int, int, int] = WHITE,
    max_lines: int = 5,
    align: str = "left",
) -> None:
    x0, y0, x1, y1 = _rect_px(rect, canvas_w, canvas_h)
    max_w = x1 - x0
    lines = _wrap_upper(text, font, max_w, max_lines)
    lh = int(font.size * 1.12)
    y = y0
    for line in lines:
        tw = font.getlength(line)
        if align == "center":
            x = x0 + (max_w - int(tw)) // 2
        else:
            x = x0
        draw.text((x, y), line, fill=colour, font=font)
        y += lh
        if y > y1:
            break


def _draw_locked_headline(
    draw: ImageDraw.ImageDraw,
    rect: dict[str, Any],
    font: ImageFont.FreeTypeFont,
    *,
    canvas_w: int,
    canvas_h: int,
    accent_words: set[str],
) -> None:
    x0, y0, x1, y1 = _rect_px(rect, canvas_w, canvas_h)
    lines = ["A SHORT TRIP", "FOR A LONG DRIVE"]
    lh = int(font.size * 1.08)
    y = y0 + max(0, (y1 - y0 - lh * len(lines)) // 2)
    for line in lines:
        x = x0
        for word in line.split():
            colour = ACCENT if word in accent_words else WHITE
            draw.text((x, y), word + " ", fill=colour, font=font)
            x += int(font.getlength(word + " "))
        y += lh


def _draw_route(draw: ImageDraw.ImageDraw, rect: dict[str, Any], segments: list[list[float]], w: int, h: int) -> None:
    x0, y0, x1, y1 = _rect_px(rect, w, h)
    rw, rh = x1 - x0, y1 - y0
    pts = [(x0 + int(s[0] * rw), y0 + int(s[1] * rh)) for s in segments]
    draw.line(pts, fill=ACCENT, width=8, joint="curve")


def _paste_asset(base: Image.Image, brand_id: str, rel: str, rect: dict[str, Any]) -> None:
    path = _pack_dir(brand_id) / "assets" / rel
    if not path.is_file():
        path = _brand_dir(brand_id) / rel
    img = _load_image(path)
    w, h = base.size
    x0, y0, x1, y1 = _rect_px(rect, w, h)
    tw, th = max(1, x1 - x0), max(1, y1 - y0)
    src = img.convert("RGBA")
    sw, sh = src.size
    scale = min(tw / sw, th / sh)
    nw, nh = max(1, int(sw * scale)), max(1, int(sh * scale))
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)
    ox = x0 + (tw - nw) // 2
    oy = y0 + (th - nh) // 2
    base.paste(resized, (ox, oy), resized)


def compose_stick_location_drive(
    *,
    brand_id: str,
    archetype: dict[str, Any],
    canvas_w: int,
    canvas_h: int,
    fields: dict[str, str],
    photo_bytes: bytes | None,
) -> bytes:
    if Image is None:
        raise RuntimeError("PIL unavailable")
    style = _style(fields, archetype)
    base = Image.new("RGB", (canvas_w, canvas_h), NAVY)
    draw = ImageDraw.Draw(base)
    accent_words = {"LONG", "DRIVE"}
    locked = archetype.get("locked_headline") if isinstance(archetype.get("locked_headline"), dict) else {}
    aw = locked.get("accent_on_words") if isinstance(locked.get("accent_on_words"), list) else []
    accent_words = {str(w).upper() for w in aw} or accent_words

    h1 = _load_brand_font(brand_id, "display", 56)
    h4 = _load_brand_font(brand_id, "h3", 36)
    h3 = _load_brand_font(brand_id, "h3", 42)
    pill_font = _load_brand_font(brand_id, "h3", 28)

    headline_rect = {"x0": 0.04, "y0": 0.66, "x1": 0.97, "y1": 0.86}
    if style == "route-line":
        headline_rect = {"x0": 0.04, "y0": 0.72, "x1": 0.97, "y1": 0.86}

    if style == "map-photo":
        photo_data = photo_bytes or _default_map_photo(brand_id)
        if photo_data:
            _paste_cover(base, Image.open(io.BytesIO(photo_data)), {"x0": 0.06, "y0": 0.07, "x1": 0.52, "y1": 0.85})
        draw = ImageDraw.Draw(base)
        _rounded_pill(
            base,
            {"x0": 0.50, "y0": 0.05, "x1": 0.97, "y1": 0.18},
            fill=ACCENT,
            radius_frac=0.04,
            icon="pin",
            label="stick",
            font=pill_font,
        )
        hook = str(fields.get("caption_hook") or "")
        if hook:
            _draw_text_block(
                draw,
                {"x0": 0.55, "y0": 0.28, "x1": 0.97, "y1": 0.62},
                hook,
                h4,
                canvas_w=canvas_w,
                canvas_h=canvas_h,
                max_lines=5,
            )
        vendor = str(fields.get("vendor_name") or "LOCATION")
        _rounded_pill(
            base,
            {"x0": 0.06, "y0": 0.85, "x1": 0.65, "y1": 0.96},
            fill=ACCENT,
            radius_frac=0.04,
            icon="pin",
            label=vendor,
            font=pill_font,
        )
    else:
        pin_rect = {"x0": 0.10, "y0": 0.05, "x1": 0.22, "y1": 0.16}
        px0, py0, px1, py1 = _rect_px(pin_rect, canvas_w, canvas_h)
        _draw_pin(draw, (px0 + px1) // 2, (py0 + py1) // 2, py1 - py0, WHITE)
        vendor = str(fields.get("vendor_name") or "LOCATION")
        _draw_text_block(
            draw,
            {"x0": 0.10, "y0": 0.18, "x1": 0.55, "y1": 0.26},
            vendor,
            h3,
            canvas_w=canvas_w,
            canvas_h=canvas_h,
            max_lines=1,
        )
        zones = archetype.get("zones_route_line") if isinstance(archetype.get("zones_route_line"), dict) else {}
        route = zones.get("route_line") if isinstance(zones.get("route_line"), dict) else {}
        segs = route.get("segments") if isinstance(route.get("segments"), list) else [
            [0.85, 0.10],
            [0.30, 0.40],
            [0.85, 0.55],
            [0.30, 0.78],
        ]
        _draw_route(draw, {"x0": 0.30, "y0": 0.07, "x1": 0.85, "y1": 0.78}, segs, canvas_w, canvas_h)
        kicker = str(fields.get("caption_kicker") or "")
        if kicker:
            _draw_text_block(
                draw,
                {"x0": 0.07, "y0": 0.30, "x1": 0.95, "y1": 0.36},
                kicker,
                h4,
                canvas_w=canvas_w,
                canvas_h=canvas_h,
                max_lines=1,
            )
        hook = str(fields.get("caption_hook") or "")
        if hook:
            _draw_text_block(
                draw,
                {"x0": 0.07, "y0": 0.43, "x1": 0.95, "y1": 0.55},
                hook,
                h4,
                canvas_w=canvas_w,
                canvas_h=canvas_h,
                max_lines=2,
            )
        _paste_asset(
            base,
            brand_id,
            "stick-wordmark-white.png",
            {"x0": 0.62, "y0": 0.55, "x1": 0.95, "y1": 0.66},
        )
        draw = ImageDraw.Draw(base)

    _draw_locked_headline(draw, headline_rect, h1, canvas_w=canvas_w, canvas_h=canvas_h, accent_words=accent_words)
    buf = io.BytesIO()
    base.save(buf, format="PNG", compress_level=6)
    return buf.getvalue()
