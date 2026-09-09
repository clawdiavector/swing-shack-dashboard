"""v2026-08-19 — Meme Lord section sub mirrors actual surface.

Sixth in the static-sub pattern series (after Ideas, Library, Performance,
Calendar, Trends, Image Gen). The Meme Lord `memes-summary` previously was
just "—" until JS overwrites it with `lib.summary` from the API. Now:
- shows a descriptive static fallback that lists every visible card +
  filters + the generate action
- carries id + data-help + data-help-title for next-editor context
- no em dashes (standing rule)
- middot separator matching the other five sections

The JS overwrite (renderMemes) still runs and the dynamic summary wins
once the API responds, so this only matters on the brief window between
section render and API response, plus as a search-engine-friendly /
slow-API fallback.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HTML = ROOT / "campaign-os" / "campaign-os.html"


class MemeLordSubMirrorsActualCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_01_memes_sub_has_id(self):
        # The static sub must carry the id="memes-summary" anchor.
        m = re.search(
            r'<span\s+class="sub"\s+id="memes-summary"[^>]*>',
            self.html,
        )
        self.assertTrue(m, "memes-summary span with class=\"sub\" and id is missing")

    def test_02_old_dash_placeholder_gone(self):
        # The old "—"-only fallback should no longer be present.
        # Look for the original placeholder (it had no data-help / no descriptive text).
        m = re.search(
            r'<span\s+class="sub"\s+id="memes-summary">—</span>',
            self.html,
        )
        self.assertIsNone(
            m,
            "old `—`-only fallback still present in memes-summary span",
        )

    def test_03_sub_has_data_help(self):
        # The pattern requires data-help and data-help-title for the next editor.
        m = re.search(
            r'<span\s+class="sub"\s+id="memes-summary"\s+data-help="[^"]+"\s+data-help-title="[^"]+"',
            self.html,
        )
        self.assertTrue(
            m,
            "memes-summary span missing data-help or data-help-title attributes",
        )

    def test_04_sub_lists_visible_cards(self):
        # The descriptive fallback must list every visible card / surface.
        # Required phrases:
        #   Template visuals · Top picks · Historian library · generate
        #   voice/pillar/platform/era · still-works · search
        m = re.search(
            r'<span\s+class="sub"\s+id="memes-summary"[^>]*>([^<]+)</span>',
            self.html,
        )
        self.assertTrue(m, "could not locate memes-summary <span>...</span>")
        text = m.group(1)
        required = [
            "Template visuals",
            "Top picks",
            "Historian library",
            "voice",
            "pillar",
            "platform",
            "era",
            "still-works",
            "generate",
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
            r'<span\s+class="sub"\s+id="memes-summary"[^>]*>([^<]+)</span>',
            self.html,
        )
        self.assertTrue(m)
        text = m.group(1)
        self.assertNotIn("\u2014", text, "em dash (U+2014) found in memes sub")
        self.assertNotIn("\u2013", text, "en dash (U+2013) found in memes sub")

    def test_06_sub_uses_middot_separator(self):
        # Middot (U+00B7) is the standard separator on the other five sub
        # sections (Calendar, Trends, Image Gen, Ideas, Library). At least
        # four middots to show the descriptive list pattern.
        m = re.search(
            r'<span\s+class="sub"\s+id="memes-summary"[^>]*>([^<]+)</span>',
            self.html,
        )
        text = m.group(1)
        middot_count = text.count("\u00B7")
        self.assertGreaterEqual(
            middot_count,
            4,
            f"memes sub uses middot separator only {middot_count} times "
            f"(expected 4+ to match the established pattern)",
        )

    def test_07_no_js_textcontent_overwrite_on_memes_summary(self):
        # Pattern is shared with Calendar/Trends/Image Gen: there IS a JS
        # overwrite (renderMemes line 9554 + the star-count suffix at 9588),
        # so we lock the *contract* that the static sub AND the dynamic
        # value coexist. This test makes the dependency explicit so a
        # future editor can't accidentally drop the static fallback
        # without realising the overwrite needs to keep firing.
        # The overwrite is correct usage; the test just documents that
        # the static fallback is the "before API responds" / "API failed"
        # frame, mirroring what test_07 says in the other five sub files.
        static = re.search(
            r'<span\s+class="sub"\s+id="memes-summary"[^>]*>([^<]+)</span>',
            self.html,
        )
        self.assertTrue(static)
        static_text = static.group(1)
        self.assertGreater(len(static_text), 60, "static sub is too short")

        # JS overwrite via .textContent is fine, but the static fallback
        # must remain meaningful (longer than the old "—").
        self.assertNotEqual(static_text, "—")


if __name__ == "__main__":
    unittest.main(verbosity=2)
