"""Deterministic archetype renderer (compose_post stage)."""

from __future__ import annotations

import io
import zlib
from itertools import combinations
from typing import Any

from _lib import archetypes_v2 as archetypes
from _lib.brand_overlay import (
    _brand_dir,
    _candidate_brand_dirs,
    _find_color_palette,
    _find_fonts,
    _find_logo,
    _hex_to_rgba,
    _load_brand_font,
    _load_image,
    _load_image_from_bytes,
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
        for zid, patch in overrides[canvas_id].items():
            if not isinstance(patch, dict):
                merged[zid] = patch
                continue
            base_z = merged.get(zid)
            if isinstance(base_z, dict):
                zcopy = dict(base_z)
                if set(patch.keys()) <= {"rect"} and isinstance(patch.get("rect"), dict):
                    zcopy["rect"] = patch["rect"]
                else:
                    zcopy.update(patch)
                merged[zid] = zcopy
            else:
                merged[zid] = patch
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


def _wrap_explicit(text: str, max_lines: int) -> list[str]:
    """Author-controlled breaks: one line per \\n (or |) item, never reflowed."""
    raw = (text or "").replace("|", "\n")
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if len(lines) > max_lines:
        raise ComposeError("text overflow")
    return lines


def _wrap_balanced(
    text: str,
    body_font,
    emph_font,
    max_lines: int,
    emphasis: set[str],
    tracking_px: float,
) -> list[str]:
    """Use as many lines as allowed (one word minimum each), minimising the widest line."""
    words = (text or "").strip().split()
    if not words:
        return []
    n_lines = min(max_lines, len(words))
    best: tuple[float, list[str]] | None = None
    for cuts in combinations(range(1, len(words)), n_lines - 1):
        bounds = (0, *cuts, len(words))
        lines = [words[bounds[i]:bounds[i + 1]] for i in range(n_lines)]
        widest = max(_line_width(ln, body_font, emph_font, emphasis, tracking_px) for ln in lines)
        if best is None or widest < best[0]:
            best = (widest, [" ".join(ln) for ln in lines])
    return best[1] if best else []


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
    nominal = int(zone.get("max_font_px") or _font_nominal_size(brand_id, role, zone_h))
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
            wrap_mode = str(zone.get("wrap") or "")
            if wrap_mode == "balanced":
                lines = _wrap_balanced(text, body, emph, max_lines, emphasis, track)
            elif wrap_mode == "explicit":
                lines = _wrap_explicit(text, max_lines)
            else:
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
    stroke_width: int = 0,
    stroke_fill=None,
) -> float:
    if not text:
        return x
    stroke = {"stroke_width": stroke_width, "stroke_fill": stroke_fill} if stroke_width > 0 else {}
    if tracking_px <= 0:
        draw.text((x, baseline), text, font=font, fill=fill, anchor="ls", **stroke)
        return x + _run_length(text, font, 0.0)
    cx = x
    for i, ch in enumerate(text):
        draw.text((cx, baseline), ch, font=font, fill=fill, anchor="ls", **stroke)
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
    stroke_width: int = 0,
    stroke_fill=None,
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
        x = _draw_tracked_run(draw, x, baseline, word, font, fill, tracking_px, stroke_width, stroke_fill)
        if wi < len(words) - 1:
            x = _draw_tracked_run(draw, x, baseline, " ", body_font, fill, 0.0)


def _zone_colour(zone: dict[str, Any], brand_id: str, text: str, fields: dict[str, str]) -> tuple[int, int, int, int]:
    options = zone.get("colour_options")
    if isinstance(options, list) and options:
        picked = str(fields.get("accent") or "").strip()
        if picked not in options:
            picked = str(options[zlib.crc32(text.upper().encode("utf-8")) % len(options)])
        return _palette_colour(picked, brand_id)
    return _palette_colour(str(zone.get("colour") or "white"), brand_id)


def _draw_text_zone(
    draw,
    *,
    zone: dict[str, Any],
    text: str,
    brand_id: str,
    canvas_w: int,
    canvas_h: int,
    base_canvas_h: int = 1350,
    base=None,
    fields: dict[str, str] | None = None,
    anchor_bottom: int | None = None,
) -> tuple[int, int]:
    """Draw a text zone; returns the (top, bottom) pixel rows of the drawn block."""
    _require_raqm()
    rect = zone.get("rect") if isinstance(zone.get("rect"), dict) else {}
    x0, y0, x1, y1 = _rect_px(rect, canvas_w, canvas_h)
    role = str(zone.get("font_role") or "body")
    min_px = int(zone.get("min_font_px") or 12)
    if base_canvas_h > 0 and canvas_h < base_canvas_h:
        min_px = max(10, int(min_px * canvas_h / base_canvas_h))
    text = _apply_text_transform(text, zone)
    colour = _zone_colour(zone, brand_id, text, fields or {})
    h_scale = float(zone.get("h_scale") or 1.0)
    echo = zone.get("echo") if isinstance(zone.get("echo"), dict) else None
    layered = base is not None and (h_scale != 1.0 or echo is not None)
    zone_w = x1 - x0
    zone_h = y1 - y0
    origin_x = float(zone.get("text_origin_x") or x0)
    wrap_x1 = zone.get("wrap_x1")
    if wrap_x1 is not None:
        wrap_w = max(zone_w, int(float(wrap_x1) * canvas_w) - int(origin_x))
    else:
        wrap_w = zone_w
    if layered:
        wrap_w = int(wrap_w / h_scale)
        if echo is not None:
            nominal = int(zone.get("max_font_px") or _font_nominal_size(brand_id, role, zone_h))
            wrap_w -= int(abs(float(echo.get("dx_em") or 0.0)) * nominal)
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
    if anchor_bottom is not None:
        y_base = anchor_bottom - block_h
    elif valign in ("center", "middle"):
        y_base = y0 + (zone_h - block_h) // 2
    elif valign == "bottom":
        y_base = y1 - block_h
    tracking_px = _tracking_px(zone, size)
    emphasis = _emphasis_words(zone)
    align = str(zone.get("align") or "left")
    inline = zone.get("inline_asset") if isinstance(zone.get("inline_asset"), dict) else None
    if inline is not None and align == "center" and len(lines) == 1:
        line_w = _line_width(lines[0].split(), body_font, emph_font, emphasis, tracking_px)
        th = int(inline.get("height_px") or 63)
        gap = int(inline.get("gap_px") or 0)
        from _lib.brand_overlay import _resolve_brand_relative

        path = _resolve_brand_relative(brand_id, str(inline.get("asset") or ""))
        asset_w = 0
        if path is not None:
            probe = _load_image(path)
            if probe is not None:
                asset_w = max(1, int(probe.width * th / max(1, probe.height)))
        scaled_text_w = int(line_w * h_scale)
        total = scaled_text_w + gap + asset_w
        start_x = int((canvas_w - total) / 2)
        baseline = y_base + cap
        if layered and base is not None:
            layer_w = int(canvas_w / min(1.0, h_scale)) + 1
            layer = Image.new("RGBA", (layer_w, canvas_h), (0, 0, 0, 0))
            target = ImageDraw.Draw(layer)
            _draw_line_mixed(
                target,
                float(start_x),
                baseline,
                lines[0],
                body_font,
                emph_font,
                emphasis,
                colour,
                tracking_px,
                "left",
                start_x,
                start_x + int(line_w),
            )
            if h_scale != 1.0:
                scaled = layer.resize((max(1, int(layer_w * h_scale)), canvas_h), Image.LANCZOS)
                layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
                layer.paste(scaled, (0, 0))
            else:
                layer = layer.crop((0, 0, canvas_w, canvas_h))
            base.paste(layer, (0, 0), layer)
        else:
            _draw_line_mixed(
                draw,
                start_x,
                baseline,
                lines[0],
                body_font,
                emph_font,
                emphasis,
                colour[:3],
                tracking_px,
                "left",
                start_x,
                start_x + int(line_w),
            )
        _paste_inline_asset(
            base,
            brand_id=brand_id,
            zone=zone,
            x=start_x + scaled_text_w,
            text_cap_y=y_base,
            text_cap_h=cap,
        )
        return int(y_base), int(y_base + block_h)

    layer_w = int(canvas_w / min(1.0, h_scale)) + 1
    layer = Image.new("RGBA", (layer_w, canvas_h), (0, 0, 0, 0)) if layered else None
    target = ImageDraw.Draw(layer) if layer is not None else draw
    for i, line in enumerate(lines):
        baseline = y_base + cap + i * pitch
        if echo is not None and layer is not None:
            shadow_a = int(float(echo.get("shadow_alpha", 0.6)) * 255)
            _draw_line_mixed(
                target,
                origin_x + float(echo.get("dx_em") or 0.0) * size,
                baseline + float(echo.get("dy_em") or 0.0) * size,
                line,
                body_font,
                emph_font,
                emphasis,
                (0, 0, 0, shadow_a),
                tracking_px,
                align,
                x0,
                x1,
                stroke_width=max(1, round(float(echo.get("stroke_em") or 0.01) * size)),
                stroke_fill=colour,
            )
        _draw_line_mixed(
            target,
            origin_x,
            baseline,
            line,
            body_font,
            emph_font,
            emphasis,
            colour if layer is not None else colour[:3],
            tracking_px,
            align,
            x0,
            x1,
        )
    if layer is not None:
        if h_scale != 1.0:
            pivot = origin_x if align == "left" else (x0 + x1) / 2
            scaled = layer.resize((max(1, int(layer_w * h_scale)), canvas_h), Image.LANCZOS)
            layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            layer.paste(scaled, (int(round(pivot - pivot * h_scale)), 0))
        base.paste(layer, (0, 0), layer.crop((0, 0, canvas_w, canvas_h)))
    return int(y_base), int(y_base + block_h)


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


def _paste_brand_asset(
    base,
    brand_id: str,
    zone: dict[str, Any],
    *,
    mirror_x: bool = False,
    align_override: str | None = None,
) -> None:
    from _lib.brand_overlay import _resolve_brand_relative

    rel = zone.get("asset")
    if not isinstance(rel, str) or not rel.strip():
        raise ComposeError("missing zone asset")
    path = _resolve_brand_relative(brand_id, rel)
    if path is None:
        raise ComposeError(f"missing asset {rel}")
    img = _load_image(path)
    if img is None:
        raise ComposeError(f"missing asset {rel}")
    rect = zone.get("rect") if isinstance(zone.get("rect"), dict) else {}
    x0, y0, x1, y1 = _rect_px(rect, base.width, base.height)
    zone_w = x1 - x0
    zone_h = y1 - y0
    fit = str(zone.get("fit") or "aspect_fit").lower()
    align = str(align_override or zone.get("align") or "left").lower()
    if mirror_x:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
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
        c0 = _palette_colour(str(grad.get("from") or "#000000"), brand_id)
        c1 = _palette_colour(str(grad.get("to") or "#FFFFFF"), brand_id)
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


_PHOTO_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")


def _library_photo(brand_id: str, rel_dir: str, seed: str):
    rel = rel_dir.strip().strip("/")
    for d in _candidate_brand_dirs(brand_id):
        folder = d / rel
        if not folder.is_dir():
            continue
        files = sorted(p for p in folder.iterdir() if p.suffix.lower() in _PHOTO_SUFFIXES)
        if files:
            return _load_image(files[zlib.crc32(seed.encode("utf-8")) % len(files)])
    return None


def _photo_cover_background(base, archetype: dict[str, Any], brand_id: str, photo_bytes: bytes | None, seed: str) -> None:
    """Full-bleed photo, centre-cropped to cover the canvas, then the scrim darkening."""
    bg = archetype.get("background") if isinstance(archetype.get("background"), dict) else {}
    photo = _load_image_from_bytes(photo_bytes) if photo_bytes else None
    library = bg.get("library")
    if photo is None and isinstance(library, str) and library.strip():
        photo = _library_photo(brand_id, library, seed)
    if photo is None:
        raise ComposeError("missing background photo")
    w, h = base.size
    scale = max(w / photo.width, h / photo.height)
    pw, ph = max(w, round(photo.width * scale)), max(h, round(photo.height * scale))
    photo = photo.convert("RGB").resize((pw, ph), Image.LANCZOS)
    focus_y = float(bg.get("focus_y", 0.5))
    left = (pw - w) // 2
    top = int(round((ph - h) * min(1.0, max(0.0, focus_y))))
    base.paste(photo.crop((left, top, left + w, top + h)), (0, 0))
    scrim = bg.get("scrim") if isinstance(bg.get("scrim"), dict) else None
    if scrim is None:
        return
    x0, y0, x1, y1 = _rect_px(scrim.get("rect") or {"x0": 0, "y0": 0, "x1": 1, "y1": 1}, w, h)
    a0 = float(scrim.get("from_alpha", 0.6))
    a1 = float(scrim.get("to_alpha", a0))
    shade = Image.new("L", (1, max(1, y1 - y0)))
    for y in range(shade.height):
        t = y / max(1, shade.height - 1)
        shade.putpixel((0, y), int(255 * (a0 * (1 - t) + a1 * t)))
    mask = shade.resize((x1 - x0, y1 - y0))
    base.paste((0, 0, 0), (x0, y0, x1, y1), mask)


def _draw_frame(base, zone: dict[str, Any], brand_id: str) -> None:
    w, h = base.size
    inset = int(zone.get("inset_px") or 0)
    inset_x = int(zone.get("inset_x_px") if zone.get("inset_x_px") is not None else inset)
    inset_y = int(zone.get("inset_y_px") if zone.get("inset_y_px") is not None else inset)
    stroke = int(zone.get("stroke_px") or 4)
    colour = _palette_colour(str(zone.get("colour") or "white"), brand_id)
    alpha = int(float(zone.get("alpha", 1.0)) * 255)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rectangle(
        [inset_x, inset_y, w - 1 - inset_x, h - 1 - inset_y],
        outline=colour[:3] + (alpha,),
        width=stroke,
    )
    base.paste(layer, (0, 0), layer)


def _draw_rule(base, zone: dict[str, Any], brand_id: str) -> None:
<<<<<<< HEAD
    w, h = base.size
    rect = zone.get("rect") if isinstance(zone.get("rect"), dict) else {}
    x0, y0, x1, y1 = _rect_px(rect, w, h)
    colour = _palette_colour(str(zone.get("colour") or "white"), brand_id)
    alpha = int(float(zone.get("alpha", 1.0)) * 255)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rectangle([x0, y0, x1, y1], fill=colour[:3] + (alpha,))
=======
    rect = zone.get("rect") if isinstance(zone.get("rect"), dict) else {}
    x0, y0, x1, y1 = _rect_px(rect, *base.size)
    stroke = int(zone.get("stroke_px") or 2)
    colour = _palette_colour(str(zone.get("colour") or "white"), brand_id)
    alpha = int(float(zone.get("alpha", 1.0)) * 255)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rectangle(
        [x0, y0, x1 - 1, y0 + stroke - 1],
        fill=colour[:3] + (alpha,),
    )
>>>>>>> origin/feat/stick-statement-template
    base.paste(layer, (0, 0), layer)


def _uses_photo_cover(archetype: dict[str, Any]) -> bool:
    bg = archetype.get("background") if isinstance(archetype.get("background"), dict) else {}
    return str(bg.get("kind") or "") == "photo_full_bleed" and bool(bg.get("cover"))


def _content_for_source(source: str, fields: dict[str, str], zone: dict[str, Any]) -> str:
    if source == "static":
        return str(zone.get("text") or "")
    if source == "caption_hook_first_word":
        hook = str(fields.get("caption_hook") or "").strip()
        return hook.split(None, 1)[0] if hook else ""
    if source == "caption_hook_tail":
        hook = str(fields.get("caption_hook") or "").strip()
        parts = hook.split(None, 1)
        return parts[1] if len(parts) > 1 else ""
    val = fields.get(source) or ""
    text = str(val)
    suffix = zone.get("text_suffix")
    if suffix is not None and str(suffix):
        text = f"{text}{suffix}"
    return text


def _paste_inline_asset(
    base,
    *,
    brand_id: str,
    zone: dict[str, Any],
    x: int,
    text_cap_y: int,
    text_cap_h: int,
) -> None:
    inline = zone.get("inline_asset") if isinstance(zone.get("inline_asset"), dict) else None
    if inline is None:
        return
    from _lib.brand_overlay import _resolve_brand_relative

    rel = inline.get("asset")
    if not isinstance(rel, str) or not rel.strip():
        return
    path = _resolve_brand_relative(brand_id, rel)
    if path is None:
        raise ComposeError(f"missing inline asset {rel}")
    img = _load_image(path)
    if img is None:
        raise ComposeError(f"missing inline asset {rel}")
    gap = int(inline.get("gap_px") or 0)
    th = int(inline.get("height_px") or img.height)
    scale = th / max(1, img.height)
    tw = max(1, int(img.width * scale))
    img = img.resize((tw, th), Image.LANCZOS)
    py = text_cap_y + (text_cap_h - th) // 2
    base.paste(img, (x + gap, py), img if img.mode == "RGBA" else None)


def _compose_variant(fields: dict[str, str]) -> str:
    explicit = str(fields.get("variant") or "").strip().lower()
    if explicit in ("lab", "avoda"):
        return explicit
    cat = str(fields.get("service_category") or "").upper()
    if cat in ("AVODA", "WORKSHOP"):
        return "avoda"
    return "lab"


def _zone_variant_ok(zone: dict[str, Any], variant: str) -> bool:
    want = zone.get("variant")
    if want is None or want == "":
        return True
    return str(want).strip().lower() == variant


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
    if str(archetype.get("id") or "") == "stick-location-drive":
        from _lib.stick_location_drive import compose_stick_location_drive  # noqa: PLC0415

        canvases = doc.get("canvases") if isinstance(doc.get("canvases"), dict) else {}
        spec = canvases.get(canvas_id)
        if not isinstance(spec, dict):
            raise ComposeError(f"unknown canvas {canvas_id}")
        w = int(spec.get("w") or 1080)
        h = int(spec.get("h") or 1350)
        return compose_stick_location_drive(
            brand_id=brand_id,
            archetype=archetype,
            canvas_w=w,
            canvas_h=h,
            fields=fields,
            photo_bytes=photo_bytes,
        )
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
    variant = _compose_variant(fields)
    base = Image.new("RGB", (w, h), (7, 60, 82))
    bg_kind = str((archetype.get("background") or {}).get("kind") or "")
    photo_cover = _uses_photo_cover(archetype)
    if photo_cover:
        seed = str(fields.get("photo_seed") or fields.get("caption_hook") or "")
        _photo_cover_background(base, archetype, brand_id, photo_bytes, seed)
    elif bg_kind != "photo_full_bleed" or not photo_bytes:
        _background(base, archetype, brand_id)
    draw = ImageDraw.Draw(base)
    text_blocks: dict[str, tuple[int, int]] = {}
    ordered = sorted(
        ((zid, z) for zid, z in zones.items() if isinstance(z, dict)),
        key=lambda item: 1 if isinstance(item[1].get("attach_above"), dict) else 0,
    )
    for zid, zone in ordered:
        if not _zone_variant_ok(zone, variant):
            continue
        kind = str(zone.get("kind") or "")
        if kind == "decorative":
            shape = str(zone.get("shape") or "")
            if shape == "frame":
                _draw_frame(base, zone, brand_id)
            elif shape == "rule":
                _draw_rule(base, zone, brand_id)
            draw = ImageDraw.Draw(base)
        elif kind == "decorative" and str(zone.get("shape") or "") == "rule":
            _draw_rule(base, zone, brand_id)
            draw = ImageDraw.Draw(base)
        elif kind == "band":
            rect = zone.get("rect") if isinstance(zone.get("rect"), dict) else {}
            x0, y0, x1, y1 = _rect_px(rect, w, h)
            fill = _palette_colour(str(zone.get("fill") or "teal"), brand_id)
            draw.rectangle([x0, y0, x1, y1], fill=fill[:3])
        elif kind == "image":
            source = str(zone.get("source") or "")
            rect = zone.get("rect") if isinstance(zone.get("rect"), dict) else {}
            if source == "photo" and photo_cover:
                continue
            if source == "photo":
                if photo_bytes:
                    _paste_photo(base, photo_bytes, rect)
                elif not zone.get("optional"):
                    raise ComposeError("missing photo")
            elif source == "asset":
                try:
                    paste_zone = zone
                    mirror = variant == "avoda" and isinstance(zone.get("mirror_corners"), list)
                    if mirror and isinstance(rect, dict):
                        paste_zone = dict(zone)
                        paste_zone["rect"] = {
                            "x0": 1.0 - float(rect["x1"]),
                            "y0": float(rect["y0"]),
                            "x1": 1.0 - float(rect["x0"]),
                            "y1": float(rect["y1"]),
                        }
                    _paste_brand_asset(
                        base,
                        brand_id,
                        paste_zone,
                        mirror_x=mirror,
                        align_override="right" if mirror else None,
                    )
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
            anchor_bottom = None
            attach = zone.get("attach_above") if isinstance(zone.get("attach_above"), dict) else None
            if attach is not None:
                above = text_blocks.get(str(attach.get("zone") or ""))
                if above is None:
                    raise ComposeError(f"zone {zid} attaches to a missing text zone")
                anchor_bottom = above[0] - int(attach.get("gap_px") or 0)
            text_blocks[zid] = _draw_text_zone(
                draw,
                zone=zone,
                text=text,
                brand_id=brand_id,
                canvas_w=w,
                canvas_h=h,
                base_canvas_h=base_h,
                base=base,
                fields=fields,
                anchor_bottom=anchor_bottom,
            )
            draw = ImageDraw.Draw(base)
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
    allowed = (archetype.get("applies_to") or {}).get("channels")
    channel_canvas = archetype.get("channel_canvas") if isinstance(archetype.get("channel_canvas"), dict) else {}
    canvases = doc.get("canvases") if isinstance(doc.get("canvases"), dict) else {}
    for channel in channels:
        if isinstance(allowed, list) and allowed and channel not in allowed:
            continue
        if channel in channel_canvas and channel_canvas[channel] in canvases:
            canvas_id = str(channel_canvas[channel])
        else:
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
