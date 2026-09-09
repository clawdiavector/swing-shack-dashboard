"""v2026-08-09 - Insights v2: insights-lens context banner.

The Insights tab is a v2 rebuild (renderInsightsV2) that renders its own cards
(headlines, top IG posts, top pages, ad correlation). The Performance tab is
the data-first view; the Insights tab is the pattern-finding view. The framing
difference is invisible to a first-time user - they land on a wall of cards
without knowing what this view is "for".

Earlier (now-dead) code inside renderInsights() had a "How to read this view"
banner that explained the pattern-signal framing, but renderInsights() returns
early at `await renderInsightsV2(); return;` so that code never runs in the
shipped path. The user never sees the context banner.

Fix: prepend a `.insights-lens-ctx` card into the body template inside
renderInsightsV2, immediately before the headlines grid. Banner explains:
  - the green/yellow/red tone legend
  - what Top IG Posts is teaching (pattern, not snapshot)
  - what Top pages means (high-traffic = high-leverage copy fixes)
  - what the ad-correlation card honestly says when no ad data is wired
  - cross-link to Performance (raw numbers) + Learning (long-memory)

These tests are read-only - they probe the static HTML for the expected
markers, so a regression where the banner disappears (or moves into a dead
branch) fails loudly.
"""

import os
import re
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HTML_PATH = os.path.join(REPO_ROOT, "campaign-os", "campaign-os.html")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _v2_body_template(html: str) -> str:
    """Locate the body.innerHTML template literal inside renderInsightsV2.

    The literal starts at `body.innerHTML = \`` (with whitespace variations)
    and ends at the matching backtick on its own line (`    \`;`) before the
    next top-level statement `const igList`.
    """
    m = re.search(
        r"body\.innerHTML\s*=\s*`(.*?)`\s*;\s*\n\s*const igList",
        html,
        re.DOTALL,
    )
    if not m:
        raise AssertionError("Could not locate renderInsightsV2 body template literal")
    return m.group(1)


def _ri_body(html: str) -> str:
    """Return the full body of renderInsights(). The function is now a single
    delegation to renderInsightsV2() (the old clone-into-sec-insights branch
    was deleted as dead code). Used to assert the banner marker does NOT live
    in renderInsights itself - it lives in renderInsightsV2 only.
    """
    m = re.search(
        r"async function renderInsights\(\)\{(.*?)^\}",
        html,
        re.DOTALL | re.MULTILINE,
    )
    if not m:
        raise AssertionError("Could not locate renderInsights()")
    return m.group(1)


class InsightsLensCtxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read(HTML_PATH)
        cls.v2_body = _v2_body_template(cls.html)
        cls.ri_body = _ri_body(cls.html)

    def test_banner_class_marker_present(self):
        # The .insights-lens-ctx class is what the banner is anchored on.
        self.assertIn("insights-lens-ctx", self.html)

    def test_banner_inside_renderInsightsV2_body_template(self):
        body = self.v2_body
        self.assertIn("insights-lens-ctx", body)
        self.assertIn("How to read this view", body)

    def test_banner_not_in_renderInsights_body(self):
        # The shipped banner lives in renderInsightsV2 (tested above). It
        # must NOT also live in renderInsights itself - renderInsights is
        # now a thin pass-through to renderInsightsV2. If a future refactor
        # re-introduces content into renderInsights, this test will fail -
        # that's intentional, the thin-wrapper invariant is structural.
        self.assertNotIn("How to read this view", self.ri_body)
        # Confirm the thin-wrapper shape: only renderInsightsV2 invocation.
        self.assertIn("renderInsightsV2()", self.ri_body)

    def test_banner_explains_color_legend(self):
        # A first-time user needs to know what green/yellow/red mean.
        for marker in ("green", "yellow", "red"):
            self.assertIn(marker, self.html.lower())

    def test_banner_mentions_each_v2_card(self):
        # Each card the banner explains must be mentioned, so the user can
        # match the explanation to the actual card on the page.
        for card_label in (
            "Top Instagram Posts",
            "Top pages by sessions",
            "Did the ad drive this spike",
        ):
            self.assertIn(card_label, self.html)

    def test_banner_cross_links_to_performance_and_learning(self):
        # The banner should explicitly mention Performance + Learning so the
        # user understands how the three tabs relate.
        body = self.v2_body
        self.assertIn("Performance", body)
        self.assertIn("Learning", body)

    def test_banner_precedes_headlines_grid(self):
        # The banner should appear in the body template BEFORE the headlines
        # grid so the user reads the framing first. The headlines grid
        # marker in the v2 template is the `ins-headline` class on each
        # headline card.
        body = self.v2_body
        banner_idx = body.find("insights-lens-ctx")
        grid_idx = body.find("ins-headline")
        self.assertGreater(banner_idx, 0)
        self.assertGreater(grid_idx, 0)
        self.assertLess(banner_idx, grid_idx)

    def test_no_regression_v2_cards_still_render(self):
        # The banner is added; it must not displace the v2 cards.
        for marker in (
            "ins-headline",
            "Top Instagram Posts",
            "Top pages by sessions",
            "Did the ad drive this spike",
            "ad-correlation",
        ):
            self.assertIn(marker, self.html)

    def test_no_smart_quotes_in_banner(self):
        # Standing rule: copy that goes live shouldn't carry AI smart-quote
        # artifacts. Guard against a future editor copy-pasting a curly
        # variant into the banner block.
        body = self.v2_body
        self.assertNotIn("\u2018", body)
        self.assertNotIn("\u2019", body)
        self.assertNotIn("\u201c", body)
        self.assertNotIn("\u201d", body)


if __name__ == "__main__":
    unittest.main()