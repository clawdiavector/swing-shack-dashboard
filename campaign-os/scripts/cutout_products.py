#!/usr/bin/env python3
"""Cut products out of their photos (RGBA PNG, cropped to the product) for the route engine.

Uses rembg (open source, MIT). It is not a repo dependency: install it where this runs
(the Mac), e.g. `uv pip install "rembg[cpu]"`. BiRefNet gave clean edges on clubs, putters,
bags and balls; use --model birefnet-general for pale-on-pale photos (ball boxes).

  python campaign-os/scripts/cutout_products.py IN_DIR OUT_DIR [--model birefnet-general-lite] [files...]
"""
import argparse
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--model", default="birefnet-general-lite")
    a = ap.parse_args()
    from PIL import Image
    from rembg import new_session, remove
    sess = new_session(a.model)
    src, dst = Path(a.src), Path(a.dst)
    dst.mkdir(parents=True, exist_ok=True)
    names = a.files or [p.name for p in sorted(src.iterdir()) if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
    for n in names:
        out = remove(Image.open(src / n).convert("RGB"), session=sess).convert("RGBA")
        out = out.crop(out.getbbox())
        out.save(dst / (n + ".png"))
        print("cut", n, out.size)


if __name__ == "__main__":
    main()
