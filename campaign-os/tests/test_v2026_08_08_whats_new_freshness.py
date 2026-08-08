"""Regression: /api/whats-new reflects the most recent nightshift polish.

Bug fixed 2026-08-08: WHATS_NEW was a frozen 8-item list ending at
2026-07-30T01:30 — every nightshift tick since then (12+ commits)
shipped improvements that never made it into the "What's new" card
on the Morning Brief. Card rendered 10-day-old stale entries
("30 sidebar tooltips", "Visual library real-data join", etc.) and
the most recent fixes (brief counts, orphan-DNA tiles, meme
thumbs, etc.) were invisible.

This test pins three guarantees:
1. Endpoint returns at least 8 items.
2. Top item is from 2026-08-07 or later (was stuck at 2026-07-30).
3. Each item has the 4 required fields (ts, tag, title, body).
4. The list is sorted newest-first by timestamp.
"""
import os, sys, tempfile, unittest

# Set DATA_DIR BEFORE importing the app — the app module-level
# os.makedirs(WEEKLY_REPORT_DATA_DIR) at import time touches the
# filesystem, and on a read-only sandbox the default '/data' raises
# OSError. We point DATA_DIR at a tmpdir we own.
_TEST_TMP = tempfile.mkdtemp(prefix='whats_new_test_')
os.environ['DATA_DIR'] = _TEST_TMP

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app, WHATS_NEW, SHARED_PASSWORD  # noqa: E402


class WhatsNewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Log in once — /api/whats-new is gated by the shared-password
        # auth middleware just like every other API route.
        cls.c = app.test_client()
        cls.c.post('/login', data={'password': SHARED_PASSWORD})

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_endpoint_envelope(self):
        r = self.c.get('/api/whats-new')
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertIn('items', b)
        self.assertIsInstance(b['items'], list)
        self.assertGreaterEqual(len(b['items']), 8)

    def test_top_item_is_recent(self):
        """Top entry must be from 2026-08-07 or later — the morning
        Brief surfaces the FIRST row most prominently, so a stale top
        defeats the entire purpose of the card."""
        top_ts = self.c.get('/api/whats-new').get_json()['items'][0]['ts']
        self.assertGreaterEqual(
            top_ts[:10], '2026-08-07',
            f"Top WHATS_NEW entry is {top_ts!r} — morning Brief would "
            f"show stale polish to Christelle. Each nightshift tick "
            f"must prepend its own entry."
        )

    def test_items_have_required_fields(self):
        for i, it in enumerate(self.c.get('/api/whats-new').get_json()['items']):
            for k in ('ts', 'tag', 'title', 'body'):
                self.assertIn(k, it, f"item[{i}] missing {k!r}: {it}")
            self.assertIsInstance(it['title'], str)
            self.assertIsInstance(it['body'], str)
            self.assertGreater(len(it['title']), 0)
            self.assertGreater(len(it['body']), 0)

    def test_list_sorted_newest_first(self):
        items = self.c.get('/api/whats-new').get_json()['items']
        ts_list = [it['ts'] for it in items]
        self.assertEqual(
            ts_list, sorted(ts_list, reverse=True),
            "WHATS_NEW must be sorted newest-first so the Brief's "
            "first row is always the freshest tick."
        )

    def test_constant_keeps_in_sync(self):
        """WHATS_NEW in app.py must match what the endpoint returns."""
        r = self.c.get('/api/whats-new').get_json()
        self.assertEqual(
            [it['ts'] for it in r['items']],
            [it['ts'] for it in WHATS_NEW],
            "WHATS_NEW list and /api/whats-new response diverged — "
            "the endpoint should serve the constant verbatim."
        )


if __name__ == '__main__':
    unittest.main()
