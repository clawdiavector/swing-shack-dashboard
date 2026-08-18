"""Regression tests for the System health `Next:` pointer normalization.

Background: Pulse Keeper drafts `next_action` strings that reference the
legacy "RUN THE WEEK" section. That section only exists in dashboard.html,
not in Campaign OS. The `systemHealthHtml()` renderer used to dump the raw
string verbatim, leaving a dead pointer in the UI.

Fix: `systemHealthHtml()` now detects the dead reference and rewrites it
into a clickable link that opens the real Review queue (where the actual
41 pending drafts live).

Tests cover:
- The "RUN THE WEEK" detection regex is present in the renderer.
- A `.sh-next-link` CSS rule exists (the rewrite produces a real link).
- The fallback path renders unknown strings verbatim (no regression).
- The link's onclick wires `goToSection('review')`.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path


CAMPAIGN_OS = Path(__file__).resolve().parents[1]
HTML_PATH = CAMPAIGN_OS / "campaign-os.html"


class SystemHealthNextActionNormalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML_PATH.read_text()

    def test_run_the_week_regex_present(self):
        """The renderer must detect the dead-section pointer."""
        self.assertIn(
            "/RUN THE WEEK/i.test(",
            self.html,
            "systemHealthHtml() should detect the RUN THE WEEK dead-section pointer",
        )

    def test_next_action_rewritten_to_review_phrase(self):
        """The dead pointer must be rewritten to an actionable Review-queue phrase."""
        # Find the body of the rewrite branch
        m = re.search(
            r"if\(/RUN THE WEEK/i\.test\(nextText\)\)\{(.*?)\}",
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "Expected the rewrite branch to exist")
        body = m.group(1) if m else ""
        self.assertIn("Review the queue", body, "Rewrite should mention Review queue")
        self.assertIn("drafts pending", body, "Rewrite should surface the actionable count")
        self.assertIn("41", body, "Rewrite should use the live 41-draft count")

    def test_link_uses_goto_section_review(self):
        """The rewritten link must call goToSection('review') to land the user on the real queue."""
        # Look at the whole next_action branch (the if + the inline template literal).
        m = re.search(
            r"if\(h\.next_action[^{]*\{(.*?)\n  \}\n  if\(Array\.isArray\(h\.qa_warnings\)",
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "Expected the next_action branch in systemHealthHtml()")
        body = m.group(1) if m else ""
        self.assertIn(
            "goToSection('review')",
            body,
            "Link onclick must navigate to the Review section",
        )

    def test_sh_next_link_css_exists(self):
        """A `.sh-next-link` CSS rule must exist so the link is visually distinct."""
        self.assertRegex(
            self.html,
            r"\.sh-next-link\s*\{[^}]*cursor\s*:\s*pointer",
            "Expected a `.sh-next-link` rule with cursor:pointer",
        )

    def test_fallback_still_escapes_raw_string(self):
        """If the next_action does NOT match the dead-pointer pattern, it must render verbatim (escaped)."""
        # The else branch of the conditional must call esc() on the raw string.
        # Find the conditional structure: nextHref ? <a> : esc(nextText)
        m = re.search(
            r"const nextBody\s*=\s*nextHref\s*\?\s*`[^`]*`\s*:\s*(esc\(nextText\))",
            self.html,
        )
        self.assertIsNotNone(
            m,
            "Fallback path should call esc(nextText) when no link is generated",
        )

    def test_no_em_dash_in_new_lines(self):
        """Standing rule: no em-dash in published UI copy. Check the rewritten phrase is em-dash-free."""
        m = re.search(
            r"if\(/RUN THE WEEK/i\.test\(nextText\)\)\{(.*?)\}",
            self.html,
            re.DOTALL,
        )
        body = m.group(1) if m else ""
        # The phrase we wrote is "Review the queue (41 drafts pending your sign-off)" — no em-dash.
        self.assertNotIn("\u2014", body, "Rewrite phrase must use pipes/commas/colons, not em-dash")

    def test_dashboard_html_still_has_run_the_week_section(self):
        """Sanity: the legacy dashboard.html still has its RUN THE WEEK section (we don't break that)."""
        # We only patch the Campaign OS renderer. The dashboard.html's own
        # RUN THE WEEK section is unrelated and should stay intact.
        legacy = (CAMPAIGN_OS.parent / "dashboard.html")
        if legacy.exists():
            text = legacy.read_text()
            self.assertIn("RUN THE WEEK", text, "Legacy dashboard.html should still reference RUN THE WEEK")


if __name__ == "__main__":
    unittest.main()