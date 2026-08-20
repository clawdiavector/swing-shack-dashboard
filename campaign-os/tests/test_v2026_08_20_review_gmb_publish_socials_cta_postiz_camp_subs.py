"""v2026-08-20 — Seven remaining section subs that still showed a literal "—"

before the JS call finished. All seven now mirror their actual surface +
carry id + data-help + data-help-title, matching the pattern already shipped
for Ideas, Library, Performance, Calendar, Trends, Image Gen, Meme Lord,
Hooks, and Billboard Lab (10 sections total covered so far).

Sections swept this tick:
  1. Review queue  (id="review-summary",  overwritten by renderReview  ~line 7277)
  2. GMB drafts    (id="gmb-summary",     overwritten by renderGmb     ~line 7430)
  3. Publish pipe  (id="publish-summary", overwritten by renderPublish ~line 8116)
  4. Socials       (id="socials-summary", overwritten by renderSocials ~line 8508)
  5. CTA Generator (id="cta-summary",     overwritten by cta render   ~line 10226)
  6. Postiz        (id="postiz-summary",  overwritten by renderPostiz  ~line 11298)
  7. Campaigns     (id="camp-summary",    overwritten by renderCamps   ~line 11356)

Standing rules covered: no em-dash (U+2014) or en-dash (U+2013) in any of the
7 fallback strings; middot separator (U+00B7) used to match the 10 already-
shipped sections; id + data-help + data-help-title all present.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HTML = ROOT / "campaign-os" / "campaign-os.html"

# (sub_id, required_phrases, short_name)
SECTIONS = [
    ("review-summary",  ["Pending inbox", "Approved", "Rejected", "Stale"], "Review"),
    ("gmb-summary",     ["Drafts list", "New draft", "push to Postiz", "templates"], "GMB"),
    ("publish-summary", ["4-stage flow", "Drafts", "Scheduled", "Published", "Failed"], "Publish"),
    ("socials-summary", ["IG history grid", "Meta Graph", "oEmbed", "Refresh"], "Socials"),
    ("cta-summary",     ["filter bar", "Just generated", "History", "Generate"], "CTA"),
    ("postiz-summary",  ["Postiz Queue", "Refs", "platform target"], "Postiz"),
    ("camp-summary",    ["Active", "archived", "Full plan", "Calendar", "active-campaign pill"], "Campaigns"),
]


class SevenPlaceholderDashesGone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def _span(self, sub_id):
        m = re.search(
            rf'<span\s+class="sub"\s+id="{sub_id}"[^>]*>([^<]+)</span>',
            self.html,
        )
        return m

    def test_01_no_placeholder_dashes_remain(self):
        """All seven <span class="sub" id="X-summary">—</span> placeholders
        must be gone. If any are still literal dashes, the JS overwrite
        window (which can be 100-800ms on slow networks) shows a confusing
        '—' instead of a self-describing sub."""
        for sub_id, _, _ in SECTIONS:
            with self.subTest(sub_id=sub_id):
                m = re.search(
                    rf'<span\s+class="sub"\s+id="{sub_id}">—</span>',
                    self.html,
                )
                self.assertIsNone(
                    m,
                    f"{sub_id} still has the literal-dash placeholder",
                )

    def test_02_each_sub_carries_id_data_help_and_data_help_title(self):
        """Every sub must carry id + data-help + data-help-title so the next
        editor gets the same affordance the 10 already-shipped sections have."""
        pat = re.compile(
            r'<span\s+class="sub"\s+id="[^"]+"\s+data-help="[^"]+"\s+data-help-title="What is in this section"',
        )
        for sub_id, _, _ in SECTIONS:
            with self.subTest(sub_id=sub_id):
                m = re.search(
                    rf'<span\s+class="sub"\s+id="{sub_id}"\s+data-help="[^"]+"\s+data-help-title="What is in this section"',
                    self.html,
                )
                self.assertTrue(
                    m,
                    f"{sub_id} missing data-help or data-help-title='What is in this section'",
                )

    def test_03_each_sub_lists_visible_cards(self):
        """Each descriptive fallback must list the visible sub-cards / actions
        so a first-time visitor knows what lives below before the JS call lands."""
        for sub_id, phrases, _name in SECTIONS:
            with self.subTest(sub_id=sub_id):
                m = self._span(sub_id)
                self.assertTrue(m, f"{sub_id} span not found")
                if m is None:  # pragma: no cover (assertTrue above)
                    continue
                text = m.group(1)
                missing = [p for p in phrases if p not in text]
                self.assertEqual(
                    missing,
                    [],
                    f"{sub_id} fallback is missing required phrases: {missing}",
                )

    def test_04_no_em_dash_or_en_dash_in_any_sub(self):
        """Standing rule: no em-dash (U+2014) or en-dash (U+2013) in published
        copy / sub text. Replaces must use middot or colon or parens."""
        for sub_id, _, _ in SECTIONS:
            with self.subTest(sub_id=sub_id):
                m = self._span(sub_id)
                self.assertTrue(m)
                if m is None:  # pragma: no cover
                    continue
                text = m.group(1)
                self.assertNotIn(
                    "\u2014",
                    text,
                    f"em dash (U+2014) found in {sub_id}",
                )
                self.assertNotIn(
                    "\u2013",
                    text,
                    f"en dash (U+2013) found in {sub_id}",
                )

    def test_05_each_sub_uses_middot_separator(self):
        """The 10 already-shipped sections all use middot (U+00B7) as the
        separator. New sub must have at least 3 middots to keep the visual
        rhythm consistent."""
        for sub_id, _, _ in SECTIONS:
            with self.subTest(sub_id=sub_id):
                m = self._span(sub_id)
                self.assertTrue(m)
                if m is None:  # pragma: no cover
                    continue
                text = m.group(1)
                count = text.count("\u00B7")
                self.assertGreaterEqual(
                    count,
                    3,
                    f"{sub_id} uses middot only {count} times "
                    f"(expected 3+ to match the established pattern)",
                )

    def test_06_static_fallback_meaningful_length(self):
        """The static fallback must be longer than the old "—" (1 char).
        Real sub text is 100+ chars. Anything under 60 chars is a regression."""
        for sub_id, _, _ in SECTIONS:
            with self.subTest(sub_id=sub_id):
                m = self._span(sub_id)
                self.assertTrue(m)
                if m is None:  # pragma: no cover
                    continue
                text = m.group(1)
                self.assertGreater(
                    len(text),
                    60,
                    f"{sub_id} static fallback is too short ({len(text)} chars)",
                )
                self.assertNotEqual(
                    text,
                    "—",
                    f"{sub_id} is back to the literal dash",
                )

    def test_07_js_overwrite_paths_still_intact(self):
        """All seven subs have JS overwrites that set the dynamic summary
        string when the API call returns. The static fallback is the
        'before API' / 'API failed' frame; the dynamic value wins once
        the API responds. This test documents the contract so a future
        editor cannot drop the static fallback without realising the
        overwrite needs to keep firing."""
        # Each (sub_id, the line that does the overwrite, the regex that
        # proves the overwrite is still in the file)
        # Real JS in the HTML uses single-quoted selectors: $("#x-summary")
        # The test patterns must include the optional leading quote so the
        # regex actually matches the line that overwrites the sub.
        contract = [
            ("review-summary",  r"\$\(['\"]\#review-summary['\"]\)\.textContent\s*=\s*r\.summary"),
            ("gmb-summary",     r"const\s+summary\s*=\s*\$\(['\"]\#gmb-summary['\"]\)"),
            ("publish-summary", r"\$\(['\"]\#publish-summary['\"]\)\.textContent\s*=\s*p\.summary"),
            # socials uses a local `summary` var instead of a chained selector.
            # The line that picks it up is `const summary = $('#socials-summary');`
            # and the line that overwrites it is `summary.textContent = ...`.
            # Match the local-var assignment so future renames still get caught.
            ("socials-summary", r"const\s+summary\s*=\s*\$\(['\"]\#socials-summary['\"]\)"),
            ("cta-summary",     r"\$\(['\"]\#cta-summary['\"]\)\.textContent"),
            ("postiz-summary",  r"\$\(['\"]\#postiz-summary['\"]\)\.textContent\s*=\s*p\.summary"),
            ("camp-summary",    r"\$\(['\"]\#camp-summary['\"]\)\.textContent\s*=\s*ids\.length"),
        ]
        for sub_id, pattern in contract:
            with self.subTest(sub_id=sub_id):
                self.assertRegex(
                    self.html,
                    pattern,
                    f"{sub_id} JS overwrite path is missing or moved",
                )

    def test_08_data_help_includes_sub_change_rationale(self):
        """Each data-help long-text should explicitly say the old behaviour
        (literal dash) so the next editor can grep for it later and see the
        change history directly in the source. Locks the explanatory breadcrumb
        pattern already used in the 10 already-shipped sections."""
        for sub_id, _, _ in SECTIONS:
            with self.subTest(sub_id=sub_id):
                m = re.search(
                    rf'<span\s+class="sub"\s+id="{sub_id}"[^>]*data-help="([^"]+)"',
                    self.html,
                )
                self.assertTrue(m, f"{sub_id} data-help attribute missing")
                if m is None:  # pragma: no cover
                    continue
                help_text = m.group(1)
                self.assertIn(
                    "literal dash",
                    help_text,
                    f"{sub_id} data-help should mention the old 'literal dash' "
                    f"behaviour so the next editor sees the change history",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
