"""
test_v2026_08_14_ad_correlation_trend_summary.py

Regression test for the ad-correlation trend summary.

The Insights card "Did the ad drive this spike?" used to render 16 separate
Google Ads verdicts and 20 Meta Ads verdicts with no headline — the user saw
the parts but not the pattern. Reading "R0.26 per session · 10.2% click
ratio" 16 times doesn't tell you that spend climbed from R117 to R952 over
the active window.

This test seeds two scenarios and asserts:

  1. Server attaches a `trend_summary` object to each platform block.
  2. The summary has real numbers (first/last/peak/trough month, total
     spend, avg cost-per-session, direction).
  3. Direction is computed correctly for rising, falling, and stable series.
  4. summary_text includes the headline numbers and no em-dash (standing
     rule).
  5. When no campaigns exist, trend_summary is omitted (None) rather than
     fabricated.

The fix lives in campaign-os/_lib/insights_correlator.py — new helper
`_trend_summary()` called from `get_ad_correlation_verdicts()`.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


CAMPAIGN_OS = Path(__file__).resolve().parents[1]


class AdCorrelationTrendSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="campaign-os-ads-trend-"))
        cls.bundled_dir = Path(tempfile.mkdtemp(prefix="campaign-os-ads-trend-bundled-"))
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["BUNDLED_DATA_DIR"] = str(cls.bundled_dir)
        sys.path.insert(0, str(CAMPAIGN_OS))
        import app as campaign_app
        cls.module = campaign_app
        cls.flask_app = campaign_app.app
        cls.client = cls.flask_app.test_client()
        cls.module.init_repo = lambda: None
        cls.client.post("/login", data={"password": cls.module.SHARED_PASSWORD})

    def setUp(self):
        """Clear tmpdir + bundled_dir before each test so files don't leak."""
        for d in (self.tmpdir, self.bundled_dir):
            for p in d.glob("*"):
                if p.is_file():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)
        shutil.rmtree(cls.bundled_dir, ignore_errors=True)
        os.environ.pop("DATA_DIR", None)
        os.environ.pop("BUNDLED_DATA_DIR", None)
        cls.client.post("/logout")

    # ------------------------------------------------------------------
    # Scenario 1: rising spend series — 6 campaigns, spend climbs from R100
    # to R800. trend_summary.direction must be "rising", peak/trough must
    # match real extrema, and summary_text must contain the real numbers.
    # ------------------------------------------------------------------
    def test_rising_spend_series_trend_summary(self):
        (self.tmpdir / "ga4-metrics.json").write_text(json.dumps({
            "pages": [{"path": "/", "sessions": 500, "engRate": "55%"}],
        }))
        (self.tmpdir / "google-ads.json").write_text(json.dumps({
            "campaigns": [
                {"id": f"g-{m}", "name": f"Rising {m}",
                 "start_date": sd, "end_date": sd.replace("-01", "-28"),
                 "spend": sp, "clicks": int(sp / 2.5),
                 "impressions": int(sp * 80), "landing_page": "/"}
                for sd, sp, m in [
                    ("202410-01", 100.0, "Oct24"),
                    ("202411-01", 250.0, "Nov24"),
                    ("202412-01", 400.0, "Dec24"),
                    ("202501-01", 600.0, "Jan25"),
                    ("202502-01", 700.0, "Feb25"),
                    ("202503-01", 800.0, "Mar25"),
                ]
            ]
        }))

        r = self.client.get("/api/insights/ad-correlation")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        trend = data["google_ads"].get("trend_summary")
        self.assertIsNotNone(trend, "google_ads.trend_summary should be present")

        # Real numbers from the seeded series.
        self.assertEqual(trend["campaign_count"], 6)
        self.assertEqual(trend["first_month"], "202410")
        self.assertEqual(trend["last_month"], "202503")
        self.assertEqual(trend["peak_month"], "202503")
        self.assertAlmostEqual(trend["peak_spend"], 800.0, places=2)
        self.assertEqual(trend["trough_month"], "202410")
        self.assertAlmostEqual(trend["trough_spend"], 100.0, places=2)
        self.assertAlmostEqual(trend["total_spend"], 2850.0, places=2)
        self.assertEqual(trend["direction"], "rising")

        # summary_text should include the start/end months and total spend.
        st = trend["summary_text"]
        self.assertIn("202410", st)
        self.assertIn("202503", st)
        self.assertIn("R2,850", st)
        # Standing rule: no em-dash anywhere in surfaced text.
        self.assertNotIn("—", st)

    # ------------------------------------------------------------------
    # Scenario 2: falling spend series — 5 campaigns, spend halves over
    # the window. direction must be "falling".
    # ------------------------------------------------------------------
    def test_falling_spend_series_direction(self):
        (self.tmpdir / "ga4-metrics.json").write_text(json.dumps({
            "pages": [{"path": "/", "sessions": 400, "engRate": "50%"}],
        }))
        (self.tmpdir / "google-ads.json").write_text(json.dumps({
            "campaigns": [
                {"id": f"g-{m}", "name": f"Falling {m}",
                 "start_date": sd, "end_date": sd.replace("-01", "-28"),
                 "spend": sp, "clicks": 50, "impressions": 1000,
                 "landing_page": "/"}
                for sd, sp, m in [
                    ("202501-01", 1000.0, "Jan25"),
                    ("202502-01", 800.0, "Feb25"),
                    ("202503-01", 600.0, "Mar25"),
                    ("202504-01", 400.0, "Apr25"),
                    ("202505-01", 200.0, "May25"),
                ]
            ]
        }))

        r = self.client.get("/api/insights/ad-correlation")
        data = r.get_json()
        trend = data["google_ads"]["trend_summary"]
        self.assertEqual(trend["direction"], "falling")
        # Peak is at the start (Jan25), trough at the end (May25).
        self.assertEqual(trend["peak_month"], "202501")
        self.assertEqual(trend["trough_month"], "202505")

    # ------------------------------------------------------------------
    # Scenario 3: stable spend series — 3 campaigns within +-10% of each
    # other. direction must be "stable".
    # ------------------------------------------------------------------
    def test_stable_spend_series_direction(self):
        (self.tmpdir / "ga4-metrics.json").write_text(json.dumps({
            "pages": [{"path": "/", "sessions": 300, "engRate": "50%"}],
        }))
        (self.tmpdir / "google-ads.json").write_text(json.dumps({
            "campaigns": [
                {"id": "g-a", "name": "Stable A", "start_date": "202501-01",
                 "end_date": "202501-28", "spend": 500.0, "clicks": 100,
                 "impressions": 5000, "landing_page": "/"},
                {"id": "g-b", "name": "Stable B", "start_date": "202502-01",
                 "end_date": "202502-28", "spend": 510.0, "clicks": 102,
                 "impressions": 5100, "landing_page": "/"},
                {"id": "g-c", "name": "Stable C", "start_date": "202503-01",
                 "end_date": "202503-28", "spend": 505.0, "clicks": 101,
                 "impressions": 5050, "landing_page": "/"},
            ]
        }))

        r = self.client.get("/api/insights/ad-correlation")
        data = r.get_json()
        trend = data["google_ads"]["trend_summary"]
        self.assertEqual(trend["direction"], "stable")
        # No "spend up/down X%" should appear in summary_text for stable.
        self.assertNotIn("spend up", trend["summary_text"])
        self.assertNotIn("spend down", trend["summary_text"])

    # ------------------------------------------------------------------
    # Scenario 4: single campaign — direction is "single".
    # ------------------------------------------------------------------
    def test_single_campaign_direction(self):
        (self.tmpdir / "ga4-metrics.json").write_text(json.dumps({
            "pages": [{"path": "/", "sessions": 100, "engRate": "50%"}],
        }))
        (self.tmpdir / "google-ads.json").write_text(json.dumps({
            "campaigns": [
                {"id": "g-only", "name": "Lone ranger",
                 "start_date": "202501-01", "end_date": "202501-31",
                 "spend": 250.0, "clicks": 50, "impressions": 1000,
                 "landing_page": "/"},
            ]
        }))

        r = self.client.get("/api/insights/ad-correlation")
        data = r.get_json()
        trend = data["google_ads"]["trend_summary"]
        self.assertEqual(trend["campaign_count"], 1)
        self.assertEqual(trend["direction"], "single")
        self.assertEqual(trend["first_month"], "202501")
        self.assertEqual(trend["last_month"], "202501")

    # ------------------------------------------------------------------
    # Scenario 5: no campaigns → trend_summary must be absent / None,
    # not fabricated. Block should still report configured=False.
    # ------------------------------------------------------------------
    def test_no_campaigns_no_trend_summary(self):
        (self.tmpdir / "ga4-metrics.json").write_text(json.dumps({
            "pages": [{"path": "/", "sessions": 100, "engRate": "50%"}],
        }))
        # Empty google-ads.json → not configured → no trend_summary attached.
        (self.tmpdir / "google-ads.json").write_text(json.dumps({"campaigns": []}))

        r = self.client.get("/api/insights/ad-correlation")
        data = r.get_json()
        self.assertFalse(data["google_ads"].get("configured"))
        # trend_summary should NOT exist (we only attach it when configured).
        self.assertNotIn("trend_summary", data["google_ads"])

    # ------------------------------------------------------------------
    # Scenario 6: Meta Ads series also gets a trend_summary (same helper).
    # ------------------------------------------------------------------
    def test_meta_ads_also_has_trend_summary(self):
        (self.tmpdir / "ga4-metrics.json").write_text(json.dumps({
            "pages": [{"path": "/", "sessions": 100, "engRate": "50%"}],
        }))
        (self.tmpdir / "meta-ads.json").write_text(json.dumps({
            "campaigns": [
                {"id": f"m-{i}", "name": f"Meta {i}",
                 "start_date": sd, "end_date": sd,
                 "spend": sp, "clicks": 0, "impressions": 100,
                 "landing_page": "/"}
                for sd, sp, i in [
                    ("202601-01", 10.0, 0),
                    ("202602-01", 25.0, 1),
                    ("202603-01", 50.0, 2),
                ]
            ]
        }))

        r = self.client.get("/api/insights/ad-correlation")
        data = r.get_json()
        mtrend = data["meta_ads"].get("trend_summary")
        self.assertIsNotNone(mtrend, "meta_ads.trend_summary should be present")
        self.assertEqual(mtrend["campaign_count"], 3)
        self.assertEqual(mtrend["direction"], "rising")
        self.assertEqual(mtrend["first_month"], "202601")
        self.assertEqual(mtrend["last_month"], "202603")
        self.assertNotIn("—", mtrend["summary_text"])


if __name__ == "__main__":
    unittest.main()
