#!/usr/bin/env python3
"""Check a carousel's slides together and make the two files a person needs to review it.

    python3 carousel_check.py 01.png 02.png 03.png --out out/

Slides are taken in the order given. Problems (exit 1):
  - fewer than 2 or more than 10 slides (2 to 10 is what the lodge will take, wiki T18);
  - any slide not 1080x1350. Instagram crops every slide to slide 1's shape, so one
    square slide in a 4:5 set loses its top and bottom;
  - a file name that doesn't start with its slide number (01_hero.png, 02_detail.png),
    so the order never depends on how names happen to sort.

Writes, problems or not:
  - contact-sheet.jpg: every slide in one numbered row, to look at the set as a whole;
  - gbp-slide-1.jpg: slide 1 at 1200x900 on a blurred copy of itself. A stopgap only:
    Google Business takes one image, and a recomposed 4:3 hero is better;
  - manifest.json: the slides in order, the contact sheet and the cover.

Pillow only. No model touches the pixels.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SLIDE = (1080, 1350)
GBP = (1200, 900)
THUMB = (360, 450)
GAP = 16
MIN_SLIDES, MAX_SLIDES = 2, 10


def problems(paths: list[Path]) -> list[str]:
    out = []
    if not MIN_SLIDES <= len(paths) <= MAX_SLIDES:
        out.append(f"{len(paths)} slide(s): a carousel takes 2 to 10")
    for n, p in enumerate(paths, 1):
        num = re.match(r"\d+", Path(p).name)
        if not num or int(num.group()) != n:
            out.append(f"slide {n} is named {Path(p).name}: name it {n:02d}_<role>.png so the order is in the name")
        with Image.open(p) as im:
            if im.size != SLIDE:
                out.append(f"slide {n} ({Path(p).name}) is {im.width}x{im.height}, not 1080x1350")
    return out


def contact_sheet(images: list[Image.Image]) -> Image.Image:
    w = len(images) * THUMB[0] + (len(images) + 1) * GAP
    sheet = Image.new("RGB", (w, THUMB[1] + 2 * GAP), (235, 235, 235))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=28)
    for n, im in enumerate(images, 1):
        x = GAP + (n - 1) * (THUMB[0] + GAP)
        sheet.paste(im.convert("RGB").resize(THUMB), (x, GAP))
        draw.rectangle((x, GAP, x + 52, GAP + 44), fill=(0, 0, 0))
        draw.text((x + 12, GAP + 6), str(n), fill=(255, 255, 255), font=font)
    return sheet


def gbp_cover(slide: Image.Image) -> Image.Image:
    slide = slide.convert("RGB")
    bg = slide.resize((GBP[0], round(GBP[0] * slide.height / slide.width)))
    top = (bg.height - GBP[1]) // 2
    bg = bg.crop((0, top, GBP[0], top + GBP[1])).filter(ImageFilter.GaussianBlur(40))
    fg = slide.resize((round(GBP[1] * slide.width / slide.height), GBP[1]))
    bg.paste(fg, ((GBP[0] - fg.width) // 2, 0))
    return bg


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slides", nargs="+", type=Path, help="slide images, in order")
    ap.add_argument("--out", type=Path, required=True, help="folder for the contact sheet and GBP cover")
    args = ap.parse_args(argv)

    found = problems(args.slides)
    args.out.mkdir(parents=True, exist_ok=True)
    images = [Image.open(p) for p in args.slides]
    contact_sheet(images).save(args.out / "contact-sheet.jpg", quality=90)
    gbp_cover(images[0]).save(args.out / "gbp-slide-1.jpg", quality=92)
    manifest = {
        "slides": [{"slide": n, "file": str(p.resolve())} for n, p in enumerate(args.slides, 1)],
        "contact_sheet": str((args.out / "contact-sheet.jpg").resolve()),
        "gbp_cover": str((args.out / "gbp-slide-1.jpg").resolve()),
        "problems": found,
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    for p in found:
        print(f"PROBLEM: {p}")
    print(f"{len(args.slides)} slides; wrote contact-sheet.jpg, gbp-slide-1.jpg and manifest.json in {args.out}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
