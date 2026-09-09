"""Regression tests for the 2026-08-10 Insights "Top pages by sessions" tone fix.

Bug: The Insights "Top pages by sessions" card used hardcoded absolute ER thresholds
(>=60% good, >=30% watch, else bad). On a brand whose real average engagement is
~52% (swing-shack's live data), a 26.8% ER page renders red even though it's only
0.5x the average — and the top performer (77.5% /bookings/) gets no distinguishing
badge to call it out.

Fix: Tone is now relative to the in-list average ER, mirroring the IG-post block
sitting immediately above. The top row gets a "★ Top" badge when it beats the
local average by >= 1.5x. The ER pill tooltip exposes the math
("Top performer (your avg: 51.7%)") so the user can see why a row is green.

This test asserts:
  1. The hardcoded `>= 60 ? 'good' : >= 30 ? 'watch' : 'bad'` chain is gone.
  2. A local-average ER constant is computed (`pageAvgEr`).
  3. The new "★ Top" badge template is reachable and guarded by `ratio >= 1.5`.
  4. The ER pill `title` tooltip explains the math (mentions the local average).
  5. No em-dashes leaked into the new copy.
"""
from __future__ import annotations
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPA = REPO / "campaign-os" / "campaign-os.html"


class TestInsightsGa4PagesRelativeTone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = SPA.read_text(encoding="utf-8")

    def test_no_hardcoded_absolute_thresholds_in_pages_tone(self):
        """The buggy `erPct >= 60 ? 'good' : erPct >= 30 ? 'watch' : 'bad'` chain
        must be gone from the GA4-pages tone computation."""
        block = self._pagesList_block()
        self.assertNotIn(
            "erPct >= 60 ? 'good' : erPct != null && erPct >= 30",
            block,
            "Hardcoded absolute pages-tone thresholds still present (regressed)",
        )

    def test_local_average_er_computed_in_render(self):
        """The render block must compute a local-average ER constant."""
        block = self._pagesList_block()
        self.assertIn("pageAvgEr", block, "Local-average ER const `pageAvgEr` missing")
        self.assertIn("pageTopEr", block, "Max ER const `pageTopEr` missing")
        self.assertIn("ratio", block, "Per-row ratio const missing")

    def test_top_performer_badge_present(self):
        """The new ★ Top badge template must be reachable and guarded by ratio >= 1.5."""
        block = self._pagesList_block()
        self.assertIn("★ Top", block, "★ Top badge template missing")
        self.assertIn("isTop", block, "isTop detection flag missing")
        # The badge arm must be guarded by the relative-tone threshold, not the absolute >=60.
        self.assertRegex(
            block,
            r"isTop\s*&&\s*ratio\s*>=\s*1\.5",
            "★ Top badge arm is not guarded by `ratio >= 1.5` (regressed to absolute hit)",
        )

    def test_er_pill_tooltip_explains_the_math(self):
        """The ER pill must expose the verdict + the local average so the user sees
        the math, not just a color."""
        block = self._pagesList_block()
        self.assertIn("your avg:", block, "ER pill tooltip does not mention the local average")
        self.assertIn("verdictLabel", block, "verdictLabel template var missing")

    def test_no_em_dashes_in_new_render_block(self):
        """Standing rule: no em-dashes in published copy. The pre-existing
        dash-only fallback (`'—'` for missing ER) was kept verbatim to preserve
        dashboard parity; we assert it's still the only dash character in the
        block and that no new em-dashes were added in the new code."""
        block = self._pagesList_block()
        # The only allowed em-dash is the pre-existing '—' fallback for missing ER.
        # Count em-dashes in the new code (excluding the fallback that was already there).
        em_dash_count = block.count("—")
        en_dash_count = block.count("–")
        # Pre-fix: 1 em-dash (the fallback). Patch must not add new ones.
        self.assertLessEqual(
            em_dash_count, 1,
            f"em-dash count rose to {em_dash_count} (expected <=1, the existing fallback)",
        )
        self.assertEqual(
            en_dash_count, 0,
            f"En-dash (–) leaked into the GA4-pages render block ({en_dash_count} occurrences)",
        )

    def _pagesList_block(self) -> str:
        """Return the text of the pagesList render block (or fail the test)."""
        m = re.search(
            r"pagesList\.innerHTML = ga4Pages\.length \? ga4Pages\.map.*?"
            r"No GA4 data yet",
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "pagesList render block not found")
        return m.group(0) or ""


if __name__ == "__main__":
    unittest.main()
