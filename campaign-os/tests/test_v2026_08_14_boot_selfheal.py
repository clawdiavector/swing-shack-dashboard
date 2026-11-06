"""
Boot-time Windsor self-heal is retired (Windsor waived). Calls must no-op.
"""

import importlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
APP_DIR = os.path.join(REPO, 'campaign-os')
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


class BootSelfhealTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.tmp, 'data')
        os.makedirs(self.data_dir, exist_ok=True)
        for mod in list(sys.modules):
            if mod == 'app' or mod.startswith('app.'):
                del sys.modules[mod]
        os.environ['DATA_DIR'] = self.data_dir

    def _import_app(self):
        app_module = importlib.import_module('app')
        app_module.DATA_DIR = self.data_dir
        return app_module

    def test_selfheal_never_fires_even_when_data_is_fresh(self):
        live_payload = {
            "_meta": {"note": "Live Meta Ads data via Windsor.ai connector."},
            "campaigns": [{"spend": 100, "name": "real campaign"}],
        }
        with open(os.path.join(self.data_dir, 'meta-ads.json'), 'w') as f:
            json.dump(live_payload, f)

        app_module = self._import_app()

        with patch('threading.Thread') as mock_thread:
            app_module._boot_selfheal_windsor()
            mock_thread.assert_not_called()

    def test_selfheal_never_fires_when_data_is_synthesised(self):
        synth_payload = {
            "_meta": {"note": "Synthesised from IG post engagement. Replace with live API."},
            "campaigns": [{"spend": 1.5, "name": "fake"}],
        }
        with open(os.path.join(self.data_dir, 'meta-ads.json'), 'w') as f:
            json.dump(synth_payload, f)

        app_module = self._import_app()

        with patch('threading.Thread') as mock_thread:
            app_module._boot_selfheal_windsor()
            mock_thread.assert_not_called()

    def test_selfheal_never_fires_when_data_is_missing(self):
        app_module = self._import_app()

        with patch('threading.Thread') as mock_thread:
            app_module._boot_selfheal_windsor()
            mock_thread.assert_not_called()


if __name__ == '__main__':
    unittest.main()
