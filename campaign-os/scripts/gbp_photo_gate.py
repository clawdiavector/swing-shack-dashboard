"""Quality gate for photos going on Google Business posts.

Checks a finished photo (after the Topaz Standard enhance and grade in
runbooks/enhance-real-product-photos) and prints PASS or the reasons it fails.

PASS only means no technical fault was found. It cannot see lens flare, haze,
a backlit room or shrink-wrap reflections: on 2026-10-21 a flared simulator
photo and a backlit entrance both passed. Open every photo at full size and
look at it before it goes on a draft.

    python campaign-os/scripts/gbp_photo_gate.py photo1.jpg photo2.jpg
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageFilter, ImageStat

MIN_LONG_SIDE = 1600
MIN_SHORT_SIDE = 1000
MAX_BYTES = 8 * 1024 * 1024
MEAN_RANGE = (85, 170)
MAX_CLIPPED = 0.02
MIN_SHARPNESS = 500
MAX_BLACK_LEVEL = 45  # 5th percentile brightness; above this the shadows are lifted (haze or backlight)
EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def check(path: str) -> list[str]:
    fails: list[str] = []
    if os.path.splitext(path)[1].lower() not in EXTENSIONS:
        return ["not_jpg_png_or_webp"]
    if os.path.getsize(path) > MAX_BYTES:
        fails.append("over_8mb")
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        if max(w, h) < MIN_LONG_SIDE or min(w, h) < MIN_SHORT_SIDE:
            fails.append(f"too_small_{w}x{h}")
        g = im.convert("L")
        g.thumbnail((1000, 1000))
        mean = ImageStat.Stat(g).mean[0]
        if not MEAN_RANGE[0] <= mean <= MEAN_RANGE[1]:
            fails.append(f"exposure_{mean:.0f}")
        px = g.size[0] * g.size[1]
        hist = g.histogram()
        if sum(hist[250:]) / px > MAX_CLIPPED:
            fails.append("blown_highlights")
        if sum(hist[:6]) / px > MAX_CLIPPED * 2:
            fails.append("crushed_shadows")
        cum, p5 = 0, 0
        for i, c in enumerate(hist):
            cum += c
            if cum >= px * 0.05:
                p5 = i
                break
        if p5 > MAX_BLACK_LEVEL:
            fails.append(f"lifted_blacks_{p5}")
        sharp = ImageStat.Stat(g.filter(ImageFilter.FIND_EDGES)).var[0]
        if sharp < MIN_SHARPNESS:
            fails.append(f"soft_{sharp:.0f}")
    return fails


def main(paths: list[str]) -> int:
    bad = 0
    for p in paths:
        fails = check(p)
        bad += bool(fails)
        print(f"{'PASS' if not fails else 'FAIL'}  {os.path.basename(p)}  {', '.join(fails)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
