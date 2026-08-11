"""
Regression test: no em-dashes inside the Connect-Instagram / Connect-analytics
empty-state explainers or the Search Console button copy.

Background:
    The standing rule is "no em-dash in published copy". The b992ca4 fix swept
    section/card headings + dropdowns, but the Connect-Instagram + Connect-
    analytics empty-state explainers (visible every time Christelle opens
    Socials or Performance with IG not connected) and the Search Console
    button copy were missed.

Fix (2026-08-11 nightshift tick):
    Replaced 8 em-dashes inside the Socials + Performance connect explainers
    (Meta Graph API bullet, oEmbed fallback bullet, 'Ask Heidi to spin up'
    line, 'widening the range' inline empty msg, 3 Performance bullets,
    the 'Ask Heidi to spin up' Performance line, and the 'Check Search
    Console' button text). Used colons/parentheses as the b992ca4 fix did;
    no copy lost.

Tests:
    All static-HTML checks against campaign-os.html. The 7 numbered sites
    are:
      1. Socials Meta Graph API bullet
      2. Socials oEmbed fallback bullet
      3. Socials 'Ask Heidi to spin up' line
      4. Socials inline 'widening the range' empty msg
      5. Performance Instagram + Facebook bullet
      6. Performance Google Analytics 4 bullet
      7. Performance Google Search Console bullet
      8. Performance 'Ask Heidi to spin up' line
      9. Performance 'Check Search Console' button copy
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HTML = REPO / "campaign-os.html"


def _read() -> str:
    return HTML.read_text(encoding="utf-8")


class TestNoEmdashesInConnectExplainer(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = _read()

    # ---- slice helpers -----------------------------------------------------

    def _slice_between(self, start_marker: str, end_marker: str) -> str:
        """Return HTML between two unique markers (first occurrence after start_marker)."""
        s = self.html.find(start_marker)
        self.assertNotEqual(s, -1, f"start marker {start_marker!r} not found")
        e = self.html.find(end_marker, s)
        self.assertNotEqual(e, -1, f"end marker {end_marker!r} not found after start")
        return self.html[s:e]

    def _socials_connect_cta(self) -> str:
        """Return the connectCta template literal body for Socials."""
        m = re.search(
            r"const connectCta = `.*?`;",
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "connectCta block not found")
        return m.group(0)

    def _perf_connect_block(self) -> str:
        """Return the Connect-analytics explainer block (3-source list + setup line)."""
        m = re.search(
            r"<div style=\"font-size:14px;font-weight:600;margin-bottom:\.4rem;color:var\(--ac\)\">📊 Connect analytics.*?</div>\s*</div>",
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "Connect-analytics explainer not found")
        return m.group(0)

    def _bullet_body(self, bold_label: str, within: str | None = None) -> str:
        """Return the full <li>...</li> body for the bullet whose leading <b> matches bold_label.

        Used for em-dash checks that must traverse nested <code>/<b> tags.
        """
        haystack = self.html if within is None else within
        # Find the <li> whose first <b>...</b> label is bold_label.
        # Greedy .*? across </li> handles nested <code>/<b> inside the bullet body.
        # Don't use re.escape — these labels are constant strings from our own code,
        # and re.escape over-escapes '\' and ' ' which makes the pattern not match.
        pat = re.compile(r"<li>" + bold_label + r".*?</li>", re.DOTALL)
        m = pat.search(haystack)
        self.assertIsNotNone(m, f"bullet with leading label {bold_label!r} not found")
        return m.group(0)

    # ---- test cases --------------------------------------------------------

    def test_01_no_emdash_socials_meta_graph_bullet(self) -> None:
        # The first <li> in the Socials connect explainer carries the Meta Graph API
        # deliverable. Must use ':' or ',' as the separator, never '—'.
        body = self._bullet_body("<b>Meta Graph API</b>")
        self.assertNotIn("\u2014", body,
                         "Meta Graph API bullet must not contain an em-dash")
        self.assertNotIn("\u2013", body,
                         "Meta Graph API bullet must not contain an en-dash")

    def test_02_no_emdash_socials_oembed_bullet(self) -> None:
        body = self._bullet_body("<b>oEmbed fallback</b>")
        self.assertNotIn("\u2014", body,
                         "oEmbed fallback bullet must not contain an em-dash")
        self.assertNotIn("\u2013", body,
                         "oEmbed fallback bullet must not contain an en-dash")

    def test_03_no_emdash_socials_ask_heidi_line(self) -> None:
        # The 'Ask Heidi to spin up the setup-portal at /meta' line for Socials.
        cta = self._socials_connect_cta()
        # First Ask-Heidi line in the connectCta block is the Socials one
        m = re.search(
            r"Ask Heidi to spin up the setup-portal at <code>/meta</code>.*?</div>",
            cta,
        )
        self.assertIsNotNone(m, "Socials Ask-Heidi setup-portal line not found")
        body = m.group(0)
        self.assertNotIn("\u2014", body,
                         "Socials Ask-Heidi line must not contain an em-dash")

    def test_04_no_emdash_socials_widening_inline(self) -> None:
        # The emptyMsg template literal with graphEmpty ternary.
        m = re.search(
            r"const emptyMsg = graphEmpty\s*\?\s*`.*?`\s*:\s*`.*?`;",
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "emptyMsg ternary not found")
        body = m.group(0)
        self.assertNotIn("\u2014", body,
                         "Socials widening-the-range inline empty msg must not contain an em-dash")

    def test_05_no_emdash_perf_instagram_bullet(self) -> None:
        block = self._perf_connect_block()
        body = self._bullet_body("<b>Instagram \\+ Facebook</b>", within=block)
        self.assertNotIn("\u2014", body,
                         "Performance Instagram bullet must not contain an em-dash")

    def test_06_no_emdash_perf_ga4_bullet(self) -> None:
        block = self._perf_connect_block()
        body = self._bullet_body("<b>Google Analytics 4</b>", within=block)
        self.assertNotIn("\u2014", body,
                         "Performance GA4 bullet must not contain an em-dash")

    def test_07_no_emdash_perf_gsc_bullet(self) -> None:
        block = self._perf_connect_block()
        body = self._bullet_body("<b>Google Search Console</b>", within=block)
        self.assertNotIn("\u2014", body,
                         "Performance Google Search Console bullet must not contain an em-dash")

    def test_08_no_emdash_perf_ask_heidi_line(self) -> None:
        # The 'Ask Heidi to spin up the setup-portal at /meta or /ga4' line for Performance.
        m = re.search(
            r"Ask Heidi to spin up the setup-portal at <code>/meta</code> or <code>/ga4</code>.*?</div>",
            self.html,
        )
        self.assertIsNotNone(m, "Performance Ask-Heidi setup-portal line not found")
        body = m.group(0)
        self.assertNotIn("\u2014", body,
                         "Performance Ask-Heidi line must not contain an em-dash")

    def test_09_no_emdash_perf_search_console_button(self) -> None:
        # The 'Check Search Console' button's onclick prompt must not contain an em-dash.
        # The button uses window.ASK_HEIDI_OPEN||alert pattern with literal string.
        m = re.search(
            r"onclick=\"\(window\.ASK_HEIDI_OPEN\|\|alert\)\('Ask Heidi: confirm Search Console status[^']*'\)",
            self.html,
        )
        self.assertIsNotNone(m, "Check Search Console button onclick not found")
        body = m.group(0)
        self.assertNotIn("\u2014", body,
                         "Check Search Console button copy must not contain an em-dash")

    # ---- preservation guards ----------------------------------------------

    def test_10_key_substrings_preserved(self) -> None:
        """The em-dash removal must not have stripped any keyword the existing
        tests in test_v2026_08_09_socials_connect_cta.py depend on."""
        for kw in (
            "Connect Instagram",
            "setup-portal",
            "widening the range",
            "IG business account",
            "Facebook page",
            "Meta Graph API",
            "oEmbed fallback",
            "Google Search Console",
            "Google Analytics 4",
        ):
            self.assertIn(kw, self.html,
                          f"keyword {kw!r} must still appear in campaign-os.html "
                          f"(the em-dash sweep must not have stripped it)")

    def test_11_arrow_preserved_in_oembed_bullet(self) -> None:
        """The 'older posts (30d → 1y)' arrow is a unicode right-arrow, not an
        em-dash. The sweep must have left it alone — it is conventional in
        range expressions."""
        self.assertIn("30d \u2192 1y", self.html,
                      "'30d → 1y' arrow must still be present (it's a range arrow, "
                      "not an em-dash, and must survive the sweep)")


if __name__ == "__main__":
    import sys
    result = unittest.main(exit=False, verbosity=2)[0]
    sys.exit(0 if result.wasSuccessful() else 1)