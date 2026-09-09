"""Regression test: ensure scripts/walk_full_sweep_live.py actually clicks visible nav rows.

Background
----------
The walker used to call `page.locator(sel).first.click(force=True)` on every `.nav[data-go=X]`.
Several slugs (memes, ideas, imagegen, ctas, hashtagseo, faqs, reddit, insights, trends,
performance, learning, seo, seo-audit, calendar, publish, captions, headlines, hooks,
billboards) live inside collapsed sidebar nav groups (`<div class="nav-group" hidden>`).
For those slugs, `locator(sel).first` resolves to the hidden row, the force-click "succeeds"
but the section switch handler doesn't fire — so the walker reports the sidebar nav as the
section content and `em_dash_count` / `empty_hits` / `pageerrors` are all measured against
the wrong surface. NAV_ERR showed up on 19/28 tabs in the pre-fix walker output.

This test guards against that regression by asserting the walker source code:
1. Expands all collapsed `.nav-group-h` before the click loop
2. Skips hidden matches and picks the first visible `.nav[data-go=X]` instead of `.first`
3. Tracks sub-navs (the slugs that historically failed) explicitly so future maintainers
   can see the contract being enforced
"""

import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WALKER = ROOT / "scripts" / "walk_full_sweep_live.py"


class WalkerNavGroupExpansionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not WALKER.exists():
            raise unittest.SkipTest(f"walker not found at {WALKER}")
        cls.src = WALKER.read_text()

    def test_01_walker_expands_collapsed_nav_groups(self):
        """Walker must click all `.nav-group-h[aria-expanded='false']` elements before the click loop."""
        # The fix uses querySelectorAll + forEach click on the chevron headers.
        # Allow either an explicit click dispatch or a page.evaluate that sets aria-expanded=true.
        pattern = re.compile(
            r"(nav-group-h\[aria-expanded=[\"\']false[\"\']\]|\.nav-group-h\b)",
            re.MULTILINE,
        )
        self.assertRegex(
            self.src,
            pattern,
            "Walker must touch `.nav-group-h[aria-expanded='false']` to expand "
            "collapsed sidebar nav groups before clicking .nav[data-go=X] rows.",
        )

    def test_02_walker_picks_visible_nav_not_first(self):
        """Walker must NOT use `.first.click()` blindly — it must pick a visible row."""
        # The buggy line was:
        #   page.locator(sel).first.scroll_into_view_if_needed(...); page.locator(sel).first.click(force=True, ...)
        # The fix uses an `is_visible()` loop and a `target.click(timeout=...)` (no force=True).
        self.assertNotIn(
            ".first.click(force=True",
            self.src,
            "Walker still uses .first.click(force=True) — hits hidden rows in collapsed "
            "nav groups and breaks section switching for ~19/28 tabs.",
        )

    def test_03_walker_iterates_matches_to_find_visible(self):
        """Walker must loop over matches and select the first visible one."""
        # The fix uses `for i in range(cnt): ... if cand.is_visible(): target = cand`.
        self.assertRegex(
            self.src,
            r"is_visible\(\)",
            "Walker must call `is_visible()` on each locator candidate to find a clickable target.",
        )

    def test_04_walker_dismisses_welcome_tour(self):
        """Walker must skip the welcome tour overlay before clicking nav rows (it intercepts pointer events)."""
        self.assertRegex(
            self.src,
            re.compile(r"welcome-skip|welcome_skip", re.IGNORECASE),
            "Walker must dismiss the welcome tour before clicking nav rows; the modal "
            "intercepts pointer events and causes NAV_ERR on every click until dismissed.",
        )

    def test_05_subnav_slugs_are_listed(self):
        """Walker must iterate the sub-nav slugs that historically failed."""
        # These slugs live inside collapsed groups (Build, Insight, Reach).
        # If any of them go missing from NAV_NAMES, the walker silently stops
        # testing that surface — which is exactly the kind of regression we want
        # to catch.
        expected_subnavs = {
            "memes", "ideas", "imagegen", "ctas", "hashtagseo", "faqs",
            "reddit", "insights", "trends", "performance", "learning",
            "seo", "seo-audit", "calendar", "publish", "captions",
            "headlines", "hooks", "billboards", "campaigns", "create",
        }
        # Parse NAV_NAMES list and check each slug appears
        for slug in expected_subnavs:
            self.assertRegex(
                self.src,
                rf"\(\s*[\"\']{slug}[\"\']\s*,",
                f"Walker NAV_NAMES is missing sub-nav slug `{slug}`. "
                f"This slug lives in a collapsed nav group and would be silently skipped.",
            )


if __name__ == "__main__":
    unittest.main()