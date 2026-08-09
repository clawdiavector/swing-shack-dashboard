"""Regression tests for the Socials 'How to read this view' lens banner.

Mirrors the `test_v2026_08_09_insights_lens_ctx.py` invariants: a static-HTML
probe that the banner block exists inside `#sec-socials`, sits before the
filter card, explains the two sources (Meta Graph + oEmbed) + the status pill
colours, and cross-links Meme Lord / Learning. No server required.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HTML = REPO / "campaign-os.html"


def _read() -> str:
    return HTML.read_text(encoding="utf-8")


def _sec_socials_slice(html: str) -> str:
    m = re.search(
        r'<section[^>]*id="sec-socials"[^>]*>(.*?)</section>',
        html,
        flags=re.DOTALL,
    )
    assert m, "sec-socials section must exist in campaign-os.html"
    return m.group(1)


class SocialsLensCtx(unittest.TestCase):
    def setUp(self) -> None:
        self.html = _read()
        self.slice = _sec_socials_slice(self.html)

    def test_banner_block_present(self):
        self.assertIn(
            'class="card col-12 socials-lens-ctx"',
            self.slice,
            "socials-lens-ctx banner must live inside #sec-socials",
        )

    def test_banner_sits_before_filter_card(self):
        banner_idx = self.slice.find("socials-lens-ctx")
        filter_idx = self.slice.find('id="socials-days"')
        self.assertGreater(banner_idx, -1, "banner must exist")
        self.assertGreater(filter_idx, -1, "filter card must exist")
        self.assertLess(
            banner_idx,
            filter_idx,
            "banner must be painted BEFORE the Range/Type filter card so users see it first",
        )

    def test_banner_sits_after_connect_cta(self):
        cta_idx = self.slice.find('id="socials-connect-cta"')
        banner_idx = self.slice.find("socials-lens-ctx")
        self.assertGreater(cta_idx, -1, "connect CTA must exist")
        self.assertGreater(banner_idx, -1, "banner must exist")
        self.assertLess(
            cta_idx,
            banner_idx,
            "Connect Instagram CTA keeps its current slot (it explains the next step), the lens banner sits below it",
        )

    def test_banner_explains_two_sources(self):
        self.assertIn("Meta Graph", self.slice, "banner must mention Meta Graph")
        self.assertIn("oEmbed", self.slice, "banner must mention oEmbed fallback")

    def test_banner_documents_status_pill_legend(self):
        for tone in ("🟢 live", "⚪ empty", "🔌 not wired"):
            self.assertIn(
                tone,
                self.slice,
                f"status pill legend must include '{tone}' so the colour-to-meaning mapping is unambiguous",
            )

    def test_banner_cross_links_meme_and_learning(self):
        self.assertIn("Meme Lord", self.slice, "banner must cross-link Meme Lord")
        self.assertIn("Learning", self.slice, "banner must cross-link 🧠 Learning")

    def test_banner_no_smart_quote_artifacts(self):
        # The Insights v2 banner had a regression on smart quotes once. Make sure
        # none of the typographically-decoded quote marks snuck into the copy.
        for bad in ("\u201c", "\u201d", "\u2018", "\u2019"):
            self.assertNotIn(
                bad,
                self.slice.split("socials-lens-ctx", 1)[1].split("</div>", 1)[0],
                f"banner must not contain smart-quote char U+{ord(bad):04X}",
            )

    def test_no_duplicate_banner(self):
        # Two banners would be a maintenance trap (the Insights v2 lane has a
        # known dead-code duplicate that bites the next reader). Lock the invariant.
        self.assertEqual(
            self.slice.count("socials-lens-ctx"),
            1,
            "socials-lens-ctx banner must appear exactly once in #sec-socials",
        )

    def test_other_tabs_unchanged(self):
        # Sanity: adding the Socials banner must not regress the Insights banner.
        full = self.html
        self.assertEqual(
            full.count("insights-lens-ctx"),
            2,
            "Insights v2 banner (live + dead-code clone) must still appear twice — no regression on the prior lane",
        )


if __name__ == "__main__":
    unittest.main()