"""google_drive must not treat the shared OAuth client secret as a file path.

GOOGLE_OAUTH_CLIENT_SECRET holds the secret string for gbp_oauth / gsc_oauth.
google_drive read the same variable as a path, so /api/google-drive/status
echoed the secret in its client_path field (found on prod 2026-10-07).
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

import _lib.google_drive as _gd  # noqa: E402

_SECRET = "GOCSPX-not-a-real-secret-0123456789"


class DriveClientPathTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._env = patch.dict(os.environ, {
            "OPENCLAW_CREDENTIALS_DIR": self._tmp.name,
        }, clear=False)
        self._env.start()
        os.environ.pop("GOOGLE_OAUTH_CLIENT_SECRET", None)
        os.environ.pop("GOOGLE_OAUTH_CLIENT_SECRET_FILE", None)
        _gd._resolve_credentials_dir.cache_clear()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()
        _gd._resolve_credentials_dir.cache_clear()

    def test_secret_string_is_not_used_as_path(self):
        os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = _SECRET
        path = _gd._oauth_client_path()
        self.assertNotIn(_SECRET, str(path))
        self.assertEqual(path.name, "google-oauth-client.json")

    def test_status_does_not_echo_secret(self):
        os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = _SECRET
        os.environ["GOOGLE_DRIVE_TOKEN"] = os.path.join(self._tmp.name, "absent.json")
        self.assertNotIn(_SECRET, repr(_gd.status()))

    def test_json_path_in_shared_var_still_works(self):
        os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "/creds/client.json"
        self.assertEqual(_gd._oauth_client_path(), Path("/creds/client.json"))

    def test_explicit_file_var_wins(self):
        os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = _SECRET
        os.environ["GOOGLE_OAUTH_CLIENT_SECRET_FILE"] = "/creds/drive-client"
        self.assertEqual(_gd._oauth_client_path(), Path("/creds/drive-client"))


if __name__ == "__main__":
    unittest.main()
