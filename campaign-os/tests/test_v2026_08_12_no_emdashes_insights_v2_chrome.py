"""Regression test: em-dashes swept from Insights v2 chrome (renderInsightsV2
section-h h2 data-help + renderPerformance empty-state fallback string).

Background:
    The standing rule is "no em-dash in published copy". The 2026-08-12 walker
    swept section tooltips (TIPS map) + Review-modal data-help, but missed
    two adjacent chrome-class leaks that live INSIDE JS template literals
    injected into the DOM at runtime (per pitfall 119, the static probe
    doesn't see them because they're not static data-help attrs):

      1. renderInsightsV2() section-h h2 data-help ("Insights" tooltip)
         '... Built for non-marketers — if you can't read a card in 5
          seconds, it's a bug.'
         → em-dash replaced with colon ('... Built for non-marketers: ...')

      2. renderPerformance() insights-strip fallback string
         ('No insights yet — connect analytics to see what is working')
         → em-dash replaced with comma
         ('No insights yet, connect analytics to see what is working')

Both are user-visible chrome: (1) appears when the user clicks the "?" icon
on the Insights v2 H2, (2) appears in the perf page's top insights strip
when the /api/intel/explain endpoint returns zero insights.

Both fixes follow the same standing rule as the 2026-08-12T04:24Z sweep
(colons / commas / periods instead of em-dashes in user-visible prose).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML_PATH = REPO / "campaign-os" / "campaign-os.html"

EM = "\u2014"  # — em-dash

# (1) renderInsightsV2 section-h h2 data-help (the Insights tooltip body)
POST_FIX_INSIGHTS_V2_TOOLTIP = (
    "Plain-English view of what is happening with your marketing. "
    "Every card shows the data AND what it means in one short sentence. "
    "Green = good signal, yellow = watch, red = needs attention. "
    "Built for non-marketers: if you can't read a card in 5 seconds, "
    "it's a bug."
)
PRE_FIX_INSIGHTS_V2_TOOLTIP = (
    "Plain-English view of what is happening with your marketing. "
    "Every card shows the data AND what it means in one short sentence. "
    "Green = good signal, yellow = watch, red = needs attention. "
    "Built for non-marketers \u2014 if you can't read a card in 5 seconds, "
    "it's a bug."
)

# (2) renderPerformance insights-strip fallback string
POST_FIX_PERF_EMPTY_INSIGHTS = (
    "No insights yet, connect analytics to see what is working"
)
PRE_FIX_PERF_EMPTY_INSIGHTS = (
    "No insights yet \u2014 connect analytics to see what is working"
)


class TestInsightsV2ChromeEmdashSweep(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = HTML_PATH.read_text(encoding="utf-8")

    # (1) renderInsightsV2 h2 data-help
    def test_01_insights_v2_tooltip_post_fix_present(self):
        self.assertIn(
            POST_FIX_INSIGHTS_V2_TOOLTIP,
            self.html,
            "Post-fix Insights v2 tooltip missing (colon form)",
        )

    def test_02_insights_v2_tooltip_pre_fix_absent(self):
        self.assertNotIn(
            PRE_FIX_INSIGHTS_V2_TOOLTIP,
            self.html,
            "Pre-fix Insights v2 tooltip still present (em-dash leak)",
        )

    # (2) renderPerformance empty-state fallback
    def test_03_perf_empty_insights_post_fix_present(self):
        self.assertIn(
            POST_FIX_PERF_EMPTY_INSIGHTS,
            self.html,
            "Post-fix renderPerformance insights-strip fallback missing (comma form)",
        )

    def test_04_perf_empty_insights_pre_fix_absent(self):
        self.assertNotIn(
            PRE_FIX_PERF_EMPTY_INSIGHTS,
            self.html,
            "Pre-fix renderPerformance insights-strip fallback still present (em-dash leak)",
        )

    # Defensive: each post-fix string must itself be em-dash-free
    def test_05_post_fix_strings_emdash_free(self):
        for name, s in [
            ("insights-v2-tooltip", POST_FIX_INSIGHTS_V2_TOOLTIP),
            ("perf-empty-insights", POST_FIX_PERF_EMPTY_INSIGHTS),
        ]:
            self.assertNotIn(
                EM,
                s,
                f"Post-fix {name} string still contains em-dash",
            )

    # Pinpoint guard: the insights-v2 tooltip must be wrapped in
    # data-help-title="Insights" so a re-introduction outside this
    # context wouldn't satisfy this test (false-positive guard).
    def test_06_insights_v2_tooltip_wired_to_data_help_title(self):
        m = re.search(
            r'data-help="[^"]*Plain-English view[^"]*" data-help-title="Insights"',
            self.html,
        )
        self.assertIsNotNone(
            m,
            "Insights v2 tooltip not wrapped in data-help-title='Insights'",
        )
        assert m is not None  # for type checkers
        self.assertNotIn(
            EM,
            m.group(0),
            "Insights v2 tooltip block still contains em-dash",
        )

    # Generic guard: every <h2 data-help=...> in campaign-os.html is
    # em-dash-free. Per the standing rule, no em-dash in any user-visible
    # chrome tooltip body. Static attrs only — runtime template-literal
    # injections are caught by test_01..04.
    def test_07_all_static_h2_datahelp_emdash_free(self):
        for m in re.finditer(r'<h2[^>]*data-help="([^"]*)"', self.html):
            value = m.group(1)
            self.assertNotIn(
                EM,
                value,
                f"<h2 data-help> still contains em-dash: {value[:120]!r}",
            )

    # Generic guard: every <h3 data-help=...> in campaign-os.html is
    # em-dash-free.
    def test_08_all_static_h3_datahelp_emdash_free(self):
        for m in re.finditer(r'<h3[^>]*data-help="([^"]*)"', self.html):
            value = m.group(1)
            self.assertNotIn(
                EM,
                value,
                f"<h3 data-help> still contains em-dash: {value[:120]!r}",
            )

    # Generic guard: every <h4 data-help=...> in campaign-os.html is
    # em-dash-free (modal h4 tooltips too).
    def test_09_all_static_h4_datahelp_emdash_free(self):
        for m in re.finditer(r'<h4[^>]*data-help="([^"]*)"', self.html):
            value = m.group(1)
            self.assertNotIn(
                EM,
                value,
                f"<h4 data-help> still contains em-dash: {value[:120]!r}",
            )


if __name__ == "__main__":
    unittest.main()