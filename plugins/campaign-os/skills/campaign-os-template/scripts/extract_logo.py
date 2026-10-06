#!/usr/bin/env python3
"""Cut a logo out of a reference post into a transparent PNG.

Pick the reference where the logo sits on the flattest background (solid colour
beats photo). Alpha comes from distance to the background luminance.

  python3 extract_logo.py ref.jpg --box 60,150,420,300 --out logo-white.png [--scale 2]
"""

from __future__ import annotations

import argparse

import numpy as np
from PIL import Image


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--box", required=True, help="x0,y0,x1,y1 search region (generous)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=float, default=1.0, help="upscale factor for small logos")
    ap.add_argument("--keep-colour", action="store_true", help="keep original RGB instead of pure white")
    ap.add_argument("--max-sat", type=int, default=35, help="ignore pixels more saturated than this")
    args = ap.parse_args()
    x0, y0, x1, y1 = (int(v) for v in args.box.split(","))
    rgb = np.asarray(Image.open(args.image).convert("RGB")).astype(float)[y0:y1, x0:x1]
    L = rgb.mean(axis=2)
    sat = np.ptp(rgb, axis=2)
    bg = float(np.median(L))
    ink = (L > bg + 50) & (sat < args.max_sat)
    if not ink.any():
        raise SystemExit("no logo ink found — widen --box or raise --max-sat")
    ys, xs = np.nonzero(ink)
    cy0, cy1, cx0, cx1 = max(0, ys.min() - 4), ys.max() + 5, max(0, xs.min() - 4), xs.max() + 5
    crop, Lc, sc = rgb[cy0:cy1, cx0:cx1], L[cy0:cy1, cx0:cx1], sat[cy0:cy1, cx0:cx1]
    alpha = np.clip((Lc - bg) / max(1.0, 250 - bg), 0, 1)
    alpha[sc > args.max_sat + 5] = 0
    out = np.zeros((*alpha.shape, 4), dtype=np.uint8)
    out[..., :3] = crop.astype(np.uint8) if args.keep_colour else 255
    out[..., 3] = (alpha * 255).astype(np.uint8)
    im = Image.fromarray(out, "RGBA")
    if args.scale != 1.0:
        im = im.resize((int(im.width * args.scale), int(im.height * args.scale)), Image.LANCZOS)
    im.save(args.out)
    print(f"bg luminance {bg:.0f}; logo at x {x0 + cx0}-{x0 + cx1} y {y0 + cy0}-{y0 + cy1} -> {args.out} {im.size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
