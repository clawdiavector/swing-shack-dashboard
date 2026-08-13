"""
test_v2026_08_13_ad_correlation_duplicate_ga4_rows.py

Regression test for the duplicate-GA4-row bug in the ad-correlation verdicts.

GA4 may emit MULTIPLE rows for the same path (one per date window — daily /
weekly / monthly snapshots stacked). The old code did
`match_page = next((p for p in pages if p.get("path") == lp))`, which always
returned the FIRST match. So every campaign that pointed to "/" (the homepage,
in the swing-shack case) rendered the same verdict: "GA4 shows 153 sessions on
that page." No matter how the campaigns actually performed, no matter what the
spend or click count was, the verdict looked identical — a fake signal.

This test seeds two scenarios and asserts the verdicts now correctly:

  1. SUM sessions across all matching GA4 rows (not first match only).
  2. Compute clicks:sessions ratio and cost:session.
  3. Verdict text includes the ratio / cost so the user sees real numbers.
  4. When no GA4 row matches the landing page, verdict says so honestly.

The fix lives in campaign-os/_lib/insights_correlator.py in the
_verdicts_for() helper. This test pins the new behaviour so a future "let's
simplify back to first-match" doesn't sneak through.
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


class AdCorrelationDuplicateRowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="campaign-os-ads-dup-"))
        cls.bundled_dir = Path(tempfile.mkdtemp(prefix="campaign-os-ads-dup-bundled-"))
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
    # Scenario 1: GA4 has 5 rows for "/", all pointed at by 2 campaigns.
    # The two campaigns have very different spend / click counts — they must
    # render DIFFERENT verdicts (clicks:sessions ratio, cost per session) and
    # both must reference the SUM of all matching sessions (not just the first).
    # ------------------------------------------------------------------
    def test_duplicate_ga4_rows_summed_per_campaign(self):
        # GA4 emits 5 separate snapshots for "/" — this is what was happening
        # in production (daily / weekly / monthly windows stacked together).
        ga4_rows = [
            {"path": "/", "sessions": 153, "engRate": "55%"},
            {"path": "/", "sessions": 149, "engRate": "53%"},
            {"path": "/", "sessions": 104, "engRate": "60%"},
            {"path": "/", "sessions": 30,  "engRate": "47%"},
            {"path": "/", "sessions": 23,  "engRate": "49%"},
        ]
        total_expected = sum(r["sessions"] for r in ga4_rows)  # 459
        (self.tmpdir / "ga4-metrics.json").write_text(json.dumps({
            "pages": ga4_rows,
            "total_sessions": total_expected,
        }))
        (self.tmpdir / "google-ads.json").write_text(json.dumps({
            "campaigns": [
                {
                    "id": "g-1", "name": "Big spender",
                    "start_date": "2025-01-01", "end_date": "2025-01-31",
                    "spend": 1000.0, "clicks": 500, "impressions": 10000,
                    "landing_page": "/",
                },
                {
                    "id": "g-2", "name": "Cheap test",
                    "start_date": "2025-02-01", "end_date": "2025-02-28",
                    "spend": 50.0, "clicks": 25, "impressions": 800,
                    "landing_page": "/",
                },
            ]
        }))

        r = self.client.get("/api/insights/ad-correlation")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data["configured"])
        verdicts = data["google_ads"]["verdicts"]
        self.assertEqual(len(verdicts), 2)

        big = next(v for v in verdicts if v["campaign_id"] == "g-1")
        cheap = next(v for v in verdicts if v["campaign_id"] == "g-2")

        # BOTH campaigns must report the SUM (459), not just the first match (153).
        self.assertEqual(big["matching_page_sessions"], total_expected,
            f"Big-spender verdict should sum all 5 GA4 rows, got {big['matching_page_sessions']}")
        self.assertEqual(cheap["matching_page_sessions"], total_expected,
            f"Cheap-test verdict should sum all 5 GA4 rows, got {cheap['matching_page_sessions']}")

        # Both verdict strings must mention the summed session total (459).
        self.assertIn("459", big["verdict"],
            f"Big-spender verdict should mention 459 (sum), got: {big['verdict']}")
        self.assertIn("459", cheap["verdict"],
            f"Cheap-test verdict should mention 459 (sum), got: {cheap['verdict']}")

        # Verdict must NOT still say the stale "153 sessions" (the old first-match bug).
        self.assertNotIn("153 sessions", big["verdict"],
            "Verdict regressed to first-match-only — old bug is back")
        self.assertNotIn("153 sessions", cheap["verdict"],
            "Verdict regressed to first-match-only — old bug is back")

        # Cost-per-session: big = R2.18, cheap = R0.11. Different numbers, so
        # the verdict must surface different ratios per campaign.
        self.assertAlmostEqual(big["cost_per_session"], round(1000.0 / 459, 2), places=2)
        self.assertAlmostEqual(cheap["cost_per_session"], round(50.0 / 459, 2), places=2)
        self.assertIn("R2.18", big["verdict"])
        self.assertIn("R0.11", cheap["verdict"])

        # clicks:sessions ratio must be in both verdicts.
        self.assertIn("of sessions", big["verdict"])
        self.assertIn("of sessions", cheap["verdict"])

        # The two verdicts must NOT be identical — the whole point of the fix.
        self.assertNotEqual(big["verdict"], cheap["verdict"],
            "Big-spender and cheap-test rendered the same verdict — the user "
            "can't tell them apart, which is the bug we're closing")

    # ------------------------------------------------------------------
    # Scenario 2: campaign landing_page has ZERO GA4 matches. Verdict must
    # say so honestly instead of silently writing "0 sessions" or "no data".
    # ------------------------------------------------------------------
    def test_unmatched_landing_page_says_so_honestly(self):
        (self.tmpdir / "ga4-metrics.json").write_text(json.dumps({
            "pages": [{"path": "/", "sessions": 200, "engRate": "50%"}],
        }))
        (self.tmpdir / "google-ads.json").write_text(json.dumps({
            "campaigns": [
                {
                    "id": "g-x", "name": "Niche push",
                    "start_date": "2025-03-01", "end_date": "2025-03-31",
                    "spend": 200.0, "clicks": 50, "impressions": 1000,
                    "landing_page": "/coaching/pga-pro/",
                },
            ]
        }))

        r = self.client.get("/api/insights/ad-correlation")
        data = r.get_json()
        v = data["google_ads"]["verdicts"][0]
        # No GA4 rows match /coaching/pga-pro/ — sessions count is 0.
        self.assertEqual(v["matching_page_sessions"], 0)
        self.assertIsNone(v["cost_per_session"])
        # Honest fallback — not "GA4 shows 0 sessions" misleading.
        self.assertIn("no data", v["verdict"].lower())
        self.assertIn("tracking gap", v["verdict"].lower())
        # Spend + landing page still in the verdict (preserves existing test contract).
        self.assertIn("200", v["verdict"])
        self.assertIn("/coaching/pga-pro/", v["verdict"])

    # ------------------------------------------------------------------
    # Scenario 3: meta_ads path also picks up the new logic (same _verdicts_for).
    # ------------------------------------------------------------------
    def test_meta_ads_also_uses_summed_sessions(self):
        (self.tmpdir / "ga4-metrics.json").write_text(json.dumps({
            "pages": [
                {"path": "/club-fitting/", "sessions": 50, "engRate": "70%"},
                {"path": "/club-fitting/", "sessions": 40, "engRate": "65%"},
            ],
        }))
        (self.tmpdir / "meta-ads.json").write_text(json.dumps({
            "campaigns": [
                {
                    "id": "m-1", "name": "Fitting promo",
                    "start_date": "2025-04-01", "end_date": "2025-04-30",
                    "spend": 300.0, "clicks": 90, "impressions": 5000,
                    "landing_page": "/club-fitting/",
                },
            ]
        }))

        r = self.client.get("/api/insights/ad-correlation")
        data = r.get_json()
        v = data["meta_ads"]["verdicts"][0]
        self.assertEqual(v["matching_page_sessions"], 90)  # 50 + 40
        self.assertIn("90 sessions", v["verdict"])
        # No em-dash in verdict text (standing rule).
        self.assertNotIn("—", v["verdict"])


if __name__ == "__main__":
    unittest.main()
