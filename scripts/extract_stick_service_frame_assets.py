#!/usr/bin/env python3
"""Extract stick wordmark + tagline PNGs from swingasses.jpg (deterministic)."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

NAVY = (7, 60, 82)  # brand navy_deep #073C52
NAVY_TOL = 36
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/brand-directory/stick/images/Services/swingasses.jpg"
LOGO_OUT = ROOT / "data/brand-directory/stick/logo.png"
TAGLINE_OUT = ROOT / "data/brand-directory/stick/images/tagline-light.png"
TEMPLATE_ASSETS = ROOT / "data/brand-directory/stick/templates/service-frame/assets"


def _navy_key(img: Image.Image) -> Image.Image:
    rgb = img.convert("RGB")
    w, h = rgb.size
    out = Image.new("RGBA", rgb.size, (0, 0, 0, 0))
    px = rgb.load()
    ap = out.load()
    nr, ng, nb = NAVY
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            dist = abs(r - nr) + abs(g - ng) + abs(b - nb)
            if r > 200 and g > 200 and b > 200:
                ap[x, y] = (255, 255, 255, 255)
            elif dist <= NAVY_TOL:
                ap[x, y] = (0, 0, 0, 0)
            else:
                ap[x, y] = (r, g, b, 255)
    return out


def _crop_rgba(src: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    return src.crop(box)


def main() -> int:
    if not SOURCE.exists():
        print(f"missing source {SOURCE}", file=sys.stderr)
        return 1
    img = Image.open(SOURCE).convert("RGB")
    # Crops from plan §1.4 (1080×1350 swingasses.jpg)
    wordmark = _crop_rgba(img, (135, 1114, 374, 1199))
    tagline = _crop_rgba(img, (465, 1126, 943, 1196))
    wordmark = _navy_key(wordmark)
    tagline = _navy_key(tagline)
    LOGO_OUT.parent.mkdir(parents=True, exist_ok=True)
    TAGLINE_OUT.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATE_ASSETS.mkdir(parents=True, exist_ok=True)
    png_opts = {"compress_level": 0}
    wordmark.save(LOGO_OUT, format="PNG", **png_opts)
    tagline.save(TAGLINE_OUT, format="PNG", **png_opts)
    wordmark.save(TEMPLATE_ASSETS / "logo-wordmark-white.png", format="PNG", **png_opts)
    tagline.save(TEMPLATE_ASSETS / "tagline-better-begins-here.png", format="PNG", **png_opts)
    print(f"wrote {LOGO_OUT} ({LOGO_OUT.stat().st_size} bytes)")
    print(f"wrote {TAGLINE_OUT} ({TAGLINE_OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
