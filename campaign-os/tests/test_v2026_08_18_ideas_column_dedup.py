"""v2026-08-18 — Ideas: Post today + This week columns no longer duplicate Content ideas.

Background
----------
The Ideas page renders three idea columns side-by-side:
  - Content ideas (col-6)    — full backlog from `data.ideas`
  - Post today   (col-3)      — top picks from `data.post_today`
  - This week    (col-3)      — batch queue from `data.this_week`

The data file stores `post_today` and `this_week` as *subsets* of the full
ideas list (it's the source-of-truth ranking). The previous render path
plumbed each list straight into the columns without deduplication, so the
same card appeared in BOTH the Content ideas column AND the Post today
column. For Swing Shack today: `post_today` = [slice-fix-2026-08-13-a,
coaching-2026-08-13-a] — both already in `ideas` (which has 8 entries).
The same idea card was rendered twice in adjacent columns, which looked
like a rendering bug to the operator.

Fix
---
`renderIdeas()` now builds a Set of idea_ids from the main `ideas` list,
filters `post_today` and `this_week` to exclude items already present,
and shows a friendly fallback empty-state card if the column is empty
after dedup. The fallback uses the existing `.ideas-empty-friendly`
pattern (same border-left + emoji + title + sub as Missed opportunities
and Funnel leaks), so the column is never a blank card.

This test pins:
  1. the dedup code path exists inside renderIdeas(),
  2. post_today and this_week are filtered by idea_id against the main set,
  3. the fallback cards render the explicit "today sits in backlog" copy,
  4. the fallback cards use the same `.ideas-empty-friendly` class so the
     visual contract matches the other empty cards,
  5. no em-dashes in the new copy (standing rule),
  6. the original `d.ideas` list is rendered unchanged (no accidental
     filter on the main list).
"""
from __future__ import annotations

import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
HTML_PATH = os.path.join(ROOT, "campaign-os", "campaign-os.html")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class IdeasColumnDedupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read(HTML_PATH)
        # Find the dedup block inside renderIdeas() — between the
        # `ideas-list` render line and the `ideas-missed` render line.
        cls.dedup_block = re.search(
            r"\$\('#ideas-list'\)\.innerHTML = renderList\(d\.ideas, 'idea'\);"
            r"[\s\S]+?"
            r"\$\('#ideas-missed'\)\.innerHTML",
            cls.html,
        )
        assert cls.dedup_block, "dedup block must exist inside renderIdeas()"
        cls.block = cls.dedup_block.group(0)

    def test_01_dedup_block_present_in_render_ideas(self):
        """renderIdeas() must own the new dedup block."""
        self.assertIn("const _ideaIds = new Set", self.block)
        self.assertIn("const _dedup = (arr)", self.block)

    def test_02_post_today_filtered_by_idea_id(self):
        """The dedup function must filter by idea_id against the main list."""
        # Real dedup logic — Set membership check, not reference equality.
        self.assertIn("_ideaIds.has(i.idea_id)", self.block)
        self.assertIn("_todayUnique", self.block)
        self.assertIn("_weekUnique", self.block)

    def test_03_fallback_cards_use_ideas_empty_friendly_pattern(self):
        """The fallback cards must reuse the existing .ideas-empty-friendly class."""
        self.assertIn("ideas-empty-friendly", self.block)
        # Both fallbacks (today + week) must use the pattern.
        self.assertIn("Today's top picks sit in the backlog", self.block)
        self.assertIn("Week batch already in backlog", self.block)

    def test_04_post_today_fallback_exists(self):
        """The post-today fallback must explicitly say the top picks are in the backlog."""
        self.assertIn("Today's top picks sit in the backlog", self.block)
        self.assertIn("already in the Content ideas list", self.block)

    def test_05_this_week_fallback_exists(self):
        """The this-week fallback must explicitly say the week batch is in the backlog."""
        self.assertIn("Week batch already in backlog", self.block)
        self.assertIn("This week's queued ideas are already in the Content ideas list", self.block)

    def test_06_render_uses_unique_list_not_raw(self):
        """The columns must render the *deduped* list, not the raw one."""
        self.assertIn("$('#ideas-today').innerHTML = _todayUnique.length ? renderList(_todayUnique, 'idea') : _todayFallback", self.block)
        self.assertIn("$('#ideas-week').innerHTML = _weekUnique.length ? renderList(_weekUnique, 'idea') : _weekFallback", self.block)
        # The old direct render must be gone from this block.
        self.assertNotIn("$('#ideas-today').innerHTML = renderList(d.post_today, 'idea')", self.block)
        self.assertNotIn("$('#ideas-week').innerHTML = renderList(d.this_week, 'idea')", self.block)

    def test_07_main_ideas_list_unchanged(self):
        """The Content ideas list must still render the FULL d.ideas list (no accidental filter)."""
        self.assertIn("$('#ideas-list').innerHTML = renderList(d.ideas, 'idea')", self.block)

    def test_08_no_new_em_dashes_in_published_copy(self):
        """Standing rule: no em-dashes in the new fallback copy."""
        copy_lines = [ln for ln in self.block.split("\n") if "—" in ln and not ln.strip().startswith("//")]
        # Filter out CSS-styled borders (border-left:3px solid #xxx) which
        # use regular hyphens/dashes, not em-dashes. The check is for U+2014.
        copy_lines = [ln for ln in copy_lines if "—" in ln]
        self.assertFalse(copy_lines, f"em-dashes found in new copy: {copy_lines}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
