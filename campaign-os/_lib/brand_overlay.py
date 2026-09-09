"""
brand_overlay.py — Deterministic post-composition for AI-generated images.

AI image models hallucinate logos + brand typography. This module
overlays the REAL brand logo + canonical brand fonts + a supplied
headline / CTA on top of the AI output, so the final composition is
publish-ready instead of "AI generated this, now we need a designer".

Three entry points:
  - overlay_logo_only(image_bytes, brand_id, position) -> PNG bytes
  - overlay_brand_text(image_bytes, brand_id, headline, cta) -> PNG bytes
  - overlay_post(image_bytes, brand_id, headline, subhead, cta) -> PNG bytes

All operations use Pillow (PIL.Image, ImageDraw, ImageFont). They are
deterministic — same inputs always produce same pixels. Safe to cache.

For brand fonts, the module reads:
  data/brand-directory/<brand>/typography/fonts.json
which the operator populates with brand font names + asset paths.

For brand logos, the module looks up:
  data/brand-directory/<brand>/logo.png  OR
  data/brand-directory/<brand>/assets/logo.png
If neither exists, the logo step is skipped silently — the AI image
is returned unchanged.
"""
from __future__ import annotations

import io
import json
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except Exception:
    Image = ImageDraw = ImageFont = ImageFilter = None  # type: ignore

_LOG = logging.getLogger("campaign_os.brand_overlay")

DEFAULT_PADDING = 32
HEADLINE_FALLBACK_FONT_SIZE = 64
SUBHEADLINE_FALLBACK_FONT_SIZE = 32
CTA_FALLBACK_FONT_SIZE = 28


# ── Brand asset paths ─────────────────────────────────────────────────
def _candidate_brand_dirs(brand_id: str) -> list:
    """Return likely on-disk brand directories in priority order."""
    return [
        Path(f"/data/campaign-os/brand-directory/{brand_id}"),
        Path(f"/data/campaign-os/{brand_id}"),
        Path(
            f"/Users/fivefriday/.openclaw-instance2/workspace/"
            f"swing-shack-dashboard/data/brand-directory/{brand_id}"
        ),
    ]


def _find_logo(brand_id: str) -> Optional[Path]:
    """Find the canonical brand logo. Returns None if not found."""
    candidates = [
        "logo.png", "logo.svg", "logo.jpg",
        "assets/logo.png", "brand-logo.png",
    ]
    for d in _candidate_brand_dirs(brand_id):
        if not d.exists():
            continue
        for name in candidates:
            p = d / name
            if p.exists():
                return p
    return None


def _find_fonts(brand_id: str) -> dict:
    """Read typography/fonts.json. Returns empty dict if missing."""
    for d in _candidate_brand_dirs(brand_id):
        fp = d / "typography" / "fonts.json"
        if fp.exists():
            try:
                return json.loads(fp.read_text())
            except Exception:
                continue
    return {}


def _find_color_palette(brand_id: str) -> dict:
    """Read palette/brand.json. Returns empty dict if missing."""
    for d in _candidate_brand_dirs(brand_id):
        fp = d / "palette" / "brand.json"
        if fp.exists():
            try:
                return json.loads(fp.read_text())
            except Exception:
                continue
    return {}


def _load_image(path: Path):
    if Image is None or not path.exists():
        return None
    try:
        return Image.open(path).convert("RGBA")
    except Exception as e:
        _LOG.warning(f"could not open {path}: {e}")
        return None


def _hex_to_rgba(hexstr: str, alpha: int = 255):
    h = hexstr.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4)) + (alpha,)
    except Exception:
        return (255, 255, 255, alpha)


def _load_font(font_path: Optional[str], size: int):
    if not font_path or ImageFont is None:
        return ImageFont.load_default() if ImageFont else None
    try:
        if Path(font_path).exists():
            return ImageFont.truetype(font_path, size=size)
    except Exception:
        pass
    for path in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default() if ImageFont else None


def _load_image_from_bytes(image_bytes: bytes):
    if Image is None or not image_bytes:
        return None
    try:
        return Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    except Exception:
        return None


def _to_png_bytes(im) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def overlay_logo_only(image_bytes: bytes, brand_id: str, position: str = "bottom-right") -> bytes:
    """Overlay just the brand logo on top of the image. Returns PNG bytes."""
    if Image is None:
        return image_bytes
    base = _load_image_from_bytes(image_bytes)
    if base is None:
        return image_bytes
    logo_path = _find_logo(brand_id)
    if not logo_path:
        return image_bytes
    logo = _load_image(logo_path)
    if logo is None:
        return image_bytes
    # Scale logo to ~20% of base width
    target_w = max(64, int(base.width * 0.2))
    aspect = logo.height / max(1, logo.width)
    target_h = int(target_w * aspect)
    logo = logo.resize((target_w, target_h), Image.LANCZOS)
    # Position
    if position == "top-left":
        x, y = DEFAULT_PADDING, DEFAULT_PADDING
    elif position == "top-right":
        x = base.width - target_w - DEFAULT_PADDING
        y = DEFAULT_PADDING
    elif position == "bottom-left":
        x = DEFAULT_PADDING
        y = base.height - target_h - DEFAULT_PADDING
    elif position == "center":
        x = (base.width - target_w) // 2
        y = (base.height - target_h) // 2
    else:  # bottom-right default
        x = base.width - target_w - DEFAULT_PADDING
        y = base.height - target_h - DEFAULT_PADDING
    base.paste(logo, (x, y), logo if logo.mode == "RGBA" else None)
    return _to_png_bytes(base)


def overlay_brand_text(image_bytes: bytes, brand_id: str, headline: str, cta: str = "") -> bytes:
    """Overlay real brand fonts + a headline + optional CTA. Returns PNG bytes."""
    if Image is None:
        return image_bytes
    base = _load_image_from_bytes(image_bytes)
    if base is None:
        return image_bytes
    fonts = _find_fonts(brand_id)
    palette = _find_color_palette(brand_id)
    # Choose colours
    text_color = (255, 255, 255, 255)
    accent_color = (255, 200, 50, 255)
    if palette:
        accent = palette.get("accent", {})
        if isinstance(accent, dict) and "hex" in accent:
            accent_color = _hex_to_rgba(accent["hex"], 255)
        text = palette.get("text", {})
        if isinstance(text, dict) and "hex" in text:
            text_color = _hex_to_rgba(text["hex"], 255)
    headline_font_path = fonts.get("headline") if isinstance(fonts, dict) else None
    cta_font_path = fonts.get("cta") if isinstance(fonts, dict) else None
    headline_font = _load_font(headline_font_path, HEADLINE_FALLBACK_FONT_SIZE)
    cta_font = _load_font(cta_font_path, CTA_FALLBACK_FONT_SIZE)
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # Headline — lower-third area, centred
    headline_y = int(base.height * 0.78)
    headline_bbox = draw.textbbox((0, 0), headline, font=headline_font)
    headline_w = headline_bbox[2] - headline_bbox[0]
    headline_h = headline_bbox[3] - headline_bbox[1]
    headline_x = (base.width - headline_w) // 2
    # Dark gradient underlay for readability
    grad_h = int(headline_h * 2.5)
    grad = Image.new("RGBA", (base.width, grad_h), (0, 0, 0, 0))
    for y in range(grad_h):
        alpha = int(180 * (y / grad_h))
        draw_g = ImageDraw.Draw(grad)
        draw_g.line([(0, y), (base.width, y)], fill=(0, 0, 0, alpha))
    base.paste(grad, (0, headline_y - grad_h // 3), grad)
    # Headline text
    draw.text(
        (headline_x, headline_y), headline,
        font=headline_font, fill=text_color,
    )
    # CTA
    if cta:
        cta_y = headline_y + headline_h + 16
        cta_bbox = draw.textbbox((0, 0), cta, font=cta_font)
        cta_w = cta_bbox[2] - cta_bbox[0]
        cta_h = cta_bbox[3] - cta_bbox[1]
        cta_x = (base.width - cta_w) // 2
        pad = 12
        draw.rectangle(
            [cta_x - pad, cta_y - pad // 2, cta_x + cta_w + pad, cta_y + cta_h + pad // 2],
            fill=accent_color,
        )
        draw.text(
            (cta_x, cta_y), cta,
            font=cta_font, fill=(0, 0, 0, 255),
        )
    base = Image.alpha_composite(base.convert("RGBA"), overlay)
    return _to_png_bytes(base)


def overlay_post(
    image_bytes: bytes,
    brand_id: str,
    *,
    headline: str,
    subhead: str = "",
    cta: str = "",
) -> bytes:
    """Composite: headline + optional subhead + CTA + brand logo (if exists)."""
    if Image is None:
        return image_bytes
    composed = overlay_brand_text(image_bytes, brand_id, headline, cta)
    composed = overlay_logo_only(composed, brand_id, position="bottom-right")
    return composed