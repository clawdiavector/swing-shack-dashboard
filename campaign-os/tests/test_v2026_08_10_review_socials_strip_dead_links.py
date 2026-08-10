"""Regression tests for the 2026-08-10 Review-modal IG history strip dead-link fix.

Bug: The IG history strip in the Review modal rendered every post as
`<a href="${esc(p.permalink || '#')}" ...>` — a stub anchor with a clickable
cursor that goes nowhere when permalink is missing. This is the same
"lying affordance" pattern fixed in the Insights "Top Instagram Posts" card
(commit 71c62cc prior tick).

Fix: When `p.permalink` is missing the strip now renders a static `<div>` so
the cursor doesn't pretend the tile is clickable. When permalink is present
the strip still renders a real `<a>` to the IG post.

This test asserts:
  1. The old `href="${esc(p.permalink || '#')}"` dead-link shape is gone.
  2. A conditional render branch (`if (p.permalink)`) is in place.
  3. When permalink is present, the anchor uses the direct href (no `|| '#'`).
  4. No em-dashes leaked into the new render block.
  5. The IG history strip element (#rv-socials-strip) is still wired and
     pops posts into it (smoke check).
"""
from __future__ import annotations
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPA = REPO / "campaign-os" / "campaign-os.html"


class TestReviewSocialsStripDeadLinks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = SPA.read_text(encoding="utf-8")

    def _strip_block(self) -> str:
        """Return the IG history strip render block (or fail the test)."""
        m = re.search(
            r"strip\.innerHTML = posts\.map.*?Couldn't load socials",
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "IG history strip render block not found")
        assert m is not None  # for type narrowing
        return m.group(0) or ""

    def test_no_dead_href_hash_for_missing_permalink(self):
        """The old `href="${esc(p.permalink || '#')}"` dead-link shape must be gone."""
        block = self._strip_block()
        self.assertNotIn(
            "p.permalink || '#'",
            block,
            "Old `permalink || '#'` dead-link fallback still in place (regressed)",
        )
        # Also assert the literal '<a href="${esc(... || \'#\')}"' pattern is gone
        self.assertNotIn(
            "href=\"${esc(p.permalink || '#')}\"",
            block,
            "Old `<a href=${esc(p.permalink || '#')}>` anchor still present (regressed)",
        )

    def test_conditional_render_branch_present(self):
        """The fix shape: a conditional render branch `if (p.permalink) { ... }`."""
        block = self._strip_block()
        self.assertIn("if (p.permalink)", block, "Permalink conditional render branch missing")
        self.assertIn("href=\"${esc(p.permalink)}\"", block, "Direct permalink href missing")

    def test_static_div_when_no_permalink(self):
        """When permalink is missing, render as a `<div>` (not an anchor)."""
        block = self._strip_block()
        # The fallback return must be a div, not an anchor
        fallback = re.search(r"return `<div[^`]*`", block)
        self.assertIsNotNone(fallback, "Static-div fallback for missing permalink missing")
        # Anchor is only in the if-branch
        self.assertIn("<a href=\"${esc(p.permalink)}\"", block, "Anchor branch missing")

    def test_no_em_dashes_in_strip_block(self):
        """Standing rule: no em-dashes in published copy."""
        block = self._strip_block()
        self.assertNotIn("—", block, "Em-dash (—) leaked into the IG strip render block")
        self.assertNotIn("–", block, "En-dash (–) leaked into the IG strip render block")

    def test_strip_element_still_wired(self):
        """Smoke: the `#rv-socials-strip` element + its getter are still in place."""
        self.assertIn('id="rv-socials-strip"', self.html, "RV-socials-strip element missing")
        self.assertIn("getElementById('rv-socials-strip')", self.html, "RV-socials-strip getter missing")
        self.assertIn("/api/socials/for-asset/", self.html, "Socials-for-asset endpoint call missing")


if __name__ == "__main__":
    unittest.main()
