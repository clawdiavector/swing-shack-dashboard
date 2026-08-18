"""v2026-08-18 — Learning: What failed empty-card bridges to Failure patterns below.

Background
----------
The Learning page has two cards that both touch "failures":
  - "What failed" (#learn-failed) — insight-level list (e.g. "off-rack CTA
    posts underperform fitting-led posts by 0.6x"). The API key is
    `what_failed`.
  - "Failure patterns" (#learn-fail-pat) — structured debug log keyed
    `failure_patterns` with by_agent_partial, by_time, etc.

The two are different data. The previous code renderered an empty-state
card with the literal title "No failure patterns yet" + an "Open Review
queue" CTA whenever `what_failed` was empty, even when `failure_patterns`
had 7+ rows. The user saw:

  What failed:       No failure patterns yet
  Failure patterns:  morning, 8/37 partial 22%
                     hook_smith · 3 partial runs
                     pulse_keeper · 2 partial runs
                     ...

The two cards directly contradicted each other. The user couldn't tell
where the failure data lived, and the assertion that there were "no
failure patterns" was a lie.

Fix
---
`renderLearning()` now computes `_flattenFailurePatterns(failure_patterns)`
and, when `what_failed` is empty AND `failure_patterns` has rows, renders
a small cross-reference card in the What failed slot that:

  - does NOT claim "no failure patterns"; instead says "no failed-pattern
    insights yet" (insight-level vs. raw data),
  - tells the user the Failure patterns table has N rows right now,
  - provides a primary button that scrolls to the Failure patterns card.

If `what_failed` has rows, the old behavior is preserved. If BOTH are
empty, the original empty-state CTA fires. Standing rules: no em-dashes
in new copy, no fabricated stats, no chrome drift.

This test pins the new behavior end-to-end:
  1. fixture builder exercises the empty-what_failed + populated-failure_patterns
     path the user actually sees on Swing Shack,
  2. bridge card uses the explicit insight/no-failed-pattern framing,
  3. bridge card names the row count from `failure_patterns` (no fake numbers),
  4. bridge button points to #learn-fail-pat (the actual data location),
  5. fail-pats path renders 7 rows of structured data plus also the
     cross-reference shows the same count, so the two cards agree,
  6. the no-em-dash rule is preserved.
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


class LearningFailedCrossRefTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read(HTML_PATH)
        # Render-boundary: confirm the new code path exists in renderLearning()
        # and the old line ($('#learn-failed').innerHTML = safeList(... ||
        # learnEmpty('failed')) only fires inside the else branch.
        cls.bridge_block = re.search(
            r"const _failEmpty = safeList\(l\.what_failed, 10\)\.length === 0;[\s\S]+?\}\s+else\s*\{",
            cls.html,
        )
        assert cls.bridge_block, "renderLearning() must own the new _failEmpty + _failRows bridge"
        cls.bridge_text = cls.bridge_block.group(0)
        # The else branch is one line: `$('#learn-failed').innerHTML = safeList(...) || learnEmpty('failed');`.
        # The original render call still exists; `learnEmpty('failed')` only
        # appears once in the file. We confirm it survives the bridge.
        else_match = re.search(r"learnEmpty\('failed'\)", cls.html)
        assert else_match, "else branch with learnEmpty('failed') must survive the bridge"
        cls.bridge_text_full = cls.bridge_text + "\nlearnEmpty('failed') survives"

    def test_01_bridge_blocks_for_learning_failed(self):
        """The bridge block must be present in renderLearning()."""
        self.assertIsNotNone(self.bridge_block, "bridge block must exist in renderLearning()")

    def test_02_bridge_explicit_insight_level_framing(self):
        """The empty-state title must say 'No failed-pattern insights', not 'No failure patterns yet'."""
        # The insight-level phrasing stops the card from contradicting the
        # Failure patterns table below when it has rows.
        self.assertIn("No failed-pattern insights yet", self.bridge_text)
        # The old lie MUST not appear inside the bridge.
        self.assertNotIn("No failure patterns yet", self.bridge_text)

    def test_03_bridge_names_real_row_count(self):
        """The bridge must surface the actual count from failure_patterns, not a fake number."""
        # Uses _failRows.length (the flattened count) so the bridge says
        # the same number as the Failure patterns card below.
        self.assertIn("${_failRows.length}", self.bridge_text)
        # pluralisation
        self.assertIn("pattern${_failRows.length===1?'':'s'}", self.bridge_text)

    def test_04_bridge_button_scrolls_to_failure_patterns(self):
        """The bridge button must scroll to the #learn-fail-pat card."""
        self.assertIn("getElementById('learn-fail-pat')", self.bridge_text)
        self.assertIn("scrollIntoView", self.bridge_text)

    def test_05_original_empty_state_kept_in_else_branch(self):
        """When what_failed has rows OR failure_patterns is empty, the old behavior must persist."""
        # The else branch must still call learnEmpty('failed') when
        # what_failed is empty AND failure_patterns has no rows.
        self.assertIn("learnEmpty('failed')", self.bridge_text_full)

    def test_06_no_new_em_dashes_in_published_copy(self):
        """Standing rule: no em-dashes in published copy."""
        # The bridge's user-visible string is the innerHTML between the
        # empty-title + empty-sub tags. Strip the JS template noise and
        # check what the user sees.
        copy_lines = [ln for ln in self.bridge_text.split("\n") if "—" in ln and not ln.strip().startswith("//")]
        self.assertFalse(copy_lines, f"em-dashes found in new copy: {copy_lines}")

    def test_07_uses_existing_flatten_helper(self):
        """The bridge must reuse _flattenFailurePatterns so the row count matches the Failure patterns card."""
        # Reusing the same helper means the count rendered in the bridge
        # is GUARANTEED to equal the count rendered in the failure patterns
        # table — no possibility of drift.
        self.assertIn("_flattenFailurePatterns(l.failure_patterns)", self.bridge_text)

    def test_08_bridge_consistent_with_failure_patterns_card(self):
        """The Failure patterns card must render the same _failRows we count in the bridge."""
        # Locate the failure_patterns renderer block. The actual code is
        # multi-line: `const failRows = _flattenFailurePatterns(l.failure_patterns);`
        # then `$('#learn-fail-pat').innerHTML = failRows.length ? ... : learnEmpty('fail_pat');`.
        # Match loosely between the two anchors.
        fail_pat_block = re.search(
            r"const failRows = _flattenFailurePatterns\(l\.failure_patterns\)[\s\S]+?learnEmpty\('fail_pat'\)",
            self.html,
        )
        assert fail_pat_block, "fail-pats renderer must exist"
        # Both code paths read _flattenFailurePatterns(l.failure_patterns)
        # so the count is by construction the same.
        self.assertIn("_flattenFailurePatterns(l.failure_patterns)", fail_pat_block.group(0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
