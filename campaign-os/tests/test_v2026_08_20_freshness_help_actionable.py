"""Regression test: Data freshness card help text is actionable, not a changelog.

Background:
    The `<h3 data-help>` tooltip on the Agents page "Data freshness" card ended
    with an internal changelog note aimed at agents, not at Christelle:

        "This card used to live on the home (brief) page but it was hiding the
         actual marketing recommendation - moved here where fleet + ops issues
         belong."

    Two problems:
      1. It carried the last remaining em-dash in any static <h3 data-help>
         attribute in campaign-os.html, so
         test_v2026_08_12_no_emdashes_insights_v2_chrome::test_08 failed on a
         clean tree (pre-existing failure, flagged across several nightshift
         ticks).
      2. Help copy should tell the user what to DO with the card, per the
         MARKETING_OS_NORTH_STAR rule that every surface answers
         what / why / why-it-matters / what-to-do. "This card used to live
         somewhere else" answers none of those.

    Fix: replace the changelog sentence with the actual decision rule
    (a rotten feed means recommendations built on it are unreliable) plus a
    plain statement of why the card lives on the ops page.

These tests are string-level guards on campaign-os.html so they run without a
browser and stay fast in the pytest suite.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML_PATH = REPO / "campaign-os" / "campaign-os.html"

EM = "\u2014"  # em-dash

# The actionable sentence that replaced the changelog note.
POST_FIX_ACTIONABLE = (
    "If a feed shows up as rotten here, treat any recommendation built on it "
    "as unreliable until it refreshes."
)

# The changelog phrasing that must never come back.
BANNED_CHANGELOG_FRAGMENTS = (
    "This card used to live on the home",
    "moved here where fleet",
)


class TestFreshnessHelpActionable(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = HTML_PATH.read_text(encoding="utf-8")

    def _freshness_help(self) -> str:
        """Return the data-help body of the Data freshness card's <h3>."""
        matches = [
            m.group(1)
            for m in re.finditer(r'<h3[^>]*data-help="([^"]*)"', self.html)
            if "Per-file age check" in m.group(1)
        ]
        self.assertEqual(
            len(matches),
            1,
            f"expected exactly 1 Data freshness h3 data-help, found {len(matches)}",
        )
        return matches[0]

    def test_01_freshness_help_present(self):
        help_text = self._freshness_help()
        self.assertIn("Files older than 14 days", help_text)
        self.assertIn("rotten", help_text)

    def test_02_freshness_help_has_no_emdash(self):
        self.assertNotIn(EM, self._freshness_help())

    def test_03_freshness_help_is_actionable(self):
        self.assertIn(POST_FIX_ACTIONABLE, self._freshness_help())

    def test_04_changelog_phrasing_removed(self):
        help_text = self._freshness_help()
        for fragment in BANNED_CHANGELOG_FRAGMENTS:
            self.assertNotIn(
                fragment,
                help_text,
                f"changelog phrasing regressed into help copy: {fragment!r}",
            )

    def test_05_no_changelog_phrasing_anywhere_in_html(self):
        for fragment in BANNED_CHANGELOG_FRAGMENTS:
            self.assertNotIn(
                fragment,
                self.html,
                f"changelog phrasing present elsewhere in chrome: {fragment!r}",
            )

    def test_06_all_static_h3_datahelp_emdash_free(self):
        """Belt-and-braces mirror of the 2026-08-12 generic guard."""
        offenders = [
            m.group(1)[:100]
            for m in re.finditer(r'<h3[^>]*data-help="([^"]*)"', self.html)
            if EM in m.group(1)
        ]
        self.assertEqual(offenders, [], f"h3 data-help em-dash offenders: {offenders}")


if __name__ == "__main__":
    unittest.main()
