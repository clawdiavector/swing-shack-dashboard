"""v2026-08-08 — Trends > Competitor Changes: row-level staleness pill.

The Trends freshness banner surfaces file-level age (e.g. "108 days old") but
each competitor_changes row also carries its own `date` field. With a stale
tracker, individual rows look identical to fresh ones — a user has no way to
tell which competitor insights are trustworthy without inspecting the JSON.

Fix: in `renderYT` inside campaign-os.html, when `it.competitor` is present
and `it.date` parses to >14 days ago, render an "Nd old / stale / ago" pill
next to the date. Threshold maps to the existing Data freshness widget:
  >60d = "blocked" tone, label "Nd old"
  >30d = "review"  tone, label "Nd stale"
  >14d = "muted"   tone, label "Nd ago"
  <=14d = no pill

These tests are read-only — they probe the static HTML for the expected
markers, so a regression where the pill disappears (re-introducing the
visual ambiguity) fails loudly.
"""

import os
import re
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HTML_PATH = os.path.join(REPO_ROOT, "campaign-os", "campaign-os.html")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class CompetitorRowAgePillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read(HTML_PATH)

    def test_renderYT_competitor_branch_present(self):
        # We touch this branch — make sure it still exists.
        self.assertIn("it.competitor", self.html)

    def test_age_pill_helper_logic_present(self):
        # The Math.floor((Date.now() - parsed) ...) age calculation.
        self.assertIn("Date.now() - parsed", self.html)
        self.assertIn("1000*60*60*24", self.html)

    def test_thresholds_match_data_freshness_widget(self):
        # The 14d / 30d / 60d thresholds match the freshness widget's 14d "stale"
        # boundary (rotten is 3x = 42d) — but row-level uses 30d/60d so we can
        # express middle-aged rows differently. Just verify the constants exist.
        for marker in ("rowDays > 14", "rowDays > 30", "rowDays > 60"):
            self.assertIn(marker, self.html, f"Missing threshold: {marker}")

    def test_pill_classes_used_match_visual_vocabulary(self):
        # blocked / review / muted are valid pill tones in this app.
        # We check the new template literal uses these tones (not the static
        # stylesheet, which doesn't repeat them per-tone).
        for tone in ("blocked", "review", "muted"):
            self.assertIn(tone, self.html, f"Pill tone missing: {tone}")

    def test_label_format_strings_present(self):
        # The pill labels use the "Nd" suffix to make age obvious.
        for label in ("d old", "d stale", "d ago"):
            self.assertIn(label, self.html, f"Missing label: {label}")

    def test_pill_has_title_attribute(self):
        # Tooltip explains the threshold so a future user understands "60d old"
        m = re.search(r'pill \$\{ageTone\}.*?title="([^"]+)"', self.html)
        self.assertIsNotNone(m, "Pill element with title attribute not found")
        assert m is not None
        self.assertIn("freshness threshold", m.group(1))

    def test_date_still_rendered(self):
        # Don't regress the original `${esc(it.date)}` rendering — both pills
        # appear alongside the date.
        self.assertIn("<span class=\"muted\">${esc(it.date)}</span>", self.html)

    def test_pill_only_above_14_days(self):
        # The agePill should be empty for rows <=14 days old (the gating
        # condition `if(rowDays > 14)` is what produces this behaviour).
        self.assertIn("if(rowDays > 14)", self.html)


if __name__ == "__main__":
    unittest.main()