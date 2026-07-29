import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app

class TodayPanelTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.old = os.environ.get('DATA_DIR')
        os.environ['DATA_DIR'] = self.t.name
        self.c = app.test_client()
    def tearDown(self):
        if self.old is None: os.environ.pop('DATA_DIR', None)
        else: os.environ['DATA_DIR'] = self.old
        self.t.cleanup()
    def test_envelope(self):
        r = self.c.get('/api/today/panel')
        self.assertEqual(r.status_code, 200)
        b = r.get_json()
        self.assertTrue(b['ok'])
        self.assertIn('ts', b); self.assertIn('cards', b); self.assertIn('count', b)
        self.assertIsInstance(b['cards'], list)
        self.assertIsInstance(b['dismissed'], list)
    def test_dismiss_validation(self):
        self.assertEqual(self.c.post('/api/today/panel/dismiss', json={}).status_code, 400)
    def test_dismiss_persists(self):
        panel = self.c.get('/api/today/panel').get_json()
        if panel['cards']:
            ident = panel['cards'][0]['id']
            r = self.c.post('/api/today/panel/dismiss', json={'id': ident})
            self.assertTrue(r.get_json()['ok'])
            ids = [x['id'] for x in self.c.get('/api/today/panel').get_json()['cards']]
            self.assertNotIn(ident, ids)
