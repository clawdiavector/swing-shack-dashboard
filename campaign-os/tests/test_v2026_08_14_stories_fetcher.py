"""
Tests for the IG + FB page stories fetchers + weekly-report wire-up.

Added 2026-08-14 in response to Christelle's call-out:
"Report says swing shack stories 0 is a lie there are currently 2 stories.
Stories go up every day. You can use more than one data stream and reference
from each, compare dates times and stats use math to find the truth!"

Tests:
  - get_ig_stories() returns a structured payload with flattened insights
  - get_page_stories() normalises post_id -> id and creation_time -> ISO
  - summarize_stories() cross-references both, de-dups by id, computes combined count
  - _weekly_collect_current() populates ig_stories / fb_stories / stories_combined_count
"""

import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

REPO = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard'
sys.path.insert(0, os.path.join(REPO, 'campaign-os'))

from _lib import meta_api as _meta  # noqa: E402


# ── app.py pre-import patch (avoids Read-only /data crash) ─────────────────
# app.py does os.makedirs('/data/...') at module load. To run its tests locally
# without write access to /data, set os.environ['DATA_DIR'] to a writable path
# BEFORE importing app. The constants at module top use DATA_DIR.
_TEST_TMPDIR = tempfile.mkdtemp(prefix='stories_fetcher_test_')
_TEST_DATA_DIR = os.path.join(_TEST_TMPDIR, 'data')
os.makedirs(_TEST_DATA_DIR, exist_ok=True)
os.environ['DATA_DIR'] = _TEST_DATA_DIR
# app.py reads DATA_DIR at module top to set WEEKLY_REPORT_DATA_DIR, so this
# environment variable has to be set before the import below.


# ── Real Graph API fixtures (captured 2026-08-14) ──────────────────────────
REAL_IG_STORIES_PAYLOAD = {
    "data": [
        {
            "id": "18124822414756519",
            "media_type": "VIDEO",
            "timestamp": "2026-08-14T10:21:16+0000",
            "permalink": "https://www.instagram.com/stories/swingshack/3963473413997893231",
            "insights": {"data": [
                {"name": "reach", "values": [{"value": 0}]},
                {"name": "follows", "values": [{"value": 0}]},
                {"name": "total_interactions", "values": [{"value": 0}]},
            ]},
        },
        {
            "id": "18368043292237970",
            "media_type": "VIDEO",
            "timestamp": "2026-08-13T17:37:36+0000",
            "permalink": "https://www.instagram.com/stories/swingshack/3962968279219966772",
            "insights": {"data": [
                {"name": "reach", "values": [{"value": 39}]},
                {"name": "follows", "values": [{"value": 0}]},
                {"name": "total_interactions", "values": [{"value": 0}]},
            ]},
        },
    ],
    "paging": {"cursors": {"before": "x", "after": "y"}},
}

REAL_FB_PAGE_STORIES_PAYLOAD = {
    "data": [
        {
            "post_id": "1947172192626492",
            "status": "published",
            "creation_time": "1786702894",  # Unix epoch
            "media_type": "video",
            "url": "https://facebook.com/stories/...",
            "media_id": "1777033239988187",
        }
    ],
    "paging": {"cursors": {"before": "x", "after": "y"}},
}


class TestGetIGStories(unittest.TestCase):
    """Test get_ig_stories() flattens insights into per-story dict."""

    def test_flattens_insights_into_story_dict(self):
        with patch.object(_meta, '_graph_get', return_value=REAL_IG_STORIES_PAYLOAD):
            out = _meta.get_ig_stories(limit=10)
        self.assertEqual(out['_meta']['fetched'], 2)
        stories = out['data']
        self.assertEqual(len(stories), 2)
        # First story: 0 reach
        s0 = stories[0]
        self.assertEqual(s0['id'], '18124822414756519')
        self.assertEqual(s0['media_type'], 'VIDEO')
        self.assertEqual(s0['reach'], 0)
        self.assertEqual(s0['follows'], 0)
        self.assertEqual(s0['total_interactions'], 0)
        # Second story: 39 reach
        s1 = stories[1]
        self.assertEqual(s1['reach'], 39)

    def test_no_insights_mode(self):
        # When with_insights=False, the fetcher doesn't ask for insights.
        # Simulate the Graph API response shape: just id, media_type,
        # timestamp, permalink. No `insights` field.
        payload_no_insights = {
            "data": [
                {"id": "18124822414756519", "media_type": "VIDEO",
                 "timestamp": "2026-08-14T10:21:16+0000",
                 "permalink": "https://www.instagram.com/stories/..."},
            ],
            "paging": {},
        }
        with patch.object(_meta, '_graph_get', return_value=payload_no_insights):
            out = _meta.get_ig_stories(limit=10, with_insights=False)
        self.assertEqual(len(out['data']), 1)
        # No reach/follows keys should appear when no insights requested
        self.assertNotIn('reach', out['data'][0])
        self.assertNotIn('follows', out['data'][0])


class TestGetPageStories(unittest.TestCase):
    """Test get_page_stories() normalises FB page story field names."""

    def test_normalises_post_id_to_id_and_unix_to_iso(self):
        with patch.object(_meta, '_graph_get', return_value=REAL_FB_PAGE_STORIES_PAYLOAD):
            out = _meta.get_page_stories(limit=10)
        self.assertEqual(out['_meta']['fetched'], 1)
        s = out['data'][0]
        self.assertEqual(s['id'], '1947172192626492')  # was post_id
        # creation_time was 1786702894 = 2026-08-14T10:21:34+00:00
        self.assertEqual(s['created_time'], '2026-08-14T10:21:34+00:00')
        self.assertEqual(s['media_type'], 'video')

    def test_returns_empty_on_upstream_error(self):
        with patch.object(_meta, '_graph_get', side_effect=_meta.MetaUpstreamError('not available')):
            out = _meta.get_page_stories(limit=10)
        self.assertEqual(out['data'], [])
        self.assertIn('error', out['_meta'])


class TestSummarizeStories(unittest.TestCase):
    """Test cross-referencing + de-dup + combined counts."""

    def test_combines_ig_and_fb_page_stories(self):
        with patch.object(_meta, 'get_ig_stories', return_value=REAL_IG_STORIES_PAYLOAD), \
             patch.object(_meta, 'get_page_stories', return_value=REAL_FB_PAGE_STORIES_PAYLOAD):
            summary = _meta.summarize_stories()

        # IG: 2 stories, reach 39 total
        self.assertEqual(summary['ig_stories']['count'], 2)
        self.assertEqual(summary['ig_stories']['reach_total'], 39)
        self.assertEqual(summary['ig_stories']['follows_total'], 0)
        self.assertEqual(summary['ig_stories']['total_interactions_total'], 0)

        # FB page: 1 story (different id from IG stories, no overlap)
        self.assertEqual(summary['fb_page_stories']['count'], 1)

        # Combined: 2 IG + 1 FB = 3 (no id overlap)
        self.assertEqual(summary['combined_count'], 3)
        self.assertEqual(summary['combined_reach'], 39)
        self.assertEqual(summary['overlap_ids'], [])

    def test_dedupes_when_same_id_in_both(self):
        """If the same story appears in both IG and FB page feeds (cross-post
        with shared ID), combined count should not double it."""
        ig_payload = {
            "data": [
                {"id": "shared_story_123", "media_type": "VIDEO",
                 "timestamp": "2026-08-14T10:21:00+0000",
                 "permalink": "https://instagram.com/...",
                 "insights": {"data": [
                     {"name": "reach", "values": [{"value": 50}]},
                 ]}}
            ],
            "paging": {},
        }
        fb_payload = {
            "data": [
                {"post_id": "shared_story_123", "creation_time": "1786702860",
                 "media_type": "video"}
            ],
            "paging": {},
        }
        with patch.object(_meta, 'get_ig_stories', return_value=ig_payload), \
             patch.object(_meta, 'get_page_stories', return_value=fb_payload):
            summary = _meta.summarize_stories()
        self.assertEqual(summary['combined_count'], 1)
        self.assertEqual(summary['overlap_ids'], ['shared_story_123'])

    def test_handles_no_stories_at_all(self):
        empty = {"data": [], "paging": {}}
        with patch.object(_meta, 'get_ig_stories', return_value=empty), \
             patch.object(_meta, 'get_page_stories', return_value=empty):
            summary = _meta.summarize_stories()
        self.assertEqual(summary['ig_stories']['count'], 0)
        self.assertEqual(summary['fb_page_stories']['count'], 0)
        self.assertEqual(summary['combined_count'], 0)
        self.assertIn('truth_note', summary)
        # truth note should explain 24h expiry
        self.assertIn('24h', summary['truth_note'])


class TestWeeklyCollectCurrentPopulatesStories(unittest.TestCase):
    """Verify _weekly_collect_current() wires the fetcher output into the
    `28d` block so the renderer can read ig_stories / fb_stories /
    stories_combined_count / stories_combined_reach."""

    def setUp(self):
        # The app module hardcodes DATA_DIR=/data for Railway production. For
        # local tests, monkey-patch the relevant constants so app.py doesn't
        # try to mkdir /data on a read-only filesystem.
        import app as _app
        self._tmpdir = tempfile.mkdtemp(prefix='weekly_test_')
        self._data_dir = os.path.join(self._tmpdir, 'data')
        os.makedirs(self._data_dir, exist_ok=True)
        self._patchers = [
            patch.object(_app, 'DATA_DIR', self._data_dir),
            patch.object(_app, 'WEEKLY_REPORT_DATA_DIR', self._data_dir),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_populates_stories_fields(self):
        from app import _weekly_collect_current
        # Stub the fetcher so the test doesn't hit Graph API
        fake_summary = {
            'ig_stories': {
                'count': 2, 'reach_total': 39, 'follows_total': 0,
                'total_interactions_total': 0,
                'oldest': '2026-08-13T17:37:36+0000',
                'newest': '2026-08-14T10:21:16+0000',
                'items': [],
            },
            'fb_page_stories': {
                'count': 1, 'oldest': '2026-08-14T10:21:34+00:00',
                'newest': '2026-08-14T10:21:34+00:00', 'items': [],
            },
            'combined_count': 3,
            'combined_reach': 39,
            'overlap_ids': [],
            'data_sources': ['instagram_stories', 'facebook_page_stories'],
            'window_label': 'active (last 24h - Meta expires stories automatically)',
            'truth_note': 'stories expire',
        }
        with patch.object(_meta, 'summarize_stories', return_value=fake_summary), \
             patch.object(_meta, '_page_credentials_present', return_value=True), \
             patch.object(_meta, 'meta_credentials_present', return_value=True), \
             patch.object(_meta, 'get_page_info', return_value={
                 'fan_count': 445, 'followers_count': 445, 'name': 'Swing Shack', 'id': '198859063301219'
             }), \
             patch.object(_meta, 'get_page_insights', return_value={'_flat': {}, '_meta': {'metrics_returned': []}}), \
             patch.object(_meta, 'list_recent_posts', return_value={'data': [], 'paging': {}}), \
             patch.object(_meta, 'list_page_posts', return_value={'data': [], 'paging': {}}), \
             patch('app.load_data', return_value={'campaigns': {}}):
            out = _weekly_collect_current('swing-shack')

        # 28d block now has stories fields populated
        self.assertEqual(out['28d']['ig_stories'], 2)
        self.assertEqual(out['28d']['ig_stories_reach'], 39)
        self.assertEqual(out['28d']['fb_stories'], 1)
        self.assertEqual(out['28d']['stories_combined_count'], 3)
        self.assertEqual(out['28d']['stories_combined_reach'], 39)
        # meta_stories is recorded in sources
        sources = [s.get('name') for s in out.get('sources', [])]
        self.assertIn('meta_stories', sources)
        meta_stories_src = next(s for s in out['sources'] if s['name'] == 'meta_stories')
        self.assertEqual(meta_stories_src['ig_count'], 2)
        self.assertEqual(meta_stories_src['fb_page_count'], 1)
        self.assertEqual(meta_stories_src['combined'], 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)