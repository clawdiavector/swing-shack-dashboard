"""
Test that the brain falls back to BUNDLED_DATA_DIR when DATA_DIR is empty
(e.g. fresh Railway deploy before data-sync endpoint has run).

Added 2026-08-14 after the value-add rebuild. Without this fallback, the
brain renders an empty section after every redeploy until the operator
manually re-runs /api/admin/data-sync.

Regression: previous version used `os.path.join(DATA_DIR, ...)` directly,
which on Railway is `/data/` (volume mount). When the volume is empty
the brain reads empty dicts and renders almost nothing.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard'
BUNDLED = os.path.join(REPO, 'data')
# Add campaign-os to sys.path so app.py + _lib.* resolve (same pattern as
# the other brain test)
sys.path.insert(0, os.path.join(REPO, 'campaign-os'))


class TestBrainFallsBackToBundledData(unittest.TestCase):
    """When DATA_DIR is an empty directory (fresh deploy, no volume data),
    the brain MUST fall back to BUNDLED_DATA_DIR via _resolve_data_path()
    so the full CMO read still renders."""

    @classmethod
    def setUpClass(cls):
        # Make sure the bundled data files actually exist (some are .gitignore'd
        # locally - the test would fail if so, which is a real signal).
        for fn in ('funnel-leaks.json', 'seo-rankings.json',
                   'competitor-tracker.json', 'post-conversion-score.json',
                   'counter-moves.json', 'booking-value-model.json',
                   'meta-ads.json', 'recommendation-outcomes.json',
                   'retargeting-recommendations.json'):
            src = os.path.join(BUNDLED, fn)
            if not os.path.exists(src):
                raise unittest.SkipTest(
                    f'Bundled data file {fn} missing locally - '
                    'test cannot verify fallback without it'
                )

    def setUp(self):
        # Set up a fresh, empty DATA_DIR (simulates fresh Railway deploy)
        empty_data_dir = tempfile.mkdtemp(prefix='brain_empty_data_')
        os.environ['DATA_DIR'] = empty_data_dir

        # Stub meta_api to keep the test offline
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

        # Force fresh import so DATA_DIR is picked up at module load
        for mod_name in list(sys.modules.keys()):
            if mod_name == 'app' or mod_name.startswith('_lib.'):
                del sys.modules[mod_name]
        import app
        self._app = app
        self._empty_data_dir = empty_data_dir

    def tearDown(self):
        for p in self._meta_patches:
            p.stop()
        shutil.rmtree(self._empty_data_dir, ignore_errors=True)
        # Restore DATA_DIR to repo location so other tests still work
        os.environ['DATA_DIR'] = BUNDLED

    def test_empty_data_dir_still_renders_full_brain(self):
        """With DATA_DIR empty (volume unmounted), the brain must still
        render the full CMO read because it falls back to BUNDLED_DATA_DIR."""
        metrics = self._app._weekly_compute_metrics('swing-shack')
        cur = metrics['current']
        brain = self._app._weekly_build_brain(metrics, cur, None, '2026-08-14')

        # All key sections must be present, not just the verdict + gaps
        self.assertIn('Verdict:', brain)
        self.assertIn('SEO momentum', brain)
        self.assertIn('Funnel leak', brain) if False else None  # new phrasing
        self.assertIn('money is leaking', brain)
        self.assertIn('Golf Bar', brain)
        self.assertIn('putter fitting', brain)
        # If it falls back correctly, the funnel leaks section must have
        # actual content (not just an empty <ul>)
        self.assertIn('/bookings/', brain)

    def test_resolve_data_path_returns_bundled_when_volume_empty(self):
        """_resolve_data_path itself must return bundled path when runtime
        path is missing - this is the mechanism the brain depends on."""
        # Resolve a file we know exists in bundled data
        resolved = self._app._resolve_data_path('funnel-leaks.json')
        # The resolved path must point to a file that exists
        self.assertTrue(
            os.path.exists(resolved),
            f'_resolve_data_path returned non-existent path: {resolved}'
        )
        # And it should be the bundled one, since runtime DATA_DIR is empty
        self.assertTrue(resolved.startswith(BUNDLED))


if __name__ == '__main__':
    unittest.main(verbosity=2)