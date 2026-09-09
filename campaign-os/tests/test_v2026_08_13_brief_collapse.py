"""v2026-08-13: brief-grid collapsed 'More signals' accordion.

The Today/Brief page used to render 6 large body cards below the KPI
stats (Hot right now, Do first, Needs your review, Ready to publish,
High-impact misses, SEO quick wins, Post today). That made the page
roughly 4+ viewport heights. We collapsed the 4 least-actioned cards
(Hot trends, SEO quick wins, Post today, High-impact misses) into a
single <details> accordion that defaults closed. Do first + Needs your
review + Ready to publish remain visible above the fold.
"""
import re
import unittest
from pathlib import Path


HTML_PATH = Path(__file__).resolve().parent.parent / "campaign-os.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _brief_grid_render(html: str) -> str:
    """Extract the inner template literal that renders $('#brief-grid').innerHTML."""
    m = re.search(
        r"\$\('#brief-grid'\)\.innerHTML\s*=\s*`(.*?)`\s*;",
        html,
        re.DOTALL,
    )
    if not m:
        raise AssertionError("Could not locate brief-grid render block")
    return m.group(1)


class BriefMoreSignalsCollapseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read(HTML_PATH)
        cls.grid_html = _brief_grid_render(cls.html)

    def test_more_signals_accordion_exists(self):
        # The collapsible <details id="brief-more-signals"> wrapper.
        self.assertIn('id="brief-more-signals"', self.grid_html)
        self.assertIn("<details", self.grid_html)

    def test_more_signals_defaults_closed(self):
        # Without an `open` attribute, the <details> is collapsed by default.
        # That's the whole point - collapse to cut viewport-height footprint.
        details_match = re.search(
            r'<details[^>]*id="brief-more-signals"[^>]*>',
            self.grid_html,
        )
        self.assertIsNotNone(details_match)
        open_tag = details_match.group(0)
        self.assertNotIn("open", open_tag)

    def test_more_signals_contains_the_four_collapsed_cards(self):
        # The 4 cards we promised to fold into the accordion:
        self.assertIn("Hot right now", self.grid_html)
        self.assertIn("High-impact misses", self.grid_html)
        self.assertIn("SEO quick wins", self.grid_html)
        self.assertIn("Post today", self.grid_html)

    def test_actionable_cards_stay_visible_above_fold(self):
        # Do first, Needs your review, Ready to publish must NOT be inside
        # the accordion - they are the page's primary actionables.
        details_open = self.grid_html.find('<details')
        details_close = self.grid_html.find("</details>")
        self.assertGreater(details_open, 0)
        self.assertGreater(details_close, details_open)
        accordion_body = self.grid_html[details_open:details_close]
        self.assertNotIn("Do first", accordion_body)
        self.assertNotIn("Needs your review", accordion_body)
        self.assertNotIn("Ready to publish", accordion_body)

    def test_no_duplicate_card_headers(self):
        # Same H3 visible header appearing twice would mean we accidentally
        # duplicated a card instead of moving it. The accordion is supposed
        # to MOVE the 4 cards into itself, not double-render them. We match
        # the visible ">🎯 Do first</h3>" pattern so data-help-title="..."
        # attribute occurrences don't false-positive.
        for header in (
            "Hot right now",
            "High-impact misses",
            "SEO quick wins",
            "Post today",
            "Do first",
            "Needs your review",
            "Ready to publish",
        ):
            # Match either bare emoji-prefixed header or with emoji
            patterns = [
                f">{header}</h3>",
                f"🔥 {header}</h3>",
                f">🎯 {header}</h3>",
                f">📝 {header}</h3>",
                f">🚀 {header}</h3>",
                f">⚠️ {header}</h3>",
                f">🔎 {header}</h3>",
                f">📮 {header}</h3>",
            ]
            count = sum(self.grid_html.count(p) for p in patterns)
            self.assertEqual(
                count, 1,
                f"'{header}' H3 appears {count}x in brief-grid - expected exactly 1. "
                f"Either the accordion dupes it or it was removed by mistake.",
            )


if __name__ == "__main__":
    unittest.main()
