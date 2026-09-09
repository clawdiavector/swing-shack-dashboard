"""Regression test: every section must use the standard <span class="sub"> subtitle pattern.

Background
----------
A 2026-08-17 nightshift probe of all 28 sections of campaign-os/campaign-os.html
on the LIVE deployment found six sections missing the standard subtitle pattern:
    - sec-gbp           (Google Business)
    - sec-reddit        (Reddit Outreach)
    - sec-faqs          (FAQ Opportunities)
    - sec-seo           (SEO Assistant)
    - sec-hashtagseo    (was a <div class="muted"> instead of <span class="sub">)
    - sec-agents        (Agents & health)

The other ~22 sections use a consistent pattern:
    <div class="section-h"><h2 ...>Title</h2><span class="sub">subtitle copy</span></div>

The missing sub-labels left those sections visually inconsistent — every other
section tells the user what the surface is for in one line of muted text, and
those six had nothing.

This sweep adds a single <span class="sub"> line to each, matching the existing
copy pattern: "what's here" + "what to do next" in plain English, no em-dashes
(standing rule), no fabricated stats.

This test guards the contract by parsing the rendered SPA bundle (the SPA is
served as a single HTML payload, so a substring check on the served HTML is the
deterministic ground truth — equivalent to a Playwright probe but doesn't
require a browser session).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML_PATH = REPO / "campaign-os" / "campaign-os.html"
HTML = HTML_PATH.read_text(encoding="utf-8")


# (section-id, expected literal sub-text, slug for the test name)
EXPECTED_SUBS = [
    ("sec-gbp",        "GBP drafts route through Review before they hit the live profile."),
    ("sec-reddit",     "drafted replies route through Review before posting"),
    ("sec-faqs",       "each entry pairs the question with a brand pillar and a draft answer."),
    ("sec-seo",        "no social posting from here."),
    ("sec-hashtagseo", "no social actions, safe during rest-mode."),
    ("sec-agents",     "this is where to look when nothing is posting right now."),
]


class SectionSubtitleConsistencyTests(unittest.TestCase):
    """All sections must use the standard <span class="sub"> subtitle pattern."""

    def _section_block(self, sec_id: str) -> str:
        """Return the slice of HTML covering the <section id="sec-..."> open through </section>."""
        m = re.search(rf'<section class="section"\s+id="{sec_id}">', HTML)
        self.assertIsNotNone(m, f"Section {sec_id} not found in SPA bundle")
        start = m.start()
        # Find the matching </section> by simple stack-walk (sections don't nest in this file)
        end_m = re.search(r"</section>", HTML[start:])
        self.assertIsNotNone(end_m, f"Closing tag for {sec_id} not found")
        return HTML[start: start + end_m.end()]

    # --- 1. Each fixed section has a <span class="sub"> with the expected text ---
    def test_01_gbp_has_sub(self):
        block = self._section_block("sec-gbp")
        self.assertRegex(block, r'<span class="sub">[^<]*GBP drafts route through Review[^<]*</span>',
                         "sec-gbp missing <span class=\"sub\"> subtitle")

    def test_02_reddit_has_sub(self):
        block = self._section_block("sec-reddit")
        self.assertRegex(block, r'<span class="sub">[^<]*drafted replies route through Review[^<]*</span>',
                         "sec-reddit missing <span class=\"sub\"> subtitle")

    def test_03_faqs_has_sub(self):
        block = self._section_block("sec-faqs")
        self.assertRegex(block, r'<span class="sub">[^<]*brand pillar and a draft answer[^<]*</span>',
                         "sec-faqs missing <span class=\"sub\"> subtitle")

    def test_04_seo_has_sub(self):
        block = self._section_block("sec-seo")
        self.assertRegex(block, r'<span class="sub">[^<]*no social posting from here\.[^<]*</span>',
                         "sec-seo missing <span class=\"sub\"> subtitle")

    def test_05_hashtagseo_has_sub(self):
        block = self._section_block("sec-hashtagseo")
        self.assertRegex(block, r'<span class="sub">[^<]*no social actions, safe during rest-mode\.[^<]*</span>',
                         "sec-hashtagseo missing <span class=\"sub\"> subtitle")
        # Also verify the old <div class="muted"> in section-h is gone (replaced by span.sub)
        self.assertNotIn('class="muted" style="font-size:11px;margin-top:.25rem"',
                         block,
                         "sec-hashtagseo still has the old <div class=\"muted\"> subtitle block — should be replaced with <span class=\"sub\">.")

    def test_06_agents_has_sub(self):
        block = self._section_block("sec-agents")
        self.assertRegex(block, r'<span class="sub">[^<]*this is where to look when nothing is posting right now\.[^<]*</span>',
                         "sec-agents missing <span class=\"sub\"> subtitle")

    # --- 2. No em-dashes leaked into the new sub labels (standing rule) ---
    def test_07_no_em_dash_in_new_subs(self):
        for sec_id, expected_text in EXPECTED_SUBS:
            block = self._section_block(sec_id)
            m = re.search(r'<span class="sub">([^<]*)</span>', block)
            self.assertIsNotNone(m, f"{sec_id}: no <span class=\"sub\"> found")
            sub_text = m.group(1)
            self.assertNotIn("\u2014", sub_text,
                             f"{sec_id}: em-dash leaked into new subtitle — standing rule violation. Got: {sub_text!r}")
            self.assertNotIn("--", sub_text,
                             f"{sec_id}: double-hyphen leaked into new subtitle. Got: {sub_text!r}")

    # --- 3. No fabricated stats in the new sub labels (no fake numbers) ---
    def test_08_no_fabricated_numbers_in_new_subs(self):
        for sec_id, _ in EXPECTED_SUBS:
            block = self._section_block(sec_id)
            m = re.search(r'<span class="sub">([^<]*)</span>', block)
            sub_text = m.group(1)
            # Numbers like "5 themes", "10 keywords", "3 categories" would be fabrication
            # (these are surface-level labels, not data). Allow "0" since that signals "empty".
            nums = re.findall(r'\b\d+\b', sub_text)
            self.assertEqual(nums, [],
                             f"{sec_id}: subtitle contains fabricated numbers: {nums}. Sub: {sub_text!r}")

    # --- 4. New subs aren't empty ---
    def test_09_subs_have_substantive_content(self):
        for sec_id, expected_text in EXPECTED_SUBS:
            block = self._section_block(sec_id)
            m = re.search(r'<span class="sub">([^<]*)</span>', block)
            sub_text = m.group(1).strip()
            self.assertGreater(len(sub_text), 30,
                               f"{sec_id}: subtitle too short ({len(sub_text)} chars) — needs a real explanation. Got: {sub_text!r}")
            self.assertIn(expected_text, sub_text,
                          f"{sec_id}: subtitle text drifted. Expected fragment {expected_text!r} in {sub_text!r}")

    # --- 5. Standard pattern preserved: <h2> + <span class="sub"> in same section-h ---
    def test_10_pattern_h2_then_sub(self):
        for sec_id, _ in EXPECTED_SUBS:
            block = self._section_block(sec_id)
            # Find <h2 ...>Title</h2> followed by <span class="sub">
            self.assertRegex(block,
                            r'<h2[^>]*>[^<]*</h2><span class="sub">',
                            f"{sec_id}: pattern broken — <span class=\"sub\"> must immediately follow <h2>...</h2> in section-h.")


if __name__ == "__main__":
    unittest.main()