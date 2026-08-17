"""Regression test: Learning > CTA rankings card reads label fields and shows stats, not raw JSON.

Background
-----------
cta-performance.json ranks ship every row as
    { cta_type, label, intent, post_count, avg_engagement_rate,
      conversion_signal, rank, color, ... }

The pre-fix renderer (campaign-os.html ~L9073) only knew it.cta / it.text,
neither of which exist in that payload. The fallback JSON.stringify(it)
then dumped the whole row into the card title as a flat string. Visually:
    {"avg_comments":0,"avg_engagement_rate":0.26,"avg_likes":0,...}

That hid the actual CTA label AND the meaningful stats (rank, post count,
avg engagement rate, intent) behind a wall of JSON braces.

The Caption Studio CTA renderer ($cap-cta) already handles the same
payload correctly via it.label / it.cta_type. This test pins the Learning
side to the same pattern, and asserts the meaningful stats are surfaced as
pills (not buried inside a JSON blob).

Tests
-----
1. The Learning CTA renderer reads it.label (the human-readable label) for
   the card title, not the JSON fallback.
2. The renderer surfaces it.rank as a pill, NOT embedded inside a JSON blob.
3. The renderer surfaces it.post_count and avg_engagement_rate as pills.
4. No raw JSON braces leak into the rendered card HTML.
5. No em-dash leaked into the renderer (standing rule).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HTML_PATH = REPO / "campaign-os" / "campaign-os.html"
HTML = HTML_PATH.read_text(encoding="utf-8")


def _learn_cta_block() -> str:
    """Return the body of the `$('#learn-cta').innerHTML = ...` arrow function."""
    m = re.search(r"\$\('#learn-cta'\)\.innerHTML\s*=\s*safeList\(l\.cta_rankings", HTML)
    assert m, "Learning CTA rankings renderer not found in SPA bundle"
    start = m.start()
    # Walk forward to the matching }).join('') || learnEmpty('cta');
    end_m = re.search(r"\}\)\.join\('\'\)\s*\|\|\s*learnEmpty\('cta'\);", HTML[start:])
    assert end_m, "Could not find end of Learning CTA renderer"
    return HTML[start: start + end_m.end()]


class LearnCtaRankingsTests(unittest.TestCase):
    """Learning > CTA rankings must read label fields and surface stats, not dump JSON."""

    def test_01_uses_label_field_not_json_fallback(self):
        """The renderer must read it.label (or it.cta / it.text / it.cta_type) for the title.
        The pre-fix code's `JSON.stringify(it)` fallback is the exact thing we are guarding against."""
        block = _learn_cta_block()
        self.assertRegex(block, r"it\.label\s*\|\|\s*it\.cta\s*\|\|\s*it\.text\s*\|\|\s*it\.cta_type",
                         "Renderer must read it.label || it.cta || it.text || it.cta_type for the title")
        self.assertNotIn("JSON.stringify(it)", block,
                         "Renderer still has JSON.stringify(it) fallback — must be removed so raw JSON never bleeds into the title")

    def test_02_rank_surfaced_as_pill(self):
        """it.rank must be rendered as a pill so users can see the ranking."""
        block = _learn_cta_block()
        self.assertRegex(block, r"it\.rank",
                         "Renderer does not reference it.rank at all")
        self.assertRegex(block, r"pill\('on',\s*'rank '\s*\+\s*it\.rank\)",
                         "Renderer must surface it.rank as a pill")

    def test_03_post_count_and_engagement_surfaced(self):
        """it.post_count and avg_engagement_rate must be surfaced as pills."""
        block = _learn_cta_block()
        self.assertRegex(block, r"it\.post_count",
                         "Renderer does not reference it.post_count")
        self.assertRegex(block, r"it\.avg_engagement_rate",
                         "Renderer does not reference it.avg_engagement_rate")

    def test_04_no_raw_json_braces_in_output(self):
        """The whole renderer block must not contain a literal '{' that would end up in innerHTML
        (other than the JS object/JSX wrappers). No `JSON.stringify` and no direct '{' in the title."""
        block = _learn_cta_block()
        # JSON.stringify was the symptom; assert it's gone
        self.assertNotIn("JSON.stringify", block,
                         "JSON.stringify is still referenced — raw JSON can still bleed through")

    def test_05_no_em_dash_in_renderer(self):
        """Standing rule: no em-dash in published copy. Comments may carry one if leftover,
        but the new code introduced in this fix must not contain em-dash."""
        block = _learn_cta_block()
        self.assertNotIn("\u2014", block,
                         f"Em-dash leaked into Learning CTA renderer: {block!r}")

    def test_06_intent_surfaced_as_pill(self):
        """it.intent (e.g. 'low' / 'high') must be surfaced as a pill so the read of the row
        carries the CTA intent."""
        block = _learn_cta_block()
        self.assertRegex(block, r"it\.intent",
                         "Renderer does not reference it.intent")
        self.assertRegex(block, r"intent\s*'\s*\+\s*it\.intent",
                         "Renderer must surface it.intent as a pill text")


if __name__ == "__main__":
    unittest.main()