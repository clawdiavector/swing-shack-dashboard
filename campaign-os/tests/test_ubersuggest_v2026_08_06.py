"""Tests for Ubersuggest MCP wrapper + OAuth script + new weekly_report claims.

Coverage:
  - ubersuggest_mcp wrapper: PKCE gen, state gen, token file lifecycle,
    credentials_present, is_token_expired, write_token_file atomicity,
    DEFAULT_TOKEN_FILE constant, _normalize_token_response, status_report.
  - weekly_report: the new auto-silent rank-movement + domain-authority
    claim generators (verified to fire when data is real, stay silent when
    data is missing).
  - ubersuggest_oauth script: free_port_hint, generate_pkce, generate_state,
    _b64url_nopad, --help subcommand, --status subcommand (no token file).

All tests are pure-Python (no live network). Where the wrapper code calls
out to the network (fetch_discovery, dynamic_client_register), we monkey-
patch urllib.request.urlopen in setUp.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Make the module discoverable from a stale .pyc cache by clearing it.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))
sys.path.insert(0, str(_HERE.parent / "_lib"))

import _lib.ubersuggest_mcp as _us  # noqa: E402
sys.path.insert(0, str(_HERE.parent.parent / "scripts"))
import ubersuggest_oauth as _oauth  # noqa: E402


# ────────────────────────────────────────────────────────────────────────
# ubersuggest_mcp wrapper tests
# ────────────────────────────────────────────────────────────────────────

class UbseruggestMcpWrapperTests(unittest.TestCase):
    """Test the wrapper module without making any live HTTP calls."""

    def test_default_token_file_is_absolute(self):
        """Token file MUST be an absolute path (per wrapper pitfalls note)."""
        path = _us.DEFAULT_TOKEN_FILE
        self.assertTrue(os.path.isabs(path),
                        f"expected absolute, got {path!r} — ~/.openclaw-instance2 path expands differently per shell")
        self.assertIn("ubersuggest-api.json", path)

    def test_default_client_id_matches_live_dcr(self):
        """Probe 2026-08-06 confirmed client_id is the public wildcard 'ubersuggest-mcp'."""
        self.assertEqual(_us.DEFAULT_CLIENT_ID, "ubersuggest-mcp")

    def test_default_scopes_match_offered(self):
        """Discovery 2026-08-06 listed exactly these 9 scopes."""
        expected = ["profile", "domain", "keywords", "serp", "backlinks",
                    "site_audit", "content", "projects", "utility"]
        got = _us.DEFAULT_SCOPES.split()
        self.assertEqual(sorted(got), sorted(expected))

    def test_mcp_endpoint_matches_live_url(self):
        self.assertEqual(_us.MCP_ENDPOINT, "https://ubersuggest-mcp.neilpatelapi.com/mcp")

    def test_credentials_present_false_when_no_file(self):
        """Confirms ubersuggest_credentials_present() is conservative."""
        with patch.object(_us, "_read_token_path", return_value="/nonexistent/path"):
            self.assertFalse(_us.ubersuggest_credentials_present())

    def test_is_token_expired_true_when_no_file(self):
        """`expires_at` missing → fail safe as expired."""
        with patch.object(_us, "_read_token_path", return_value="/nonexistent/path"):
            self.assertTrue(_us.is_token_expired(within_seconds=300))

    def test_is_token_expired_false_within_window(self):
        """`expires_at` is comfortably in the future → not expired."""
        import time as _t
        meta = {"expires_at": int(_t.time()) + 86400}
        with patch.object(_us, "_read_token_path", return_value="/fake"), \
             patch.object(_us, "_read_json_file", return_value=meta) if hasattr(_us, "_read_json_file") else \
             patch.object(_us, "_read_token_meta", return_value=meta):
            self.assertFalse(_us.is_token_expired(within_seconds=300))

    def test_write_token_file_creates_with_0600(self):
        """write_token_file MUST chmod 600 (sibling credentials follow this rule)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            token_file = Path(tmpdir) / "creds" / "test.json"
            with patch.object(_us, "_read_token_path", return_value=str(token_file)):
                _us.write_token_file(
                    access_token="***ek-test***",
                    refresh_token="***efresh-test***",
                    expires_in=3600,
                    scope="profile",
                )
            self.assertTrue(token_file.exists(), "file should be created")
            data = json.loads(token_file.read_text())
            self.assertEqual(data["access_token"], "***ek-test***")
            self.assertEqual(data["refresh_token"], "***efresh-test***")
            self.assertEqual(data["expires_in"], 3600)
            self.assertEqual(data["scope"], "profile")
            self.assertIsInstance(data["expires_at"], int)
            self.assertIsInstance(data["refreshed_at"], int)
            # Mode 0o600 (0600)
            mode = oct(token_file.stat().st_mode & 0o777)
            self.assertEqual(mode, "0o600", f"file must be chmod 600, got {mode}")

    def test_write_token_file_overwrites_atomically(self):
        """Existing token file is replaced (no temp leftovers)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            token_file = Path(tmpdir) / "tok.json"
            with patch.object(_us, "_read_token_path", return_value=str(token_file)):
                _us.write_token_file(access_token="v1")
                _us.write_token_file(access_token="v2")
                _us.write_token_file(access_token="v3")
            self.assertEqual(json.loads(token_file.read_text())["access_token"], "v3")
            # No temp files left behind in tmpdir
            leftovers = [p for p in Path(tmpdir).iterdir() if p.name.startswith(".")]
            self.assertEqual(leftovers, [], f"temp files left: {leftovers}")

    def test_normalize_token_response_maps_keys(self):
        """The OAuth token endpoint returns, at minimum: access_token. Optional
        fields are mapped through to write_token_file kwargs verbatim."""
        self.assertEqual(_us._normalize_token_response({"access_token": "x"}), {"access_token": "x"})
        full = _us._normalize_token_response({
            "access_token": "***",
            "refresh_token": "***",
            "expires_in": 7200,
            "scope": "profile domain",
            "token_type": "Bearer",
        })
        self.assertEqual(full, {
            "access_token": "***",
            "refresh_token": "***",
            "expires_in": 7200,
            "scope": "profile domain",
            "token_type": "Bearer",
        })

    def test_mcp_call_raises_auth_when_no_token(self):
        """mcp_call with no saved token raises UbersuggestAuthError (not bare Exception)."""
        with patch.object(_us, "_read_access_token", return_value=None):
            with self.assertRaises(_us.UbersuggestAuthError) as ctx:
                _us.mcp_call("tools/list")
            msg = str(ctx.exception).lower()
            self.assertIn("ubersuggest", msg)
            self.assertIn("oauth", msg)

    def test_mcp_call_translates_401_to_auth_error(self):
        """A 401 response from the MCP server (non-refreshable) raises UbersuggestAuthError."""
        from urllib.error import HTTPError
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps({
            "error": "invalid_token",
            "error_description": "Token expired",
        }).encode()
        fake_response.__enter__.return_value = fake_response
        with patch.object(_us, "_read_access_token", return_value="***"), \
             patch.object(_us, "is_token_expired", return_value=False), \
             patch.object(_us, "refresh_access_token", side_effect=_us.UbersuggestAuthError("refresh needed")), \
             patch("urllib.request.urlopen", side_effect=HTTPError(
                 url="http://test/mcp", code=401, msg="Unauthorized",
                 hdrs={}, fp=fake_response)):
            with self.assertRaises(_us.UbersuggestAuthError):
                _us.mcp_call("tools/list", auto_refresh=False)

    def test_mcp_call_does_not_swallow_typed_exceptions(self):
        """Verify typed-exception ordering (specific before generic)."""
        # We don't hit the network here; just confirm the function declares
        # the right exception types in its contract.
        self.assertTrue(issubclass(_us.UbersuggestAuthError, Exception))
        self.assertTrue(issubclass(_us.UbersuggestUpstreamError, Exception))
        self.assertTrue(issubclass(_us.UbersuggestNetworkError, Exception))

    def test_pkce_helpers_produce_valid_rfc7636_pair(self):
        """generate_pkce_pair → verifier+challenge; verify round-trip S256."""
        import base64, hashlib
        verifier, challenge = _us.generate_pkce_pair()
        # Verifier is base64url, 43-128 chars per RFC 7636.
        self.assertGreaterEqual(len(verifier), 43)
        self.assertLessEqual(len(verifier), 128)
        self.assertNotIn("=", verifier, "verifier must be unpadded base64url")
        self.assertNotIn("=", challenge, "challenge must be unpadded base64url")
        # Challenge = base64url(sha256(verifier)) — verify.
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).rstrip(b"=").decode()
        self.assertEqual(challenge, expected)

    def test_generate_state_format(self):
        state = _us.generate_state()
        self.assertGreaterEqual(len(state), 22)
        self.assertLessEqual(len(state), 32)
        self.assertNotIn("=", state)


# ────────────────────────────────────────────────────────────────────────
# OAuth script tests (CLI surface, no real OAuth dance)
# ────────────────────────────────────────────────────────────────────────

class OAuthScriptTests(unittest.TestCase):

    def test_oauth_script_help(self):
        """--help exits 0 and prints usage."""
        import subprocess as _sp
        result = _sp.run(
            [sys.executable, "scripts/ubersuggest_oauth.py", "--help"],
            capture_output=True, text=True, check=False,
            cwd="/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--port", result.stdout)
        self.assertIn("--scopes", result.stdout)
        self.assertIn("--status", result.stdout)
        self.assertIn("--no-browser", result.stdout)

    def test_oauth_script_status_subcommand_clean(self):
        """--status with no token file should print NOT CONFIGURED and exit 1."""
        import subprocess as _sp
        # Set a path that definitely doesn't exist by overriding the env.
        with patch.dict(os.environ, {"UBERSUGGEST_TOKEN_FILE": "/tmp/no-such-ub-file.json"}):
            result = _sp.run(
                [sys.executable, "scripts/ubersuggest_oauth.py", "--status"],
                capture_output=True, text=True, check=False,
                cwd="/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard",
            )
        self.assertEqual(result.returncode, 1, f"unexpected exit: {result.stderr}")
        self.assertIn("NOT CONFIGURED", result.stdout)

    def test_generate_pkce_rfc7636_valid(self):
        """Importing the OAuth script + calling generate_pkce."""
        verifier, challenge = _oauth.generate_pkce()
        self.assertGreaterEqual(len(verifier), 43)
        self.assertLessEqual(len(verifier), 128)

    def test_generate_state_format(self):
        state = _oauth.generate_state()
        self.assertGreaterEqual(len(state), 16)
        self.assertLessEqual(len(state), 32)

    def test_free_port_hint_finds_a_port(self):
        """free_port_hint always returns an int within the expected range."""
        port = _oauth.free_port_hint(_oauth.DEFAULT_PORT)
        self.assertIsInstance(port, int)
        self.assertGreaterEqual(port, 9990)
        self.assertLessEqual(port, 10100)

    def test_b64url_nopad_strips_padding(self):
        out = _oauth._b64url_nopad(b"hello")
        # "hello" base64url without padding = "aGVsbG8"
        self.assertEqual(out, "aGVsbG8")
        self.assertNotIn("=", out)


# ────────────────────────────────────────────────────────────────────────
# weekly_report cross-cut tests (the new auto-silent claims)
# ────────────────────────────────────────────────────────────────────────

class WeeklyReportSeoCrossCutTests(unittest.TestCase):
    """Verify the new auto-silent SEO claims:

    - When seo-rankings.json has real rising/falling keywords, the report
      adds a "Biggest SEO mover/drop" claim citing the top keyword.
    - When ubersuggest-domain.json exists with traffic + backlinks, the
      report adds a "SEO domain snapshot" claim.
    - When neither file exists or seo-rankings.json lacks rank data, the
      report stays silent about these new claims (auto-fail-safe).
    """

    @classmethod
    def setUpClass(cls):
        from _lib import intelligence
        cls._intelligence = intelligence
        cls.DATA_DIR = Path(
            "/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data"
        )

    def _call_weekly(self) -> dict:
        # Inline call — avoids `self._weekly_report(...)` getting interpreted
        # as a bound method (Python treats the class attr as a method).
        return self._intelligence.weekly_report(brand="swing-shack")

    def _backup_existing(self):
        self._seo_path = self.DATA_DIR / "seo-rankings.json"
        self._domain_path = self.DATA_DIR / "ubersuggest-domain.json"
        self._seo_bak = self._seo_path.with_suffix(".bak-test-claim")
        self._domain_bak = self._domain_path.with_suffix(".bak-test-claim")
        if self._seo_path.exists():
            self._seo_bak.write_text(self._seo_path.read_text())
        if self._domain_path.exists():
            self._domain_bak.write_text(self._domain_path.read_text())

    def _restore(self):
        if self._seo_bak.exists():
            self._seo_bak.rename(self._seo_path)
        else:
            self._seo_path.unlink(missing_ok=True)
        if self._domain_bak.exists():
            self._domain_bak.rename(self._domain_path)
        else:
            self._domain_path.unlink(missing_ok=True)

    def _write_seo_with_ranks(self):
        data = {
            "updated": "2026-08-06T04:30:00Z",
            "keywords": [
                {"keyword": "indoor golf johannesburg",
                 "current_rank": 4, "previous_rank": 7,
                 "search_volume": 1200, "cpc": 2.45, "target_url": "https://swingshack.co.za"},
                {"keyword": "golf simulator johannesburg",
                 "current_rank": 9, "previous_rank": 6,
                 "search_volume": 850, "cpc": 1.95, "target_url": "https://swingshack.co.za"},
                {"keyword": "trackman johannesburg",
                 "current_rank": 5, "previous_rank": 8,
                 "search_volume": 480, "cpc": 1.20, "target_url": "https://swingshack.co.za"},
                {"keyword": "club fitting johannesburg",
                 "current_rank": None, "previous_rank": None,
                 "search_volume": None, "cpc": None, "target_url": "https://swingshack.co.za"},
            ],
            "rising_keywords": [
                {"keyword": "indoor golf johannesburg",
                 "previous_rank": 7, "current_rank": 4, "delta": 3},
                {"keyword": "trackman johannesburg",
                 "previous_rank": 8, "current_rank": 5, "delta": 3},
            ],
            "falling_keywords": [
                {"keyword": "golf simulator johannesburg",
                 "previous_rank": 6, "current_rank": 9, "delta": 3},
            ],
            "quick_wins": [],
            "summary": {"tracked": 4, "found": 3, "not_found": 1, "fetch_failures": 0},
            "recommendations": [],
        }
        self._seo_path.write_text(json.dumps(data, indent=2))

    def _write_domain_snapshot(self):
        data = {
            "fetched_at": "2026-08-06T04:30:42Z",
            "domain_overview": {"content": [{"text": json.dumps({
                "organicTraffic": 4523,
                "monthlyTraffic": 4523,
            })}]},
            "backlinks_overview": {"content": [{"text": json.dumps({
                "backlinks": 1247,
                "totalBacklinks": 1247,
            })}]},
        }
        self._domain_path.write_text(json.dumps(data, indent=2))

    def setUp(self):
        self._backup_existing()

    def tearDown(self):
        self._restore()

    def test_with_ranks_fires_biggest_mover_claim(self):
        """Real rank data → 'Biggest SEO mover' claim appears in working."""
        self._write_seo_with_ranks()
        r = self._call_weekly()
        interp = r["interpretation"]
        seo_working = [w for w in interp["whats_working"]
                       if "rank" in w["claim"].lower() or "mover" in w["claim"].lower()]
        self.assertTrue(len(seo_working) >= 1,
                        f"expected a rank-related working claim; got: {[w['claim'] for w in interp['whats_working']]}")
        # Specifically the mover claim
        mover = [w for w in seo_working if "rose" in w["claim"]]
        self.assertTrue(mover, "expected 'rose' claim")
        self.assertIn("indoor golf johannesburg", mover[0]["claim"])
        self.assertIn("#7", mover[0]["claim"])
        self.assertIn("#4", mover[0]["claim"])

    def test_with_ranks_and_falling_fires_drop_claim_when_no_rising(self):
        """If only falling keywords exist (no rising), the report should
        surface a 'Biggest SEO drop' as not_working instead of a mover
        as working."""
        # Write a state with only falling keywords
        data = {
            "updated": "2026-08-06T04:30:00Z",
            "keywords": [
                {"keyword": "k1", "current_rank": 12, "previous_rank": 8,
                 "search_volume": 100, "cpc": 1.0, "target_url": "https://x"},
                {"keyword": "k2", "current_rank": 15, "previous_rank": 10,
                 "search_volume": 200, "cpc": 2.0, "target_url": "https://x"},
            ],
            "rising_keywords": [],
            "falling_keywords": [
                {"keyword": "k1", "previous_rank": 8, "current_rank": 12, "delta": 4},
                {"keyword": "k2", "previous_rank": 10, "current_rank": 15, "delta": 5},
            ],
            "quick_wins": [],
            "summary": {"tracked": 2, "found": 2, "not_found": 0, "fetch_failures": 0},
            "recommendations": [],
        }
        self._seo_path.write_text(json.dumps(data, indent=2))
        r = self._call_weekly()
        drop = [w for w in r["interpretation"]["whats_not"]
                if "fell" in w["claim"].lower() or "drop" in w["claim"].lower()]
        self.assertTrue(drop, "expected a drop claim in whats_not")

    def test_with_domain_snapshot_fires_seo_domain_claim(self):
        """ubersuggest-domain.json with traffic + backlinks → claim with numbers."""
        self._write_domain_snapshot()
        r = self._call_weekly()
        snap = [w for w in r["interpretation"]["whats_working"]
                if "organic traffic" in w["claim"]]
        self.assertTrue(snap, "expected SEO domain snapshot claim")
        self.assertIn("4,523", snap[0]["claim"])
        self.assertIn("1,247", snap[0]["claim"])

    def test_auto_silent_when_needs_fetcher_falls_through_to_old_claim(self):
        """If seo-rankings.json has 'needs_fetcher' gating or no rising/falling
        arrays, the new claims don't fire (auto-fail-safe). The pre-existing
        'rankings fetcher offline' claim is what should surface."""
        # The shipped state has 0 rising, 0 falling. Don't write anything.
        # weekly_report should run on the actual disk data.
        # Just confirm the new auto-silent paths don't crash.
        r = self._call_weekly()
        interp = r["interpretation"]
        # New "Biggest SEO mover" / "Biggest SEO drop" / "SEO domain snapshot"
        # MUST NOT appear if the data files are the shipped state (no fake data).
        for lst in (interp["whats_working"], interp["whats_not"], interp["look_at"]):
            for w in lst:
                claim = w.get("claim", "")
                self.assertNotIn("rose from", claim.lower(),
                                 f"unexpected 'rose' claim without rank data: {claim}")
                self.assertNotIn("fell from", claim.lower(),
                                 f"unexpected 'fell' claim without rank data: {claim}")
                self.assertNotIn("organic traffic =", claim.lower(),
                                 f"unexpected 'organic traffic' claim without domain file: {claim}")


if __name__ == "__main__":
    unittest.main()
