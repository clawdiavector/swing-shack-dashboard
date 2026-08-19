"""test_v2026_08_19_imagegen_sub_mirrors_actual_cards.py

Regression: the Image Generation (sec-imagegen) <span class="sub"> was a
tag list "Provider-ready prompt specs: Ideogram · DALL-E · Midjourney ·
Stable Diffusion" that only listed the 4 output providers. It did not
tell a first-time visitor what sub-cards actually live below the section
header. The real surface is a Visual Recipe card (matches against the
active brand's approved image library) and a Prompt Spec card (with
Reference prompt, Negative prompt, Color keywords, Platform config,
Composition, and a Hook / Subject override). Each provider gets its own
dialed-in prompt via the provider tabs; the meta line shows brand-fit
score and a Visual DNA recipe.

Fix: the static sub now mirrors the actual surface
"Visual Recipe from Brand Library · Prompt Spec (Reference · Negative ·
Colors · Platform · Composition · Hook) · 4 providers · brand-fit
score" and carries id="ig-summary" + data-help + data-help-title for
next-editor context. No JS path overwrites this sub (verified: no
`#ig-summary` textContent setter anywhere in the file), so the static
text is the first-frame AND steady-state description.

The test reads the static <section id="sec-imagegen">...</section>
block from campaign-os.html and asserts:

  1. The old tag-list sub ("Provider-ready prompt specs: Ideogram …
     Midjourney … Stable Diffusion") is gone.
  2. The new descriptive sub string is present and names every visible
     sub-card (Visual Recipe · Prompt Spec · Reference · Negative ·
     Colors · Platform · Composition · Hook · 4 providers · brand-fit
     score).
  3. The sub is wrapped in <span class="sub" id="ig-summary">…</span>.
  4. The sub carries data-help and data-help-title (next-editor hint).
  5. The sub contains no em-dashes (standing rule).
  6. The sub uses · (middot) separators, consistent with the rest of
     Campaign OS.
  7. No JS path overwrites #ig-summary's textContent, so the static
     fallback is the steady-state description (unlike Calendar which
     has a dynamic summary slot).

Pattern mirrors campaign-os/tests/test_v2026_08_19_calendar_sub_mirrors_actual_cards.py
and campaign-os/tests/test_v2026_08_19_trends_sub_mirrors_actual_cards.py.
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


def _extract_sub_span(section_html: str) -> str:
    """Return the first <span class="sub" ...>...</span> in the section header."""
    # Greedy enough to span the whole data-help attribute (which contains
    # the breadcrumb of the old sub text inside it).
    m = re.search(
        r'<span class="sub"[^>]*>(.*?)</span>',
        section_html,
        re.DOTALL,
    )
    assert m, "no <span class=\"sub\"> found in section block"
    return m.group(0)


class TestImagegenSubMirrorsActualCards(unittest.TestCase):
    """The Image Generation <span class="sub" id="ig-summary"> mirrors the actual sub-cards."""

    @classmethod
    def setUpClass(cls):
        with open(HTML_PATH, "r", encoding="utf-8") as fh:
            cls.html = fh.read()
        cls.section = _section_block(cls.html, "sec-imagegen")
        cls.sub_span = _extract_sub_span(cls.section)

    def test_01_old_tag_list_sub_is_gone(self):
        """The old provider-only tag list is no longer the visible sub."""
        # The old text may still live INSIDE the data-help attribute as a
        # breadcrumb of what we replaced. We assert the visible <span
        # class="sub"> text does NOT equal the old text.
        old = "Provider-ready prompt specs: Ideogram · DALL-E · Midjourney · Stable Diffusion"
        # Find the sub span's text node content (between > and </span>,
        # not inside attributes). The first > after class="sub" is the
        # close of the opening tag.
        first_close = self.sub_span.find(">")
        text = self.sub_span[first_close + 1 : -len("</span>")]
        self.assertNotEqual(
            text.strip(),
            old.strip(),
            "old tag-list sub is still the visible sub text on sec-imagegen",
        )
        self.assertNotIn(
            "Provider-ready prompt specs",
            text,
            "old 'Provider-ready prompt specs' phrase leaked into the visible sub text",
        )

    def test_02_new_descriptive_sub_lists_every_visible_card(self):
        """The new sub names the 2 main cards and all 6 Prompt Spec sub-fields."""
        first_close = self.sub_span.find(">")
        text = self.sub_span[first_close + 1 : -len("</span>")]
        expected_phrases = [
            "Visual Recipe from Brand Library",
            "Prompt Spec",
            "Reference",
            "Negative",
            "Colors",
            "Platform",
            "Composition",
            "Hook",
            "4 providers",
            "brand-fit score",
        ]
        for phrase in expected_phrases:
            self.assertIn(
                phrase,
                text,
                f"new imagegen sub missing required phrase: {phrase!r}",
            )

    def test_03_sub_uses_standard_pattern(self):
        """The sub is wrapped in <span class="sub" id="ig-summary" ...>."""
        self.assertIn('class="sub"', self.sub_span)
        self.assertIn('id="ig-summary"', self.sub_span)
        self.assertTrue(
            self.sub_span.startswith('<span class="sub"'),
            f"sub span should start with '<span class=\"sub\"', got: {self.sub_span[:60]!r}",
        )

    def test_04_sub_has_data_help(self):
        """The sub carries data-help= and data-help-title= for next-editor context."""
        self.assertIn("data-help=", self.sub_span)
        self.assertIn("data-help-title=", self.sub_span)
        # data-help-title value should be the standard 'What is in this section'
        m = re.search(r'data-help-title="([^"]+)"', self.sub_span)
        self.assertTrue(m, "no data-help-title attribute found")
        self.assertEqual(
            m.group(1),
            "What is in this section",
            "data-help-title should be 'What is in this section'",
        )

    def test_05_sub_no_em_dash(self):
        """No em-dash (U+2014) or en-dash (U+2013) in the visible sub text (standing rule)."""
        first_close = self.sub_span.find(">")
        text = self.sub_span[first_close + 1 : -len("</span>")]
        self.assertNotIn("\u2014", text, "em-dash U+2014 found in new imagegen sub")
        self.assertNotIn("\u2013", text, "en-dash U+2013 found in new imagegen sub")

    def test_06_sub_uses_middot_separator(self):
        """The sub uses · (U+00B7) separators, 4+ of them."""
        first_close = self.sub_span.find(">")
        text = self.sub_span[first_close + 1 : -len("</span>")]
        middot_count = text.count("\u00b7")
        self.assertGreaterEqual(
            middot_count,
            4,
            f"new imagegen sub should use 4+ middot separators, found {middot_count}",
        )

    def test_07_no_js_textContent_overwrite_on_ig_summary(self):
        """No JS path overwrites #ig-summary's textContent, so the static sub IS the steady-state."""
        # Look for any textContent assignment on the ig-summary id.
        patterns = [
            r'getElementById\(\s*[\'"]ig-summary[\'"]\s*\)\.textContent',
            r'\$\(\s*[\'"]#ig-summary[\'"]\s*\)\.textContent',
            r'\$\(\s*[\'"]#ig-summary[\'"]\s*\)\.html\(',
            r'document\.getElementById\(\s*[\'"]ig-summary[\'"]\s*\)',
        ]
        for pat in patterns:
            m = re.search(pat, self.html)
            self.assertIsNone(
                m,
                f"unexpected JS overwrite path for #ig-summary found: {pat!r} at offset {m.start() if m else 'n/a'}",
            )


if __name__ == "__main__":
    unittest.main()
