"""Regression test: section explainer-tooltip em-dashes swept from
section descriptions (TIPS map) and Review modal IG-history data-help.

Background:
    The standing rule is "no em-dash in published copy". The 2026-08-11 and
    2026-08-12 ticks swept headings + dropdowns, main-card copy, empty-state
    strings, the connect explainers, inline muted prose, sub-headers, and
    loading labels. This tick closes the next lane: the auto-injected
    section-explainer tooltip bodies (the TIPS map at line ~4518 that
    powers the ? button after every section-h h2/h3) and one Review-modal
    data-help tooltip body that surfaces inside the asset-edit modal.

    The walker sweep on 2026-08-12T04:24Z caught these 4 em-dashes:
        Review (1)  — sec-review tooltip
        Reddit (1)  — sec-reddit tooltip
        Agents (1)  — sec-agents tooltip
        Review modal data-help (1) — IG history heading tooltip

    Note: Review (30) and Reddit (8) walker em-dash counts come from
    CONTENT (Takomo asset names + Reddit thread titles), not UI copy.
    This test only pins the 4 UI tooltip/data-help violations.

Pre-fix:
    * sec-review:  '... or publish — all in one place.'
    * sec-reddit:  'Reddit outreach opportunities — threads where...'
    * sec-agents:  'Health of every agent lane — what ran, what failed...'
    * Review modal: '... talked about this topic before — match the voice...'

Post-fix:
    * sec-review:  em-dash → comma
    * sec-reddit:  em-dash → colon
    * sec-agents:  em-dash → colon
    * Review modal: em-dash → period (sentence break)
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML_PATH = REPO / "campaign-os" / "campaign-os.html"

EM = "\u2014"  # — em-dash

POST_FIX_SEC_REVIEW = (
    "Every generated asset lands here. Approve, reject, edit, regenerate, "
    "schedule, or publish, all in one place."
)
PRE_FIX_SEC_REVIEW = (
    "Every generated asset lands here. Approve, reject, edit, regenerate, "
    "schedule, or publish \u2014 all in one place."
)

POST_FIX_SEC_REDDIT = (
    "Reddit outreach opportunities: threads where your brand can contribute."
)
PRE_FIX_SEC_REDDIT = (
    "Reddit outreach opportunities \u2014 threads where your brand can contribute."
)

POST_FIX_SEC_AGENTS = (
    "Health of every agent lane: what ran, what failed, what queued."
)
PRE_FIX_SEC_AGENTS = (
    "Health of every agent lane \u2014 what ran, what failed, what queued."
)

POST_FIX_IG_HISTORY = (
    "Past Instagram posts that mention this asset's product, service, or "
    "keywords. Ranked by caption overlap. Use it to see how the brand has "
    "talked about this topic before. Match the voice, or remix the winner."
)
PRE_FIX_IG_HISTORY = (
    "Past Instagram posts that mention this asset's product, service, or "
    "keywords. Ranked by caption overlap. Use it to see how the brand has "
    "talked about this topic before \u2014 match the voice, or remix the winner."
)


class TestSectionTipEmdashSweep(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = HTML_PATH.read_text(encoding="utf-8")

    # sec-review tooltip
    def test_01_sec_review_post_fix_present(self):
        self.assertIn(
            POST_FIX_SEC_REVIEW,
            self.html,
            "Post-fix sec-review tooltip missing (comma form)",
        )

    def test_02_sec_review_pre_fix_absent(self):
        self.assertNotIn(
            PRE_FIX_SEC_REVIEW,
            self.html,
            "Pre-fix sec-review tooltip still present (em-dash leak)",
        )

    # sec-reddit tooltip
    def test_03_sec_reddit_post_fix_present(self):
        self.assertIn(
            POST_FIX_SEC_REDDIT,
            self.html,
            "Post-fix sec-reddit tooltip missing (colon form)",
        )

    def test_04_sec_reddit_pre_fix_absent(self):
        self.assertNotIn(
            PRE_FIX_SEC_REDDIT,
            self.html,
            "Pre-fix sec-reddit tooltip still present (em-dash leak)",
        )

    # sec-agents tooltip
    def test_05_sec_agents_post_fix_present(self):
        self.assertIn(
            POST_FIX_SEC_AGENTS,
            self.html,
            "Post-fix sec-agents tooltip missing (colon form)",
        )

    def test_06_sec_agents_pre_fix_absent(self):
        self.assertNotIn(
            PRE_FIX_SEC_AGENTS,
            self.html,
            "Pre-fix sec-agents tooltip still present (em-dash leak)",
        )

    # Review modal IG history data-help
    def test_07_ig_history_post_fix_present(self):
        self.assertIn(
            POST_FIX_IG_HISTORY,
            self.html,
            "Post-fix Review-modal IG-history data-help missing (period form)",
        )

    def test_08_ig_history_pre_fix_absent(self):
        self.assertNotIn(
            PRE_FIX_IG_HISTORY,
            self.html,
            "Pre-fix Review-modal IG-history data-help still present (em-dash leak)",
        )

    # Each post-fix string must itself be em-dash-free (defensive)
    def test_09_all_post_fix_strings_emdash_free(self):
        for name, s in [
            ("sec-review", POST_FIX_SEC_REVIEW),
            ("sec-reddit", POST_FIX_SEC_REDDIT),
            ("sec-agents", POST_FIX_SEC_AGENTS),
            ("ig-history", POST_FIX_IG_HISTORY),
        ]:
            self.assertNotIn(
                EM,
                s,
                f"Post-fix {name} string still contains em-dash",
            )

    # Generic TIPS-map guard: every sec-* entry under the TIPS object
    # must be em-dash-free. Parses the map literally.
    def test_10_all_tips_map_entries_emdash_free(self):
        m = re.search(
            r"const\s+TIPS\s*=\s*\{(.*?)\n\s*\};",
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "TIPS map literal not found in campaign-os.html")
        block = m.group(1)
        # Each entry: 'sec-X': '...',
        for entry_m in re.finditer(
            r"'sec-[a-z0-9_-]+'\s*:\s*'((?:[^'\\]|\\.)*)'",
            block,
        ):
            value = entry_m.group(1).replace("\\'", "'")
            self.assertNotIn(
                EM,
                value,
                f"sec-* tooltip entry still contains em-dash: {entry_m.group(0)[:100]!r}",
            )

    # Generic data-help guard inside the rvVisualBriefHelp / IG-history
    # data-help block — make sure no NEW em-dash got reintroduced.
    def test_11_rv_modal_datahelps_emdash_free(self):
        # The Review modal template literal — extract the IG-history h4
        # data-help only (pinpointed, so false positives are minimised).
        m = re.search(
            r'<h4 data-help="Past Instagram posts[^"]+" data-help-title="IG history',
            self.html,
        )
        self.assertIsNotNone(
            m,
            "Review-modal IG-history h4 data-help not found",
        )
        self.assertNotIn(
            EM,
            m.group(0),
            "Review-modal IG-history h4 data-help still contains em-dash",
        )


if __name__ == "__main__":
    unittest.main()