"""Regression tests for the 'What happened' card column-class adaptation.

Live problem: the grid hardcoded `col-4` for every headline card. When only
1 or 2 data sources produced headlines (today: GA4 + IG, no SEO because
Ubersuggest is not wired), the grid rendered 2 cards in `col-4 col-4` and left
a visible empty 4-column slot to the right. Fix: switch to `col-6 col-6`
when 2 cards, `col-12` when 1 card, `col-4 col-4 col-4` when 3 cards.

This test asserts the template contains a length-aware col picker that does
the right thing in all three cases.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HTML = REPO / "campaign-os.html"


def _read() -> str:
    return HTML.read_text(encoding="utf-8")


def _headline_grid_block(html: str) -> str:
    """Extract the grid that hosts `.ins-headline` cards."""
    m = re.search(
        r'<div class="grid"[^>]*>\s*\$\{\(\(\) =>.*?\}\)\(\)\}\s*</div>',
        html,
        flags=re.DOTALL,
    )
    assert m, "The 'What happened' grid must use the length-aware col picker"
    return m.group(0)


class WhatHappenedGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read()
        cls.grid = _headline_grid_block(cls.html)

    def test_grid_uses_iife_col_picker(self):
        # The grid must not still use the static col-4 for every card.
        self.assertIn("(() => {", self.grid)
        self.assertIn("const colCls = hs.length === 3", self.grid)
        self.assertIn("hs.length === 2", self.grid)

    def test_col_picker_has_all_three_cases(self):
        # 3 cards -> col-4, 2 cards -> col-6, 1 card -> col-12
        self.assertIn("'col-4'", self.grid)
        self.assertIn("'col-6'", self.grid)
        self.assertIn("'col-12'", self.grid)

    def test_no_static_col4_only_template(self):
        # Guard: the broken `headlines.slice(0,3).map(...)` form must be gone.
        self.assertNotIn(
            'headlines.slice(0,3).map((h, i) => `<div class="card col-4 ins-headline',
            self.html,
        )

    def test_headline_cards_still_render(self):
        # Non-regression: every v2 card marker is still present.
        for marker in ("ins-headline", "What happened", "ins-data", "ins-take"):
            self.assertIn(marker, self.html)

    def test_no_smart_quotes_in_grid_block(self):
        # Standing rule
        for ch in ("\u2018", "\u2019", "\u201c", "\u201d"):
            self.assertNotIn(ch, self.grid)


if __name__ == "__main__":
    unittest.main()