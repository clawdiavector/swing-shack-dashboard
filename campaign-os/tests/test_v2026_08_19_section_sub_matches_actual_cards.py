"""Regression test: section sub-headers on Opportunities + Library mirror the
actual sub-cards on those pages, not a stale subset.

Background
----------
A 2026-08-19 nightshift probe walked every Campaign OS section via Playwright
on the LIVE deployment and pulled the rendered card-headings from two
sections where the static <span class="sub"> line on the page header was
listing only a subset of the actual sub-cards:

1. **Opportunities (sec-ideas)** — the static sub said
   "Ideas · missed · upsell · bundles · funnel leaks" (5 of 9).
   Actual cards on the page:
     - Opportunity detected (auto-picked top idea, with score + Build button)
     - Just generated (session-only)
     - Content ideas (full backlog)
     - Post today (highest urgency)
     - This week (batch queue)
     - Missed opportunities (retros)
     - Upsells (high-margin angles)
     - Bundles (cross-sell)
     - Funnel leaks (highest-ROI fixes)
     - Landing-page fixes (SEO)

2. **Library (sec-library)** — the static sub said
   "Everything you've already made: approved captions, generated memes,
   generated images. Search or filter." (mentions 3 of 9 surfaces).
   Actual surfaces on the page:
     - 3 quick-launch tiles: Visual Library, Meme Lab, universal search
     - 6 tabs: Recently generated, Approved assets, Captions, Hooks, Memes, Images

A first-time visitor who read the sub and then scrolled would be surprised
by 4-5 extra cards they didn't know were there (the Opportunity detector,
Just generated, Post today, This week, Landing-page fixes on Opportunities;
Captions, Hooks, Approved assets, Recently generated, and the search tile
on Library). That's a small but real UX bug — section sub-headers are the
first thing the user reads to know what a surface is for.

The fix updates both sub lines to mirror the actual surface, and adds a
`data-help` so the next person who edits the page knows why it's there.

This test guards the contract by parsing the rendered SPA bundle (the SPA is
served as a single HTML payload, so a substring check on the served HTML is
the deterministic ground truth — equivalent to a Playwright probe but
doesn't require a browser session).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML_PATH = REPO / "campaign-os" / "campaign-os.html"
HTML = HTML_PATH.read_text(encoding="utf-8")


# (section-id, expected substring of the new sub line)
EXPECTED_SUB_FRAGMENTS = [
    # sec-ideas: new sub lists all 8 idea sub-cards (excluding the auto-generated
    # Opportunity detector card, which is data-driven and not always shown).
    ("sec-ideas",
     "Just generated · content ideas · post today · this week · missed · upsells · bundles · funnel leaks · landing-page fixes"),
    # sec-library: new sub lists 6 tabs + 3 quick-launch tiles.
    ("sec-library",
     "6 tabs: generated · approved · captions · hooks · memes · images · plus Visual Library, Meme Lab, and universal search"),
]

# Pre-fix substrings that MUST NOT appear (stale copy)
PRE_FIX_BANNED = [
    ("sec-ideas",   "Ideas · missed · upsell · bundles · funnel leaks"),
    ("sec-library", "Everything you've already made: approved captions, generated memes, generated images. Search or filter."),
]


class SectionSubMatchesActualCardsTests(unittest.TestCase):
    """Section sub-headers must mirror the actual sub-cards on the page."""

    def _section_block(self, sec_id: str) -> str:
        """Return the relevant HTML block for a section.

        For sections with static markup (most of them), returns the slice
        from <section id="sec-X"> to its matching </section>. For sections
        that are built dynamically by a render*() function, the static
        block is empty (just a comment), so we look up the render function
        and return its body instead. This handles both the static and
        dynamic-render patterns with one helper.
        """
        m = re.search(rf'<section class="section"\s+id="{sec_id}">', HTML)
        self.assertIsNotNone(m, f"Section {sec_id} not found in SPA bundle")
        start = m.start()
        end_m = re.search(r"</section>", HTML[start:])
        self.assertIsNotNone(end_m, f"Closing tag for {sec_id} not found")
        block = HTML[start: start + end_m.end()]
        # If the static block is empty (just a comment), fall back to the
        # body of the corresponding render*() function — that is where
        # the section-h sub actually lives for dynamically-built sections.
        body_only = re.sub(r'<[^>]+>', '', block).strip()
        if not body_only:
            # Map known dynamic sections to their render function names.
            dyn_map = {
                "sec-library": "renderLibrary",
            }
            fn = dyn_map.get(sec_id)
            if fn:
                fn_m = re.search(rf'(async\s+)?function\s+{fn}\s*\([^)]*\)\s*\{{', HTML)
                if fn_m:
                    fn_start = fn_m.end()
                    # Walk braces to find the end of the function body.
                    depth = 1
                    i = fn_start
                    while i < len(HTML) and depth > 0:
                        if HTML[i] == '{':
                            depth += 1
                        elif HTML[i] == '}':
                            depth -= 1
                        i += 1
                    return HTML[fn_m.start():i]
        return block

    # --- 1. Each fixed section has the new sub-line substring in the served HTML
    def test_01_ideas_sub_lists_all_eight_sub_cards(self):
        block = self._section_block("sec-ideas")
        needle = "Just generated · content ideas · post today · this week · missed · upsells · bundles · funnel leaks · landing-page fixes"
        self.assertIn(needle, block,
                      "sec-ideas <span class=\"sub\"> is missing the new line that lists all 8 idea sub-cards")

    def test_02_library_sub_lists_all_six_tabs_plus_three_tiles(self):
        block = self._section_block("sec-library")
        needle = "6 tabs: generated · approved · captions · hooks · memes · images · plus Visual Library, Meme Lab, and universal search"
        self.assertIn(needle, block,
                      "sec-library <span class=\"sub\"> is missing the new line that lists all 6 tabs + 3 quick-launch tiles")

    # --- 2. The pre-fix stale sub-line strings are gone
    def test_03_ideas_pre_fix_sub_is_gone(self):
        block = self._section_block("sec-ideas")
        self.assertNotIn("Ideas · missed · upsell · bundles · funnel leaks", block,
                         "sec-ideas still has the pre-fix stale sub-line")

    def test_04_library_pre_fix_sub_is_gone(self):
        block = self._section_block("sec-library")
        self.assertNotIn("Everything you've already made: approved captions, generated memes, generated images. Search or filter.", block,
                         "sec-library still has the pre-fix stale sub-line")

    # --- 3. New sub lines are wrapped in <span class="sub"> (the standard pattern)
    def test_05_ideas_sub_uses_standard_pattern(self):
        block = self._section_block("sec-ideas")
        self.assertRegex(block, r'<span class="sub"[^>]*>Just generated · content ideas · post today · this week · missed · upsells · bundles · funnel leaks · landing-page fixes</span>',
                         "sec-ideas new sub must be inside <span class=\"sub\">...</span>")

    def test_06_library_sub_uses_standard_pattern(self):
        block = self._section_block("sec-library")
        self.assertRegex(block, r'<span class="sub"[^>]*>6 tabs: generated · approved · captions · hooks · memes · images · plus Visual Library, Meme Lab, and universal search</span>',
                         "sec-library new sub must be inside <span class=\"sub\">...</span>")

    # --- 4. New sub lines carry the data-help attribute so future editors see why
    def test_07_ideas_sub_has_data_help(self):
        block = self._section_block("sec-ideas")
        # Find the <span class="sub"...> that contains the new sub text
        m = re.search(r'<span class="sub"[^>]*>Just generated · content ideas', block)
        self.assertIsNotNone(m, "sec-ideas new sub <span> not found")
        self.assertIn("data-help=", m.group(0),
                      "sec-ideas new sub must carry data-help so the next editor knows why it's there")
        self.assertIn("data-help-title=", m.group(0),
                      "sec-ideas new sub must carry data-help-title for the help popover")

    def test_08_library_sub_has_data_help(self):
        block = self._section_block("sec-library")
        m = re.search(r'<span class="sub"[^>]*>6 tabs:', block)
        self.assertIsNotNone(m, "sec-library new sub <span> not found")
        self.assertIn("data-help=", m.group(0),
                      "sec-library new sub must carry data-help so the next editor knows why it's there")
        self.assertIn("data-help-title=", m.group(0),
                      "sec-library new sub must carry data-help-title for the help popover")

    # --- 5. Standing rule: no em-dashes in the new sub lines
    def test_09_ideas_sub_no_em_dash(self):
        block = self._section_block("sec-ideas")
        m = re.search(r'<span class="sub"[^>]*>Just generated[^<]*</span>', block)
        self.assertIsNotNone(m, "sec-ideas new sub <span> not found")
        self.assertNotIn("\u2014", m.group(0),
                         "sec-ideas new sub must not contain an em-dash (standing rule)")

    def test_10_library_sub_no_em_dash(self):
        block = self._section_block("sec-library")
        m = re.search(r'<span class="sub"[^>]*>6 tabs:[^<]*</span>', block)
        self.assertIsNotNone(m, "sec-library new sub <span> not found")
        self.assertNotIn("\u2014", m.group(0),
                         "sec-library new sub must not contain an em-dash (standing rule)")


if __name__ == "__main__":
    unittest.main()