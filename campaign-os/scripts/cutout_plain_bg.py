#!/usr/bin/env python3
"""Cut a product off a plain studio background (maker pack shots on white or light grey).

Only the background connected to the image edges is removed, so white parts of the
product (a ball, a white box panel) stay. Pillow only. The product pixels are not
changed; check the result on a dark background before using it.

    python campaign-os/scripts/cutout_plain_bg.py in.jpg out.png [--tolerance 6] [--preview]

Use it for the stick-product-post template (maker stack), which takes a transparent
cut-out. Photos that already have transparency (Vice, Takomo, L.A.B.) need no cut.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SENTINEL = (255, 0, 255)


def cutout(src: Image.Image, tolerance: int = 6) -> Image.Image:
    rgb = src.convert("RGB")
    marked = rgb.copy()
    w, h = rgb.size
    for xy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if marked.getpixel(xy) != SENTINEL:
            ImageDraw.floodfill(marked, xy, SENTINEL, thresh=tolerance)
    r, g, b = marked.split()
    is_bg = Image.merge("RGB", (r.point(lambda v: 255 if v == 255 else 0),
                                g.point(lambda v: 255 if v == 0 else 0),
                                b.point(lambda v: 255 if v == 255 else 0))).convert("L").point(lambda v: 255 if v == 255 else 0)
    alpha = is_bg.point(lambda v: 0 if v else 255).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.0))
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    box = alpha.point(lambda v: 255 if v > 60 else 0).getbbox()
    return out.crop(box) if box else out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--tolerance", type=int, default=6, help="how far a pixel may be from the edge colour (0-255)")
    ap.add_argument("--preview", action="store_true", help="also write <out>-preview.jpg on Stick navy")
    a = ap.parse_args()
    im = cutout(Image.open(a.src), a.tolerance)
    im.save(a.out)
    if a.preview:
        bg = Image.new("RGBA", im.size, (7, 41, 61, 255))
        bg.alpha_composite(im)
        bg.convert("RGB").save(str(Path(a.out).with_suffix("")) + "-preview.jpg", quality=85)
    print(f"{a.out} {im.size[0]}x{im.size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
