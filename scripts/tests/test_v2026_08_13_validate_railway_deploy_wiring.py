"""Tests for validate_railway_deploy_wiring.py.

v2026-08-13: validates the five-check structure of the deploy-wiring
validator. We can't test against the real Railway (no token in the
test env), so we mock the HTTP layer and exercise each check.

Run: cd scripts && python3 -m pytest tests/test_v2026_08_13_validate_railway_deploy_wiring.py -v
"""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Make scripts/ importable
HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

# Force "not on Railway" context for these tests
os.environ.pop("CAMPAIGN_OS_RUNNING_ON_RAILWAY", None)

import validate_railway_deploy_wiring as v  # noqa: E402


class TestCheckStructure(unittest.TestCase):
    """The five checks are present and have the right shape."""

    def test_five_checks_registered(self):
        labels = [lbl for lbl, _ in v.CHECKS]
        self.assertEqual(labels, ["A", "B", "C", "D", "E"])

    def test_each_check_returns_required_fields(self):
        results = v.run_checks()
        self.assertEqual(len(results), 5)
        for r in results:
            self.assertIn("check", r)
            self.assertIn("status", r)
            self.assertIn("evidence", r)
            self.assertIn("fix", r)
            self.assertIn(r["status"], v.STATUS_BADGE.keys(),
                          f"Invalid status: {r['status']}")


class TestCheckA(unittest.TestCase):
    """Check A: GITHUB_TOKEN env var present."""

    def test_pass_when_token_in_local_env(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "github_pat_AAA111"}):
            r = v.check_a_github_token_env()
        self.assertEqual(r["status"], v.STATUS_OK)
        self.assertIn("length=17", r["evidence"])
        # Never expose the value
        self.assertNotIn("github_pat_AAA111", r["evidence"])

    def test_warn_when_local_and_remote_both_missing(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GITHUB_TOKEN", None)
            os.environ.pop("GH_TOKEN", None)
            with patch.object(v, "_http_get", return_value=(200, {}, json.dumps({"env": {}}))):
                r = v.check_a_github_token_env()
        self.assertEqual(r["status"], v.STATUS_WARN)
        self.assertIn("Railway env vars", r["evidence"])

    def test_fail_when_on_railway_and_missing(self):
        with patch.dict(os.environ, {"CAMPAIGN_OS_RUNNING_ON_RAILWAY": "1"}, clear=False):
            os.environ.pop("GITHUB_TOKEN", None)
            os.environ.pop("GH_TOKEN", None)
            with patch.object(v, "_http_get", return_value=(200, {}, json.dumps({"env": {}}))):
                r = v.check_a_github_token_env()
        self.assertEqual(r["status"], v.STATUS_FAIL)

    def test_pass_when_remote_env_debug_shows_token(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GITHUB_TOKEN", None)
            os.environ.pop("GH_TOKEN", None)
            mock_debug = json.dumps({"env": {"GITHUB_TOKEN": {"set": True, "length": 91, "prefix": "github_pat_..."}}})
            with patch.object(v, "_http_get", return_value=(200, {}, mock_debug)):
                r = v.check_a_github_token_env()
        self.assertEqual(r["status"], v.STATUS_OK)
        self.assertIn("Railway service", r["evidence"])
        self.assertIn("github_pat_...", r["evidence"])


class TestCheckC(unittest.TestCase):
    """Check C: live endpoint returns 200 with expected marker."""

    def _mock_login_ok(self):
        return "session_cookie_value"

    def test_pass_on_200_with_marker(self):
        # Marker is 'post-conversion-score' — the response includes it in
        # the schema URL like "schema": "https://clawdia.io/agents/post-conversion-score/v1".
        body = json.dumps({
            "ok": True,
            "schema": "https://clawdia.io/agents/post-conversion-score/v1",
            "summary": {"posts_scored": 16, "winning_format": "image"},
        })
        with patch.object(v, "_login", return_value="cookie"), \
             patch.object(v, "_http_get", return_value=(200, {}, body)):
            r = v.check_c_latest_endpoint_responds()
        self.assertEqual(r["status"], v.STATUS_OK)
        self.assertIn("Posts scored", r["evidence"])

    def test_fail_on_404(self):
        with patch.object(v, "_login", return_value="cookie"), \
             patch.object(v, "_http_get", return_value=(404, {}, "")):
            r = v.check_c_latest_endpoint_responds()
        self.assertEqual(r["status"], v.STATUS_FAIL)
        self.assertIn("returns 404", r["evidence"])

    def test_fail_on_401_after_login(self):
        with patch.object(v, "_login", return_value="cookie"), \
             patch.object(v, "_http_get", return_value=(401, {}, "")):
            r = v.check_c_latest_endpoint_responds()
        self.assertEqual(r["status"], v.STATUS_FAIL)
        self.assertIn("401", r["evidence"])

    def test_fail_on_200_without_marker(self):
        body = json.dumps({"ok": True, "summary": {}})  # no marker
        with patch.object(v, "_login", return_value="cookie"), \
             patch.object(v, "_http_get", return_value=(200, {}, body)):
            r = v.check_c_latest_endpoint_responds()
        self.assertEqual(r["status"], v.STATUS_FAIL)
        self.assertIn("does not contain expected marker", r["evidence"])

    def test_fail_when_login_fails(self):
        with patch.object(v, "_login", return_value=None):
            r = v.check_c_latest_endpoint_responds()
        self.assertEqual(r["status"], v.STATUS_FAIL)
        self.assertIn("Could not log in", r["evidence"])

    def test_fail_when_service_unreachable(self):
        with patch.object(v, "_login", return_value="cookie"), \
             patch.object(v, "_http_get", return_value=(0, {}, "")):
            r = v.check_c_latest_endpoint_responds()
        self.assertEqual(r["status"], v.STATUS_FAIL)
        self.assertIn("Could not reach", r["evidence"])


class TestCheckD(unittest.TestCase):
    """Check D: data file freshness."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp()) if False else None
        # Use a temp file
        import tempfile
        self.tmpfile = Path(tempfile.mkdtemp()) / "pcs.json"
        self._orig_data_file = v.DATA_FILE
        v.DATA_FILE = str(self.tmpfile)

    def tearDown(self):
        v.DATA_FILE = self._orig_data_file

    def test_fail_when_file_missing(self):
        self.tmpfile.unlink(missing_ok=True)
        r = v.check_d_data_file_freshness()
        self.assertEqual(r["status"], v.STATUS_FAIL)
        self.assertIn("does not exist", r["evidence"])

    def test_pass_when_fresh(self):
        import datetime as dt
        recent = dt.datetime.now(dt.timezone.utc).isoformat()
        self.tmpfile.write_text(json.dumps({"generated": recent}))
        r = v.check_d_data_file_freshness()
        self.assertEqual(r["status"], v.STATUS_OK)
        self.assertIn("Fresh", r["evidence"])

    def test_warn_when_stale(self):
        import datetime as dt
        old = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)).isoformat()
        self.tmpfile.write_text(json.dumps({"generated": old}))
        r = v.check_d_data_file_freshness()
        self.assertEqual(r["status"], v.STATUS_WARN)
        self.assertIn("30 days", r["evidence"])


class TestExitCodes(unittest.TestCase):
    """Exit code decision logic."""

    def test_exit_0_on_all_ok(self):
        results = [
            {"check": "A", "status": v.STATUS_OK, "evidence": "x", "fix": None},
            {"check": "C", "status": v.STATUS_OK, "evidence": "x", "fix": None},
            {"check": "E", "status": v.STATUS_MANUAL, "evidence": "x", "fix": "y"},
        ]
        # No FAIL, no WARN, only OK + MANUAL → exit 0 (manual is informational)
        has_fail = any(r["status"] == v.STATUS_FAIL for r in results)
        has_warn = any(r["status"] == v.STATUS_WARN for r in results)
        has_manual = any(r["status"] == v.STATUS_MANUAL for r in results)
        self.assertFalse(has_fail)
        self.assertFalse(has_warn)
        self.assertTrue(has_manual)

    def test_exit_1_on_fail(self):
        results = [{"check": "C", "status": v.STATUS_FAIL, "evidence": "x", "fix": "y"}]
        self.assertTrue(any(r["status"] == v.STATUS_FAIL for r in results))


class TestNoSecretsInOutput(unittest.TestCase):
    """The validator must NEVER leak token values in its output."""

    def test_token_value_not_in_check_a_output(self):
        fake_token = "github_pat_AAA_super_secret_111"
        with patch.dict(os.environ, {"GITHUB_TOKEN": fake_token}):
            r = v.check_a_github_token_env()
        # Full value should NEVER appear in the output
        self.assertNotIn(fake_token, r["evidence"])
        self.assertNotIn(fake_token, r["fix"] or "")

    def test_token_value_not_in_check_b_output(self):
        fake_token = "github_pat_BBB_super_secret_222"
        with patch.dict(os.environ, {"GITHUB_TOKEN": fake_token}):
            with patch.object(v, "_http_get") as mock_http:
                mock_http.return_value = (200, {}, json.dumps({"login": "x", "permissions": {"push": True}}))
                r = v.check_b_token_authenticates()
        self.assertNotIn(fake_token, r["evidence"])


if __name__ == "__main__":
    unittest.main()
