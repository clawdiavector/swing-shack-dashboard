"""The Swing Shack lockup is a closed box: a vertical line down BOTH sides (2026-10-28).

The repo's logo.png and swing-shack-logo-{white,dark}.png had lost the right-hand vertical line, leaving only
the top line and a small dash at the bottom right, so the mark looked cut off wherever it was used. The
official artwork (white on dark, black on white, grey on white) has the closed box.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BRAND = ROOT / "data" / "brand-directory" / "swing-shack"
LOCKUPS = [BRAND / "logo.png", BRAND / "logos" / "swing-shack-logo-white.png", BRAND / "logos" / "swing-shack-logo-dark.png"]


def edge_run(path: Path, side: str) -> tuple[int, int]:
    """(tallest vertical run of opaque pixels in the outer 3% on `side`, height of the mark)."""
    a = Image.open(path).convert("RGBA").split()[3]
    x0, y0, x1, y1 = a.getbbox()
    band = max(8, (x1 - x0) // 33)
    xs = range(x0, x0 + band) if side == "left" else range(x1 - band, x1)
    best = 0
    for x in xs:
        best = max(best, sum(1 for y in range(y0, y1) if a.getpixel((x, y)) > 128))
    return best, y1 - y0


class ClosedBoxTests(unittest.TestCase):
    def test_every_lockup_has_a_tall_line_on_both_sides(self):
        for path in LOCKUPS:
            for side in ("left", "right"):
                run, height = edge_run(path, side)
                self.assertGreaterEqual(run, 0.6 * height,
                                        "%s: %s edge line is %dpx of a %dpx mark" % (path.name, side, run, height))

    def test_the_lockups_are_the_same_shape(self):
        sizes = {Image.open(p).size for p in LOCKUPS}
        self.assertEqual(len(sizes), 1, "white, dark and logo.png should share one canvas: %s" % sizes)


if __name__ == "__main__":
    unittest.main()
