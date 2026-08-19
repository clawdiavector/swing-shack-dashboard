"""test_v2026_08_19_trends_sub_mirrors_actual_cards.py

Regression: the Trend Catcher (sec-trends) <span class="sub"> was a tag
list "Marketing · Golf News · Competitors" that didn't tell a first-time
visitor what sub-cards live below the section header. The actual surface
is Signal radar (the scored slice above the grid) plus a 2x2 grid of 4
source panels: Reddit trends, YouTube signals, Golf news, Competitor
moves. Each card carries a 0 to 100 score and a 1-line why-now.

Fix: the static sub now mirrors the actual surface
"Signal radar (scored 0 to 100) · Reddit trends · YouTube signals ·
Golf news · Competitor moves · 1-line why-now on each" and carries an
id="tr-summary" anchor + data-help + data-help-title for next-editor
context. No JS path overwrites this sub (verified: no `#tr-summary`
textContent setter anywhere in the file), so the static text is the
first-frame AND steady-state description.

The test reads the static <section id="sec-trends">...</section> block
from campaign-os.html and asserts:

  1. The old tag-list sub ("Marketing · Golf News · Competitors") is gone.
  2. The new descriptive sub string is present and names every visible
     sub-card (Signal radar · Reddit · YouTube · Golf news · Competitor
     moves · 1-line why-now).
  3. The sub is wrapped in <span class="sub" id="tr-summary">…</span>.
  4. The sub carries data-help and data-help-title (next-editor hint).
  5. The sub contains no em-dashes (standing rule).
  6. The sub uses · (middot) separators, consistent with the rest of
     Campaign OS.
  7. No JS path overwrites #tr-summary's textContent, so the static
     fallback is the steady-state description (unlike Calendar which
     has a dynamic summary slot).

Pattern mirrors campaign-os/tests/test_v2026_08_19_calendar_sub_mirrors_actual_cards.py
and campaign-os/tests/test_v2026_08_19_performance_sub_matches_actual_cards.py.
"""
import os
import re
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HTML_PATH = os.path.join(REPO_ROOT, "campaign-os", "campaign-os.html")


def _section_block(html: str, sec_id: str) -> str:
    """Return the full static <section id="sec-id">...</section> block."""
    open_tag = f'<section class="section" id="{sec_id}">'
    start = html.find(open_tag)
    assert start != -1, f"section {sec_id} not found in {HTML_PATH}"
    end = html.find("</section>", start)
    assert end != -1, f"</section> close not found after {sec_id}"
    return html[start : end + len("</section>")]


class TestTrendsSubMirrorsActualCards(unittest.TestCase):
    """The Trend Catcher <span class="sub" id="tr-summary"> mirrors the actual sub-cards."""

    @classmethod
    def setUpClass(cls):
        with open(HTML_PATH, "r", encoding="utf-8") as fh:
            cls.html = fh.read()
        cls.block = _section_block(cls.html, "sec-trends")

    def test_01_old_tag_list_sub_is_gone(self):
        """The old 'Marketing · Golf News · Competitors' tag-list sub is removed.

        Note: the new sub's data-help= attribute deliberately quotes the old
        label so a future editor can see what was replaced. We check that the
        old label is NOT used as actual sub text content, not that it doesn't
        appear anywhere in the section.
        """
        # Find the sub span and assert its text content is the new descriptive string.
        m = re.search(
            r'<span class="sub" id="tr-summary"[^>]*data-help-title="What is in this section"[^>]*>([^<]+)</span>',
            self.block,
        )
        assert m is not None, "Trends tr-summary span not found"
        sub_text = m.group(1).strip()
        self.assertNotIn(
            "Marketing · Golf News · Competitors",
            sub_text,
            "Trends sub still carries the pre-fix tag-list label as its visible text",
        )
        self.assertIn(
            "Signal radar",
            sub_text,
            "Trends sub text does not start with the new descriptive surface list",
        )

    def test_02_new_descriptive_sub_lists_every_visible_card(self):
        """The new sub names every visible sub-card in Trends."""
        sub_text = self._extract_sub_text()
        # All 5 sub-cards must be named:
        for needle in (
            "Signal radar",
            "Reddit",
            "YouTube",
            "Golf news",
            "Competitor moves",
            "1-line why-now",
            "0 to 100",
        ):
            self.assertIn(
                needle,
                sub_text,
                f"Trends sub is missing visible sub-card reference: {needle!r}",
            )

    def test_03_sub_uses_standard_pattern(self):
        """The sub is wrapped in <span class=\"sub\" id=\"tr-summary\">…</span>."""
        # The span also carries data-help and data-help-title attributes before the
        # text content, so the attribute whitelist must accept the standard pattern.
        self.assertRegex(
            self.block,
            r'<span class="sub" id="tr-summary"\s+[^>]*data-help-title="What is in this section"\s*[^>]*>[^<]+</span>',
            "Trends sub is not wrapped in <span class=\"sub\" id=\"tr-summary\" data-help-title=…>…</span>",
        )

    def test_04_sub_has_data_help(self):
        """The sub carries data-help= and data-help-title= attributes for the next editor."""
        # Pull out the tr-summary span and inspect its attributes.
        m = re.search(
            r'<span class="sub" id="tr-summary"([^>]*)>',
            self.block,
        )
        assert m is not None, "Trends tr-summary span not found"
        attrs = m.group(1)
        self.assertIn("data-help=", attrs, "Trends tr-summary missing data-help=")
        self.assertIn(
            "data-help-title=",
            attrs,
            "Trends tr-summary missing data-help-title=",
        )

    def test_05_sub_no_em_dash(self):
        """The sub contains no em-dash (U+2014) or en-dash (U+2013) per standing rule."""
        sub_text = self._extract_sub_text()
        self.assertNotIn(
            "\u2014",
            sub_text,
            "Trends sub contains a U+2014 em-dash (banned in published copy)",
        )
        self.assertNotIn(
            "\u2013",
            sub_text,
            "Trends sub contains a U+2013 en-dash (banned in published copy)",
        )

    def test_06_sub_uses_middot_separator(self):
        """The sub uses · (U+00B7) separators consistent with the rest of Campaign OS."""
        sub_text = self._extract_sub_text()
        # The new sub should contain at least 4 middots separating the 5+ items.
        middot_count = sub_text.count("\u00b7")
        self.assertGreaterEqual(
            middot_count,
            4,
            f"Trends sub should use \u00b7 (middot) separators; found {middot_count}",
        )

    def test_07_no_js_textContent_overwrite_on_tr_summary(self):
        """No JS path overwrites #tr-summary.textContent, so the static sub is steady-state.

        Unlike Calendar (which has a dynamic summary slot overwritten by
        renderCalendar()), Trends has no live-count overwrite — the static
        sub IS the description. Documenting this in the test prevents the
        next editor from accidentally adding a JS overwrite without a
        fallback (a regression on the static-sub pattern).
        """
        # Search the rest of the HTML for any `tr-summary` textContent / innerText / innerHTML set.
        # Limit to a sane window so we don't catch unrelated identifiers.
        patterns = (
            r"getElementById\(['\"]tr-summary['\"]\)\.textContent",
            r"getElementById\(['\"]tr-summary['\"]\)\.innerText",
            r"getElementById\(['\"]tr-summary['\"]\)\.innerHTML",
            r"\$\(['\"]#tr-summary['\"]\)\.text\(",
            r"\$\(['\"]#tr-summary['\"]\)\.html\(",
            r"#tr-summary\.textContent",
            r"#tr-summary\.innerHTML",
            r"#tr-summary\.text",
            r"#tr-summary\.html",
        )
        for pat in patterns:
            self.assertNotRegex(
                self.html,
                pat,
                f"Trends sub has a JS overwrite path ({pat}); the static sub should remain steady-state",
            )

    # ----- helpers -----

    def _extract_sub_text(self) -> str:
        m = re.search(
            r'<span class="sub" id="tr-summary"[^>]*>([^<]+)</span>',
            self.block,
        )
        assert m is not None, "Trends tr-summary span not found"
        return m.group(1).strip()


if __name__ == "__main__":
    unittest.main()
