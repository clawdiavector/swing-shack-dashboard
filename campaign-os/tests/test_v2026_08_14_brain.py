"""
Tests for the CMO brain section (_weekly_build_brain).

Added 2026-08-14 in response to Christelle's call-out:
"You have access to ALL the data but you are not using it. This is not
intelligent, this does not carry weigh. Can you not think like a marketing agent?"

The brain MUST:
  - read funnel-leaks.json + cross-reference GA4 booking-page traffic
  - read seo-rankings.json + surface rising/falling keywords
  - read competitor-tracker.json + recommend a counter-move
  - read post-conversion-score.json + name the winning themes + hooks
  - call out the paid-reach gap honestly (meta-ads.json _meta note)
  - compute reach efficiency: stories/hr vs posts/hr
  - model the funnel-leak revenue exposure (sessions x conversion x basket)
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

REPO = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard'
sys.path.insert(0, os.path.join(REPO, 'campaign-os'))

# Pre-import setup so app.py can import (DATA_DIR must be writable)
_TEST_TMPDIR = tempfile.mkdtemp(prefix='brain_test_')
_TEST_DATA_DIR = os.path.join(_TEST_TMPDIR, 'data')
os.makedirs(_TEST_DATA_DIR, exist_ok=True)
os.environ['DATA_DIR'] = _TEST_DATA_DIR


class TestWeeklyBuildBrain(unittest.TestCase):
    """Test that _weekly_build_brain reads everything it should and produces a
    non-trivial marketing read section."""

    @classmethod
    def setUpClass(cls):
        # Copy the real data files we need into the test DATA_DIR
        REAL = os.path.join(REPO, 'data')
        for fn in ('funnel-leaks.json', 'seo-rankings.json',
                   'competitor-tracker.json', 'post-conversion-score.json',
                   'counter-moves.json', 'booking-value-model.json',
                   'meta-ads.json', 'recommendation-outcomes.json',
                   'retargeting-recommendations.json'):
            src = os.path.join(REAL, fn)
            dst = os.path.join(_TEST_DATA_DIR, fn)
            if os.path.exists(src):
                shutil.copy(src, dst)

    def setUp(self):
        import app
        self._app = app
        # Stub the live meta_api calls so the test doesn't hang on Graph API.
        # We don't care about exact post/fan counts for the brain — the brain
        # reads from on-disk JSON files, not from Graph API.
        from _lib import meta_api
        self._meta_patches = [
            patch.object(meta_api, 'get_page_info', return_value={
                'fan_count': 445, 'followers_count': 445,
                'name': 'Swing Shack', 'id': '198859063301219'
            }),
            patch.object(meta_api, 'get_page_insights', return_value={
                '_flat': {}, '_meta': {'metrics_returned': []}
            }),
            patch.object(meta_api, 'list_recent_posts', return_value={'data': [], 'paging': {}}),
            patch.object(meta_api, 'list_page_posts', return_value={'data': [], 'paging': {}}),
            patch.object(meta_api, 'summarize_stories', return_value={
                'ig_stories': {'count': 2, 'reach_total': 41, 'follows_total': 0,
                               'total_interactions_total': 0, 'oldest': None, 'newest': None,
                               'items': []},
                'fb_page_stories': {'count': 1, 'oldest': None, 'newest': None, 'items': []},
                'combined_count': 3, 'combined_reach': 41, 'overlap_ids': [],
                'data_sources': ['instagram_stories'], 'truth_note': '24h',
            }),
        ]
        for p in self._meta_patches:
            p.start()

    def test_brain_returns_html(self):
        metrics = self._app._weekly_compute_metrics('swing-shack')
        cur = metrics['current']
        brain = self._app._weekly_build_brain(metrics, cur, metrics.get('prev'), '2026-08-14')
        self.assertIsInstance(brain, str)
        self.assertGreater(len(brain), 500)  # non-trivial
        self.assertIn('class="section brain"', brain)

    def test_brain_includes_verdict(self):
        metrics = self._app._weekly_compute_metrics('swing-shack')
        cur = metrics['current']
        brain = self._app._weekly_build_brain(metrics, cur, None, '2026-08-14')
        self.assertIn('Verdict:', brain)
        # If 0 content published this week, verdict mentions that
        if cur.get('weekly', {}).get('content_published', 0) == 0:
            self.assertIn('paused', brain.lower())

    def test_brain_references_funnel_leaks(self):
        metrics = self._app._weekly_compute_metrics('swing-shack')
        cur = metrics['current']
        brain = self._app._weekly_build_brain(metrics, cur, None, '2026-08-14')
        # The funnel-leaks file mentions /bookings/ specifically
        self.assertIn('/bookings/', brain)
        # Renamed section "Funnel leak" -> "Where the money is leaking" in
        # 2026-08-14 value-add rebuild. Test checks the new phrasing.
        self.assertIn('money is leaking', brain)

    def test_brain_references_seo_movers(self):
        metrics = self._app._weekly_compute_metrics('swing-shack')
        cur = metrics['current']
        brain = self._app._weekly_build_brain(metrics, cur, None, '2026-08-14')
        # SEO file has 'putter fitting' as a rising keyword
        self.assertIn('putter fitting', brain)
        self.assertIn('SEO momentum', brain)

    def test_brain_references_competitor(self):
        metrics = self._app._weekly_compute_metrics('swing-shack')
        cur = metrics['current']
        brain = self._app._weekly_build_brain(metrics, cur, None, '2026-08-14')
        self.assertIn('Golf Bar', brain)
        # Renamed "Counter-move ready" -> "The only counter-move that works" in
        # 2026-08-14 value-add rebuild. Test checks the new phrasing.
        self.assertIn('counter-move', brain.lower())

    def test_brain_references_winning_themes(self):
        metrics = self._app._weekly_compute_metrics('swing-shack')
        cur = metrics['current']
        brain = self._app._weekly_build_brain(metrics, cur, None, '2026-08-14')
        # post-conversion-score.json has 'club_fitting' and 'booking_cta' as top themes
        self.assertIn('club_fitting', brain)
        self.assertIn('booking_cta', brain)

    def test_brain_calls_out_paid_reach_gap(self):
        metrics = self._app._weekly_compute_metrics('swing-shack')
        cur = metrics['current']
        brain = self._app._weekly_build_brain(metrics, cur, None, '2026-08-14')
        # meta-ads.json has a _meta.note about being synthesised
        self.assertIn('Paid reach', brain)
        self.assertIn('synthesised', brain.lower())

    def test_brain_models_revenue_exposure(self):
        metrics = self._app._weekly_compute_metrics('swing-shack')
        cur = metrics['current']
        brain = self._app._weekly_build_brain(metrics, cur, None, '2026-08-14')
        self.assertIn('Money on the table', brain)
        self.assertIn('modelled', brain.lower())

    def test_brain_includes_story_vs_post_efficiency(self):
        metrics = self._app._weekly_compute_metrics('swing-shack')
        cur = metrics['current']
        brain = self._app._weekly_build_brain(metrics, cur, None, '2026-08-14')
        # Should reference stories vs posts efficiency
        self.assertIn('Stories', brain)
        self.assertIn('hr', brain.lower())

    def test_brain_includes_ship_today_recommendation(self):
        metrics = self._app._weekly_compute_metrics('swing-shack')
        cur = metrics['current']
        brain = self._app._weekly_build_brain(metrics, cur, None, '2026-08-14')
        self.assertIn('What to ship', brain)
        self.assertIn('Ship today', brain)

    def test_brain_includes_gaps_section(self):
        metrics = self._app._weekly_compute_metrics('swing-shack')
        cur = metrics['current']
        brain = self._app._weekly_build_brain(metrics, cur, None, '2026-08-14')
        self.assertIn('Gaps', brain)
        # recommendation-outcomes.json has 0 exec_rate - brain should flag it
        self.assertIn('exec rate', brain.lower())

    def test_brain_survives_empty_data_dir(self):
        """If DATA_DIR is empty (first deploy, no data files yet), brain must
        not crash - it should return a valid HTML with placeholders."""
        # Wipe DATA_DIR (handle both files and subdirs)
        for entry in os.listdir(_TEST_DATA_DIR):
            p = os.path.join(_TEST_DATA_DIR, entry)
            try:
                if os.path.isfile(p) or os.path.islink(p):
                    os.remove(p)
                elif os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
            except (PermissionError, OSError):
                pass
        # Use a fresh tmpdir to avoid touching the global DATA_DIR
        empty = tempfile.mkdtemp(prefix='brain_empty_')
        os.environ['DATA_DIR'] = empty
        try:
            # Force re-import by clearing cached modules
            for mod_name in list(sys.modules.keys()):
                if mod_name == 'app' or mod_name.startswith('_lib.'):
                    del sys.modules[mod_name]
            import app as fresh_app
            # Re-stub meta_api after re-import
            from _lib import meta_api as fresh_meta
            for fn in ('get_page_info', 'get_page_insights', 'list_recent_posts',
                       'list_page_posts', 'summarize_stories'):
                setattr(fresh_meta, fn, lambda *a, **kw: {'_flat': {}, 'data': [], '_meta': {}})
            metrics = fresh_app._weekly_compute_metrics('swing-shack')
            cur = metrics['current']
            brain = fresh_app._weekly_build_brain(metrics, cur, None, '2026-08-14')
            self.assertIsInstance(brain, str)
            self.assertIn('section brain', brain)
        finally:
            os.environ['DATA_DIR'] = _TEST_DATA_DIR
            shutil.rmtree(empty, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)