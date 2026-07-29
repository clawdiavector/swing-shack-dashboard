import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app
class TrendV2Tests(unittest.TestCase):
    def setUp(self): self.client = app.test_client()
    def test_envelope_and_lanes(self):
        body = self.client.get('/api/intel/trends_v2').get_json()
        self.assertTrue(body['ok']); self.assertGreaterEqual(body['count'], 6)
        self.assertEqual(set(body['sources']), {'marketing-industry','golf-news','competitor'})
        for signal in body['signals']: self.assertIn('suggested_response', signal)
    def test_filter_and_sort(self):
        body = self.client.get('/api/intel/trends_v2?source=golf-news&min_relevance=90').get_json()
        self.assertTrue(all(s['source'] == 'golf-news' and s['relevance'] >= 90 for s in body['signals']))
        self.assertEqual(body['signals'], sorted(body['signals'], key=lambda s:s['relevance'], reverse=True))
