"""
Tests for the Windsor.ai paid-media fetcher (scripts/fetch_windsor.py) +
_lib/windsor_client.py + the brain's data-aware paid-reach warning.

Added 2026-08-14 in response to Christelle's call-out:
"You have access to ALL the data but you are not using it. REAL DATA ALWAYS."

Tests:
  _lib.windsor_client:
    - read_api_key() resolves from env first, then on-disk creds, never raises
    - fetch_connector() handles bare-list, {"data": [...]} and {"error": ...}
    - iso_window / week_window / month_window return sensible YYYY-MM-DD pairs
    - no network calls are made (read-only constraint verified)

  scripts/fetch_windsor:
    - build_meta_ads() with mocked client produces the live-shape payload
      (totals, week, live=True, _meta with Windsor note)
    - build_google_ads() with mocked client produces dashboard-shape payload
      (top-level spend/impressions/clicks/conversions matching app.py:11444)
    - currency detection picks the most common currency across rows
    - _window_subset() filters correctly to last N days
    - failed fetch produces live=False + error in payload (no fabricated data)
    - _iso_date() handles both YYYYMMDD and YYYY-MM-DD Windsor variants

  app.py brain:
    - "Paid reach is invisible" warning still fires for synthesised files
    - "Paid reach is invisible" warning is REPLACED by "X is live via Windsor"
      when meta-ads.json or weekly['google_ads'] has live=True
    - "attempted but Windsor fetch failed" surfaces the error note honestly
"""
from __future__ import annotations

import datetime as dt
import importlib
import importlib.util as _ilu
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock


REPO = "/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard"
sys.path.insert(0, os.path.join(REPO, "campaign-os"))

# ── Locally import _lib.windsor_client (no global side-effects) ─────────────
from _lib import windsor_client as _wc  # noqa: E402

# ── Pre-import app.py with writable DATA_DIR so module load doesn't crash ────
_TEST_TMPDIR = tempfile.mkdtemp(prefix="windsor_test_")
_TEST_DATA_DIR = os.path.join(_TEST_TMPDIR, "data")
os.makedirs(_TEST_DATA_DIR, exist_ok=True)
os.environ["DATA_DIR"] = _TEST_DATA_DIR


def _load_fetcher_module():
    """Load campaign-os/_lib/windsor_fetcher.py fresh each time so tests don't share state.

    The fetcher module does `from . import windsor_client as _w` which only works
    when loaded as part of the _lib package. We register _lib as a package alias
    so both relative and absolute imports resolve correctly.
    """
    import types
    pkg = types.ModuleType("_lib")
    pkg.__path__ = [os.path.join(REPO, "campaign-os", "_lib")]
    sys.modules["_lib"] = pkg
    # Pre-load the dependent module under the right name
    import _lib.windsor_client as _wc_pkg
    sys.modules["windsor_client"] = _wc_pkg  # so the fetcher's fallback works too
    spec = _ilu.spec_from_file_location(
        "_lib.windsor_fetcher",
        os.path.join(REPO, "campaign-os", "_lib", "windsor_fetcher.py"),
        submodule_search_locations=pkg.__path__,
    )
    assert spec is not None, "Failed to create module spec for windsor_fetcher.py"
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Fixtures ─────────────────────────────────────────────────────────────────
REAL_FACEBOOK_ROWS = [
    {
        "date": "2026-08-13",
        "campaign": "Club Fitting Awareness",
        "campaign_id": "23847000000001",
        "spend": 425.50,
        "impressions": 12480,
        "clicks": 213,
        "reach": 8120,
        "frequency": 1.54,
        "currency": "ZAR",
    },
    {
        "date": "2026-08-12",
        "campaign": "Club Fitting Awareness",
        "campaign_id": "23847000000001",
        "spend": 380.00,
        "impressions": 11200,
        "clicks": 187,
        "reach": 7400,
        "frequency": 1.51,
        "currency": "ZAR",
    },
    {
        "date": "2026-07-30",
        "campaign": "TrackMan Sessions",
        "campaign_id": "23847000000002",
        "spend": 250.00,
        "impressions": 8500,
        "clicks": 142,
        "reach": 6100,
        "currency": "ZAR",
    },
]

REAL_GOOGLE_ROWS = [
    {
        "date": "2026-08-13",
        "campaign": "Search - club fitting near me",
        "campaign_id": "1234567890",
        "spend": 195.40,
        "impressions": 4200,
        "clicks": 87,
        "currency": "ZAR",
    },
    {
        "date": "2026-08-12",
        "campaign": "Search - club fitting near me",
        "campaign_id": "1234567890",
        "spend": 110.20,
        "impressions": 3100,
        "clicks": 54,
        "currency": "ZAR",
    },
    {
        "date": "2026-07-20",
        "campaign": "Display - remarketing",
        "campaign_id": "1234567891",
        "spend": 50.00,
        "impressions": 8200,
        "clicks": 18,
        "currency": "ZAR",
    },
]


# ── Test: read_api_key resolution ───────────────────────────────────────────
class TestReadApiKey(unittest.TestCase):
    def setUp(self):
        self._env_backup = {}
        for k in ("WINDSOR_API_KEY", "WINDSOR_API_KEY_FILE", "SWING_SHACK_REPO_ROOT"):
            self._env_backup[k] = os.environ.get(k)
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._env_backup.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)

    def test_env_var_wins_over_file(self):
        os.environ["WINDSOR_API_KEY"] = "env-key-12345"
        # Even if a creds file exists, env var wins
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        tmp.write(json.dumps({"api_key": "file-key-should-lose"}))
        tmp.close()
        os.environ["WINDSOR_API_KEY_FILE"] = tmp.name
        try:
            self.assertEqual(_wc.read_api_key(), "env-key-12345")
        finally:
            os.unlink(tmp.name)

    def test_file_fallback(self):
        # Write a creds file in a temp dir, point SWING_SHACK_REPO_ROOT at it
        creds_dir = os.path.join(tempfile.mkdtemp(prefix="wc_creds_"), "credentials")
        os.makedirs(creds_dir, exist_ok=True)
        creds_path = os.path.join(creds_dir, "windsor-api.json")
        with open(creds_path, "w") as f:
            json.dump({"api_key": "file-key-67890"}, f)
        repo_root = os.path.dirname(creds_dir)
        os.environ["SWING_SHACK_REPO_ROOT"] = repo_root
        self.assertEqual(_wc.read_api_key(), "file-key-67890")

    def test_quotes_stripped(self):
        os.environ["WINDSOR_API_KEY"] = '"key-with-quotes"'
        self.assertEqual(_wc.read_api_key(), "key-with-quotes")
        os.environ["WINDSOR_API_KEY"] = "'single-quoted-key'"
        self.assertEqual(_wc.read_api_key(), "single-quoted-key")

    def test_missing_returns_empty_string(self):
        # No env vars, no creds file - should return "" not raise
        self.assertEqual(_wc.read_api_key(), "")


# ── Test: fetch_connector response shapes ────────────────────────────────────
class TestFetchConnector(unittest.TestCase):
    def test_bare_list_response(self):
        fake_url = "https://connectors.windsor.ai/facebook?..."
        with patch.object(_wc, "_http_get_json", return_value=REAL_FACEBOOK_ROWS):
            rows, meta = _wc.fetch_connector(
                "facebook", api_key="k", fields=["date", "spend"], date_from="x", date_to="y"
            )
        self.assertEqual(len(rows), 3)
        self.assertTrue(meta["ok"])
        self.assertEqual(meta["row_count"], 3)

    def test_data_wrapper_response(self):
        with patch.object(_wc, "_http_get_json",
                          return_value={"data": REAL_GOOGLE_ROWS}):
            rows, meta = _wc.fetch_connector(
                "google_ads", api_key="k", fields=["date"], date_from="x", date_to="y"
            )
        self.assertEqual(len(rows), 3)

    def test_error_response_returns_empty_with_error_meta(self):
        with patch.object(_wc, "_http_get_json",
                          return_value={"error": "Please check the API key used: FOO"}):
            rows, meta = _wc.fetch_connector(
                "facebook", api_key="bad", fields=["date"], date_from="x", date_to="y"
            )
        self.assertEqual(rows, [])
        self.assertIn("API key", meta.get("error", ""))

    def test_no_api_key_rejected(self):
        rows, meta = _wc.fetch_connector(
            "facebook", api_key="", fields=["date"], date_from="x", date_to="y"
        )
        self.assertEqual(rows, [])
        self.assertEqual(meta["error"], "no_api_key")

    def test_no_write_actions_exposed(self):
        """Read-only contract: no write side, period."""
        self.assertFalse(hasattr(_wc, "create_campaign"))
        self.assertFalse(hasattr(_wc, "update_budget"))
        self.assertFalse(hasattr(_wc, "pause_ad"))
        # The client itself only has read-side affordances
        public = [n for n in dir(_wc) if not n.startswith("_")]
        # Only read + resolution + helpers
        self.assertIn("read_api_key", public)
        self.assertIn("fetch_connector", public)
        self.assertIn("iso_window", public)


# ── Test: window helpers ─────────────────────────────────────────────────────
class TestWindowHelpers(unittest.TestCase):
    def test_iso_window_shape(self):
        s, e = _wc.iso_window(days_back=30)
        self.assertRegex(s, r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(e, r"^\d{4}-\d{2}-\d{2}$")
        d_s = dt.date.fromisoformat(s)
        d_e = dt.date.fromisoformat(e)
        self.assertEqual((d_e - d_s).days, 30)

    def test_week_window_is_7_days(self):
        s, e = _wc.week_window()
        self.assertEqual((dt.date.fromisoformat(e) - dt.date.fromisoformat(s)).days, 7)

    def test_month_window_is_30_days(self):
        s, e = _wc.month_window()
        self.assertEqual((dt.date.fromisoformat(e) - dt.date.fromisoformat(s)).days, 30)


# ── Test: fetch_windsor normalisation + builders ─────────────────────────────
class TestFetchWindsorNormalisation(unittest.TestCase):
    def setUp(self):
        self.mod = _load_fetcher_module()

    def test_iso_date_accepts_yyyymmdd(self):
        self.assertEqual(self.mod._iso_date("20260813"), "2026-08-13")
        self.assertEqual(self.mod._iso_date("2026-08-13"), "2026-08-13")
        self.assertEqual(self.mod._iso_date(""), "")
        self.assertEqual(self.mod._iso_date(None), "")

    def test_safe_num_handles_none_and_strings(self):
        self.assertEqual(self.mod._safe_num("12.5"), 12.5)
        self.assertEqual(self.mod._safe_num(None), 0)
        self.assertEqual(self.mod._safe_num("not a number"), 0)
        self.assertEqual(self.mod._safe_num(0), 0)

    def test_detect_currency_picks_most_common(self):
        rows = [{"currency": "USD"}, {"currency": "ZAR"}, {"currency": "ZAR"}]
        self.assertEqual(self.mod._detect_currency(rows), "ZAR")
        # All empty -> default USD
        self.assertEqual(self.mod._detect_currency([{}, {}]), "USD")

    def test_window_subset_filters_by_days_back(self):
        rows = [
            {"date": "2026-08-13", "spend": 100},
            {"date": "2026-08-12", "spend": 200},
            {"date": "2026-07-01", "spend": 999},
        ]
        subset = self.mod._window_subset(rows, days_back=7)
        # The 2026-07-01 row should be filtered out (older than 7d from today)
        dates = [r["date"] for r in subset]
        self.assertNotIn("2026-07-01", dates)
        self.assertIn("2026-08-13", dates)

    def test_aggregate_computes_cpc_ctr(self):
        rows = [
            {"spend": 100, "impressions": 1000, "clicks": 50, "reach": 800, "conversions": 2},
            {"spend": 200, "impressions": 2000, "clicks": 80, "reach": 1500, "conversions": 3},
        ]
        agg = self.mod._aggregate(rows)
        self.assertEqual(agg["spend"], 300)
        self.assertEqual(agg["impressions"], 3000)
        self.assertEqual(agg["clicks"], 130)
        self.assertEqual(agg["reach"], 2300)
        self.assertEqual(agg["conversions"], 5)
        # CTR = 130 / 3000 * 100 = 4.33%
        self.assertAlmostEqual(agg["ctr_pct"], 4.33, places=1)
        # CPC = 300 / 130 = 2.31
        self.assertAlmostEqual(agg["cpc"], 2.31, places=1)
        # conversions key still present (sums from r.get('conversions'))
        self.assertEqual(agg["conversions"], 5)


# ── Test: build_meta_ads live shape ──────────────────────────────────────────
class TestBuildMetaAds(unittest.TestCase):
    def setUp(self):
        self.mod = _load_fetcher_module()

    def _stub(self, rows=REAL_FACEBOOK_ROWS, ok=True, error=None):
        if ok:
            return patch.object(
                self.mod._w, "fetch_connector",
                return_value=(rows, {"ok": True, "fetched_at": "2026-08-14T00:00:00Z",
                                     "row_count": len(rows)}),
            )
        return patch.object(
            self.mod._w, "fetch_connector",
            return_value=([], {"error": error or "unknown"}),
        )

    def test_live_payload_shape(self):
        with self._stub():
            payload = self.mod.build_meta_ads("test-key")
        # live flag
        self.assertTrue(payload["live"])
        self.assertEqual(payload["_meta"]["source"], "windsor-facebook")
        self.assertIn("Windsor", payload["_meta"]["note"])
        # campaigns normalised
        self.assertEqual(len(payload["campaigns"]), 3)
        first = payload["campaigns"][0]
        self.assertIn("spend", first)
        self.assertEqual(first["currency"], "ZAR")
        self.assertEqual(first["source"], "windsor-facebook")
        # totals computed
        t = payload["totals"]
        self.assertEqual(t["spend"], 425.50 + 380.00 + 250.00)
        self.assertEqual(t["impressions"], 12480 + 11200 + 8500)
        self.assertEqual(t["clicks"], 213 + 187 + 142)
        self.assertEqual(t["reach"], 8120 + 7400 + 6100)
        self.assertEqual(t["currency"], "ZAR")
        # week subset (last 7d) populated
        self.assertIn("week", payload)
        self.assertIn("spend", payload["week"])
        # 7-day window should be subset of all (less than 30d totals)
        self.assertLessEqual(payload["week"]["spend"], t["spend"])

    def test_failed_fetch_marks_live_false_and_includes_error(self):
        with self._stub(ok=False, error="Please check the API key"):
            payload = self.mod.build_meta_ads("bad-key")
        self.assertFalse(payload["live"])
        self.assertEqual(payload["campaigns"], [])
        self.assertIn("Please check the API key", payload["_meta"]["note"])
        self.assertEqual(payload["error"], "Please check the API key")
        # totals still present (zeroed) so brain doesn't KeyError
        self.assertEqual(payload["totals"]["spend"], 0)

    def test_currency_defaults_to_usd_when_missing(self):
        rows = [
            {"date": "2026-08-13", "campaign": "Test", "spend": 100,
             "impressions": 1000, "clicks": 10}
        ]  # no currency field
        with patch.object(
            self.mod._w, "fetch_connector",
            return_value=(rows, {"ok": True, "fetched_at": "x", "row_count": 1}),
        ):
            payload = self.mod.build_meta_ads("k")
        self.assertEqual(payload["totals"]["currency"], "USD")


# ── Test: build_google_ads dashboard-shape ───────────────────────────────────
class TestBuildGoogleAds(unittest.TestCase):
    def setUp(self):
        self.mod = _load_fetcher_module()

    def test_dashboard_top_level_keys_present(self):
        with patch.object(
            self.mod._w, "fetch_connector",
            return_value=(REAL_GOOGLE_ROWS, {"ok": True, "fetched_at": "x",
                                             "row_count": len(REAL_GOOGLE_ROWS)}),
        ):
            payload = self.mod.build_google_ads("k")
        # These are the keys app.py:11444 reads (ga_data.get('spend') etc.)
        for k in ("spend", "impressions", "clicks", "conversions",
                  "local_actions", "calls", "ctr", "cpc"):
            self.assertIn(k, payload, f"dashboard key missing: {k}")
        self.assertTrue(payload["live"])
        # local_actions + calls stay 0 (Windsor doesn't expose them - honest)
        self.assertEqual(payload["local_actions"], 0)
        self.assertEqual(payload["calls"], 0)
        # spend is the week subset, not 30d totals
        self.assertLessEqual(payload["spend"], payload["totals"]["spend"])

    def test_failed_fetch_propagates_to_dashboard_zeros(self):
        with patch.object(
            self.mod._w, "fetch_connector",
            return_value=([], {"error": "HTTP 500: server error"}),
        ):
            payload = self.mod.build_google_ads("k")
        self.assertFalse(payload["live"])
        for k in ("spend", "impressions", "clicks", "conversions"):
            self.assertEqual(payload[k], 0)
        self.assertEqual(payload["error"], "HTTP 500: server error")


# ── Test: Atomic write helper ────────────────────────────────────────────────
class TestAtomicWrite(unittest.TestCase):
    def test_writes_and_sets_mode(self):
        mod = _load_fetcher_module()
        tmpdir = tempfile.mkdtemp(prefix="atomic_")
        path = os.path.join(tmpdir, "test.json")
        try:
            mod._atomic_write(path, {"hello": "world"})
            self.assertTrue(os.path.exists(path))
            with open(path) as f:
                self.assertEqual(json.load(f), {"hello": "world"})
            mode = os.stat(path).st_mode & 0o777
            self.assertEqual(mode, 0o600)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ── Test: Brain data-aware "Paid reach" warning ──────────────────────────────
class TestBrainPaidReachWarning(unittest.TestCase):
    """Verify the brain's _weekly_build_brain (or inline logic) shows real
    numbers when meta-ads.json or weekly['google_ads'] is live, and keeps the
    synthesised warning when it isn't."""

    def setUp(self):
        # Make app importable with a writable DATA_DIR
        import app as _app
        self._app = _app
        self._tmpdir = tempfile.mkdtemp(prefix="brain_test_")
        self._data_dir = os.path.join(self._tmpdir, "data")
        os.makedirs(self._data_dir, exist_ok=True)
        self._patchers = [
            patch.object(_app, "DATA_DIR", self._data_dir),
            patch.object(_app, "WEEKLY_REPORT_DATA_DIR", self._data_dir),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _run_brain(self, meta_ads_payload, ga_weekly_payload):
        """Invoke _weekly_build_brain with the given meta-ads + google-ads dicts."""
        # Write the synthesised meta-ads fallback for the warning path
        for name, data in [
            ("funnel-leaks.json", {}),
            ("seo-rankings.json", {}),
            ("competitor-tracker.json", {}),
            ("post-conversion-score.json", {}),
            ("counter-moves.json", {}),
            ("meta-ads.json", meta_ads_payload or {}),
            ("recommendation-outcomes.json", {}),
            ("booking-value-model.json", {}),
        ]:
            with open(os.path.join(self._data_dir, name), "w") as f:
                json.dump(data, f)

        from app import _weekly_build_brain
        today = dt.date.today().isoformat()
        metrics = {
            "rows": [], "working": [], "attention": [],
            "has_prev": False, "fb_rows": [], "ig_rows": [],
        }
        cur = {
            "28d": {
                "stories_combined_count": 0, "ig_stories": 0, "fb_stories": 0,
                "stories_combined_reach": 0, "ig_posts_count": 0,
                "ig_reach": 0,
            },
            "weekly": {
                "content_published": 0,
                "ga4_sessions": 0,
                "google_ads": ga_weekly_payload or {},
            },
        }
        return _weekly_build_brain(metrics, cur, prev={}, today=today)

    def test_synthesised_meta_ads_still_triggers_warning(self):
        meta = {
            "_meta": {"note": "Synthesised from IG post engagement. Replace with live API."},
            "campaigns": [{"spend": 1.5, "name": "fake"}],
        }
        html = self._run_brain(meta, {})
        # 2026-08-14 bullet-driven rebuild: the synthesised warning now
        # surfaces as "Paid reach is synthesised" + an explicit
        # "synthesised from organic IG" bullet (no more "Paid reach is
        # invisible" prose wall).
        self.assertIn("synthesised", html.lower())
        self.assertIn("Windsor", html)
        self.assertNotIn("is live", html)

    def test_live_meta_ads_replaces_warning_with_numbers(self):
        meta = {
            "_meta": {"note": "Live Meta Ads data via Windsor.ai connector."},
            "live": True,
            "totals": {"spend": 1234.50, "impressions": 50000, "clicks": 800,
                       "reach": 32000, "ctr_pct": 1.6, "cpc": 1.54,
                       "currency": "ZAR"},
            "week": {"spend": 234.0, "impressions": 9000, "clicks": 142,
                     "reach": 6100, "currency": "ZAR"},
            "campaigns": [{"id": "1"}, {"id": "2"}, {"id": "3"}],
        }
        html = self._run_brain(meta, {})
        # 2026-08-14 bullet-driven rebuild: synthesised warning must NOT
        # appear. Live data appears in TL;DR + Rand stake section + (when
        # organic reach > 0) the cross-referenced "Where attention is
        # coming from." section. The test fixture has no IG organic so
        # we assert against the simpler data paths.
        self.assertNotIn("synthesised", html.lower())
        self.assertIn("Paid", html)  # paid reach surfaces in TL;DR
        self.assertIn("1,234", html)  # spend formatted (ZAR stake)
        self.assertIn("CTR", html)  # CTR in TL;DR
        self.assertIn("CPC", html)  # CPC in TL;DR

    def test_live_google_ads_replaces_warning(self):
        ga = {
            "_meta": {"note": "Live Google Ads data via Windsor.ai connector."},
            "live": True,
            "totals": {"spend": 500.0, "impressions": 12000, "clicks": 240,
                       "conversions": 8, "currency": "ZAR"},
            "week": {"spend": 100.0, "impressions": 2500, "clicks": 50,
                     "conversions": 2, "currency": "ZAR"},
            "campaigns": [{"id": "a"}, {"id": "b"}],
            "spend": 100.0, "impressions": 2500, "clicks": 50,
            "conversions": 2,
        }
        html = self._run_brain({}, ga)
        # 2026-08-14 bullet-driven rebuild: synthesised warning must NOT
        # appear. Google Ads live data surfaces in the Rand stake section.
        self.assertNotIn("synthesised", html.lower())
        self.assertIn("500", html)
        self.assertIn("12,000", html)

    def test_failed_fetch_shows_attempted_but_failed(self):
        meta = {
            "_meta": {"note": "Windsor fetch failed: HTTP 401: Unauthorized"},
            "campaigns": [],
            "live": False,
        }
        html = self._run_brain(meta, {})
        self.assertNotIn("Paid reach is invisible", html)
        self.assertIn("attempted but Windsor fetch failed", html)
        self.assertIn("HTTP 401", html)

    def test_currency_appears_in_live_message(self):
        meta = {
            "_meta": {"note": "Live Meta Ads data via Windsor.ai connector."},
            "live": True,
            "totals": {"spend": 100, "impressions": 1000, "clicks": 10,
                       "reach": 800, "ctr_pct": 1.0, "cpc": 10.0,
                       "currency": "USD"},
            "week": {"spend": 50, "impressions": 500, "clicks": 5,
                     "reach": 400, "currency": "USD"},
            "campaigns": [{"id": "1"}],
        }
        html = self._run_brain(meta, {})
        # USD flag must appear somewhere when Meta Ads is live (currency
        # appears in the Rand stake section as the "Meta Ads spend over 30
        # days" line).
        self.assertIn("USD", html)


if __name__ == "__main__":
    unittest.main()