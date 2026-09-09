"""v2026-08-20 — Two final section subs (Insights v2 + SEO Audit) that still
showed a literal loading placeholder before the JS call finished. They now
mirror their actual surface + carry id + data-help + data-help-title, matching
the pattern already shipped for Review, GMB, Publish, Socials, CTA, Postiz,
Campaigns (the b40b7fe sweep) and the 10 sections covered before that.

Sections swept this tick:
  1. Insights v2   (id="ins-v2-summary", overwritten by renderInsights ~line 5128)
  2. SEO Audit     (id="sa-summary",     overwritten by renderSEOAudit ~line 10887)

Standing rules covered: no em-dash (U+2014) or en-dash (U+2013) in either
fallback string; middot separator (U+00B7) used to match the 17 already-
shipped sections; id + data-help + data-help-title all present.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HTML = ROOT / "campaign-os" / "campaign-os.html"

# (sub_id, required_phrases, short_name, old_placeholder_phrase)
SECTIONS = [
    (
        "ins-v2-summary",
        ["Insight strip", "stat tiles", "top IG", "A/B tests", "weekly report"],
        "Insights v2",
        "loading…",
    ),
    (
        "sa-summary",
        ["Health score", "filter bar", "findings", "fix-it"],
        "SEO Audit",
        "Auditing site",
    ),
]


class TwoLoadingPlaceholdersGone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def _span(self, sub_id):
        m = re.search(
            rf'<span\s+class="sub"\s+id="{sub_id}"[^>]*>([^<]+)</span>',
            self.html,
        )
        return m

    def test_01_no_old_loading_placeholders_remain(self):
        """Both <span class="sub" id="X-summary">…</span> placeholders must
        be gone. If any are still the old loading string, the JS overwrite
        window (which can be 100-800ms on slow networks) shows a confusing
        'loading…' / 'Auditing site…' instead of a self-describing sub."""
        for sub_id, _, _name, old in SECTIONS:
            with self.subTest(sub_id=sub_id):
                m = re.search(
                    rf'<span\s+class="sub"\s+id="{sub_id}"[^>]*>{re.escape(old)}',
                    self.html,
                )
                self.assertIsNone(
                    m,
                    f"{sub_id} still has the old loading placeholder",
                )

    def test_02_each_sub_carries_id_data_help_and_data_help_title(self):
        """Every sub must carry id + data-help + data-help-title so the next
        editor gets the same affordance the 17 already-shipped sections have."""
        for sub_id, _, _name, _ in SECTIONS:
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
        for sub_id, phrases, _name, _ in SECTIONS:
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
        for sub_id, _, _name, _ in SECTIONS:
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
        """The 17 already-shipped sections all use middot (U+00B7) as the
        separator. New sub must have at least 3 middots to keep the visual
        rhythm consistent."""
        for sub_id, _, _name, _ in SECTIONS:
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
        """The static fallback must be longer than the old placeholder
        ('loading…' is 9 chars; 'Auditing site…' is 15 chars). Real sub
        text is 100+ chars. Anything under 60 chars is a regression."""
        for sub_id, _, _name, _ in SECTIONS:
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

    def test_07_js_overwrite_paths_still_intact(self):
        """Both subs have JS overwrites that set the dynamic summary string
        when the API call returns. The static fallback is the 'before API' /
        'API failed' frame; the dynamic value wins once the API responds.
        This test documents the contract so a future editor cannot drop the
        static fallback without realising the overwrite needs to keep firing."""
        contract = [
            # Insights v2 uses a local `summary` var; the line that picks
            # it up is `const summary = $('#ins-v2-summary');` and the line
            # that overwrites it is `summary.textContent = ...`.
            ("ins-v2-summary", r"const\s+summary\s*=\s*\$\(['\"]\#ins-v2-summary['\"]\)"),
            # SEO Audit overwrites sa-summary directly.
            ("sa-summary", r"\$\(['\"]\#sa-summary['\"]\)\.textContent"),
        ]
        for sub_id, pattern in contract:
            with self.subTest(sub_id=sub_id):
                self.assertRegex(
                    self.html,
                    pattern,
                    f"{sub_id} JS overwrite path is missing or moved",
                )

    def test_08_data_help_includes_old_placeholder_rationale(self):
        """Each data-help long-text should explicitly say what the old
        placeholder was (literal 'loading…' or 'Auditing site…') so the next
        editor can grep for it later and see the change history directly in
        the source. Locks the explanatory breadcrumb pattern already used in
        the 17 already-shipped sections."""
        for sub_id, _, _name, old in SECTIONS:
            with self.subTest(sub_id=sub_id):
                m = re.search(
                    rf'<span\s+class="sub"\s+id="{sub_id}"[^>]*data-help="([^"]+)"',
                    self.html,
                )
                self.assertTrue(m, f"{sub_id} data-help attribute missing")
                if m is None:  # pragma: no cover
                    continue
                help_text = m.group(1)
                # Match either the literal placeholder phrase or the structural
                # description of the old behaviour. 'loading…' and 'Auditing
                # site…' both show up as a 'placeholder / loading state'.
                self.assertTrue(
                    old in help_text or "loading state" in help_text,
                    f"{sub_id} data-help should mention the old '{old}' "
                    f"placeholder so the next editor sees the change history",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
