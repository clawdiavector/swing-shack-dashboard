"""test_v2026_08_19_performance_sub_matches_actual_cards.py

Regression: the Performance section's <span class="sub"> previously read
"What worked, what's leaking, what to scale" — a 3-phrase mission statement
that didn't name a single one of the actual sub-surfaces on the page. A
first-time visitor who read the sub then scrolled would find 4 stat tiles,
5 content cards, an insight strip, a connect CTA, and a why-this-worked
explainer panel that were not mentioned in the sub at all.

Fix: the sub now mirrors the actual surface (4 stat tiles + 5 named cards +
why-this-worked explainer) and carries data-help + data-help-title so the next
editor sees why the line exists and can refresh it if the surface changes.

The test reads the static <section id="sec-performance">...</section> block
from campaign-os.html and asserts:

  1. The aspirational pre-fix sub string is gone.
  2. The new descriptive sub string is present and lists every visible card.
  3. The sub is wrapped in <span class="sub">...</span>.
  4. The sub carries data-help and data-help-title.
  5. The sub contains no em-dashes (standing rule).

Pattern mirrors campaign-os/tests/test_v2026_08_19_section_sub_matches_actual_cards.py.
"""
import os
import re
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HTML_PATH = os.path.join(REPO_ROOT, "campaign-os", "campaign-os.html")


def _section_block(html: str, sec_id: str) -> str:
    """Return the full static <section id="sec-id">...</section> block.

    The block may span thousands of lines, so we walk a brace/quote aware
    scan to find the closing </section>. The campaign-os.html template
    uses no JSX / no <section> nesting inside <section> bodies, so a simple
    find on the section-level close tag is reliable.
    """
    open_tag = f'<section class="section" id="{sec_id}">'
    start = html.find(open_tag)
    assert start != -1, f"section {sec_id} not found in {HTML_PATH}"
    end = html.find("</section>", start)
    assert end != -1, f"</section> close not found after {sec_id}"
    return html[start : end + len("</section>")]


class TestPerformanceSubMirrorsActualCards(unittest.TestCase):
    """The Performance <span class="sub"> mirrors the actual sub-cards."""

    @classmethod
    def setUpClass(cls):
        with open(HTML_PATH, "r", encoding="utf-8") as fh:
            cls.html = fh.read()
        cls.block = _section_block(cls.html, "sec-performance")

    def test_01_aspirational_pre_fix_sub_is_gone(self):
        """The old 'What worked, what's leaking, what to scale' mission line is removed."""
        self.assertNotIn(
            "What worked, what&#39;s leaking, what to scale",
            self.block,
            "Performance still carries the pre-fix aspirational sub",
        )
        self.assertNotIn(
            "What worked, what's leaking, what to scale",
            self.block,
            "Performance still carries the pre-fix aspirational sub (raw apostrophe)",
        )

    def test_02_new_descriptive_sub_lists_every_visible_card(self):
        """The new sub names every card on the page."""
        sub_match = re.search(r'<span class="sub"[^>]*>([^<]+)</span>', self.block)
        self.assertIsNotNone(sub_match, "Performance has no <span class=\"sub\"> line")
        sub_text = sub_match.group(1)

        # 4 stat tiles are referenced (IG posts, GA4 sessions, SEO rising, SEO falling).
        self.assertIn("4 stat tiles", sub_text, "Sub does not mention 4 stat tiles")

        # 5 content cards are referenced: top IG, top SEO, A/B tests, top pages, insights.
        for needle in ("top IG", "top SEO", "A/B tests", "top pages", "insights"):
            self.assertIn(needle, sub_text, f"Sub does not mention '{needle}'")

        # Why-this-worked explainer panel is referenced.
        self.assertIn(
            "why-this-worked explainer", sub_text, "Sub does not mention the why-this-worked explainer panel"
        )

    def test_03_sub_uses_standard_pattern(self):
        """The sub is wrapped in <span class=\"sub\">...</span>."""
        self.assertRegex(
            self.block,
            r'<span class="sub"[^>]*>[^<]+</span>',
            "Performance sub is not wrapped in <span class=\"sub\">...</span>",
        )

    def test_04_sub_has_data_help(self):
        """The sub carries data-help so the next editor sees why it exists."""
        sub_match = re.search(r'<span class="sub"([^>]*)>', self.block)
        self.assertIsNotNone(sub_match, "Performance has no <span class=\"sub\">")
        attrs = sub_match.group(1)
        self.assertIn("data-help=", attrs, "Performance sub missing data-help attribute")
        self.assertIn("data-help-title=", attrs, "Performance sub missing data-help-title attribute")

    def test_05_sub_no_em_dash(self):
        """Standing rule: no em-dashes in published copy."""
        sub_match = re.search(r'<span class="sub"[^>]*>([^<]+)</span>', self.block)
        self.assertIsNotNone(sub_match, "Performance has no <span class=\"sub\">")
        sub_text = sub_match.group(1)
        # Em-dash is U+2014. Also reject en-dash (U+2013) to keep style consistent.
        self.assertNotIn("\u2014", sub_text, "Performance sub contains an em-dash")
        self.assertNotIn("\u2013", sub_text, "Performance sub contains an en-dash")

    def test_06_new_sub_visible_in_static_section(self):
        """The new descriptive sub text is the one in the section block."""
        self.assertIn(
            "why-this-worked explainer",
            self.block,
            "Performance section block does not contain the new sub text",
        )

    def test_07_sub_uses_middot_separator(self):
        """The sub uses · (middot) separators, consistent with the rest of Campaign OS."""
        sub_match = re.search(r'<span class="sub"[^>]*>([^<]+)</span>', self.block)
        self.assertIsNotNone(sub_match, "Performance has no <span class=\"sub\">")
        sub_text = sub_match.group(1)
        self.assertIn("\u00b7", sub_text, "Performance sub does not use · separators")


if __name__ == "__main__":
    unittest.main()
    sys.exit(0)
