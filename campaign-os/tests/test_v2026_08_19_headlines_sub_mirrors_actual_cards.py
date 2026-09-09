"""v2026-08-19 — Headline Generator section sub mirrors actual surface.

Eighth in the static-sub pattern series (after Ideas, Library, Performance,
Calendar, Trends, Image Gen, Meme Lord, Hook Bank). The Headlines
`head-summary` previously was just a JS-overwritten literal
("Click Generate to produce 5 fresh headlines from current signals.").
Now:
- shows a descriptive static fallback that names the filter bar, the
  Just generated stack, the History stack, and the clear-history helper
- carries id + data-help + data-help-title for next-editor context
- no em dashes (standing rule)
- middot separator matching the established pattern across seven other
  sections

The JS overwrite (renderHeadlines tail line ~10066) still runs and the
dynamic summary wins once the API responds, so this only matters on the
brief window between section render and API response, plus as a
slow-API fallback, exactly the same contract as the seven prior sub fixes.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HTML = ROOT / "campaign-os" / "campaign-os.html"


class HeadlineGeneratorSubMirrorsActualCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_01_head_sub_has_id(self):
        # The static sub must carry the id="head-summary" anchor.
        m = re.search(
            r'<span\s+class="sub"\s+id="head-summary"[^>]*>',
            self.html,
        )
        self.assertTrue(m, "head-summary span with class=\"sub\" and id is missing")

    def test_02_old_dash_placeholder_gone(self):
        # The old "—"-only fallback should no longer be present.
        m = re.search(
            r'<span\s+class="sub"\s+id="head-summary">—</span>',
            self.html,
        )
        self.assertIsNone(
            m,
            "old `—`-only fallback still present in head-summary span",
        )

    def test_03_sub_has_data_help(self):
        # The pattern requires data-help and data-help-title for the next editor.
        m = re.search(
            r'<span\s+class="sub"\s+id="head-summary"\s+data-help="[^"]+"\s+data-help-title="[^"]+"',
            self.html,
        )
        self.assertTrue(
            m,
            "head-summary span missing data-help or data-help-title attributes",
        )

    def test_04_sub_lists_visible_cards(self):
        # The descriptive fallback must name every visible card / surface.
        # Required phrases:
        #   filter bar · Just generated · History · clear-history
        m = re.search(
            r'<span\s+class="sub"\s+id="head-summary"[^>]*>([^<]+)</span>',
            self.html,
        )
        self.assertTrue(m, "could not locate head-summary <span>...</span>")
        text = m.group(1)
        required = [
            "filter bar",
            "Just generated",
            "History",
            "clear-history",
        ]
        missing = [r for r in required if r not in text]
        self.assertEqual(
            missing,
            [],
            f"descriptive fallback is missing required phrases: {missing}",
        )

    def test_05_sub_no_em_dash(self):
        # Standing rule: no em dash (U+2014) or en dash (U+2013) in published
        # copy / sub text. Both are banned to keep social copy typography honest.
        m = re.search(
            r'<span\s+class="sub"\s+id="head-summary"[^>]*>([^<]+)</span>',
            self.html,
        )
        self.assertTrue(m)
        text = m.group(1)
        self.assertNotIn("\u2014", text, "em dash (U+2014) found in head sub")
        self.assertNotIn("\u2013", text, "en dash (U+2013) found in head sub")

    def test_06_sub_uses_middot_separator(self):
        # Middot (U+00B7) is the standard separator on the other seven sub
        # sections. At least three middots to show the descriptive list pattern.
        m = re.search(
            r'<span\s+class="sub"\s+id="head-summary"[^>]*>([^<]+)</span>',
            self.html,
        )
        text = m.group(1)
        middot_count = text.count("\u00B7")
        self.assertGreaterEqual(
            middot_count,
            3,
            f"head sub uses middot separator only {middot_count} times "
            f"(expected 3+ to match the established pattern)",
        )

    def test_07_static_fallback_kept_meaningful(self):
        # Pattern is shared with hooks: there IS a JS overwrite
        # (renderHeadlines sets the saved-batch count when history is
        # non-empty, or 'Click Generate…' as a no-history fallback), so we
        # lock the contract that the static sub AND the dynamic value
        # coexist. The overwrite is correct usage; the test just documents
        # that the static fallback is the "before API responds" /
        # "API failed" frame, mirroring test_07 in the other sub files.
        static = re.search(
            r'<span\s+class="sub"\s+id="head-summary"[^>]*>([^<]+)</span>',
            self.html,
        )
        self.assertTrue(static)
        static_text = static.group(1)
        self.assertGreater(len(static_text), 60, "static sub is too short")

        # JS overwrite via .textContent is fine, but the static fallback
        # must remain meaningful (longer than the old "—").
        self.assertNotEqual(static_text, "\u2014")
        self.assertNotEqual(static_text.strip(), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
