"""
Test the boot-time Windsor self-heal.

When the app boots on Railway and meta-ads.json is still the bundled
synthesised file (or missing), the system should automatically re-pull from
Windsor so the next render shows live data. This is the fix for the
"report says Paid reach is synthesised" failure mode Christelle kept hitting
after every deploy wiped the volume.
"""

import importlib
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch


REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
APP_DIR = os.path.join(REPO, 'campaign-os')
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


class BootSelfhealTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.tmp, 'data')
        os.makedirs(self.data_dir, exist_ok=True)
        # Reset module so each test sees fresh DATA_DIR env.
        if 'app' in sys.modules:
            del sys.modules['app']
        os.environ['DATA_DIR'] = self.data_dir

    def test_skips_when_data_is_fresh(self):
        """Live meta-ads.json with no synthesised note -> no refresh fired."""
        live_payload = {
            "_meta": {"note": "Live Meta Ads data via Windsor.ai connector."},
            "campaigns": [{"spend": 100, "name": "real campaign"}],
        }
        with open(os.path.join(self.data_dir, 'meta-ads.json'), 'w') as f:
            json.dump(live_payload, f)

        # Reload app so it picks up our DATA_DIR + file.
        app_module = importlib.import_module('app')

        with patch('app._app_log') as mock_log, \
             patch('threading.Thread') as mock_thread:
            app_module._boot_selfheal_windsor()
            mock_thread.assert_not_called()
            self.assertFalse(any(
                'Boot self-heal' in str(call)
                for call in mock_log.info.call_args_list
            ))

    def test_fires_when_data_is_synthesised(self):
        """Synthesised note in meta-ads.json + Windsor key present -> fires thread."""
        synth_payload = {
            "_meta": {"note": "Synthesised from IG post engagement. Replace with live API."},
            "campaigns": [{"spend": 1.5, "name": "fake"}],
        }
        with open(os.path.join(self.data_dir, 'meta-ads.json'), 'w') as f:
            json.dump(synth_payload, f)

        app_module = importlib.import_module('app')

        fake_key = 'd09f901081a7f2422abff2286b151a346062a3b56df162d0a30bbde248d3925f'
        with patch('threading.Thread') as mock_thread, \
             patch.dict(sys.modules, {
                 '_lib.windsor_client': MagicMock(read_api_key=MagicMock(return_value=fake_key)),
                 '_lib.windsor_fetcher': MagicMock(
                     build_meta_ads=MagicMock(return_value={"_meta": {"note": "Live"}}),
                     build_google_ads=MagicMock(return_value={"_meta": {"note": "Live"}}),
                     _atomic_write=MagicMock(),
                 ),
             }), \
             patch('app._app_log'):
            app_module._boot_selfheal_windsor()
            mock_thread.assert_called_once()

    def test_fires_when_data_is_missing(self):
        """meta-ads.json absent + Windsor key present -> fires thread."""
        # Don't create meta-ads.json at all.
        app_module = importlib.import_module('app')

        fake_key = 'd09f901081a7f2422abff2286b151a346062a3b56df162d0a30bbde248d3925f'
        with patch('threading.Thread') as mock_thread, \
             patch.dict(sys.modules, {
                 '_lib.windsor_client': MagicMock(read_api_key=MagicMock(return_value=fake_key)),
                 '_lib.windsor_fetcher': MagicMock(
                     build_meta_ads=MagicMock(return_value={"_meta": {"note": "Live"}}),
                     build_google_ads=MagicMock(return_value={"_meta": {"note": "Live"}}),
                     _atomic_write=MagicMock(),
                 ),
             }), \
             patch('app._app_log'):
            app_module._boot_selfheal_windsor()
            mock_thread.assert_called_once()

    def test_skips_when_no_windsor_key(self):
        """Synthesised data + no Windsor key -> skip silently (no crash)."""
        synth_payload = {
            "_meta": {"note": "Synthesised from IG post engagement. Replace with live API."},
            "campaigns": [{"spend": 1.5, "name": "fake"}],
        }
        with open(os.path.join(self.data_dir, 'meta-ads.json'), 'w') as f:
            json.dump(synth_payload, f)

        app_module = importlib.import_module('app')

        with patch('threading.Thread') as mock_thread, \
             patch.dict(sys.modules, {
                 '_lib.windsor_client': MagicMock(read_api_key=MagicMock(return_value="")),
             }), \
             patch('app._app_log'):
            app_module._boot_selfheal_windsor()
            mock_thread.assert_not_called()


if __name__ == '__main__':
    unittest.main()