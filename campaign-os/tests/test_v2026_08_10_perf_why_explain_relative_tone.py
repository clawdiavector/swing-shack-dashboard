"""Regression tests for the 2026-08-10 Performance "Why this worked / failed" fix.

Bug: The "Why" explainer button on the Performance widget tone-coded every
asset against hardcoded absolute engagement-rate thresholds
(er > 4 ? 'Strong' : er > 2 ? 'Average' : er > 0 ? 'Underperformer' : 'No data').
On Swing Shack — where the real average IG engagement rate is ~52% (top_posts
return ER in percent units, not decimals) — every post in the dropdown ranked
"Strong performer" regardless of where it actually stood in the in-list
distribution. The same bug class as pitfalls 89/90 (lying affordance /
lying tone) applied to a third surface.

Fix: Tone is now relative to the in-list average ER from top_posts. Top row
gets a "★ Top" badge when it beats the local average by >= 1.5x. The ER pill
exposes the math via a tooltip ("Top performer (your avg: 51.7%)") so the
user sees the verdict and the reason. Em-dashes in the visible output are
replaced with " · " / "no data" / "x" forms (standing rule).

This test asserts:
  1. The hardcoded `(er > 4) ? 'Strong performer' : (er > 2) ? 'Average'`
     chain is gone from the why-explain click handler.
  2. A local-average ER constant is computed (`whyAvgEr`).
  3. The new "★ Top" badge template is reachable and guarded by `whyRatio >= 1.5`.
  4. The verdict tooltip explains the math (mentions "your avg:") and the
     inline ratio badge shows the multiplier.
  5. No em-dashes leaked into the new copy.
  6. The fallback explanation now uses `1.5x` / `0.8x` thresholds (matching
     the live render), not `2x` / `0.5x` as before.
  7. The Why-asset dropdown population (`whySel`) and explain button hookup
     (`whyBtn`) are still wired (no regression on the entry-point plumbing).
"""
from __future__ import annotations
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPA = REPO / "campaign-os" / "campaign-os.html"


class TestPerfWhyExplainRelativeTone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = SPA.read_text(encoding="utf-8")

    def test_no_hardcoded_absolute_thresholds_in_why_verdict(self):
        """The buggy `er > 4 ? 'Strong' : er > 2 ? 'Average'` chain must be
        gone from the why-explain click handler."""
        block = self._whyHandler_block()
        self.assertNotIn(
            "(er > 4) ? '✅ Strong performer'",
            block,
            "Hardcoded absolute why-verdict thresholds still present (regressed)",
        )
        self.assertNotIn(
            "(er > 2) ? '🟡 Average performer'",
            block,
            "Hardcoded average-performer threshold still present (regressed)",
        )
        self.assertNotIn(
            "(er > 0) ? '🔴 Underperformer'",
            block,
            "Hardcoded underperformer threshold still present (regressed)",
        )

    def test_local_average_er_computed_in_handler(self):
        """The why-explain handler must compute a local-average ER constant
        from top_posts (the same list the dropdown is populated from)."""
        block = self._whyHandler_block()
        self.assertIn("whyAvgEr", block, "Local-average ER const `whyAvgEr` missing")
        self.assertIn("whyTopEr", block, "Max ER const `whyTopEr` missing")
        self.assertIn("whyRatio", block, "Per-row ratio const missing")
        self.assertIn("whyIsTop", block, "Top-detection flag missing")

    def test_top_performer_badge_present_and_guarded(self):
        """The new ★ Top badge template must be reachable and guarded by
        `whyRatio >= 1.5` (mirrors the GA4 pages fix)."""
        block = self._whyHandler_block()
        self.assertIn("★ Top", block, "★ Top badge template missing")
        # The badge must be guarded by the relative threshold, not absolute.
        self.assertRegex(
            block,
            r"whyIsTop\s*&&\s*whyRatio\s*>=\s*1\.5",
            "\u2605 Top badge arm is not guarded by `whyRatio >= 1.5` (regressed to absolute hit)",
        )

    def test_verdict_tooltip_explains_the_math(self):
        """The verdict pill must expose the verdict + the local average so the
        user sees the math, not just an emoji."""
        block = self._whyHandler_block()
        self.assertIn("your avg:", block, "Verdict tooltip does not mention the local average")
        self.assertIn("whyVerdictLabel", block, "verdictLabel template var missing")
        # Inline ratio badge in the visible output so the multiplier is unmissable.
        self.assertIn("x avg", block, "Inline ratio badge missing (e.g. '1.42x avg')")

    def test_fallback_explanation_uses_relative_thresholds(self):
        """The fallback explanation (when /api/engagement returns null)
        now uses the same `1.5x` / `0.8x` ladder as the verdict, not the old
        `2x` / `0.5x` ladder which was misleading at the 52% scale."""
        block = self._whyHandler_block()
        # The hardcoded `2x average` and `0.5x` are gone.
        self.assertNotIn("2\u00d7 average", block, "Old `2x average` string still present (regressed)")
        self.assertNotIn("0.5\u00d7", block, "Old `0.5x` threshold still present (regressed)")
        # The new thresholds are present.
        self.assertIn("1.5x", block, "New `1.5x` threshold missing in fallback")
        self.assertIn("0.8x", block, "New `0.8x` threshold missing in fallback")

    def test_no_em_dashes_in_why_handler_block(self):
        """Standing rule: no em-dashes in published copy. The old handler
        had em-dashes for the verdict separator and the missing-data fallback."""
        block = self._whyHandler_block()
        # Em-dash (—) and en-dash (–) banned in the new code.
        self.assertNotIn("\u2014", block, "Em-dash (\u2014) leaked into the why-explain handler")
        self.assertNotIn("\u2013", block, "En-dash (\u2013) leaked into the why-explain handler")
        # The threshold strings use literal `x` (not U+00D7) so they're
        # keyboard-friendly and the standing rule finds no em-dash even when
        # scanning the fallback.
        self.assertIn("1.5x", block, "New `1.5x` threshold string missing in fallback")
        self.assertIn("0.8x", block, "New `0.8x` threshold string missing in fallback")

    def test_dropdown_and_button_still_wired(self):
        """The why-asset dropdown population (`whySel`) and the click handler
        (`whyBtn`) must still be wired (no regression on entry-point plumbing)."""
        # The dropdown population sits just before the click handler.
        self.assertIn("#why-asset", self.html, "why-asset dropdown hook missing")
        self.assertIn("#why-explain-btn", self.html, "why-explain-btn hook missing")
        self.assertIn("whySel", self.html, "Dropdown population code missing")
        self.assertIn("whyBtn", self.html, "Click handler binding missing")
        # And the result slot is rendered.
        self.assertIn("#why-result", self.html, "why-result render slot missing")

    def _whyHandler_block(self) -> str:
        """Return the text of the why-explain click handler block (or fail)."""
        m = re.search(
            r"whyBtn && !whyBtn\._bound\).*?out\.innerHTML = '<i>Engagement endpoint failed: '\s*\+\s*esc\(err\.message",
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "why-explain click handler block not found")
        return m.group(0) if m else ""


if __name__ == "__main__":
    unittest.main()
