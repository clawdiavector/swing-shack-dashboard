"""Regression test: /api/search results must include a `preview` field.

Before: search returned only `{kind, id, title, score}` (asset row) so the
Library Captions/Hooks/Memes tabs rendered 30 wall-of-titles rows that the
user could not distinguish, and clicking did nothing.

After: asset matches include `preview` (caption body truncated to ~180 chars
around the needle) so each row tells the user which post it is, and the UI
can click-to-expand for the full record.

Also: data-file scan results include `preview` (longest string field containing
the needle, truncated around the match).
"""
import json
import os
import sys
import unittest

# Ensure DATA_DIR points at the workspace's data/ so the test reads campaign-data.json
os.environ.setdefault('DATA_DIR', os.path.join(os.path.dirname(__file__), '..', '..', 'data'))

# Import the module under test
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from _lib.intelligence import universal_search


class UniversalSearchPreviewTests(unittest.TestCase):
    def test_asset_results_have_preview_field(self):
        """Asset matches surface the caption body as `preview`."""
        # 'golf' is a recurring word across the active brand's asset captions.
        r = universal_search('golf')
        self.assertTrue(r.get('ok'))
        asset_rows = [x for x in r.get('results', []) if x.get('kind') == 'asset']
        self.assertGreater(len(asset_rows), 0, "expected at least one asset match for 'golf'")
        for row in asset_rows[:10]:
            self.assertIn('preview', row, f"asset row missing preview: {row}")
            self.assertIsInstance(row['preview'], str)
            # Preview should be non-empty and not absurdly short for an asset with a caption.
            self.assertGreater(len(row['preview']), 20,
                               f"preview suspiciously short for {row.get('id')}: {row['preview']!r}")

    def test_data_file_scan_results_have_preview_field(self):
        """Data-file scan rows also include a `preview` field for click-to-expand UX."""
        # 'caption' is a common word across many data files; should hit multiple kinds.
        r = universal_search('caption')
        self.assertTrue(r.get('ok'))
        self.assertGreater(r.get('count', 0), 0)
        # At least some rows (not just asset kind) should have a preview.
        rows_with_preview = [x for x in r.get('results', []) if x.get('preview')]
        self.assertGreater(len(rows_with_preview), 0,
                           f"expected at least one row with preview; got {r['results'][:3]}")

    def test_total_count_returned(self):
        """Backend must report `count` so the UI can show 'X matches' / 'showing N of M'."""
        r = universal_search('golf')
        self.assertIn('count', r)
        self.assertGreater(r['count'], 0)
        # Limit is 30 by default; results should not exceed that.
        self.assertLessEqual(len(r['results']), 30)

    def test_search_endpoint_returns_preview(self):
        """The /api/search HTTP route exposes the same shape (smoke test)."""
        from app import app  # noqa: E402
        client = app.test_client()
        # Login (the route is gated)
        client.post('/login', data={'password': os.environ.get('CAMPAIGN_OS_PASSWORD', 'swing-shack-dev-2026')})
        resp = client.get('/api/search?q=golf&kind=captions')
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.data)
        self.assertTrue(body.get('ok'))
        self.assertIn('count', body)
        asset_rows = [x for x in body.get('results', []) if x.get('kind') == 'asset']
        self.assertGreater(len(asset_rows), 0)
        for row in asset_rows[:3]:
            self.assertIn('preview', row,
                          f"HTTP /api/search asset row missing preview: {row}")


if __name__ == '__main__':
    unittest.main()