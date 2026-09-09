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
        """Return the full topGA4Take function body.

        Walks the body with a brace counter so nested if/else blocks + template
        literal ${} interpolations don't break extraction. Returns the matched
        text including the `function topGA4Take(pages){` opener and the matching
        closing brace.
        """
        m = re.search(r"function topGA4Take\(pages\)\s*\{", self.html)
        self.assertIsNotNone(m, "topGA4Take function not found")
        start = m.start()
        depth = 0
        i = m.end() - 1  # position of the opening {
        while i < len(self.html):
            ch = self.html[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return self.html[start:i + 1]
            i += 1
        self.fail("topGA4Take function body never closed")

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
        """The topGA4Take template literal must use a colon (not an em-dash) before
        the ${sessions} interpolation, in the homepage branch."""
        fn = self._topga4take()
        # Locate the homepage branch: "Your ${label}" where label is "homepage"
        m = re.search(
            r"gets the most traffic:\s*\$\{sessions\}",
            fn,
        )
        self.assertIsNotNone(m, "topGA4Take colon-before-${sessions} pattern not found")
        # Whole function body must not contain an em-dash or en-dash in prose.
        self.assertNotIn("\u2014", fn,
                         "topGA4Take function must not contain an em-dash")
        self.assertNotIn("\u2013", fn,
                         "topGA4Take function must not contain an en-dash")
        # The homepage branch's tail must still be the "small copy fixes pay off most" copy.
        self.assertIn("small copy fixes pay off most", fn,
                      "topGA4Take homepage branch tail must be preserved")

    # ---- preservation guards ----------------------------------------------

    def test_04_key_substrings_preserved(self) -> None:
        """The em-dash removal must not have stripped any keyword the
        renderInsightsV2() code depends on. The topGA4Take rewrite dropped the
        literal "Your homepage gets the most traffic" string (it now lives
        inside a template: `Your ${label} gets the most traffic`), so we
        assert on the assembled fragment and the homepage tail copy instead.
        """
        # Static substrings unaffected by the rewrite
        for kw in (
            "Google Ads",
            "Meta Ads",
            "Until ad data lands",
            "did the ad drive this spike",
            "data not present",
        ):
            self.assertIn(kw, self.html,
                          f"keyword {kw!r} must still appear in campaign-os.html "
                          f"(the em-dash sweep must not have stripped it)")
        # The topGA4Take rewrite: these fragments live in different parts of
        # the file now. Assert each is still present, just not necessarily
        # as a single string.
        self.assertIn("Your ${label} gets the most traffic", self.html,
                      "topGA4Take must still build the headline from a label var")
        self.assertIn("small copy fixes pay off most", self.html,
                      "homepage-branch tail copy must be preserved")

    def test_05_replaced_text_exact(self) -> None:
        """The post-fix exact text must match the canonical colon form."""
        self.assertIn("<b>Google Ads</b>: ${esc(adCorr.google_ads", self.html,
                      "expected Google Ads colon separator not present")
        self.assertIn("<b>Meta Ads</b>: ${esc(adCorr.meta_ads", self.html,
                      "expected Meta Ads colon separator not present")
        # topGA4Take now uses ${sessions} instead of inlining the expression
        self.assertIn("gets the most traffic: ${sessions}", self.html,
                      "expected topGA4Take colon-before-${sessions} not present")


if __name__ == "__main__":
    import sys
    result = unittest.main(exit=False, verbosity=2)[0]
    sys.exit(0 if result.wasSuccessful() else 1)