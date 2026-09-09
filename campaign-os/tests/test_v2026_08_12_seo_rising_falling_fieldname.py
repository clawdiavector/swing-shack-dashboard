"""Regression test for the SEO rising/falling field-name bug.

The /api/intel/performance endpoint was returning `seo.rising=[]` and
`seo.falling=[]` even when seo-rankings.json shipped real `rising` and
`falling` lists. Three functions in _lib/intelligence.py were reading
the legacy snake_case keys `rising_keywords` / `falling_keywords`
which the live dataset never used:

  - performance_view()  (lines 836, 855-856) — drives the Performance tab
  - explain_performance() (lines 1941, 1950) — drives /api/intel/explain
  - weekly report SEO movers (lines 2318-2319) — drives weekly claims

Fix: accept both shapes — old `rising_keywords` (snake_case) and new
`rising` — mirroring the fallback pattern that already exists in the
weekly-report SEO cross-cut at line ~2853.

This test pins:
  1) performance_view returns real rising + falling lists when seo-rankings.json
     has the new-shape keys (no `rising_keywords`/`falling_keywords`).
  2) performance_view still returns real rising + falling when the old snake
     keys are used (back-compat for any leftover callers).
  3) performance_view returns both `rising` and `falling` consistently with
     the same fallback logic (no drift between the two fields).
  4) explain_performance emits a seo-trend-up claim when rising is populated.
  5) explain_performance emits a seo-trend-down claim when falling is populated.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CAMPAIGN_OS_ROOT = os.path.abspath(os.path.join(HERE, '..'))
REPO_ROOT = os.path.abspath(os.path.join(CAMPAIGN_OS_ROOT, '..'))
if CAMPAIGN_OS_ROOT not in sys.path:
    sys.path.insert(0, CAMPAIGN_OS_ROOT)


# ── Helpers ────────────────────────────────────────────────────────────────

def _isolated_app():
    """Return a Flask test client with an isolated DATA_DIR + an authed session."""
    tmp = tempfile.mkdtemp(prefix='campaign-os-rising-falling-test-')
    os.environ['DATA_DIR'] = tmp
    # Reload app module so DATA_DIR is picked up at call time
    if 'app' in sys.modules:
        del sys.modules['app']
    import app as app_module
    client = app_module.app.test_client()
    # The SPA is gated by cookie auth. _is_authed() only checks that the
    # token is a valid signed payload — content doesn't matter — so any
    # URLSafeTimedSerializer-signed token works.
    token = app_module._serializer.dumps({'authed': True})
    client.set_cookie('cos_session', token)
    return client, tmp


def _isolated_data_dir():
    """Create an isolated `data/` dir for the intelligence module to read from.
    The intelligence module resolves DATA_DIR = REPO_ROOT/data at import time
    and re-reads the file on every call, so we can just rebind the module
    attribute to point at our tmp dir for the test.
    """
    tmp_data = tempfile.mkdtemp(prefix='campaign-os-rising-falling-data-')
    # Stub the other files performance_view touches so it doesn't NPE.
    for fname in ('ig-analytics.json', 'ga4-metrics.json', 'seo-audit.json',
                  'website-insights.json', 'ab-tests.json', 'gbp-input.json'):
        with open(os.path.join(tmp_data, fname), 'w') as f:
            json.dump({}, f)
    return tmp_data


def _write_seo_rankings(data_dir, shape='new'):
    """Write a synthetic seo-rankings.json. shape='new' uses `rising`/`falling`,
    shape='old' uses `rising_keywords`/`falling_keywords`, shape='empty' uses
    neither (returns [] gracefully).
    """
    payload = {
        "metadata": {"fetched_at": "2026-08-04T00:00:00Z"},
        "summary": {"up": 5, "down": 2, "unchanged": 9},
        "binned": {"top_3": {"new": 8, "old": 6}, "top_10": {"new": 3, "old": 3}},
        "keywords": [],
        "quick_wins": [
            {"keyword": "club fitting near me", "current_rank": 5, "previous_rank": 4},
        ],
    }
    sample_rising = [
        {"keyword": "custom club fitting", "current_rank": 6, "previous_rank": 24},
        {"keyword": "indoor golf johannesburg", "current_rank": 9, "previous_rank": 30},
        {"keyword": "golf lessons beginners", "current_rank": 12, "previous_rank": 28},
        {"keyword": "trackman session", "current_rank": 4, "previous_rank": 16},
        {"keyword": "swing speed analysis", "current_rank": 7, "previous_rank": 19},
    ]
    sample_falling = [
        {"keyword": "indoor golf practice", "current_rank": 3, "previous_rank": 1},
        {"keyword": "golf simulator johannesburg", "current_rank": 8, "previous_rank": 4},
    ]
    if shape == 'new':
        payload["rising"] = sample_rising
        payload["falling"] = sample_falling
    elif shape == 'old':
        payload["rising_keywords"] = sample_rising
        payload["falling_keywords"] = sample_falling
    elif shape == 'empty':
        pass  # neither key present
    else:
        raise ValueError(f"Unknown shape: {shape}")
    with open(os.path.join(data_dir, 'seo-rankings.json'), 'w') as f:
        json.dump(payload, f)


# ── Tests ──────────────────────────────────────────────────────────────────

class PerformanceViewSeoFieldNameTests(unittest.TestCase):
    """performance_view() must return real rising/falling data regardless of
    which field shape seo-rankings.json uses.

    Test strategy: rebind _lib.intelligence.DATA_DIR to a tmp dir for the
    duration of each test so performance_view() reads our synthetic fixture
    instead of the repo-root data/ file.
    """

    def setUp(self):
        self.client, _ = _isolated_app()
        # Snapshot current DATA_DIR so we can restore it after the test
        import _lib.intelligence as intel
        self._intel = intel
        self._real_data_dir = intel.DATA_DIR
        self._tmp_data = _isolated_data_dir()
        intel.DATA_DIR = self._tmp_data

    def tearDown(self):
        self._intel.DATA_DIR = self._real_data_dir
        shutil.rmtree(self._tmp_data, ignore_errors=True)

    def test_new_shape_rising_falling_returned(self):
        """Live seo-rankings.json uses `rising`/`falling` (no snake_case).
        The Performance widget must show 5 rising + 2 falling (was 0/0 before)."""
        _write_seo_rankings(self._tmp_data, shape='new')
        rv = self.client.get('/api/intel/performance')
        self.assertEqual(rv.status_code, 200, rv.data[:200])
        body = rv.get_json()
        seo = body.get('seo', {})
        self.assertEqual(len(seo.get('rising', [])), 5,
                         f"expected 5 rising, got {len(seo.get('rising', []))}")
        self.assertEqual(len(seo.get('falling', [])), 2,
                         f"expected 2 falling, got {len(seo.get('falling', []))}")
        # Confirm the actual keywords made it through
        self.assertEqual(seo['rising'][0]['keyword'], 'custom club fitting')
        self.assertEqual(seo['falling'][0]['keyword'], 'indoor golf practice')

    def test_old_shape_still_works(self):
        """Back-compat: legacy seo-rankings.json with `rising_keywords` /
        `falling_keywords` must still populate the response."""
        _write_seo_rankings(self._tmp_data, shape='old')
        rv = self.client.get('/api/intel/performance')
        self.assertEqual(rv.status_code, 200)
        seo = rv.get_json().get('seo', {})
        self.assertEqual(len(seo.get('rising', [])), 5)
        self.assertEqual(len(seo.get('falling', [])), 2)

    def test_empty_rising_falling_returns_empty(self):
        """When neither shape is present, returns empty lists (no fake data)."""
        _write_seo_rankings(self._tmp_data, shape='empty')
        rv = self.client.get('/api/intel/performance')
        self.assertEqual(rv.status_code, 200)
        seo = rv.get_json().get('seo', {})
        self.assertEqual(seo.get('rising', []), [])
        self.assertEqual(seo.get('falling', []), [])

    def test_rising_and_falling_have_consistent_fallback(self):
        """Both fields must use the same fallback logic so they don't drift
        if one file uses old shape and one uses new shape."""
        _write_seo_rankings(self._tmp_data, shape='new')
        rv = self.client.get('/api/intel/performance')
        seo = rv.get_json().get('seo', {})
        # Both must be populated for the new shape (no shape-mismatch surprises)
        self.assertGreater(len(seo['rising']), 0)
        self.assertGreater(len(seo['falling']), 0)


class ExplainPerformanceSeoFieldNameTests(unittest.TestCase):
    """explain_performance() must emit SEO claims when rising/falling
    data is present in seo-rankings.json (regardless of which key shape).
    """

    def setUp(self):
        self.client, _ = _isolated_app()
        import _lib.intelligence as intel
        self._intel = intel
        self._real_data_dir = intel.DATA_DIR
        self._tmp_data = _isolated_data_dir()
        intel.DATA_DIR = self._tmp_data

    def tearDown(self):
        self._intel.DATA_DIR = self._real_data_dir
        shutil.rmtree(self._tmp_data, ignore_errors=True)

    def test_rising_data_emits_seo_trend_up_claim(self):
        _write_seo_rankings(self._tmp_data, shape='new')
        rv = self.client.get('/api/intel/explain')
        self.assertEqual(rv.status_code, 200, rv.data[:200])
        body = rv.get_json()
        kinds = [i.get('kind') for i in body.get('insights', [])]
        self.assertIn('seo-trend-up', kinds,
                      f"expected seo-trend-up claim, got kinds={kinds}")
        # Find the SEO rising claim and confirm the keyword made it
        rising_claim = next(i for i in body['insights'] if i.get('kind') == 'seo-trend-up')
        self.assertIn('custom club fitting', rising_claim['claim'])

    def test_falling_data_emits_seo_trend_down_claim(self):
        _write_seo_rankings(self._tmp_data, shape='new')
        rv = self.client.get('/api/intel/explain')
        self.assertEqual(rv.status_code, 200)
        body = rv.get_json()
        kinds = [i.get('kind') for i in body.get('insights', [])]
        self.assertIn('seo-trend-down', kinds,
                      f"expected seo-trend-down claim, got kinds={kinds}")
        falling_claim = next(i for i in body['insights'] if i.get('kind') == 'seo-trend-down')
        self.assertIn('indoor golf practice', falling_claim['claim'])

    def test_old_shape_emits_seo_claims_too(self):
        _write_seo_rankings(self._tmp_data, shape='old')
        rv = self.client.get('/api/intel/explain')
        self.assertEqual(rv.status_code, 200)
        kinds = [i.get('kind') for i in rv.get_json().get('insights', [])]
        self.assertIn('seo-trend-up', kinds)
        self.assertIn('seo-trend-down', kinds)


if __name__ == '__main__':
    unittest.main()