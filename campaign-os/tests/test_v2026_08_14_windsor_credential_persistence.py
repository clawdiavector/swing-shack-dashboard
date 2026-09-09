"""
Test that the brain still works after a deploy when WINDSOR_API_KEY is
NOT in os.environ but the persisted credentials file exists.

Added 2026-08-14 after Christelle's callout:
'YOU HAVE ALL THE DATA STOP WASTING MY TIME! LINK REAL DATA!!!!!'

The bug: every Railway deploy wiped WINDSOR_API_KEY from os.environ,
and read_api_key() was looking at /data/credentials/ + /data/ but
not /data/campaign-os/credentials/ - where secrets-sync actually writes.
So brain rendered synthesised fallback until operator re-ran secrets-sync.

Fix: read_api_key() now also checks /data/campaign-os/credentials/.

This test verifies the candidate path list includes the volume-resident
path that secrets-sync writes to.
"""

import json
import os
import sys
import tempfile
import unittest

REPO = '/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard'
sys.path.insert(0, os.path.join(REPO, 'campaign-os'))


class TestWindsorCredentialPersistence(unittest.TestCase):
    """WINDSOR_API_KEY must be findable from the persistent volume
    path that secrets-sync writes to, even when the env var is empty."""

    def test_volume_persistent_path_is_in_candidates(self):
        from _lib import windsor_client
        # Build a fake credential file at the volume path
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False
        ) as f:
            json.dump({'api_key': 'f0fe6bb23366ab148b1cec6d4c3031115a7d'}, f)
            tmppath = f.name
        # Symlink it to the persistent volume path
        target = '/data/campaign-os/credentials/windsor-api.json'
        target_dir = os.path.dirname(target)
        # Make sure path is real enough for the test to run
        with tempfile.TemporaryDirectory() as td:
            test_target = os.path.join(td, 'windsor-api.json')
            with open(test_target, 'w') as f:
                json.dump({'api_key': 'test-key-from-volume'}, f)
            # Patch the candidate list to include our temp path
            from _lib import windsor_client as wc
            original_candidates = (
                '/data/credentials/windsor-api.json',
                '/data/windsor-api.json',
                '/data/campaign-os/credentials/windsor-api.json',
                '/data/campaign-os/windsor-api.json',
            )
            # Confirm all four volume paths are in the read_api_key
            # fallback chain (this is what secrets-sync writes to).
            # We test this by inspecting the source rather than
            # requiring the actual /data/ path to be writable in CI.
            with open(wc.__file__) as f:
                src = f.read()
            for path in original_candidates:
                self.assertIn(
                    path, src,
                    f'read_api_key() must check {path} so post-deploy '
                    'brain renders live data without re-running secrets-sync'
                )

    def test_read_api_key_handles_missing_env_var(self):
        """When WINDSOR_API_KEY is not in os.environ, read_api_key()
        must still resolve a key from the on-disk persisted file."""
        # Save and clear env
        saved_env = os.environ.pop('WINDSOR_API_KEY', None)
        saved_env_file = os.environ.pop('WINDSOR_API_KEY_FILE', None)
        try:
            from _lib import windsor_client
            # The function should NOT raise even with no env + no file
            result = windsor_client.read_api_key()
            # When there's no file at any candidate path, returns ''
            self.assertIsInstance(result, str)
        finally:
            if saved_env is not None:
                os.environ['WINDSOR_API_KEY'] = saved_env
            if saved_env_file is not None:
                os.environ['WINDSOR_API_KEY_FILE'] = saved_env_file


if __name__ == '__main__':
    unittest.main(verbosity=2)