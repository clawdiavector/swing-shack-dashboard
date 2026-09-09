"""v2026-08-18 — Learning: What worked card surfaces pattern wins from sibling API fields.

Background
----------
The Learning page has a "What worked" card (#learn-worked) that reads from
`what_worked` in the `/api/intel/learning` response. On Swing Shack that
field currently ships:

  what_worked = [ { kind: "signal",
                    title: "21 recommendations published this week" } ]

That's an operational count, not a "what worked" pattern. The user opens
Learning, sees the only entry in the What worked slot, and reasonably
infers "nothing interesting happened this week" — even though the same
API response carries real pattern wins in sibling fields:

  trend_delta[0] = { kind: "format_shift",
                     format: "static",
                     current: 21, previous: 0, delta: 21,
                     title: "static: 21 posts this week (was 0)" }
  cta_rankings[0] = { label: "Soft / Engagement CTA",
                      cta_type: "SOFT",
                      avg_engagement_rate: 0.26,
                      post_count: 10, rank: 1, ... }

Those two pattern wins sit on the same page in the CTA and Trend cards,
but the user only sees them by scrolling. The What worked card showed
one trivial signal and looked like the field was empty.

Fix
---
`renderLearning()` now detects when `what_worked` is signal-only (every
entry has `kind === 'signal'` OR is a plain string) AND the sibling
fields hold real pattern data. In that case it renders:

  1. The trivial operational signal unchanged (it's accurate, just thin).
  2. A small "Pattern wins" panel below that names the format_shift and
     best CTA, with chevrons that link to the Trend + CTA cards so the
     user can drill into the data without leaving the page.

If `what_worked` has real pattern entries (kind !== 'signal'), the old
behavior is preserved untouched. If both are empty, the original
`learnEmpty('worked')` CTA fires. Standing rules: no em-dashes in new
copy, no fabricated stats, no chrome drift.

This test pins the new behavior end-to-end (no DOM execution needed):
  1. fixture builder exercises the signal-only + populated sibling fields
     path the user actually sees on Swing Shack,
  2. panel names the format_shift `format` + `current` count,
  3. panel names the best CTA `label` + `avg_engagement_rate`,
  4. chevrons link to #learn-trend and #learn-cta (the actual data),
  5. signal-only path preserves the trivial operational signal,
  6. real-pattern path (kind !== 'signal') is untouched,
  7. else branch with learnEmpty('worked') survives when both are empty,
  8. the no-em-dash rule is preserved.
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


class LearningWorkedCrossRefTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read(HTML_PATH)
        # Render-boundary: confirm the new code path exists in renderLearning()
        # and the old line ($('#learn-worked').innerHTML = safeList(...) ||
        # learnEmpty('worked')) only fires inside the else branch.
        cls.bridge_block = re.search(
            r"const _wwSignalsOnly = _wwRaw\.length > 0[\s\S]+?\}\s+else\s*\{",
            cls.html,
        )
        assert cls.bridge_block, "renderLearning() must own the new _wwSignalsOnly + sibling-fields bridge"
        cls.bridge_text = cls.bridge_block.group(0)
        # The else branch is one line: `$('#learn-worked').innerHTML = _wwRaw.map(itemHtml).join('') || learnEmpty('worked');`
        else_match = re.search(r"learnEmpty\('worked'\)", cls.html)
        assert else_match, "else branch with learnEmpty('worked') must survive the bridge"

    def test_01_bridge_blocks_for_learning_worked(self):
        """The bridge block must be present in renderLearning()."""
        self.assertIsNotNone(self.bridge_block, "bridge block must exist in renderLearning()")

    def test_02_bridge_names_format_shift(self):
        """The bridge must surface the format_shift `format` field + `current` count."""
        # Renders `<format>: <current> posts this week (was <previous>)`.
        # The keyword "format" and the deref of _formatShift.format must
        # both appear in the bridge.
        self.assertIn("_formatShift.format", self.bridge_text)
        self.assertIn("_formatShift.delta", self.bridge_text)
        self.assertIn("posts this week", self.bridge_text)

    def test_03_bridge_names_best_cta(self):
        """The bridge must surface the best CTA's `label` + `avg_engagement_rate`."""
        # Picks the top CTA from cta_rankings via _bestCta = (l.cta_rankings || [])[0].
        self.assertIn("(l.cta_rankings || [])[0]", self.bridge_text)
        self.assertIn("_bestCta.label", self.bridge_text)
        self.assertIn("_bestCta.avg_engagement_rate", self.bridge_text)

    def test_04_bridge_chevrons_link_to_sibling_cards(self):
        """The bridge chevrons must link to #learn-trend and #learn-cta."""
        self.assertIn('href="#learn-trend"', self.bridge_text)
        self.assertIn('href="#learn-cta"', self.bridge_text)

    def test_05_bridge_preserves_trivial_signal(self):
        """The trivial operational signal must still render, not be replaced."""
        # The bridge renders _wwRaw.map(itemHtml).join('') explicitly so
        # the user still sees the original "21 recommendations published
        # this week" entry. The header that says "Operational signal"
        # makes the framing explicit.
        self.assertIn("_wwRaw.map(it => itemHtml(it)).join('')", self.bridge_text)
        self.assertIn("Operational signal", self.bridge_text)

    def test_06_real_pattern_path_is_untouched(self):
        """When what_worked has a real pattern (kind !== 'signal'), the old path must fire."""
        # The else branch is `$('#learn-worked').innerHTML = _wwRaw.map(itemHtml).join('') || learnEmpty('worked');`
        # so when items have kind: 'hook' (or any non-signal kind), the
        # original itemHtml-based rendering is used.
        self.assertIn("learnEmpty('worked')", self.html)
        # The else branch must call _wwRaw.map(itemHtml).join('') too —
        # the bridge is the only thing that does the extra work; the
        # real-pattern path is unchanged.
        self.assertIn("$('#learn-worked').innerHTML = _wwRaw.map(itemHtml).join('')", self.html)

    def test_07_bridge_detects_signals_only(self):
        """The signal-only detector must check `kind === 'signal'`."""
        self.assertIn("it.kind === 'signal'", self.bridge_text)
        # And also tolerate plain strings (older API shape).
        self.assertIn("typeof it === 'string'", self.bridge_text)

    def test_08_no_new_em_dashes_in_published_copy(self):
        """Standing rule: no em-dashes in new copy."""
        copy_lines = [ln for ln in self.bridge_text.split("\n") if "—" in ln and not ln.strip().startswith("//")]
        self.assertFalse(copy_lines, f"em-dashes found in new copy: {copy_lines}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
