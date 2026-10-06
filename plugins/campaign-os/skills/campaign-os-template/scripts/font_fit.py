#!/usr/bin/env python3
"""Find font size + horizontal squash that reproduce measured words.

Give the measured cap height and each word's measured ink width (from measure_refs /
zoomed crops). Prints size, natural width and h_scale per font; the best font has
the most consistent h_scale across words (designers often squash to ~85–90%).

  python3 font_fit.py --cap 127 --word WRONG=663 --word HURTS=568 \
      --font Montserrat-BlackItalic.ttf --font Montserrat-ExtraBoldItalic.ttf
"""

from __future__ import annotations

import argparse
import statistics

from PIL import ImageFont


def size_for_cap(path: str, cap: int) -> int:
    for s in range(8, 400):
        b = ImageFont.truetype(path, s).getbbox("H")
        if b[3] - b[1] >= cap:
            return s
    raise SystemExit(f"cap {cap} unreachable for {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cap", type=int, required=True, help="measured cap height px")
    ap.add_argument("--word", action="append", required=True, help="TEXT=measured_width_px")
    ap.add_argument("--font", action="append", required=True)
    args = ap.parse_args()
    words = [(w.split("=", 1)[0], float(w.split("=", 1)[1])) for w in args.word]
    ranked = []
    for path in args.font:
        size = size_for_cap(path, args.cap)
        f = ImageFont.truetype(path, size)
        scales = []
        for text, measured in words:
            b = f.getbbox(text)
            scales.append(measured / (b[2] - b[0]))
        spread = statistics.pstdev(scales) if len(scales) > 1 else 0.0
        ranked.append((spread, path, size, scales))
    for spread, path, size, scales in sorted(ranked):
        print(f"{path}\n  size {size}px  h_scale mean {statistics.mean(scales):.3f}  spread {spread:.3f}  "
              + "  ".join(f"{t}:{s:.3f}" for (t, _), s in zip(words, scales)))
    print("\nlowest spread = closest letterforms; use its size as max_font_px and mean as h_scale")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
