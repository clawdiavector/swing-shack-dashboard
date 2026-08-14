"""Tests for weekly report v3 - real week-on-week comparisons from
IG daily_reach time-series when no archived snapshot exists yet.

Run: cd campaign-os && DATA_DIR=./data python3 -m pytest tests/test_v2026_08_14_weekly_report_v3.py -v
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(ROOT, "..", "data")

from app import (
    _weekly_compute_metrics,
    _weekly_derived_prev,
    _weekly_render_html,
    _weekly_render_markdown,
    _weekly_pct,
)  # noqa: E402


class WeeklyReportV3DerivedPrevTests(unittest.TestCase):
    """v2026_08_14: Derive previous-week values from IG daily_reach time-series
    when no archived snapshot exists. The report ALWAYS shows real math now."""

    def test_pct_handles_prev_zero_curr_zero(self):
        """prev=0, curr=0 should report 'flat' not '0.0%' or 'n/a'."""
        pct, direction, raw = _weekly_pct(0, 0)
        self.assertEqual(pct, "flat")
        self.assertEqual(direction, "neutral")
        self.assertEqual(raw, 0.0)
        print("PASS test_pct_handles_prev_zero_curr_zero")

    def test_pct_handles_prev_zero_curr_nonzero(self):
        """prev=0, curr>0 should report 'NEW' not blank or 'n/a'."""
        pct, direction, raw = _weekly_pct(50, 0)
        self.assertEqual(pct, "NEW")
        self.assertEqual(direction, "up")
        self.assertIsNone(raw)
        print("PASS test_pct_handles_prev_zero_curr_nonzero")

    def test_pct_handles_prev_nonzero_curr_zero(self):
        """prev>0, curr=0 should report '-100%' not blank."""
        pct, direction, raw = _weekly_pct(0, 100)
        self.assertEqual(pct, "-100%")
        self.assertEqual(direction, "down")
        self.assertEqual(raw, -100.0)
        print("PASS test_pct_handles_prev_nonzero_curr_zero")

    def test_pct_handles_normal_movement(self):
        """prev>0, curr>0 should report signed percentage."""
        pct, direction, raw = _weekly_pct(120, 100)
        self.assertEqual(pct, "+20.0%")
        self.assertEqual(direction, "up")
        self.assertAlmostEqual(raw, 20.0)
        print("PASS test_pct_handles_normal_movement")

    def test_derived_prev_returns_dict_when_timeseries_exists(self):
        """When IG daily_reach has >=14 days, _weekly_derived_prev returns a dict."""
        result = _weekly_derived_prev("swing-shack")
        # On the live data dir we know IG has 30 days of daily_reach
        ig_path = os.path.join(DATA_DIR, "ig-business-analytics.json")
        if os.path.exists(ig_path):
            with open(ig_path) as f:
                ig = json.load(f)
            if len(ig.get("daily_reach", [])) >= 14:
                self.assertIsNotNone(result)
                self.assertIn("_derived_ig_reach_7d", result)
                self.assertIn("derived_from", result)
                self.assertGreater(result["_derived_ig_reach_7d"], 0,
                                   "Derived prev IG reach should be > 0 when time-series has data")
                print(f"PASS test_derived_prev_returns_dict_when_timeseries_exists "
                      f"(prev 7d reach: {result['_derived_ig_reach_7d']})")
            else:
                print("SKIP test_derived_prev_returns_dict_when_timeseries_exists (insufficient IG data)")
        else:
            print("SKIP test_derived_prev_returns_dict_when_timeseries_exists (no IG data file)")

    def test_metrics_has_derived_prev_flag(self):
        """metrics dict should expose has_derived_prev so the renderer knows."""
        m = _weekly_compute_metrics("swing-shack")
        self.assertIn("has_derived_prev", m)
        # On live data we have IG time-series so this should be True
        ig_path = os.path.join(DATA_DIR, "ig-business-analytics.json")
        if os.path.exists(ig_path):
            with open(ig_path) as f:
                ig = json.load(f)
            if len(ig.get("daily_reach", [])) >= 14:
                self.assertTrue(m["has_derived_prev"],
                                "has_derived_prev should be True when IG time-series has 14+ days")
        print("PASS test_metrics_has_derived_prev_flag")

    def test_metrics_includes_7day_ig_reach_row(self):
        """Comparison table must include a 'Instagram reach (this week)' row."""
        m = _weekly_compute_metrics("swing-shack")
        labels = [r["label"] for r in m["rows"]]
        self.assertIn("Instagram reach (this week)", labels,
                      "Missing 7-day IG reach row in comparison table")
        # The row must have a source value > 0 when IG time-series exists
        ig_row = next(r for r in m["rows"] if r["label"] == "Instagram reach (this week)")
        ig_path = os.path.join(DATA_DIR, "ig-business-analytics.json")
        if os.path.exists(ig_path):
            self.assertGreater(ig_row["current"], 0,
                               "7-day IG reach row should have a current value when IG data exists")
        print(f"PASS test_metrics_includes_7day_ig_reach_row (current={ig_row['current']})")

    def test_hero_h1_is_interpretive_not_static(self):
        """The hero h1 must NOT be the boring 'Weekly review for X' static fallback
        when we have derived prev data — it should be an interpretive headline."""
        html = _weekly_render_html("swing-shack")
        m = re.search(r'<h1>(.*?)</h1>', html, re.DOTALL)
        hero = m.group(1).strip() if m else ""
        # Must NOT just say "Weekly review for Swing Shack" (the static fallback)
        ig_path = os.path.join(DATA_DIR, "ig-business-analytics.json")
        if os.path.exists(ig_path):
            with open(ig_path) as f:
                ig = json.load(f)
            if len(ig.get("daily_reach", [])) >= 14:
                self.assertNotIn("Weekly review for", hero,
                                 f"Hero h1 still static when derived prev is available: {hero!r}")
                # Should reference movement or be one of the interpretive headlines
                expected_keywords = ["up this week", "down this week", "cooled", "momentum",
                                     "stable", "straight", "real"]
                self.assertTrue(
                    any(kw in hero.lower() for kw in expected_keywords),
                    f"Hero h1 doesn't look interpretive: {hero!r}"
                )
        print(f"PASS test_hero_h1_is_interpretive_not_static ({hero!r})")

    def test_tldr_references_7day_ig_reach(self):
        """TL;DR bullet 1 should reference 7-day IG reach with concrete numbers."""
        html = _weekly_render_html("swing-shack")
        tldr = re.search(r'<ul class="tldr-list">(.*?)</ul>', html, re.DOTALL)
        text = re.sub(r"<[^>]+>", "", tldr.group(1))
        ig_path = os.path.join(DATA_DIR, "ig-business-analytics.json")
        if os.path.exists(ig_path):
            with open(ig_path) as f:
                ig = json.load(f)
            if len(ig.get("daily_reach", [])) >= 14:
                # Should mention reach + either 'up', 'down', 'cooled', or 'held steady'
                has_reach_signal = any(s in text for s in ["is up", "cooled", "held steady", "is down"])
                self.assertTrue(has_reach_signal,
                                f"TL;DR bullet 1 doesn't describe 7-day IG reach movement: {text[:200]!r}")
                # Should mention "previous 7 days" or "vs last"
                self.assertTrue("previous 7 days" in text or "vs last" in text,
                                f"TL;DR doesn't reference comparison window: {text[:200]!r}")
        print("PASS test_tldr_references_7day_ig_reach")

    def test_comparison_table_no_first_run_message_when_derived(self):
        """Comparison table must NOT show 'First-ever run' when derived prev exists."""
        html = _weekly_render_html("swing-shack")
        ig_path = os.path.join(DATA_DIR, "ig-business-analytics.json")
        if os.path.exists(ig_path):
            with open(ig_path) as f:
                ig = json.load(f)
            if len(ig.get("daily_reach", [])) >= 14:
                # The 'First-ever run' message should NOT be present
                self.assertNotIn("First-ever run", html,
                                 "Should not show 'First-ever run' when derived prev is available")
        print("PASS test_comparison_table_no_first_run_message_when_derived")

    def test_working_attention_includes_real_pct(self):
        """Working / Attention sections must show real %, not just 'X is up/down'."""
        html = _weekly_render_html("swing-shack")
        ig_path = os.path.join(DATA_DIR, "ig-business-analytics.json")
        if os.path.exists(ig_path):
            with open(ig_path) as f:
                ig = json.load(f)
            if len(ig.get("daily_reach", [])) >= 14:
                # Find the 'What is working' or 'What needs attention' section
                wa_match = re.search(
                    r'<h2>What is working</h2>\s*<ul>(.*?)</ul>',
                    html, re.DOTALL
                )
                if wa_match:
                    text = wa_match.group(1)
                    # Must have at least one % sign OR mention new data
                    has_pct = bool(re.search(r"[+-]?\d+\.?\d*%", text))
                    has_new = "just came online" in text or "first data point" in text
                    self.assertTrue(
                        has_pct or has_new,
                        f"Working section shows no real %: {text[:300]!r}"
                    )
        print("PASS test_working_attention_includes_real_pct")

    def test_markdown_renderer_uses_derived_prev(self):
        """Markdown export should also reflect derived prev data."""
        md = _weekly_render_markdown("swing-shack")
        ig_path = os.path.join(DATA_DIR, "ig-business-analytics.json")
        if os.path.exists(ig_path):
            with open(ig_path) as f:
                ig = json.load(f)
            if len(ig.get("daily_reach", [])) >= 14:
                # Should mention the time-series source in the footer
                self.assertIn("IG daily_reach", md,
                              "Markdown should note derived prev source when used")
                # Should have at least one real % in the comparison table
                self.assertTrue(
                    re.search(r"[+-]?\d+\.?\d*%", md),
                    "Markdown comparison table has no real %"
                )
        print("PASS test_markdown_renderer_uses_derived_prev")


if __name__ == "__main__":
    unittest.main()
