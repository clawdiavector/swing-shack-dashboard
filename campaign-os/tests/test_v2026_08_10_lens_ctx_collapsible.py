"""Regression tests for the 2026-08-10 lens-ctx-collapsible fix.

Bug: The static "How to read this view" lens context panels on Calendar,
Socials, and Insights were ALWAYS-EXPANDED divs that consumed ~250px of
viewport on every visit. Christelle ships from the Calendar daily (57
planned items right now) and was forced to scroll past the explainer
every time before she could see the actual 14-day grid. Same on Socials
(voice-history grid pushed below the fold) and Insights v2 (pattern
signals pushed below the fold).

The Trends tab and other tab explainers already use a native
<details class="help-collapsible"> pattern (collapsed by default, one
click to expand). The three hand-rolled .calendar-lens-ctx /
.socials-lens-ctx / .insights-lens-ctx divs did not.

Fix: Convert each of the three always-expanded panels into a native
<details class="help-collapsible help-section-explainer ..."> with a
<summary> title line. The body content is preserved verbatim inside a
nested .card div so the visual chrome (background, border, left-bar
accent) is unchanged. Native <details> is collapsed by default when no
`open` attribute is set, so the explainer no longer eats viewport
real-estate on the working surfaces.

This test asserts the static-HTML invariants:
  1. The Calendar lens-ctx is now a <details>, not a <div>, and has
     a <summary> titled "How to read the calendar".
  2. The Socials lens-ctx is now a <details> with a <summary>.
  3. The Insights v2 lens-ctx is now a <details> with a <summary>.
  4. None of the three have the `open` attribute (so they stay
     collapsed by default — power users do not see the explainer
     every visit).
  5. The original body content is preserved (HUD strip explanation,
     "drag a slot" copy, "🟢🟡🔴 tone" line, etc.) — the fix is
     pure restructure, no copy was lost.
  6. The body inside the <details> still carries the visual .card
     chrome so the expanded state looks like the old expanded state.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPA = REPO / "campaign-os" / "campaign-os.html"


class LensCtxCollapsibleTests(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.html = SPA.read_text(encoding="utf-8")

    # ─── Calendar ──────────────────────────────────────────────────────
    def test_calendar_lens_ctx_is_details_with_summary(self):
        m = re.search(
            r'<details class="help-collapsible help-section-explainer calendar-lens-ctx"[^>]*>'
            r'\s*<summary>([^<]+)</summary>',
            self.html,
        )
        self.assertIsNotNone(
            m,
            "Calendar lens-ctx must be a <details class=\"help-collapsible "
            "help-section-explainer calendar-lens-ctx\"> with a <summary>. "
            "If this is missing, the static Calendar intro panel is back to "
            "always-expanded and Christelle has to scroll past 250px of "
            "explainer on every visit to see the 14-day grid.",
        )
        summary = m.group(1)  # type: ignore[union-attr]
        self.assertIn("read the calendar", summary.lower(),
                      f"Calendar summary should be self-explanatory, got: {summary!r}")

    def test_calendar_lens_ctx_not_open_by_default(self):
        m = re.search(
            r'<details class="help-collapsible help-section-explainer calendar-lens-ctx"([^>]*)>',
            self.html,
        )
        self.assertIsNotNone(m, "Calendar <details> block not found")
        attrs = m.group(1)  # type: ignore[union-attr]
        self.assertNotIn(
            " open", attrs,
            "Calendar <details> must NOT have the `open` attribute — "
            "the explainer is supposed to stay collapsed on every visit.",
        )

    def test_calendar_lens_ctx_preserves_hud_strip_explanation(self):
        # The original copy mentioned the HUD strip; the fix must not drop it.
        self.assertIn(
            "HUD strip",
            self.html,
            "Calendar lens-ctx body must still explain the HUD strip (regression check).",
        )
        self.assertIn(
            "Duplicate zone",
            self.html,
            "Calendar lens-ctx body must still mention the Duplicate zone (regression check).",
        )

    def test_calendar_lens_ctx_body_has_card_chrome(self):
        # The visual chrome lives on a nested .card now (not the <details>).
        m = re.search(
            r'<details class="help-collapsible help-section-explainer calendar-lens-ctx"[^>]*>'
            r'.*?<div class="card"[^>]*border-left:3px solid var\(--ac\)',
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(
            m,
            "Calendar lens-ctx body must still carry a .card wrapper with the "
            "left-border accent so the expanded state matches the old expanded state.",
        )

    # ─── Socials ───────────────────────────────────────────────────────
    def test_socials_lens_ctx_is_details_with_summary(self):
        m = re.search(
            r'<details class="help-collapsible help-section-explainer socials-lens-ctx"[^>]*>'
            r'\s*<summary>([^<]+)</summary>',
            self.html,
        )
        self.assertIsNotNone(
            m,
            "Socials lens-ctx must be a <details class=\"help-collapsible "
            "help-section-explainer socials-lens-ctx\"> with a <summary>. "
            "If missing, the Socials voice-history grid is back to "
            "pushed-below-the-fold on every visit.",
        )

    def test_socials_lens_ctx_not_open_by_default(self):
        m = re.search(
            r'<details class="help-collapsible help-section-explainer socials-lens-ctx"([^>]*)>',
            self.html,
        )
        self.assertIsNotNone(m, "Socials <details> block not found")
        attrs = m.group(1)  # type: ignore[union-attr]
        self.assertNotIn(
            " open", attrs,
            "Socials <details> must NOT have the `open` attribute.",
        )

    def test_socials_lens_ctx_preserves_meta_graph_copy(self):
        # The original body explained the Meta Graph + oEmbed fallback — keep it.
        self.assertIn(
            "Meta Graph",
            self.html,
            "Socials lens-ctx must still mention Meta Graph as the recent-posts source.",
        )
        self.assertIn(
            "oEmbed",
            self.html,
            "Socials lens-ctx must still mention the oEmbed fallback for older posts.",
        )

    # ─── Insights v2 ───────────────────────────────────────────────────
    def test_insights_lens_ctx_is_details_with_summary(self):
        m = re.search(
            r'<details class="help-collapsible help-section-explainer insights-lens-ctx"[^>]*>'
            r'\s*<summary>([^<]+)</summary>',
            self.html,
        )
        self.assertIsNotNone(
            m,
            "Insights v2 lens-ctx must be a <details class=\"help-collapsible "
            "help-section-explainer insights-lens-ctx\"> with a <summary>. "
            "If missing, the Insights pattern-signals grid is back to "
            "pushed-below-the-fold on every visit.",
        )

    def test_insights_lens_ctx_not_open_by_default(self):
        m = re.search(
            r'<details class="help-collapsible help-section-explainer insights-lens-ctx"([^>]*)>',
            self.html,
        )
        self.assertIsNotNone(m, "Insights <details> block not found")
        attrs = m.group(1)  # type: ignore[union-attr]
        self.assertNotIn(
            " open", attrs,
            "Insights <details> must NOT have the `open` attribute.",
        )

    def test_insights_lens_ctx_preserves_tone_legend(self):
        # The 🟢🟡🔴 tone legend is the most actionable line in the explainer.
        self.assertIn(
            "🟢🟡🔴 tone",
            self.html,
            "Insights lens-ctx must still show the green/yellow/red tone legend.",
        )
        self.assertIn(
            "Top Instagram Posts",
            self.html,
            "Insights lens-ctx must still mention the Top Instagram Posts row.",
        )

    # ─── No accidentally-orphaned <div> panels ────────────────────────
    def test_no_stray_lens_ctx_divs(self):
        """The hand-rolled always-expanded divs must be gone. Only the
        <details> rewrites (and the dead-code clone at line ~5123) should
        mention the lens-ctx class names."""
        # Calendar
        self.assertNotRegex(
            self.html,
            r'<div class="card col-12 calendar-lens-ctx"',
            "Stray always-expanded <div class=\"card col-12 calendar-lens-ctx\"> "
            "still present — the convert-to-<details> fix is incomplete.",
        )
        # Socials
        self.assertNotRegex(
            self.html,
            r'<div class="card col-12 socials-lens-ctx"',
            "Stray always-expanded <div class=\"card col-12 socials-lens-ctx\"> "
            "still present — the convert-to-<details> fix is incomplete.",
        )
        # Insights v2 (in body.innerHTML template literal)
        self.assertNotRegex(
            self.html,
            r'<div class="card col-12 insights-lens-ctx"',
            "Stray always-expanded <div class=\"card col-12 insights-lens-ctx\"> "
            "still present in the Insights v2 template literal.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
