"""v2026-08-14: Regression test for SEO Rankings row showing keyword only.

Background
----------
The SEO tab's "Rankings" card used to render every keyword row through the
generic `itemHtml` helper. That helper only lifts the `keyword` string from
the payload and ignores `current_rank`, `target_url`, `search_intent`, and
`note`. The result on the Swing Shack tracker (10 tracked / 0 found / 10
quick_wins, all with `current_rank: null`) was 10 identical bare-keyword
rows under a "10 QUICK WINS" header that read as a false-positive: the user
could not tell whether the site was ranking, what URL the keyword should
land on, or what the tracker actually said.

Fix (campaign-os/campaign-os.html):
  - New `seoKeywordHtml(k)` row renderer.
    * Surfaces rank pill (`pos N` when ranked, `not ranked` when null).
    * Surfaces intent pill (commercial / informational / mixed).
    * Surfaces per-row `quick win` pill so the top header still sums correctly.
    * Expandable detail with `note` + `target_url` (clipped to host).
    * Hardens against javascript: / data: href schemes (defense in depth).
  - `renderSEO()` swaps `safeList(rank?.keywords, 10).map(itemHtml)` for
    `kwArr.map(seoKeywordHtml)`, decorating each keyword with an
    `in_quick_wins` flag looked up from the `quick_wins` string list.

This test guards the contract by parsing the rendered SPA bundle (the SPA
is served as a single HTML payload, so a substring check on the served HTML
is the deterministic ground truth — equivalent to a Playwright probe but
doesn't require a browser session).
"""
from __future__ import annotations

import os
import re
import unittest


_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_HTML_PATH = os.path.join(_ROOT, "campaign-os", "campaign-os.html")


class SeoRankingsRowEnrichmentTests(unittest.TestCase):
    """The SEO Rankings card must surface rank + intent + note + URL per row."""

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(_HTML_PATH):
            raise unittest.SkipTest(f"SPA bundle not found at {_HTML_PATH}")
        cls.src = open(_HTML_PATH, encoding="utf-8").read()

    def test_01_seo_keyword_renderer_defined(self):
        """The new seoKeywordHtml function must exist in the SPA bundle."""
        self.assertRegex(
            self.src,
            r"function\s+seoKeywordHtml\s*\(",
            "seoKeywordHtml() is not defined in the SPA bundle — "
            "the SEO Rankings row enrichment fix was lost or never landed.",
        )

    def test_02_renderer_surfaces_rank_pill(self):
        """The renderer must emit a `pos N` pill when current_rank is set."""
        # Grep the renderer body: look for the rankPill construction.
        m = re.search(
            r"function\s+seoKeywordHtml\s*\([^)]*\)\s*\{([\s\S]*?)return\s+`<li",
            self.src,
        )
        self.assertIsNotNone(
            m, "seoKeywordHtml body not found in SPA bundle"
        )
        body = m.group(1)
        self.assertIn(
            "pos ", body,
            "Renderer does not emit a `pos N` pill when current_rank is set. "
            "The pill text is `pos ${rank}` — that string must appear in the renderer.",
        )

    def test_03_renderer_surfaces_not_ranked_pill(self):
        """The renderer must emit a `not ranked` pill when current_rank is null."""
        m = re.search(
            r"function\s+seoKeywordHtml\s*\([^)]*\)\s*\{([\s\S]*?)return\s+`<li",
            self.src,
        )
        body = m.group(1)
        self.assertIn(
            "not ranked", body,
            "Renderer does not emit a `not ranked` pill for null current_rank. "
            "Without this, an unranked keyword reads as bare keyword with no signal.",
        )

    def test_04_renderer_surfaces_intent_pill(self):
        """The renderer must dispatch intent kind by search_intent value."""
        m = re.search(
            r"function\s+seoKeywordHtml\s*\([^)]*\)\s*\{([\s\S]*?)return\s+`<li",
            self.src,
        )
        body = m.group(1)
        # Expect all three intent kinds to be covered.
        self.assertIn(
            "'commercial'", body,
            "Renderer does not handle the 'commercial' search_intent value.",
        )
        self.assertIn(
            "'informational'", body,
            "Renderer does not handle the 'informational' search_intent value.",
        )

    def test_05_renderer_surfaces_target_url(self):
        """The renderer must show the target_url (clipped to host) so the user
        can see which page the keyword should land on."""
        m = re.search(
            r"function\s+seoKeywordHtml\s*\([^)]*\)\s*\{([\s\S]*?)return\s+`<li",
            self.src,
        )
        body = m.group(1)
        self.assertIn(
            "target_url", body,
            "Renderer does not read the target_url field — the user cannot see "
            "which page the keyword should rank on.",
        )
        self.assertIn(
            "new URL", body,
            "Renderer does not URL-parse the target — without parsing it can't "
            "clip to host or defend against javascript: schemes.",
        )

    def test_06_renderer_defends_against_javascript_href(self):
        """Defense in depth: renderer must not put javascript: or data: URLs
        into href attributes. Trusted data today, but the data source may drift."""
        m = re.search(
            r"function\s+seoKeywordHtml\s*\([^)]*\)\s*\{([\s\S]*?)return\s+`<li",
            self.src,
        )
        body = m.group(1)
        # Look for an explicit allow-list: only http: or https: protocols.
        self.assertIn(
            "'http:'", body,
            "Renderer does not allow-list http: in its URL scheme check — "
            "javascript: or data: URLs could slip into href.",
        )
        self.assertIn(
            "'https:'", body,
            "Renderer does not allow-list https: in its URL scheme check.",
        )

    def test_07_render_seo_uses_seo_keyword_html(self):
        """renderSEO() must use seoKeywordHtml (not the generic itemHtml)
        for the rankings list."""
        # Look for the renderSEO function body and check the seo-rank innerHTML
        # assignment uses seoKeywordHtml.
        m = re.search(
            r"\$\(\s*['\"]#seo-rank['\"]\s*\)\.innerHTML\s*=\s*`[^`]*`\s*\+\s*([\w.\[\]\(\),?\s]+)\.map\(([\w]+)\)\.join\(",
            self.src,
        )
        self.assertIsNotNone(
            m,
            "Could not locate $('#seo-rank').innerHTML assignment in renderSEO().",
        )
        called_fn = m.group(2)
        self.assertEqual(
            called_fn, "seoKeywordHtml",
            f"renderSEO() should map through seoKeywordHtml, not {called_fn}. "
            f"The fix swapped itemHtml → seoKeywordHtml in this call site.",
        )

    def test_08_render_seo_decorates_quick_wins_flag(self):
        """renderSEO() must decorate each keyword with in_quick_wins so the
        per-row quick-win pill can surface."""
        # Look for the in_quick_wins assignment near #seo-rank.
        idx = self.src.find("$('#seo-rank')")
        self.assertGreater(idx, 0, "Could not find #seo-rank reference")
        # Look 1500 chars before the #seo-rank innerHTML for the quick-wins
        # lookup. The kwArr.map decoration must set `in_quick_wins` from
        # quick_wins.
        nearby = self.src[max(0, idx-1500):idx]
        self.assertIn(
            "in_quick_wins", nearby,
            "renderSEO() must decorate each keyword with in_quick_wins so "
            "the per-row quick-win pill can render.",
        )
        self.assertIn(
            "quick_wins", nearby,
            "renderSEO() must read the quick_wins array to drive the per-row pill.",
        )

    def test_09_pre_itemHtml_collapse_does_not_break_render(self):
        """Sanity: the seo-rank render no longer depends on itemHtml for keywords,
        but itemHtml itself must still exist (other renderers depend on it)."""
        self.assertRegex(
            self.src,
            r"function\s+itemHtml\s*\(",
            "itemHtml() was removed — but other renderers depend on it. "
            "Only the SEO rank render should have been swapped.",
        )


if __name__ == "__main__":
    unittest.main()