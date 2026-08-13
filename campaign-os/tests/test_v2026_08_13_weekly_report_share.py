"""v2026-08-13: Auth-optional markdown export with signed share tokens.

Covers:
  1. weekly_report_share() mints a valid token + share_url
  2. weekly_report_share() returns 401 when called without auth
  3. weekly_report_share() clamps TTL to [60s, 7d]
  4. weekly_report_export() accepts a valid share token (no cookie)
  5. weekly_report_export() rejects an invalid/expired share token
  6. weekly_report_export() still works with the existing cookie auth
  7. Token scope-binding: a token minted for a different scope is rejected
  8. The export endpoint is in PUBLIC_ROUTES so _gate() lets it through

All tests spin up an in-process Flask test client and override
SESSION_SECRET to a known value for deterministic signing.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import unittest
from pathlib import Path

# Make sure the campaign-os dir is importable + tests can patch env BEFORE
# app.py is imported (so SESSION_SECRET is stable for the serializer).
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_HERE.parent))


class ShareTokenExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Set a deterministic SESSION_SECRET BEFORE importing app.
        os.environ["SESSION_SECRET"] = "test-secret-for-share-tokens-2026-08-13"
        os.environ["CAMPAIGN_OS_SECRET"] = "test-secret-for-share-tokens-2026-08-13"
        os.environ.setdefault("DATA_DIR", "/tmp/test-campaign-os-data")
        os.environ.setdefault("PORT", "0")
        # Import app module
        from app import app as flask_app
        cls.flask_app = flask_app
        cls.client = flask_app.test_client()

    def _login(self):
        """Authenticate the test client. Returns the session cookie."""
        return self.client.post("/login", data={"password": "swing-shack-dev-2026"})

    def test_01_share_endpoint_requires_auth(self):
        """Unauthed POST to /api/intel/weekly_report/share returns 401."""
        # Drop any auth cookie first.
        client = self.flask_app.test_client()
        r = client.post("/api/intel/weekly_report/share", json={})
        self.assertEqual(r.status_code, 401, r.data[:200])
        body = r.get_json() or {}
        self.assertFalse(body.get("ok"))
        self.assertIn("auth", body.get("error", "").lower())

    def test_02_share_endpoint_mints_token(self):
        """Authed POST returns a valid share_url + token + expires_at."""
        r = self._login()
        self.assertEqual(r.status_code, 200, r.data[:200])
        r = self.client.post("/api/intel/weekly_report/share", json={})
        self.assertEqual(r.status_code, 200, r.data[:200])
        body = r.get_json() or {}
        self.assertTrue(body.get("ok"))
        self.assertIn("share_url", body)
        self.assertIn("token", body)
        self.assertIn("expires_at", body)
        self.assertIn("ttl_seconds", body)
        # Default TTL is 24h = 86400s
        self.assertEqual(body["ttl_seconds"], 86400)
        # Token is a non-empty string
        token = body["token"]
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 20)
        # Share URL points at the export endpoint
        self.assertIn("/api/intel/weekly_report/export", body["share_url"])
        self.assertIn(token, body["share_url"])
        # Expires-at is ~24h from now
        expires = dt.datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
        delta = (expires - dt.datetime.now(dt.timezone.utc)).total_seconds()
        self.assertGreater(delta, 86000)
        self.assertLess(delta, 86500)

    def test_03_share_endpoint_clamps_ttl(self):
        """TTL is clamped to [60s, 7d]. 1s → 60s, 30d → 7d."""
        self._login()
        # 1s → 60s
        r = self.client.post("/api/intel/weekly_report/share", json={"ttl_seconds": 1})
        self.assertEqual(r.get_json()["ttl_seconds"], 60)
        # 30d → 7d = 604800s
        r = self.client.post("/api/intel/weekly_report/share", json={"ttl_seconds": 60 * 60 * 24 * 30})
        self.assertEqual(r.get_json()["ttl_seconds"], 60 * 60 * 24 * 7)
        # 1h → 3600s (in-range passthrough)
        r = self.client.post("/api/intel/weekly_report/share", json={"ttl_seconds": 3600})
        self.assertEqual(r.get_json()["ttl_seconds"], 3600)

    def test_04_export_accepts_valid_share_token(self):
        """A valid share token unlocks the export endpoint WITHOUT a cookie."""
        # Mint a token via the share endpoint (authed)
        self._login()
        r = self.client.post("/api/intel/weekly_report/share", json={"ttl_seconds": 3600})
        self.assertEqual(r.status_code, 200)
        share_url = r.get_json()["share_url"]
        token = r.get_json()["token"]
        # Build a brand-new client with NO cookie set. Hit the share URL.
        fresh = self.flask_app.test_client()
        r = fresh.get(f"/api/intel/weekly_report/export?share={token}")
        self.assertEqual(r.status_code, 200, r.data[:300])
        # Body is markdown
        self.assertIn("text/markdown", r.headers.get("Content-Type", ""))
        body = r.data.decode("utf-8", errors="replace")
        self.assertIn("# Weekly Marketing Report", body)

    def test_05_export_rejects_invalid_share_token(self):
        """Garbage tokens get 401."""
        fresh = self.flask_app.test_client()
        for bad in ("not-a-real-token", "abc.def.ghi", "", "Im-different-payload.Hello"):
            with self.subTest(token=bad[:20]):
                r = fresh.get(f"/api/intel/weekly_report/export?share={bad}")
                self.assertEqual(r.status_code, 401, f"expected 401 for {bad!r}, got {r.status_code}")

    def test_06_export_rejects_wrong_scope_token(self):
        """A token minted for a DIFFERENT scope must not unlock the export.
        This is the defense-in-depth check — payload scope must be
        'weekly_report_export', not just 'present + signed'."""
        from app import _serializer
        # Mint a token for a different scope directly via the serializer.
        bad_payload = {"scope": "anything_else", "v": 1}
        bad_token = _serializer.dumps(bad_payload)
        fresh = self.flask_app.test_client()
        r = fresh.get(f"/api/intel/weekly_report/export?share={bad_token}")
        self.assertEqual(r.status_code, 401, r.data[:200])

    def test_07_export_still_works_with_cookie(self):
        """The legacy cookie-auth path still returns 200 + markdown."""
        self._login()
        r = self.client.get("/api/intel/weekly_report/export")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/markdown", r.headers.get("Content-Type", ""))
        self.assertIn("# Weekly Marketing Report", r.data.decode("utf-8", errors="replace"))

    def test_08_export_endpoint_is_public_route(self):
        """The export endpoint must be in PUBLIC_ROUTES so the gate()
        before_request hook lets unauthed requests through (the route
        then enforces share-token auth)."""
        from app import PUBLIC_ROUTES
        self.assertIn("/api/intel/weekly_report/export", PUBLIC_ROUTES)

    def test_09_share_token_works_with_query_only(self):
        """Smoke test: build the share_url from the response and curl
        it with a fresh client. If this fails, the chain is broken."""
        self._login()
        r = self.client.post("/api/intel/weekly_report/share", json={})
        share_url = r.get_json()["share_url"]
        # The share_url is a full URL. For the Flask test client we
        # only care about the path + query (the client doesn't actually
        # dial out). urlparse drops the path entirely if host is
        # missing, so do it manually.
        if "/api/intel/weekly_report/export" in share_url:
            tail = share_url.split("/api/intel/weekly_report/export", 1)[1]
            path_qs = "/api/intel/weekly_report/export" + tail
        else:
            self.fail(f"share_url missing export path: {share_url}")
        fresh = self.flask_app.test_client()
        r = fresh.get(path_qs)
        self.assertEqual(r.status_code, 200, r.data[:200])
        self.assertIn("Weekly Marketing Report", r.data.decode("utf-8", errors="replace"))


if __name__ == "__main__":
    unittest.main()
