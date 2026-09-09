"""v2026-08-13: Regression test for Insight nav group being open by default.

Background
----------
Until v2026-08-13 the Insight nav group was hidden by default, forcing
users to click through two layers (Insight group → Insights) to see the
weekly report. With the new IG Business live-account metrics adding 4
new claims (25k reach, top post, 64% reach contraction, 2.5k followers)
to the weekly report, the discoverability gap became a real UX bug:
the most actionable signals were buried behind a collapsed chevron.

Fix (campaign-os/campaign-os.html lines 898-911):
  - data-nav-group="insight" changed aria-expanded="false" → "true"
  - chevron glyph "▸" → "▾"
  - nav-group <div hidden> attribute removed

This test guards the contract by parsing the rendered SPA bundle (the
SPA is served as a single HTML payload, so a substring check on the
served HTML is the deterministic ground truth — equivalent to a
Playwright probe but doesn't require a browser session).
"""
from __future__ import annotations

import os
import re
import sys
import unittest
import urllib.request
from http.cookiejar import CookieJar

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HTML_PATH = os.path.join(_ROOT, "campaign-os", "campaign-os.html")


class InsightNavGroupOpenByDefaultTests(unittest.TestCase):
    """The SPA source must render the Insight group expanded by default."""

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(_HTML_PATH):
            raise unittest.SkipTest(f"SPA bundle not found at {_HTML_PATH}")
        cls.src = open(_HTML_PATH, encoding="utf-8").read()

    def test_01_insight_group_header_is_aria_expanded_true(self):
        """The Insight nav-group header must render with aria-expanded='true'
        so it boots open without a click."""
        # Find the data-nav-group="insight" header and check the
        # adjacent aria-expanded attribute. The pattern is a single
        # line, so the substring anchor is sufficient.
        m = re.search(
            r'<div class="nav-group-h" data-nav-group="insight"[^>]*aria-expanded="(true|false)"',
            self.src,
        )
        self.assertIsNotNone(
            m,
            "Insight nav-group header not found in SPA bundle — "
            "data-nav-group=\"insight\" markup may have been refactored",
        )
        self.assertEqual(
            m.group(1), "true",
            "Insight nav group is closed by default — UX bug. "
            "Should be aria-expanded='true' so the weekly report "
            "(and the new IG Business live-account claims) are visible "
            "without an extra click.",
        )

    def test_02_insight_group_container_has_no_hidden_attr(self):
        """The matching nav-group container must NOT carry `hidden` —
        that's the CSS that hides a collapsed group."""
        # The nav-group container immediately follows its header. Find
        # the header, then the next <div class="nav-group" id="nav-group-insight" ...>.
        m = re.search(
            r'<div class="nav-group" id="nav-group-insight"([^>]*)>',
            self.src,
        )
        self.assertIsNotNone(
            m,
            "nav-group-insight container not found in SPA bundle",
        )
        attrs = m.group(1)
        self.assertNotIn(
            "hidden", attrs,
            "nav-group-insight container still has the `hidden` attribute — "
            "Insight tab is still hidden by default.",
        )

    def test_03_insight_chevron_points_down(self):
        """The chevron glyph for the open Insight header should be ▾
        (down-pointing). Rotated chevrons are how the SPA signals
        expanded state."""
        # Find the line right before data-nav-group="insight" — that's
        # the chevron <span>.
        idx = self.src.find('data-nav-group="insight"')
        self.assertGreater(idx, 0)
        # Walk backwards to find the previous nav-group-chev span.
        chev_match = re.search(
            r'<span class="nav-group-chev">([^<]+)</span>',
            self.src[:idx],
        )
        self.assertIsNotNone(chev_match, "No nav-group-chev span found before Insight header")
        # The most recent chevron before the Insight header should be
        # the ▾ glyph (the other collapsed groups use ▸).
        self.assertEqual(
            chev_match.group(1).strip(), "▾",
            "Insight group chevron is not pointing down — the group "
            "header is still rendering in the collapsed style.",
        )

    def test_04_other_groups_remain_collapsed_by_default(self):
        """Defensive: ensure the fix didn't accidentally open ALL groups
        (only the Insight group should be open by default — others stay
        closed to keep the sidebar compact)."""
        # All other groups: Build, Reach, External, All tools. Daily
        # is already open by default and is the model for this fix.
        for group in ("build", "reach", "external", "all"):
            with self.subTest(group=group):
                m = re.search(
                    rf'<div class="nav-group-h" data-nav-group="{group}"[^>]*aria-expanded="(true|false)"',
                    self.src,
                )
                if m is None:
                    self.fail(f"{group} header not found in SPA bundle")
                self.assertEqual(
                    m.group(1), "false",
                    f"{group} nav group should remain collapsed by default "
                    f"(only Insight was the discoverability bug)",
                )


if __name__ == "__main__":
    unittest.main()
