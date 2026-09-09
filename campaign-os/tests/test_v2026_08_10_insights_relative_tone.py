"""Regression tests for the 2026-08-10 Insights IG-post tone fix.

Bug: The Insights "Top Instagram Posts" card used hardcoded absolute ER thresholds
(>=3% good, >=1.5% watch, else bad). When the local average ER was well below 1.5%
(a typical real-world case for a small account), every single post rendered as the
"bad" red border, hiding the genuine top performer.

Fix: Tone is now relative to the in-list average ER, with a sane fallback so the
top row still gets a "Top performer" badge. Dead links (rows without a permalink)
render as a static div instead of an anchor that points at "#".

This test asserts:
  1. The hardcoded `>= 3 ? 'good' : >= 1.5 ? 'watch' : 'bad'` chain is no longer
     present in the renderInsightsV2 IG-post tone logic.
  2. The new "★ Top" badge template is present and reachable.
  3. The conditional render branch (`p.permalink ? <a ...> : <div ...>`) is in
     place so missing-permalink rows stop pretending to be clickable.
  4. No em-dashes leaked into the new copy.
"""
from __future__ import annotations
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPA = REPO / "campaign-os" / "campaign-os.html"


class TestInsightsRelativeTone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = SPA.read_text(encoding="utf-8")

    def test_no_hardcoded_absolute_thresholds_in_ig_tone(self):
        """The buggy `er >= 3 ? 'good' : er >= 1.5 ? 'watch' : 'bad'` chain
        must be gone from the IG-post tone computation."""
        block = self._igList_block()
        self.assertNotIn(
            "er >= 3 ? 'good' : er >= 1.5",
            block,
            "Hardcoded absolute IG-tone thresholds still present (regressed)",
        )

    def test_local_average_er_computed_in_render(self):
        """The render block must compute a local-average ER constant."""
        block = self._igList_block()
        self.assertIn("igAvgEr", block, "Local-average ER const `igAvgEr` missing")
        self.assertIn("ratio", block, "Per-row ratio const missing")

    def test_top_performer_badge_present(self):
        """The new ★ Top badge template must be reachable."""
        block = self._igList_block()
        self.assertIn("★ Top", block, "★ Top badge template missing")
        self.assertIn("isTop", block, "isTop detection flag missing")

    def test_no_dead_href_hash_for_missing_permalink(self):
        """When `p.permalink` is missing, the row must render as a div, not a stub anchor."""
        block = self._igList_block()
        # The bug shape: `href="${esc(p.permalink || '#')}"` — must be gone.
        self.assertNotIn(
            "p.permalink || '#'",
            block,
            "Old `permalink || '#'` dead-link fallback still in place (regressed)",
        )
        # The fix shape: a conditional render branch.
        self.assertIn("if (p.permalink)", block, "Permalink conditional render branch missing")
        self.assertIn("href=\"${esc(p.permalink)}\"", block, "Direct permalink href missing")

    def test_no_em_dashes_in_new_render_block(self):
        """Standing rule: no em-dashes in published copy."""
        block = self._igList_block()
        # Note: comments and template literals are body content; em-dashes are banned across
        # the whole block to keep the pre-commit lint happy.
        self.assertNotIn("—", block, "Em-dash (—) leaked into the IG-post render block")
        self.assertNotIn("–", block, "En-dash (–) leaked into the IG-post render block")

    def test_postiz_fetcher_captures_permalink(self):
        """The Postiz fetcher must extract permalink so the next sync has it."""
        fetcher = (REPO / "scripts" / "fetch_postiz_analytics.js").read_text(encoding="utf-8")
        self.assertIn("permalink", fetcher, "Postiz fetcher no longer captures permalink")
        self.assertIn("p.releaseURL", fetcher, "Postiz releaseURL fallback missing")

    def _igList_block(self) -> str:
        """Return the text of the IG-post igList render block (or fail the test)."""
        m = re.search(
            r"igList\.innerHTML = igPostsFinal\.length \? igPostsFinal\.map.*?"
            r"No IG posts yet",
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "igList render block not found")
        return m.group(0) or ""


if __name__ == "__main__":
    unittest.main()
