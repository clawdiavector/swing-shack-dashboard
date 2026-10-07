"""Ubersuggest token file must survive a deploy.

Before 2026-10-07 app.py rewrote the token file from the
UBERSUGGEST_ACCESS_TOKEN / UBERSUGGEST_REFRESH_TOKEN env vars on every boot,
so refreshed tokens and /secrets-sync pastes were lost at the next deploy.
ensure_token_file() makes the copy under DATA_DIR/credentials win.

Pure-Python, no network.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

import _lib.ubersuggest_mcp as _us  # noqa: E402

_ENV_KEYS = ("UBERSUGGEST_ACCESS_TOKEN", "UBERSUGGEST_REFRESH_TOKEN",
             "UBERSUGGEST_TOKEN_FILE")


class EnsureTokenFileTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = self._tmp.name
        self.path = _us.persistent_token_path(self.data_dir)
        self._env = patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in _ENV_KEYS:
            os.environ.pop(k, None)

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    def _read(self) -> dict:
        return json.loads(Path(self.path).read_text())

    def _set_env(self, access: str, refresh: str) -> None:
        os.environ["UBERSUGGEST_ACCESS_TOKEN"] = access
        os.environ["UBERSUGGEST_REFRESH_TOKEN"] = refresh

    def test_no_env_and_no_file_does_nothing(self):
        self.assertFalse(_us.ensure_token_file(self.data_dir))
        self.assertFalse(os.path.exists(self.path))
        self.assertNotIn("UBERSUGGEST_TOKEN_FILE", os.environ)

    def test_env_seeds_missing_file(self):
        self._set_env("env-access", "env-refresh")
        self.assertTrue(_us.ensure_token_file(self.data_dir))
        data = self._read()
        self.assertEqual(data["access_token"], "env-access")
        self.assertEqual(data["refresh_token"], "env-refresh")
        self.assertEqual(data["_source"], _us.ENV_SEED_SOURCE)
        self.assertEqual(os.environ["UBERSUGGEST_TOKEN_FILE"], self.path)

    def test_refreshed_tokens_survive_a_reboot(self):
        """The bug: a boot after a refresh put the stale env tokens back."""
        self._set_env("env-access", "env-refresh")
        _us.ensure_token_file(self.data_dir)
        _us.write_token_file(access_token="fresh-access",
                             refresh_token="fresh-refresh", expires_in=172800)
        os.environ.pop("UBERSUGGEST_TOKEN_FILE")  # new process

        self.assertTrue(_us.ensure_token_file(self.data_dir))
        data = self._read()
        self.assertEqual(data["access_token"], "fresh-access")
        self.assertEqual(data["refresh_token"], "fresh-refresh")
        self.assertEqual(os.environ["UBERSUGGEST_TOKEN_FILE"], self.path)

    def test_pasted_file_wins_over_env(self):
        self._set_env("env-access", "env-refresh")
        os.makedirs(os.path.dirname(self.path))
        Path(self.path).write_text(json.dumps(
            {"access_token": "pasted-access", "refresh_token": "pasted-refresh"}))
        self.assertTrue(_us.ensure_token_file(self.data_dir))
        self.assertEqual(self._read()["access_token"], "pasted-access")

    def test_pasted_file_used_without_env(self):
        os.makedirs(os.path.dirname(self.path))
        Path(self.path).write_text(json.dumps({"access_token": "pasted-access"}))
        self.assertTrue(_us.ensure_token_file(self.data_dir))
        self.assertEqual(os.environ["UBERSUGGEST_TOKEN_FILE"], self.path)

    def test_untouched_seed_follows_changed_env(self):
        """Updating the Railway vars still works while nothing has refreshed."""
        self._set_env("env-access", "env-refresh")
        _us.ensure_token_file(self.data_dir)
        self._set_env("env-access-2", "env-refresh-2")
        self.assertTrue(_us.ensure_token_file(self.data_dir))
        data = self._read()
        self.assertEqual(data["access_token"], "env-access-2")
        self.assertEqual(data["refresh_token"], "env-refresh-2")

    def test_untouched_seed_keeps_its_expiry_on_reboot(self):
        """Same env, same seed: do not restamp expires_at on every boot."""
        self._set_env("env-access", "env-refresh")
        _us.ensure_token_file(self.data_dir)
        data = self._read()
        data["expires_at"] = 12345
        Path(self.path).write_text(json.dumps(data))
        self.assertTrue(_us.ensure_token_file(self.data_dir))
        self.assertEqual(self._read()["expires_at"], 12345)

    def test_corrupt_file_is_reseeded_from_env(self):
        self._set_env("env-access", "env-refresh")
        os.makedirs(os.path.dirname(self.path))
        Path(self.path).write_text("{not json")
        self.assertTrue(_us.ensure_token_file(self.data_dir))
        self.assertEqual(self._read()["access_token"], "env-access")


class WriteTokenFileKeepsRefreshTokenTests(unittest.TestCase):

    def test_refresh_response_without_refresh_token_keeps_saved_one(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ubersuggest-api.json")
            with patch.dict(os.environ, {"UBERSUGGEST_TOKEN_FILE": path}):
                _us.write_token_file(access_token="a1", refresh_token="r1")
                _us.write_token_file(access_token="a2")
                data = json.loads(Path(path).read_text())
        self.assertEqual(data["access_token"], "a2")
        self.assertEqual(data["refresh_token"], "r1")


if __name__ == "__main__":
    unittest.main()
