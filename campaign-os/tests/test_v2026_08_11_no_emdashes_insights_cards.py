"""
Regression test: no em-dashes inside the Insights v2 main-card copy.

Background:
    The standing rule is "no em-dash in published copy". The b992ca4 fix swept
    section/card headings + dropdowns. The 2026-08-11 morning tick swept the
    Socials + Performance connect explainers (test_v2026_08_11_no_emdashes_connect_explainer.py).
    This test locks in the next lane: the 3 main-card em-dashes inside the
    Insights tab that render on every page-load (not just help-popups).

    Sites covered (3 total):
      1. Insights adBlock "Google Ads: ..." separator (was "<b>Google Ads</b> — ${...}")
      2. Insights adBlock "Meta Ads: ..." separator  (was "<b>Meta Ads</b> — ${...}")
      3. Insights topGA4Take "Your homepage gets the most traffic: X sessions"
         (was "...traffic — X sessions...")

Fix (2026-08-11 nightshift tick):
    Replaced the 3 em-dashes with colons. Same separator pattern as the
    b992ca4 dropdown fix used. No copy lost; the visible strings remain
    semantically identical (just non-typographic-punctuation).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HTML = REPO / "campaign-os.html"


def _read() -> str:
    return HTML.read_text(encoding="utf-8")


class TestNoEmdashesInsightsMainCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = _read()

    # ---- slice helpers -----------------------------------------------------

    def _adblock_innerhtml(self) -> str:
        """Return the adBlock.innerHTML template literal body for Insights v2."""
        m = re.search(
            r"adBlock\.innerHTML\s*=\s*`(.*?)`\s*;",
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "adBlock.innerHTML template not found")
        return m.group(0)

    def _topga4take(self) -> str:
        """Return the full topGA4Take function body — extract the function then
        pull out its template literal body."""
        m = re.search(
            r"function topGA4Take\(pages\)\s*\{(.*?)\n\s*\}",
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "topGA4Take function not found")
        return m.group(0)

    # ---- test cases --------------------------------------------------------

    def test_01_no_emdash_adblock_google_ads_line(self) -> None:
        """The '<b>Google Ads</b>: ${...}' separator must be a colon, never an em-dash."""
        adblock = self._adblock_innerhtml()
        m = re.search(
            r"<b>Google Ads</b>[^\$\{]*\$\{esc\(adCorr\.google_ads",
            adblock,
        )
        self.assertIsNotNone(m, "Google Ads line in adBlock not found")
        # Extract the separator between </b> and ${
        # Pull the segment between </b> and ${
        sep = re.search(r"</b>([^\$]*)\$\{esc", adblock)
        self.assertIsNotNone(sep, "separator between </b> and template var not found")
        sep_text = sep.group(1)
        self.assertNotIn("\u2014", sep_text,
                         "Google Ads separator must not be an em-dash")
        self.assertNotIn("\u2013", sep_text,
                         "Google Ads separator must not be an en-dash")
        # Confirm it IS a colon (the fix shape)
        self.assertIn(":", sep_text,
                      "Google Ads separator should be a colon (per the fix)")

    def test_02_no_emdash_adblock_meta_ads_line(self) -> None:
        """The '<b>Meta Ads</b>: ${...}' separator must be a colon, never an em-dash."""
        adblock = self._adblock_innerhtml()
        sep = re.search(r"<b>Meta Ads</b>([^\$]*)\$\{esc", adblock)
        self.assertIsNotNone(sep, "Meta Ads separator not found")
        sep_text = sep.group(1)
        self.assertNotIn("\u2014", sep_text,
                         "Meta Ads separator must not be an em-dash")
        self.assertNotIn("\u2013", sep_text,
                         "Meta Ads separator must not be an en-dash")
        self.assertIn(":", sep_text,
                      "Meta Ads separator should be a colon (per the fix)")

    def test_03_no_emdash_topga4take_homepage_line(self) -> None:
        """The 'Your homepage gets the most traffic: X sessions' string must use a colon."""
        fn = self._topga4take()
        # Locate the template literal body
        m = re.search(
            r"`(Your homepage gets the most traffic[^`]+)`",
            fn,
        )
        self.assertIsNotNone(m, "topGA4Take template literal not found")
        body = m.group(1)
        self.assertNotIn("\u2014", body,
                         "topGA4Take template literal must not contain an em-dash")
        self.assertNotIn("\u2013", body,
                         "topGA4Take template literal must not contain an en-dash")
        # Verify the colon is present in the right slot
        self.assertIn("gets the most traffic: ${", body,
                      "topGA4Take should use a colon before ${top.sessions...}")

    # ---- preservation guards ----------------------------------------------

    def test_04_key_substrings_preserved(self) -> None:
        """The em-dash removal must not have stripped any keyword the
        renderInsightsV2() code depends on."""
        for kw in (
            "Google Ads",
            "Meta Ads",
            "Your homepage gets the most traffic",
            "small copy fixes pay off most",
            "Until ad data lands",
            "did the ad drive this spike",
            "data not present",
        ):
            self.assertIn(kw, self.html,
                          f"keyword {kw!r} must still appear in campaign-os.html "
                          f"(the em-dash sweep must not have stripped it)")

    def test_05_replaced_text_exact(self) -> None:
        """The post-fix exact text must match the canonical colon form."""
        self.assertIn("<b>Google Ads</b>: ${esc(adCorr.google_ads", self.html,
                      "expected Google Ads colon separator not present")
        self.assertIn("<b>Meta Ads</b>: ${esc(adCorr.meta_ads", self.html,
                      "expected Meta Ads colon separator not present")
        self.assertIn(
            "Your homepage gets the most traffic: ${(top.sessions||0).toLocaleString()}",
            self.html,
            "expected topGA4Take colon separator not present",
        )


if __name__ == "__main__":
    import sys
    result = unittest.main(exit=False, verbosity=2)[0]
    sys.exit(0 if result.wasSuccessful() else 1)