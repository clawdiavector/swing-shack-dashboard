"""Regression test: the Create page section sub-label (#create-summary) has
been swept of an em-dash that survived from initial-template era.

Background:
    The standing rule is "no em-dash in published copy". The 2026-08-11 ticks
    swept headings + dropdowns, main-card copy, empty-state strings, the
    connect explainers, and the inline muted/empty prose strings.

    This is the next lane: the section sub-label (<span class="sub">)
    strings that render in user-visible UI before any JS update. Most of
    the .sub spans are filled in by JS (review-summary, gmb-summary,
    cal-summary, etc.), but the Create page #create-summary has full
    prose that JS never updates — the literal em-dash was visible on
    every Create page render.

Pre-fix (line 1369 area):
    <span class="sub" id="create-summary">— Pick a generator. Each one returns ready-to-publish content.</span>

Post-fix:
    <span class="sub" id="create-summary">Pick a generator. Each one returns ready-to-publish content.</span>

Fix contract:
    * The post-fix string appears verbatim somewhere in campaign-os.html
    * The post-fix string contains zero em-dash characters
    * The pre-fix string is gone (no em-dash survives)
    * No JS code anywhere updates #create-summary textContent (so the
      static label is what the user always sees) — guards against a
      future fix that drops the label without realising JS never fills
      it in.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML_PATH = REPO / "campaign-os" / "campaign-os.html"

POST_FIX_STRING = '<span class="sub" id="create-summary">Pick a generator. Each one returns ready-to-publish content.</span>'
PRE_FIX_STRING = '<span class="sub" id="create-summary">— Pick a generator. Each one returns ready-to-publish content.</span>'

INS_POST_FIX_STRING = '<span class="sub" id="ins-v2-summary">loading…</span>'
INS_PRE_FIX_STRING = '<span class="sub" id="ins-v2-summary">— loading —</span>'


class TestCreateSubSummaryEmdashSweep(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = HTML_PATH.read_text(encoding="utf-8")

    def test_01_post_fix_string_present(self):
        self.assertIn(
            POST_FIX_STRING,
            self.html,
            "Post-fix create-summary sub-label missing from campaign-os.html",
        )

    def test_02_pre_fix_string_absent(self):
        self.assertNotIn(
            PRE_FIX_STRING,
            self.html,
            "Pre-fix create-summary sub-label still present (em-dash leak on Create page)",
        )

    def test_03_post_fix_string_emdash_free(self):
        self.assertNotIn(
            "\u2014",
            POST_FIX_STRING,
            "Post-fix create-summary sub-label still contains em-dash",
        )

    def test_04_no_js_mutates_create_summary(self):
        """Static label is what the user sees — guard against a future
        JS writer that drops the prose without realising the label was
        the only source of truth."""
        # Search any textContent / innerText / innerHTML assignment that
        # targets #create-summary.
        matches = re.findall(
            r"\$\(\s*['\"]#create-summary['\"]\s*\)\.(?:text|innerText|innerHTML)",
            self.html,
        )
        self.assertEqual(
            matches, [],
            f"Unexpected JS writes to #create-summary found: {matches}. "
            "Either delete them or update this test if intentional.",
        )

    def test_05_ins_v2_summary_post_fix_present(self):
        """ins-v2-summary shows briefly during the insights fetch."""
        self.assertIn(
            INS_POST_FIX_STRING,
            self.html,
            "Post-fix ins-v2-summary loading label missing",
        )

    def test_06_ins_v2_summary_pre_fix_absent(self):
        self.assertNotIn(
            INS_PRE_FIX_STRING,
            self.html,
            "Pre-fix ins-v2-summary loading label still present (em-dash leak)",
        )

    def test_07_no_other_emdash_in_sub_label_blocks(self):
        """Scan all <span class=\"sub\"> blocks for em-dashes. The 10
        empty-state sub-labels are loading placeholders that get filled
        in by JS — they're allowed to be a bare em-dash. But any .sub
        block with prose AND an em-dash is a real leak."""
        for m in re.finditer(r'<span class="sub"[^>]*>([^<]+)</span>', self.html):
            text = m.group(1)
            if "\u2014" not in text:
                continue
            # bare "—" (loading placeholder) is OK; prose with em-dash is not
            stripped = text.strip()
            if stripped == "\u2014":
                continue
            self.fail(
                f"Sweeping needed on .sub block: {m.group(0)[:120]!r}",
            )


if __name__ == "__main__":
    unittest.main()
