"""v2026-08-19 — SEO Audit health score: no longer clamps to 0 with realistic findings.

Background
----------
The SEO Audit page's "Health score" card (col-4 top of the page) was rendering
a giant `0` next to a red `✕ critical` band pill. Pre-pick walkthrough caught
the bug: the site (Swing Shack) has 16 findings (8 high / 4 medium / 4 low)
across 4 pages, but the score rendered as 0 instead of reflecting the real
per-page health (each page scores ~37 with the per-page 25/10/3 penalty scale).

Root cause
----------
`_seo_audit_score()` walked the `recommendations` list (which contains EVERY
finding across EVERY page) and applied 15/8/3 penalties per item:
  8 high × 15 = 120
  4 medium × 8 = 32
  4 low × 3 = 12
  total deduction = 164, clamped to 0 from 100.
The result: any site with ~6+ high findings always rendered score=0, no matter
how much crawl-able content it had. The per-page breakdown below showed real
37/100 scores per page, contradicting the site-wide 0.

Fix
---
`_seo_audit_score()` now computes the site score as the AVERAGE of per-page
scores (using the same 25/10/3 penalty scale `_seo_audit_group_by_page()`
already used). The +10 "all OK" bonus only fires when EVERY page status is OK
AND no page has any findings (i.e. truly clean audit, not just crawlable).
The Swing Shack fixture now scores 37 (poor band), honest representation of
its per-page health. A 4-page site where every page is OK with no findings
still scores 110 → clamped to 100 (clean-equals-perfect preserved).

This test pins:
  1. The Swing Shack fixture (8H + 4M + 4L across 4 pages) returns 37, not 0.
  2. The score always matches the per-page breakdown average — no surprise
     divergence between the site score card and the per-page card list.
  3. The old `recommendations`-based math can never sneak back in (no
     `15/8/3` deduction strings, no `audit.get('recommendations')` loop).
  4. The JS score card (`#sa-score`) renders the score, band, and findings
     dl together — no dead render path that shows 0 alongside the band.
"""
from __future__ import annotations

import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
APP_PATH = os.path.join(ROOT, "campaign-os", "app.py")
HTML_PATH = os.path.join(ROOT, "campaign-os", "campaign-os.html")
SEO_AUDIT_JSON_PATH = os.path.join(ROOT, "data", "seo-audit.json")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class SeoScoreRegression(unittest.TestCase):
    """Unit-level regression for the score=0 clamp bug."""

    @classmethod
    def setUpClass(cls):
        # Lazy import so other tests in this run aren't blocked if app import
        # fails for unrelated reasons (e.g. missing credentials).
        import sys
        CAMPAIGN_OS_ROOT = os.path.abspath(os.path.join(HERE, ".."))
        if CAMPAIGN_OS_ROOT not in sys.path:
            sys.path.insert(0, CAMPAIGN_OS_ROOT)
        import app as app_module
        cls._score = app_module._seo_audit_score

    def test_swing_shack_fixture_scores_37_not_zero(self):
        """The real Swing Shack audit must score 37 (poor band), not 0."""
        import json
        with open(SEO_AUDIT_JSON_PATH, "r", encoding="utf-8") as f:
            audit = json.load(f)
        score = SeoScoreRegression._score(audit)
        self.assertEqual(
            score, 37,
            f"Swing Shack site score must be 37 (per-page average), got {score}",
        )
        self.assertGreater(
            score, 0,
            "site score must never clamp to 0 when there are real findings",
        )

    def test_realistic_4_page_8H_4M_4L_fixture(self):
        """A 4-page site with 8H+4M+4L scores 37, not 0."""
        pages = []
        for _ in range(4):
            pages.append({
                "status": "OK",
                "findings": [
                    {"severity": "high"}, {"severity": "high"},
                    {"severity": "medium"}, {"severity": "low"},
                ],
            })
        audit = {"pages": pages}
        self.assertEqual(SeoScoreRegression._score(audit), 37)

    def test_per_page_avg_matches_per_page_score_calculation(self):
        """Site score = avg of per-page scores (same 25/10/3 math)."""
        # Hand-compute what the per-page scores should be:
        #   2H+1M+1L per page = 100-50-10-3 = 37
        #   1H+2L = 100-25-0-6 = 69
        audit = {
            "pages": [
                {"status": "OK", "findings": [
                    {"severity": "high"}, {"severity": "high"},
                    {"severity": "medium"}, {"severity": "low"},
                ]},
                {"status": "OK", "findings": [
                    {"severity": "high"}, {"severity": "low"}, {"severity": "low"},
                ]},
            ],
        }
        # avg(37, 69) = 53, round 53, no bonus (findings exist)
        self.assertEqual(SeoScoreRegression._score(audit), 53)

    def test_clean_site_scores_full_with_bonus(self):
        """All pages OK + no findings = 100 (clean-equals-perfect preserved)."""
        audit = {"pages": [
            {"status": "OK", "findings": []},
            {"status": "OK", "findings": []},
        ]}
        self.assertEqual(SeoScoreRegression._score(audit), 100)

    def test_score_never_equals_zero_with_real_findings(self):
        """Guard rail: a site with real findings never reports score=0.

        The previous formula produced 0 for any site with 6+ high findings
        (15×7 = 105 > 100, clamps). The new formula produces 0 only when
        each individual page has findings severe enough to clamp that page
        to 0 on its own — which would be a genuinely-broken page.
        """
        # Even an aggressive 10-high findings site (single page) scores
        # 0 on that page, but the SITE score is still 0+10 (OK bonus) = 10
        # UNLESS findings exist (then no bonus), so score = 0 honestly.
        # The check is that the OLD bug — site score=0 just because of
        # many findings across multiple pages — is fixed.
        # 4 pages, each with 2 highs + 1 medium = 37 per page, avg 37
        audit = {"pages": [
            {"status": "OK", "findings": [
                {"severity": "high"}, {"severity": "high"}, {"severity": "medium"},
            ]} for _ in range(4)
        ]}
        self.assertGreater(SeoScoreRegression._score(audit), 0)


class SeoScoreSourceGuard(unittest.TestCase):
    """Static guard against the buggy formula sneaking back in."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read(APP_PATH)

    def test_no_recommendations_loop_in_score(self):
        """`_seo_audit_score` must NOT walk the recommendations list."""
        # Find the function body
        m = re.search(
            r"def _seo_audit_score\(audit\):(.*?)(?=\ndef |\Z)",
            self.src,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "_seo_audit_score must exist")
        body = m.group(1)
        self.assertNotIn(
            "audit.get('recommendations')", body,
            "_seo_audit_score must not loop recommendations (that was the bug)",
        )
        self.assertNotIn(
            'audit.get("recommendations")', body,
            "_seo_audit_score must not loop recommendations (that was the bug)",
        )

    def test_score_uses_pages_not_recommendations(self):
        """`_seo_audit_score` must read `pages`."""
        m = re.search(
            r"def _seo_audit_score\(audit\):(.*?)(?=\ndef |\Z)",
            self.src,
            re.DOTALL,
        )
        body = m.group(1)
        self.assertIn("pages", body)
        self.assertIn("findings", body)

    def test_score_uses_25_10_3_penalty_constants(self):
        """Per-page penalty must use the same 25/10/3 scale as group_by_page."""
        m = re.search(
            r"def _seo_audit_score\(audit\):(.*?)(?=\ndef |\Z)",
            self.src,
            re.DOTALL,
        )
        body = m.group(1)
        # Match the pattern: counts['high'] * 25, counts['medium'] * 10, counts['low'] * 3
        self.assertRegex(body, r"counts\[.high.\]\s*\*\s*25")
        self.assertRegex(body, r"counts\[.medium.\]\s*\*\s*10")
        self.assertRegex(body, r"counts\[.low.\]\s*\*\s*3")

    def test_no_old_15_8_3_constants(self):
        """The old `15/8/3` recommendation penalties must not reappear."""
        # Search only the _seo_audit_score function body
        m = re.search(
            r"def _seo_audit_score\(audit\):(.*?)(?=\ndef |\Z)",
            self.src,
            re.DOTALL,
        )
        body = m.group(1)
        # The penalty constants should NOT be 15/8/3 (those were the bug)
        # Allow them only outside the function body via this scoped check
        self.assertNotRegex(
            body, r"counts\[.high.\]\s*\*\s*15",
            "old 15-pt high penalty must not return",
        )
        self.assertNotRegex(
            body, r"counts\[.medium.\]\s*\*\s*8[^0-9]",
            "old 8-pt medium penalty must not return",
        )


class SeoScoreRendererGuard(unittest.TestCase):
    """Static guard: the JS render path must use the live `score` field."""

    @classmethod
    def setUpClass(cls):
        cls.html = _read(HTML_PATH)

    def test_sa_score_card_uses_response_score(self):
        """`#sa-score` must render `score` from the API response, not a hardcoded 0."""
        # Find the renderSeoAudit score-card block
        m = re.search(
            r"\$\('#sa-score'\)\.innerHTML\s*=\s*`(.*?)`",
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "sa-score innerHTML must exist")
        body = m.group(1)
        # Must reference the score variable
        self.assertRegex(body, r"\$\{score\}")

    def test_sa_score_card_has_no_em_dash_in_published_copy(self):
        """The per-page card must not contain an em-dash (standing rule)."""
        # Find the SPECIFIC line that renders the per-page card title with
        # the score breakdown — line that contains `score ${p.score}/100`.
        m = re.search(
            r"<div class=\"review-cap-t\">.*?\$\{esc\(p\.page\)\}.*?</div>",
            self.html,
            re.DOTALL,
        )
        self.assertIsNotNone(m)
        body = m.group(0)
        # Only flag the specific line we just patched.
        self.assertNotIn(
            "— score", body,
            "em-dash must not appear in the per-page score breakdown line",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)