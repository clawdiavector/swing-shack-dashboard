"""
Regression test for Ideas page empty-card collapse.

Verifies the CSS rule that prevents empty grid cards (currently the
'Missed opportunities' and 'Funnel leaks' cards when no items are present)
from stretching to match their row-tallest sibling height. Before the fix,
each empty card occupied ~556-693px of vertical space. After the fix,
empty cards collapse to ~50px.

The rule under test (campaign-os.html, near line 345):
  .card:has(> div > .empty:only-child){align-self:start}

Static grep checks the rule is present + correctly scoped. Rendered-height
checks would require a live browser session — covered by the nightshift
walkthrough capture at /tmp/co-nightshift/walkthrough_*_ideas_empty_collapse.png.
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CAMPAIGN_OS_HTML = REPO / "campaign-os" / "campaign-os.html"


class IdeasEmptyCollapseTests(unittest.TestCase):
    """Empty Ideas cards must collapse, not stretch with row siblings."""

    @classmethod
    def setUpClass(cls):
        cls.html = CAMPAIGN_OS_HTML.read_text(encoding="utf-8")

    def test_empty_card_collapse_rule_present(self):
        # As of the 2026-08-12 nightshift fix, the rule now also promotes the
        # slim empty banner to a full-width row (grid-column:1 / -1) so it
        # doesn't sit as a tiny stub alongside tall siblings like Upsells /
        # Bundles. The align-self:start part is what kept it from stretching.
        self.assertIn(
            ".card:has(> div > .empty:only-child)",
            self.html,
            "Empty-card collapse rule missing — empty Ideas cards will "
            "stretch to row-tallest sibling height again.",
        )
        self.assertIn("align-self:start", self.html)
        self.assertIn(
            "grid-column:1 / -1",
            self.html,
            "Slim empty banner is not promoted to full-width row — "
            "empty cards will sit as tiny stubs beside tall siblings.",
        )

    def test_empty_collapse_block_still_intact(self):
        # The new rule sits inside the existing empty-card collapse block
        # (Option A: slim banners). Make sure we didn't accidentally delete
        # the inner-display or text-styling rules it pairs with.
        self.assertIn(".card:has(> div > .empty:only-child) > div:has(.empty:only-child){display:inline}", self.html)
        self.assertIn(".card:has(> div > .empty:only-child) .empty{font-size:11.5px", self.html)

    def test_rule_is_scoped_to_empty_cards_only(self):
        # The rule must NOT be a generic .card align-self — that would
        # break alignment of content-rich cards (Upsells, Bundles, etc.).
        # It must remain scoped via :has(> div > .empty:only-child).
        self.assertNotIn(".card{align-self:start}", self.html)
        self.assertNotIn(".card{grid-column:1 / -1}", self.html)


if __name__ == "__main__":
    unittest.main(verbosity=2)