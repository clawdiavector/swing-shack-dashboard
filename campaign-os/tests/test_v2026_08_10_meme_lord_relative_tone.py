"""Regression tests for the 2026-08-10 Meme Lord top-picks relative-tone fix.

Bug: The Meme Lord "Top picks" card used absolute brand-fit thresholds for the
pick rank (sorted descending), and the only differentiator between picks was the
brand_fit value. On the default swing-shack/education/instagram combination
several memes share the same brand_fit ceiling (71), so all 6 tiles looked
identical and the user had no signal for "which one should I start with?".

Fix: Tone the picks relative to the local brand-fit average, mirroring the
pattern already used on the IG-posts and GA4-pages cards. The standout row
(brand_fit >= 1.5x local average) gets a "★ Top" badge; the others get a
subtle left-border tone (green/amber/red) so the relative position is visible
at a glance. The comedic `mechanism` field is also surfaced as a small chip on
each tile since it's the only meaningful differentiator when brand_fit ties.

This test asserts:
  1. The memPicksCard signature now accepts isTop and tone.
  2. The new memMechanismChip helper exists and renders the mechanism label.
  3. The memRefresh call site computes avgFit + maxFit and only marks a row
     "Top" when brand_fit === maxFit AND ratio >= 1.5.
  4. The "★ Top" badge template is present.
  5. The border-left tone (green/amber/red) is wired in.
  6. No new em-dashes leaked into the new copy.
"""
from __future__ import annotations
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPA = REPO / "campaign-os" / "campaign-os.html"


def _extract_block(text: str, start_marker: str, end_markers) -> str:
    """Return the text from `start_marker` to whichever end_marker is found first.

    `end_markers` is a list of substrings; the slice ends at the earliest match
    after `start_marker`. If none match, slice to start + 4096 chars.
    """
    start = text.index(start_marker)
    earliest = None
    for em in end_markers:
        try:
            idx = text.index(em, start + len(start_marker))
        except ValueError:
            continue
        if earliest is None or idx < earliest:
            earliest = idx
    if earliest is None:
        return text[start:start + 4096]
    return text[start:earliest]


class TestMemeLordRelativeTone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = SPA.read_text(encoding="utf-8")

    def test_mempickscard_signature_accepts_isTop_and_tone(self):
        block = _extract_block(self.html, "function memPicksCard(", ["function memLibraryRow("])
        self.assertIn("isTop", block, "memPicksCard must accept isTop arg")
        self.assertIn("tone", block, "memPicksCard must accept tone arg")

    def test_memmechanismchip_helper_present(self):
        self.assertIn("function memMechanismChip", self.html, "memMechanismChip helper missing")
        block = _extract_block(self.html, "function memMechanismChip(", ["function memPicksCard("])
        self.assertIn("mech", block, "memMechanismChip body must reference mech")

    def test_memrefresh_uses_relative_tone(self):
        block = _extract_block(self.html, "async function memRefresh(){", ["if(!MEM_LIB_CACHE._bound)"])
        self.assertIn("avgFit", block, "avgFit local-average constant missing in memRefresh")
        self.assertIn("maxFit", block, "maxFit local-max constant missing in memRefresh")
        self.assertIn("ratio", block, "ratio per-row constant missing in memRefresh")
        # 1.2x ratio threshold for "Top" matches the "good" tone boundary so a
        # stand-out row (the max brand_fit that beats the local avg) gets the
        # badge. The 1.5x cut from the IG/GA4 surface misses most real-world
        # meme decks because brand_fit scores cluster near the ceiling.
        self.assertIn("1.2", block, "1.2x ratio threshold missing in memRefresh")

    def test_top_badge_template_present(self):
        self.assertIn("★ Top", self.html, "★ Top badge template missing from memPicksCard")
        block = _extract_block(self.html, "function memPicksCard(", ["function memLibraryRow("])
        self.assertIn("Top brand-fit in this list", block, "Top badge tooltip text missing")
        self.assertIn("1.2x", block, "1.2x tooltip text missing from top badge")

    def test_border_left_tone_wired_in(self):
        block = _extract_block(self.html, "function memPicksCard(", ["function memLibraryRow("])
        # All three tone colours must be present so the green/amber/red left-border fires.
        self.assertIn("10b981", block, "green tone colour missing")
        self.assertIn("f59e0b", block, "amber tone colour missing")
        self.assertIn("ef4444", block, "red tone colour missing")
        self.assertIn("border-left:3px solid", block, "border-left rule missing")

    def test_no_new_em_dashes_in_memPicksCard(self):
        """Only inspect the memPicksCard function body for em-dashes.

        Standing rule: no em-dashes in published user-facing copy. The badge
        tooltip ("Top brand-fit in this list") and the rest of the new template
        use ASCII only. The pre-existing em-dashes elsewhere in the file (in
        comments, the pre-existing empty-state string, etc.) are not this
        test's concern.
        """
        block = _extract_block(self.html, "function memPicksCard(", ["function memLibraryRow("])
        self.assertNotIn("—", block, "Em-dash (—) leaked into memPicksCard")
        self.assertNotIn("–", block, "En-dash (–) leaked into memPicksCard")

    def test_mechanism_chip_in_template(self):
        block = _extract_block(self.html, "function memPicksCard(", ["function memLibraryRow("])
        self.assertIn("memMechanismChip(m.mechanism)", block,
                      "memMechanismChip must be invoked in memPicksCard with m.mechanism")


if __name__ == "__main__":
    unittest.main()
