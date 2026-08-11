"""
test_v2026_08_07_insights_v2.py

Tests for the Insights v2 endpoints:
  - /api/insights/top-instagram-posts — returns verdicts + plain English
  - /api/insights/ad-correlation — clean "not configured" when no ad data;
    surfaces verdicts when ad data is present
  - /api/insights/content-traffic-correlation — always returns shape
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


CAMPAIGN_OS = Path(__file__).resolve().parents[1]


class InsightsV2ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="campaign-os-insights-"))
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        sys.path.insert(0, str(CAMPAIGN_OS))
        import app as campaign_app

        cls.module = campaign_app
        cls.flask_app = campaign_app.app
        cls.client = cls.flask_app.test_client()
        cls.module.init_repo = lambda: None
        # Login once — cookie persists on the test client
        cls.client.post("/login", data={"password": cls.module.SHARED_PASSWORD})

    def setUp(self):
        """Clear tmpdir before each test so files don't leak between tests."""
        for p in self.tmpdir.glob("*"):
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                import shutil as _sh
                _sh.rmtree(p, ignore_errors=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)
        os.environ.pop("DATA_DIR", None)


# ============================================================================
# /api/insights/top-instagram-posts
# ============================================================================


class TopInstagramPostsTests(InsightsV2ApiTests):
    def _isolate_bundled(self):
        """Point BUNDLED_DATA_DIR at a fresh empty tmpdir so the loader
        only sees what THIS test seeds in self.tmpdir (DATA_DIR)."""
        bundled_dir = Path(tempfile.mkdtemp(prefix="test-bundled-"))
        orig_bundled = os.environ.get("BUNDLED_DATA_DIR")
        os.environ["BUNDLED_DATA_DIR"] = str(bundled_dir)
        return bundled_dir, orig_bundled

    def _restore_bundled(self, bundled_dir, orig_bundled):
        shutil.rmtree(bundled_dir, ignore_errors=True)
        if orig_bundled is not None:
            os.environ["BUNDLED_DATA_DIR"] = orig_bundled
        else:
            os.environ.pop("BUNDLED_DATA_DIR", None)

    def test_returns_empty_with_reason_when_no_data(self):
        """When BOTH DATA_DIR and BUNDLED_DATA_DIR have no IG data, return
        empty + reason. With the bundled-data fallback (Railway deployment
        pattern) the loader finds analytics/instagram-analytics.json in
        the repo, so this only triggers when even the bundled copy is
        missing — a test-only scenario."""
        bundled_dir, orig_bundled = self._isolate_bundled()
        try:
            r = self.client.get("/api/insights/top-instagram-posts?limit=8")
            self.assertEqual(r.status_code, 200)
            data = r.get_json()
            self.assertTrue(data["ok"])
            self.assertEqual(data["posts"], [])
            self.assertIn("reason", data["_meta"])
        finally:
            self._restore_bundled(bundled_dir, orig_bundled)

    def test_returns_verdicts_when_posts_exist(self):
        # Seed instagram.json with 3 posts of varying engagement.
        # Isolate BUNDLED_DATA_DIR so the loader only sees this test's seed.
        bundled_dir, orig_bundled = self._isolate_bundled()
        try:
            ig = {
                "updated": "2026-08-07T10:00:00Z",
                "posts": [
                    {"id": "ig-1", "caption": "Top performer", "engagementRate": 8.5,
                     "like_count": 420, "comments_count": 38, "media_type": "IMAGE",
                     "permalink": "https://www.instagram.com/p/1",
                     "thumbnail_url": "https://example.com/1.jpg",
                     "timestamp": "2026-08-06T11:00:00Z"},
                    {"id": "ig-2", "caption": "Average performer", "engagementRate": 3.0,
                     "like_count": 100, "comments_count": 10, "media_type": "IMAGE",
                     "permalink": "https://www.instagram.com/p/2",
                     "thumbnail_url": "https://example.com/2.jpg",
                     "timestamp": "2026-08-05T11:00:00Z"},
                    {"id": "ig-3", "caption": "Underperformer", "engagementRate": 0.5,
                     "like_count": 5, "comments_count": 0, "media_type": "IMAGE",
                     "permalink": "https://www.instagram.com/p/3",
                     "thumbnail_url": "https://example.com/3.jpg",
                     "timestamp": "2026-08-04T11:00:00Z"},
                ]
            }
            (self.tmpdir / "instagram.json").write_text(json.dumps(ig))
            r = self.client.get("/api/insights/top-instagram-posts?limit=8")
            self.assertEqual(r.status_code, 200)
            data = r.get_json()
            self.assertEqual(len(data["posts"]), 3)
            # First post has highest engagement → "Top performer" / "Above average"
            top = data["posts"][0]
            self.assertEqual(top["id"], "ig-1")
            self.assertIn("verdict", top)
            self.assertIn("plain_english", top)
            self.assertIn("thumbnail_url", top)
            # Color tones appear in plain_english
            self.assertIn("🟢", top["plain_english"])
            # Average engagement reported
            self.assertIsNotNone(data["_meta"]["average_engagement"])
        finally:
            self._restore_bundled(bundled_dir, orig_bundled)

    def test_third_post_is_red_underperformer(self):
        bundled_dir, orig_bundled = self._isolate_bundled()
        try:
            ig = {
                "posts": [
                    # avg = (5+3+0.2)/3 = 2.73. 5/2.73 = 1.83x → "Above average"
                    # 0.2/2.73 = 0.07x → "Underperformer"
                    {"id": "ig-a", "caption": "Great", "engagementRate": 5.0, "like_count": 1, "comments_count": 0, "permalink": "x", "thumbnail_url": "x", "timestamp": "2026-08-01T00:00:00Z"},
                    {"id": "ig-b", "caption": "OK", "engagementRate": 3.0, "like_count": 1, "comments_count": 0, "permalink": "x", "thumbnail_url": "x", "timestamp": "2026-08-02T00:00:00Z"},
                    {"id": "ig-c", "caption": "Bad", "engagementRate": 0.2, "like_count": 1, "comments_count": 0, "permalink": "x", "thumbnail_url": "x", "timestamp": "2026-08-03T00:00:00Z"},
                ]
            }
            (self.tmpdir / "instagram.json").write_text(json.dumps(ig))
            r = self.client.get("/api/insights/top-instagram-posts")
            data = r.get_json()
            verdicts = [p["verdict"] for p in data["posts"]]
            # Top is Above average, bottom is Underperformer
            self.assertEqual(verdicts[0], "Above average")
            self.assertEqual(verdicts[-1], "Underperformer")
        finally:
            self._restore_bundled(bundled_dir, orig_bundled)

    def test_limit_param(self):
        bundled_dir, orig_bundled = self._isolate_bundled()
        try:
            ig = {"posts": [{"id": f"ig-{i}", "caption": f"p{i}", "engagementRate": 1.0*i,
                              "like_count": 0, "comments_count": 0, "permalink": "x",
                              "thumbnail_url": "x", "timestamp": "2026-08-01T00:00:00Z"}
                              for i in range(15)]}
            (self.tmpdir / "instagram.json").write_text(json.dumps(ig))
            r = self.client.get("/api/insights/top-instagram-posts?limit=5")
            data = r.get_json()
            self.assertEqual(len(data["posts"]), 5)
        finally:
            self._restore_bundled(bundled_dir, orig_bundled)


# ============================================================================
# /api/insights/ad-correlation
# ============================================================================


class AdCorrelationTests(InsightsV2ApiTests):
    def _isolate_bundled(self):
        bundled_dir = Path(tempfile.mkdtemp(prefix="test-bundled-ads-"))
        orig_bundled = os.environ.get("BUNDLED_DATA_DIR")
        os.environ["BUNDLED_DATA_DIR"] = str(bundled_dir)
        return bundled_dir, orig_bundled

    def _restore_bundled(self, bundled_dir, orig_bundled):
        shutil.rmtree(bundled_dir, ignore_errors=True)
        if orig_bundled is not None:
            os.environ["BUNDLED_DATA_DIR"] = orig_bundled
        else:
            os.environ.pop("BUNDLED_DATA_DIR", None)

    def test_returns_clean_not_configured_when_no_ads(self):
        # Isolate bundled so the ad stubs in the repo don't leak in
        bundled_dir, orig_bundled = self._isolate_bundled()
        try:
            r = self.client.get("/api/insights/ad-correlation")
            self.assertEqual(r.status_code, 200)
            data = r.get_json()
            self.assertTrue(data["ok"])
            self.assertFalse(data["configured"])
            # Both platforms report not configured
            self.assertFalse(data["google_ads"]["configured"])
            self.assertFalse(data["meta_ads"]["configured"])
            # Reasons explain how to wire up
            self.assertIn("Google Ads", data["google_ads"]["reason"])
            self.assertIn("Meta Ads", data["meta_ads"]["reason"])
            # Summary honestly says not configured
            self.assertIn("not configured", data["combined_summary"])
        finally:
            self._restore_bundled(bundled_dir, orig_bundled)

    def test_google_ads_wired_returns_verdicts(self):
        bundled_dir, orig_bundled = self._isolate_bundled()
        try:
            (self.tmpdir / "google-ads.json").write_text(json.dumps({
                "campaigns": [
                    {"id": "g-1", "name": "Bookings Push", "start_date": "2026-08-05",
                     "end_date": "2026-08-12", "spend": "R4500", "clicks": 312,
                     "impressions": 12500, "landing_page": "/bookings/"}
                ]
            }))
            r = self.client.get("/api/insights/ad-correlation")
            data = r.get_json()
            self.assertTrue(data["configured"])
            self.assertTrue(data["google_ads"]["configured"])
            self.assertEqual(len(data["google_ads"]["verdicts"]), 1)
            verdict = data["google_ads"]["verdicts"][0]
            self.assertIn("R4500", verdict["verdict"])
            self.assertIn("/bookings/", verdict["verdict"])
        finally:
            self._restore_bundled(bundled_dir, orig_bundled)

    def test_meta_ads_wired_alone(self):
        bundled_dir, orig_bundled = self._isolate_bundled()
        try:
            (self.tmpdir / "meta-ads.json").write_text(json.dumps({
                "campaigns": [
                    {"id": "m-1", "name": "IG Awareness", "start_date": "2026-08-01",
                     "end_date": "2026-08-07", "spend": "R2000", "clicks": 100,
                     "impressions": 8000, "landing_page": "/club-fitting/"}
                ]
            }))
            r = self.client.get("/api/insights/ad-correlation")
            data = r.get_json()
            self.assertTrue(data["configured"])
            self.assertFalse(data["google_ads"]["configured"])
            self.assertTrue(data["meta_ads"]["configured"])
            self.assertEqual(len(data["meta_ads"]["verdicts"]), 1)
        finally:
            self._restore_bundled(bundled_dir, orig_bundled)


# ============================================================================
# /api/insights/content-traffic-correlation
# ============================================================================


class ContentTrafficCorrelationTests(InsightsV2ApiTests):
    def test_returns_shape_even_with_no_data(self):
        r = self.client.get("/api/insights/content-traffic-correlation?days=30")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data["ok"])
        self.assertIsInstance(data["matches"], list)
        self.assertIsInstance(data["unmatched_spikes"], list)
        self.assertIn("_meta", data)

    def test_days_param(self):
        r = self.client.get("/api/insights/content-traffic-correlation?days=14")
        data = r.get_json()
        self.assertEqual(data["_meta"]["days_covered"], 14)


# ============================================================================
# HTML structure — Insights v2 surface
# ============================================================================


class InsightsV2HtmlStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (CAMPAIGN_OS.parent / "campaign-os" / "campaign-os.html").read_text()

    def test_render_insights_v2_function_exists(self):
        self.assertIn("async function renderInsightsV2", self.html)

    def test_top_instagram_posts_endpoint_referenced(self):
        self.assertIn("/api/insights/top-instagram-posts", self.html)

    def test_ad_correlation_endpoint_referenced(self):
        self.assertIn("/api/insights/ad-correlation", self.html)

    def test_color_signals_present(self):
        # green / yellow / red color codes
        self.assertIn("#10b981", self.html)  # green
        self.assertIn("#f59e0b", self.html)  # yellow/amber
        self.assertIn("#ef4444", self.html)  # red

    def test_trends_freshness_banner_present(self):
        self.assertIn("tr-freshness-banner", self.html)
        self.assertIn("tr-refresh", self.html)

    def test_learning_subheader_present(self):
        self.assertIn("the long-memory view", self.html)

    def test_insights_v2_layout_present(self):
        for marker in ("ins-v2-body", "ins-ig-top-list", "ins-pages-list",
                        "ins-ad-block", "ins-ad-status"):
            self.assertIn(marker, self.html, f"Missing {marker} in Insights v2")


if __name__ == "__main__":
    unittest.main()