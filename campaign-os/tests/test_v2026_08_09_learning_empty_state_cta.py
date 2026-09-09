"""Regression tests for the Learning tab empty-state CTA buttons.

Live problem (priority #4 weak UX): the 5 empty-state cards on the Learning tab
(What worked / What failed / CTA rankings / Trend delta / Failure patterns)
rendered only descriptive text and no actionable button. The brand team reading
"Fills in once 3+ assets have published performance data. Approve + publish in
the Review queue to start learning." had no in-card way to jump to Review.

Fix: each LEARN_EMPTY entry now carries a `cta: { go, label }` object, and
`learnEmpty(key)` renders a primary button below the existing empty-sub copy
that calls `go('<target-section>')` via inline onclick. Targets map to the
correct tab:
  worked    -> review      (approve + publish is what seeds this)
  failed    -> review
  cta       -> ctas        (CTA generator is what fills this)
  trend     -> trends      (Trend Catcher kick-off)
  fail_pat  -> review

This test asserts:
  1. LEARN_EMPTY has 5 entries, each with a cta object that has `go` and `label`.
  2. learnEmpty() function is no longer a single-line arrow; it renders a button.
  3. The rendered button uses the existing .btn.primary class.
  4. The inline onclick invokes `go('<target>')` for each card.
  5. No em-dash in the shipped copy for the new strings (rules of engagement).
  6. Existing title/sub copy is preserved (we only added a CTA, not a rewrite).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HTML = REPO / "campaign-os.html"


def _read() -> str:
    return HTML.read_text(encoding="utf-8")


def _learn_empty_block(html: str) -> str:
    m = re.search(
        r"const LEARN_EMPTY = \{[\s\S]+?\n\};",
        html,
    )
    assert m, "LEARN_EMPTY const must be defined in campaign-os.html"
    return m.group(0)


def _learn_empty_fn(html: str) -> str:
    m = re.search(
        r"const learnEmpty = key => \{[\s\S]+?\n\};",
        html,
    )
    assert m, "learnEmpty(key) function must be defined as a multi-line arrow in campaign-os.html"
    return m.group(0)


class LearningEmptyStateCTATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read()
        cls.const = _learn_empty_block(cls.html)
        cls.fn = _learn_empty_fn(cls.html)

    def test_all_five_entries_have_cta(self):
        # LEARN_EMPTY has 5 keys: worked, failed, cta, trend, fail_pat
        for key in ["worked", "failed", "cta", "trend", "fail_pat"]:
            self.assertIn(f"{key}:", self.const, f"LEARN_EMPTY must contain key '{key}'")

    def test_each_entry_has_cta_go_and_label(self):
        # Every entry must carry a cta object with `go` and `label` keys.
        # Use a non-greedy match that can span the nested closing braces.
        for key in ["worked", "failed", "cta", "trend", "fail_pat"]:
            m = re.search(
                rf"{key}:\s*\{{[\s\S]*?cta:\s*\{{[\s\S]*?\}}\s*\}}",
                self.const,
            )
            self.assertIsNotNone(m, f"LEARN_EMPTY['{key}'] must have a cta object")
            entry = m.group(0)
            self.assertIn("go:", entry, f"LEARN_EMPTY['{key}'].cta must have a `go` field")
            self.assertIn("label:", entry, f"LEARN_EMPTY['{key}'].cta must have a `label` field")

    def test_cta_targets_are_real_sections(self):
        # go() targets must reference existing data-go nav entries / sec-* ids.
        # Read the set of valid data-go values from the nav.
        nav_targets = set(re.findall(r'data-go="([a-z\-]+)"', self.html))
        # Each LEARN_EMPTY.cta.go value must be one of those.
        # Use a non-greedy match that can span the nested closing braces.
        for key in ["worked", "failed", "cta", "trend", "fail_pat"]:
            m = re.search(
                rf"{key}:\s*\{{[\s\S]*?go:\s*'([a-z\-]+)'",
                self.const,
            )
            self.assertIsNotNone(m, f"LEARN_EMPTY['{key}'].cta.go must be a quoted string")
            go_value = m.group(1)
            self.assertIn(
                go_value, nav_targets,
                f"LEARN_EMPTY['{key}'].cta.go='{go_value}' must match an existing data-go nav target"
            )

    def test_learn_empty_is_multiline_with_button(self):
        # The fix moves learnEmpty from a one-line arrow to a multi-line body
        # that conditionally renders a <button class="btn primary" ...>.
        self.assertIn("class=\"btn primary\"", self.fn,
                      "learnEmpty must render a .btn.primary button")
        self.assertIn("onclick=\"go(", self.fn,
                      "Button onclick must call go(<section>)")
        # Multiline signature (was: `key => \`<div...`)
        self.assertIn("=> {", self.fn,
                      "learnEmpty must be a multi-line arrow that builds the button")

    def test_each_button_target_is_wired(self):
        # Inspect the function body to confirm the cta object's go + label
        # are wired into the rendered button via esc().
        self.assertIn("esc(e.cta.go)", self.fn,
                      "Button onclick must use esc(e.cta.go) to avoid breaking out of the inline handler")
        self.assertIn("esc(e.cta.label)", self.fn,
                      "Button label must use esc(e.cta.label) to avoid breaking out of the button text")
        # Make sure arrow character is used as visual hint (and is not an em-dash)
        self.assertIn("\u2192", self.fn,
                      "Button must use the right-arrow character (\u2192), not an em-dash, as the action hint")

    def test_no_em_dash_in_new_strings(self):
        # The standing rules ban em-dashes in shipped copy. The new cta
        # labels and the surrounding empty-sub copy must use pipes/commas/colons.
        cta_labels = re.findall(r"label:\s*'([^']+)'", self.const)
        self.assertGreaterEqual(len(cta_labels), 5, "Expected at least 5 cta label strings")
        for lbl in cta_labels:
            self.assertNotIn("\u2014", lbl,
                             f"cta label {lbl!r} must not contain an em-dash")
            self.assertNotIn("\u2013", lbl,
                             f"cta label {lbl!r} must not contain an en-dash")
        # The new function body itself must not introduce an em-dash.
        self.assertNotIn("\u2014", self.fn,
                         "learnEmpty function body must not introduce an em-dash")
        self.assertNotIn("\u2013", self.fn,
                         "learnEmpty function body must not introduce an en-dash")

    def test_existing_title_and_sub_copy_preserved(self):
        # We only added cta fields, not rewrote the existing copy. Each entry
        # still carries its original title and sub strings.
        expected_titles = {
            "worked": "No patterns yet",
            "failed": "No failure patterns yet",
            "cta": "No CTA data yet",
            "trend": "No trend data yet",
            "fail_pat": "No failure patterns yet",
        }
        for key, title in expected_titles.items():
            self.assertIn(f"title: '{title}'", self.const,
                          f"LEARN_EMPTY['{key}'].title must still be '{title}'")
        expected_subs = [
            "Fills in once 3+ assets have published performance data",
            "Same trigger as What worked",
            "Builds as captions with CTAs accumulate",
            "Updates weekly once the trend feed has 2+ weeks",
            "Recurring mistakes detected automatically across 3+ assets",
        ]
        for sub in expected_subs:
            self.assertIn(sub, self.const,
                          f"Existing empty-sub copy must be preserved: '{sub}'")


if __name__ == "__main__":
    unittest.main()