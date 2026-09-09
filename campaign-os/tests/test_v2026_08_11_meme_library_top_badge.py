"""Regression tests for the 2026-08-11 Meme Lord library list "★ Top" badge.

Bug: The Meme Lord top-picks panel (the 6-card grid at the top of #sec-memes)
already surfaced a "★ Top" badge for standout rows (>= 1.2x local average
brand_fit, set on 2026-08-10). But the wider library list (the 60-row scroller
Christelle actually uses when hunting for "what meme should I use next?") had
no badge, so standout rows in the wider deck were invisible at a glance.

Fix: Mirror the same ★ Top logic on the library rows — pass `isTop` into
`memLibraryRow()`, badge fires on the local max brand_fit when it's >= 1.2x
the local average AND >= 60 (hard floor so the badge doesn't fire on every
row in a loose filter). Surface the badge count in the #memes-summary hint
line ("· N ★ top in view") so Christelle can see how many standouts qualify
without counting rows manually.

This test asserts:
  1. memLibraryRow signature now accepts isTop.
  2. memRefresh computes libAvgFit + libMaxFit + libTopCount for the library.
  3. The "★ Top" badge template is wired into memLibraryRow.
  4. The min-60 brand_fit floor is present (the "only on strong matches" gate).
  5. The "★ top in view" suffix appears in the summary text assignment.
  6. No new em-dashes leaked into the new copy.
"""
from __future__ import annotations
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPA = REPO / "campaign-os" / "campaign-os.html"


def _extract_block(text: str, start_marker: str, end_markers) -> str:
    """Return text from `start_marker` to whichever end_marker is found first."""
    start = text.index(start_marker)
    earliest = None
    for em in end_markers:
        try:
            idx = text.index(em, start + len(start_marker))
        except ValueError:
            continue
        if earliest is None or idx < earliest:
            earliest = idx
    if earliest is None:
        return text[start:start + 4096]
    return text[start:earliest]


class TestMemeLibraryTopBadge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = SPA.read_text(encoding="utf-8")

    def test_memlibraryrow_signature_accepts_isTop(self):
        block = _extract_block(self.html, "function memLibraryRow(", ["async function memRefresh(){"])
        self.assertIn("isTop", block, "memLibraryRow must accept isTop arg")

    def test_memrefresh_computes_library_avg_max_topcount(self):
        # The library block is bounded by the next "// Library " comment or the
        # pickList assignment, whichever comes first. Use the picks block as the
        # upper bound so we only inspect the new library-locality code.
        block = _extract_block(self.html, "// Library \"\u2605 Top\" badge",
                               ["const pickList ="])
        self.assertIn("libAvgFit", block, "libAvgFit local-average constant missing")
        self.assertIn("libMaxFit", block, "libMaxFit local-max constant missing")
        self.assertIn("libTopCount", block, "libTopCount counter missing")

    def test_top_badge_template_in_memlibraryrow(self):
        block = _extract_block(self.html, "function memLibraryRow(", ["async function memRefresh(){"])
        self.assertIn("\u2605 Top", block, "\u2605 Top badge template missing from memLibraryRow")
        self.assertIn("topBadge", block, "topBadge local must be assigned in memLibraryRow")
        self.assertIn("10b98122", block, "green tone colour missing from library badge")
        self.assertIn("10b981", block, "green tone foreground missing from library badge")

    def test_min_60_floor_present(self):
        block = _extract_block(self.html, "// Library \"\u2605 Top\" badge",
                               ["const pickList ="])
        self.assertIn("bf >= 60", block, "min brand_fit 60 floor missing from library top logic")
        self.assertIn("1.2", block, "1.2x ratio threshold missing from library top logic")

    def test_top_count_suffix_in_summary(self):
        block = _extract_block(self.html, "// Library \"\u2605 Top\" badge",
                               ["const pickList ="])
        self.assertIn("\u2605 top in view", block,
                      "summary suffix '\u2605 top in view' missing from library top logic")
        self.assertIn("libTopCount", block.replace("if (libTopCount", "X"),
                      "libTopCount must drive the suffix")

    def test_no_new_em_dashes_in_memlibraryrow(self):
        block = _extract_block(self.html, "function memLibraryRow(", ["async function memRefresh(){"])
        self.assertNotIn("\u2014", block, "Em-dash (\u2014) leaked into memLibraryRow")
        self.assertNotIn("\u2013", block, "En-dash (\u2013) leaked into memLibraryRow")

    def test_no_new_em_dashes_in_library_top_block(self):
        block = _extract_block(self.html, "// Library \"\u2605 Top\" badge",
                               ["const pickList ="])
        self.assertNotIn("\u2014", block, "Em-dash (\u2014) leaked into library-top logic")
        self.assertNotIn("\u2013", block, "En-dash (\u2013) leaked into library-top logic")


if __name__ == "__main__":
    unittest.main()