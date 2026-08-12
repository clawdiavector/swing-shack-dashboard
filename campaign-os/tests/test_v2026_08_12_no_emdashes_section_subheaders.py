"""Regression test: section sub-header em-dashes swept from Hashtags + SEO
and Meme Lord sections (the third tier of visibility — UI chrome that renders
on every page-load, just like the headings/dropdowns/main-cards already swept
in earlier ticks).

Background:
    The standing rule is "no em-dash in published copy". The 2026-08-11 ticks
    swept headings + dropdowns, main-card copy, empty-state strings, the
    connect explainers, and the inline muted/empty prose strings. The
    2026-08-11T20:36Z sweep fixed create-summary and ins-v2-summary loading
    labels. This tick closes the next lane: section sub-header em-dashes
    that render in user-visible UI on every page-load.

Pre-fix:
    * Hashtags + SEO section sub-header (line 1716 area):
        "Curated hashtag sets and on-page SEO scaffolding — pure intelligence,
         no social actions. Safe during rest-mode."
    * Meme Lord "Template visuals" h3 sub-label (line 1307 area):
        "🎭 Template visuals <span ...>— not sure what one looks like? Browse here</span>"

Post-fix:
    * Hashtags + SEO sub-header: em-dash → colon (same separator pattern
      as past sweeps).
    * Meme Lord h3 sub-label: em-dash → middot (same pattern as the
      "🎯 layman terms · color-coded" / "· the long-memory view" /
      "· click to visit" pills already swept).

Fix contract:
    * The post-fix strings appear verbatim somewhere in campaign-os.html
    * The post-fix strings contain zero em-dash characters
    * The pre-fix strings are gone
    * No NEW em-dashes were introduced elsewhere
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML_PATH = REPO / "campaign-os" / "campaign-os.html"

POST_FIX_HASHTAGSEO = (
    "Curated hashtag sets and on-page SEO scaffolding: "
    "pure intelligence, no social actions. Safe during rest-mode."
)
PRE_FIX_HASHTAGSEO = (
    "Curated hashtag sets and on-page SEO scaffolding \u2014 "
    "pure intelligence, no social actions. Safe during rest-mode."
)
POST_FIX_MEME_VISUAL = (
    '\U0001f3ad Template visuals '
    '<span style="font-size:11px;color:var(--tx-3)">'
    '\u00b7 not sure what one looks like? Browse here</span>'
)
PRE_FIX_MEME_VISUAL = (
    '\U0001f3ad Template visuals '
    '<span style="font-size:11px;color:var(--tx-3)">'
    '\u2014 not sure what one looks like? Browse here</span>'
)


class TestSectionSubheaderEmdashSweep(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = HTML_PATH.read_text(encoding="utf-8")

    def test_01_hashtagseo_post_fix_present(self):
        self.assertIn(
            POST_FIX_HASHTAGSEO,
            self.html,
            "Post-fix Hashtags + SEO sub-header missing (colon form)",
        )

    def test_02_hashtagseo_pre_fix_absent(self):
        self.assertNotIn(
            PRE_FIX_HASHTAGSEO,
            self.html,
            "Pre-fix Hashtags + SEO sub-header still present (em-dash leak)",
        )

    def test_03_hashtagseo_post_fix_emdash_free(self):
        self.assertNotIn(
            "\u2014",
            POST_FIX_HASHTAGSEO,
            "Post-fix Hashtags + SEO sub-header still contains em-dash",
        )

    def test_04_meme_visual_post_fix_present(self):
        self.assertIn(
            POST_FIX_MEME_VISUAL,
            self.html,
            "Post-fix Meme Lord Template visuals h3 sub-label missing (middot form)",
        )

    def test_05_meme_visual_pre_fix_absent(self):
        self.assertNotIn(
            PRE_FIX_MEME_VISUAL,
            self.html,
            "Pre-fix Meme Lord Template visuals h3 sub-label still present (em-dash leak)",
        )

    def test_06_meme_visual_post_fix_emdash_free(self):
        self.assertNotIn(
            "\u2014",
            POST_FIX_MEME_VISUAL,
            "Post-fix Meme Lord Template visuals h3 still contains em-dash",
        )

    def test_07_no_new_emdashes_in_section_h_blocks(self):
        """Scan all <div class="section-h"> blocks (section sub-headers)
        for em-dashes inside the visible text (between h2/h3 tags), NOT
        inside data-help attributes (which are hover-only). This guards
        against future drift on adjacent sections (Ideas, GMB, Library
        sub-headers, etc.). The bare loading-placeholder em-dash is
        stripped before checking."""
        for m in re.finditer(
            r'<div class="section-h">(.*?)</div>',
            self.html,
            re.DOTALL,
        ):
            block = m.group(1)
            # Drop data-help="..." and data-help-title="..." attrs (hover-only)
            block = re.sub(r'\s+data-help(-title)?="[^"]*"', '', block)
            # Strip bare em-dash placeholder spans (loading state)
            block = re.sub(r'<span[^>]*>\u2014</span>', '', block)
            # Strip h2/h3 help attributes and comments
            block = re.sub(r'<!--.*?-->', '', block, flags=re.DOTALL)
            if "\u2014" in block:
                self.fail(
                    f"em-dash found in section-h visible text: {block[:200]!r}",
                )


if __name__ == "__main__":
    unittest.main()