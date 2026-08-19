"""test_v2026_08_19_calendar_sub_mirrors_actual_cards.py

Regression: the Calendar section's <span class="sub" id="cal-summary"> was
a literal "—" placeholder that stayed blank on first paint until the
`renderCalendar()` JS call resolved (~100 ms after page load). A first-time
visitor landing on /campaign-os would see a Calendar section header with no
description of what lives inside it for the first ~100 ms, then a dynamic
"X planned in next 14 days · Y today · see Publish page for Postiz queue"
summary line. The placeholder gave no clue what surfaces live below.

Fix: the static sub now mirrors the actual surface (14-day grid with
drag-drop · today's HUD · pillar strip · duplicate zone) and carries
data-help + data-help-title so the next editor sees why the line exists.
The JS still overwrites `textContent` on resolve — the live
"X planned · Y today · see Publish" string — but the data-help anchor and
the fallback text describe the surface immediately on first paint.

The test reads the static <section id="sec-calendar">...</section> block
from campaign-os.html and asserts:

  1. The literal "—" placeholder sub is gone.
  2. The new descriptive sub string is present and names every visible
     surface (14-day grid with drag-drop · today's HUD · pillar strip ·
     duplicate zone).
  3. The sub is wrapped in <span class="sub" id="cal-summary">…</span>.
  4. The sub carries data-help and data-help-title (next-editor hint).
  5. The sub contains no em-dashes (standing rule).
  6. The sub uses · (middot) separators, consistent with the rest of
     Campaign OS.
  7. The JS overwrite path (renderCalendar line that sets textContent on
     #cal-summary) is still present, so the static fallback is just a
     first-paint placeholder — live numbers still replace it after JS
     resolves.

Pattern mirrors campaign-os/tests/test_v2026_08_19_performance_sub_matches_actual_cards.py
and campaign-os/tests/test_v2026_08_19_section_sub_matches_actual_cards.py.
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


class TestCalendarSubMirrorsActualCards(unittest.TestCase):
    """The Calendar <span class="sub" id="cal-summary"> mirrors the actual sub-cards."""

    @classmethod
    def setUpClass(cls):
        with open(HTML_PATH, "r", encoding="utf-8") as fh:
            cls.html = fh.read()
        cls.block = _section_block(cls.html, "sec-calendar")

    def test_01_dash_placeholder_sub_is_gone(self):
        """The literal "—" placeholder is removed in favour of a descriptive sub."""
        # The pre-fix sub was literally: <span class="sub" id="cal-summary">—</span>
        # Use the HTML-escaped entity form first (the literal em-dash in source).
        self.assertNotRegex(
            self.block,
            r'<span class="sub" id="cal-summary">\s*\u2014\s*</span>',
            "Calendar still carries the pre-fix literal dash placeholder",
        )
        # And the plain ASCII hyphen-dash variant if anyone regressed.
        self.assertNotRegex(
            self.block,
            r'<span class="sub" id="cal-summary">\s*-\s*</span>',
            "Calendar still carries a placeholder dash sub",
        )

    def test_02_new_descriptive_sub_lists_every_visible_card(self):
        """The new sub names every card on the page."""
        sub_match = re.search(
            r'<span class="sub" id="cal-summary"[^>]*>([^<]+)</span>',
            self.block,
        )
        self.assertIsNotNone(sub_match, "Calendar has no <span class=\"sub\" id=\"cal-summary\"> line")
        sub_text = sub_match.group(1)

        # Every visible sub-card on the Calendar surface must be named.
        for needle in (
            "14-day grid with drag-drop",
            "today's HUD",
            "pillar strip",
            "duplicate zone",
        ):
            self.assertIn(needle, sub_text, f"Calendar sub does not mention '{needle}'")

    def test_03_sub_uses_standard_pattern(self):
        """The sub is wrapped in <span class="sub" id="cal-summary">…</span>."""
        self.assertRegex(
            self.block,
            r'<span class="sub" id="cal-summary"[^>]*>[^<]+</span>',
            "Calendar sub is not wrapped in <span class=\"sub\" id=\"cal-summary\">…</span>",
        )

    def test_04_sub_has_data_help(self):
        """The sub carries data-help so the next editor sees why it exists."""
        sub_match = re.search(
            r'<span class="sub" id="cal-summary"([^>]*)>',
            self.block,
        )
        self.assertIsNotNone(sub_match, "Calendar has no <span class=\"sub\" id=\"cal-summary\">")
        attrs = sub_match.group(1)
        self.assertIn("data-help=", attrs, "Calendar sub missing data-help attribute")
        self.assertIn("data-help-title=", attrs, "Calendar sub missing data-help-title attribute")

    def test_05_sub_no_em_dash(self):
        """Standing rule: no em-dashes in published copy."""
        sub_match = re.search(
            r'<span class="sub" id="cal-summary"[^>]*>([^<]+)</span>',
            self.block,
        )
        self.assertIsNotNone(sub_match, "Calendar has no <span class=\"sub\" id=\"cal-summary\">")
        sub_text = sub_match.group(1)
        # Em-dash is U+2014. Also reject en-dash (U+2013) to keep style consistent.
        self.assertNotIn("\u2014", sub_text, "Calendar sub contains an em-dash")
        self.assertNotIn("\u2013", sub_text, "Calendar sub contains an en-dash")

    def test_06_sub_uses_middot_separator(self):
        """The sub uses · (middot) separators, consistent with the rest of Campaign OS."""
        sub_match = re.search(
            r'<span class="sub" id="cal-summary"[^>]*>([^<]+)</span>',
            self.block,
        )
        self.assertIsNotNone(sub_match, "Calendar has no <span class=\"sub\" id=\"cal-summary\">")
        sub_text = sub_match.group(1)
        self.assertIn("\u00b7", sub_text, "Calendar sub does not use · separators")

    def test_07_js_overwrite_still_wired(self):
        """The JS path that overwrites cal-summary textContent with the live count
        must still be present — the static fallback is only a first-paint
        placeholder; renderCalendar() must still replace it once data resolves."""
        # Look for the live-count overwrite inside renderCalendar.
        self.assertRegex(
            self.html,
            r"\$\(['\"]\#cal-summary['\"]\)\.textContent\s*=\s*data\.totalScheduled",
            "renderCalendar no longer overwrites #cal-summary with the live count",
        )


if __name__ == "__main__":
    unittest.main()
