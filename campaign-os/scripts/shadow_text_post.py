#!/usr/bin/env python3
"""Put brand text inside a photo's own shadows (the "shadow text" layout).

Made for hard-light product photos (for example a Krea flat-lay with a
diagonal window shadow). The script finds the dark areas in two opposite
corners, then fits each text block inside them:

  - top block, right-aligned in the top-right shadow: the long line first
    (where a diagonal shadow is widest), the short line under it;
  - bottom block, left-aligned in the bottom-left shadow: the short lines
    first, the long line last.

Every line is measured against the shadow edge and shrunk until it fits, so
no text sits on a lit area. A light darkening inside each shadow keeps the
text readable. No numpy: Pillow only.

    python3 campaign-os/scripts/shadow_text_post.py photo.jpg out.jpg \\
        --brand stick --top "POLO SEASON." --top-sub "PSYCHO BUNNY" \\
        --bottom-lead "AVAILABLE @" --bottom "BLACK FRIDAY  ·  23–30 NOV"

Corners can be swapped with --top-corner left and --bottom-corner right.
The stick logo goes under --bottom-lead. Output is the photo's own size
(crop to 1080x1350 or 1200x900 first).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = Path(__file__).resolve().parents[2]
GREY = (210, 210, 210)  # Stick brand grey #D2D2D2 (designer palette), not the feed's mint
WHITE = (255, 255, 255)


def brand_dir(brand: str) -> Path:
    return REPO / "data" / "brand-directory" / brand


def font(brand: str, weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(brand_dir(brand) / "typography" / "fonts" / f"Montserrat-{weight}.ttf"), size)


def dark_runs(gray: Image.Image, threshold: int) -> list[tuple[int, int]]:
    """Per row: the dark span touching the left edge and the one touching the right edge."""
    w, h = gray.size
    px = gray.load()
    rows = []
    for y in range(h):
        x = 0
        while x < w and px[x, y] < threshold:
            x += 1
        left_end = x  # dark from 0 to left_end
        x = w - 1
        while x >= 0 and px[x, y] < threshold:
            x -= 1
        right_start = x + 1  # dark from right_start to w
        rows.append((left_end, right_start))
    return rows


def tracked_width(d: ImageDraw.ImageDraw, text: str, f, tracking: int) -> float:
    return sum(d.textlength(c, font=f) + tracking for c in text) - tracking


def draw_tracked(d, x, y, text, f, fill, tracking):
    for c in text:
        d.text((x, y), c, font=f, fill=fill)
        x += d.textlength(c, font=f) + tracking


def fits(rows, x0, x1, y0, y1, corner: str) -> bool:
    for y in range(max(0, y0), min(len(rows), y1)):
        left_end, right_start = rows[y]
        if corner == "right" and x0 < right_start:
            return False
        if corner == "left" and x1 > left_end:
            return False
    return True


def place(d, rows, text, weight, size, min_size, tracking, y, corner, margin, brand, w):
    """Shrink the line until it sits inside the shadow; returns (x, font, height)."""
    while size >= min_size:
        f = font(brand, weight, size)
        tw = tracked_width(d, text, f, tracking)
        top, bottom = f.getbbox(text)[1], f.getbbox(text)[3]
        x = w - margin - tw if corner == "right" else margin
        if fits(rows, int(x), int(x + tw), y + top, y + bottom, corner):
            return x, f, bottom
        size -= 2
    raise SystemExit(f"'{text}' does not fit in the {corner} shadow even at {min_size}px; "
                     "pick a photo with a wider shadow or a shorter line")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo")
    ap.add_argument("out")
    ap.add_argument("--brand", default="stick")
    ap.add_argument("--top", required=True, help="long line, white Montserrat Black")
    ap.add_argument("--top-sub", default="", help="short line under it, mint, tracked")
    ap.add_argument("--bottom-lead", default="AVAILABLE @", help="short line above the logo, white light")
    ap.add_argument("--bottom", required=True, help="long last line, mint light, tracked")
    ap.add_argument("--top-corner", choices=("right", "left"), default="right")
    ap.add_argument("--bottom-corner", choices=("left", "right"), default="left")
    ap.add_argument("--threshold", type=int, default=95, help="grey level counted as shadow (0-255)")
    ap.add_argument("--margin", type=int, default=60)
    a = ap.parse_args()

    im = Image.open(a.photo).convert("RGB")
    w, h = im.size
    k = w / 1080  # sizes below are for a 1080-wide post
    rows = dark_runs(im.convert("L"), a.threshold)

    # light darkening inside the shadows only, so the text reads
    shade = Image.new("L", (w, h), 0)
    sp = shade.load()
    for y, (left_end, right_start) in enumerate(rows):
        if y < h * 0.3:
            rng = range(right_start, w) if a.top_corner == "right" else range(0, left_end)
        elif y > h * 0.7:
            rng = range(0, left_end) if a.bottom_corner == "left" else range(right_start, w)
        else:
            continue
        for x in rng:
            sp[x, y] = 75
    shade = shade.filter(ImageFilter.GaussianBlur(30 * k))
    im = Image.composite(Image.new("RGB", (w, h), (0, 0, 0)), im, shade)
    d = ImageDraw.Draw(im)
    m = int(a.margin * k)

    # top block: long line first, short line under it
    y = int(34 * k)
    x, f, b = place(d, rows, a.top, "Black", int(66 * k), int(36 * k), 0, y, a.top_corner, m, a.brand, w)
    d.text((x, y), a.top, font=f, fill=WHITE)
    if a.top_sub:
        y = y + b + int(18 * k)
        x, f, _ = place(d, rows, a.top_sub, "ExtraBold", int(26 * k), int(18 * k), int(6 * k), y, a.top_corner, m, a.brand, w)
        draw_tracked(d, x, y, a.top_sub, f, GREY, int(6 * k))

    # bottom block: short lines first, long line last (laid out bottom-up)
    f_last = font(a.brand, "Light", int(30 * k))
    y_last = h - int(34 * k) - f_last.getbbox(a.bottom)[3]
    x, f, _ = place(d, rows, a.bottom, "Light", int(30 * k), int(18 * k), int(5 * k), y_last, a.bottom_corner, m, a.brand, w)
    draw_tracked(d, x, y_last, a.bottom, f, GREY, int(5 * k))
    logo = Image.open(brand_dir(a.brand) / "logos" / f"{a.brand}-logo-white.png").convert("RGBA")
    lw = int(160 * k)
    logo = logo.resize((lw, round(logo.height * lw / logo.width)), Image.LANCZOS)
    y_logo = y_last - int(22 * k) - logo.height
    lx = m if a.bottom_corner == "left" else w - m - lw
    if not fits(rows, lx, lx + lw, y_logo, y_logo + logo.height, a.bottom_corner):
        raise SystemExit("the logo does not fit in the bottom shadow")
    im.paste(logo, (lx, y_logo), logo)
    if a.bottom_lead:
        f_lead = font(a.brand, "Light", int(28 * k))
        y_lead = y_logo - int(12 * k) - f_lead.getbbox(a.bottom_lead)[3]
        x, f, _ = place(d, rows, a.bottom_lead, "Light", int(28 * k), int(18 * k), 0, y_lead, a.bottom_corner, m, a.brand, w)
        d.text((x, y_lead), a.bottom_lead, font=f, fill=WHITE)

    im.save(a.out, quality=93)
    print(f"ok  {a.out}  {w}x{h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
