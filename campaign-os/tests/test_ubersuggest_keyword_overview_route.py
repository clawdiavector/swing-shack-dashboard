"""Regression test for /api/intel/ubersuggest/keyword_overview loc_id fix.

Background: the route was passing a numeric `loc_id` directly to the
`_lib.ubersuggest_mcp.keyword_overview(...)` helper, but the helper expects
the kw-only `location=` argument (a country STRING like "ZA", "US").
MCP server rejects numeric `locId` with HTTP 400 / Invalid "location" parameter.

This test exercises the HTTP route in-process (Flask test client) and
stubs the upstream `_us.keyword_overview` so we don't need a live token.
Verifies that:
  - `?keyword=foo`              -> calls helper with location='US' (default loc_id 2840)
  - `?keyword=foo&loc_id=2076`  -> calls helper with location='ZA'
  - `?keyword=foo&location=GB`  -> calls helper with location='GB' (explicit wins)
  - empty keyword               -> 400

The bug was discovered via the live URL returning HTTP 500 with
`keyword_overview() got an unexpected keyword argument 'loc_id'`.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

CAMPAIGN_OS = Path(__file__).resolve().parents[1]


class KeywordOverviewRouteTests(unittest.TestCase):  # type: ignore[name-defined]
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="campaign-os-us-route-"))
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        sys.path.insert(0, str(CAMPAIGN_OS))
        import app as campaign_app  # noqa: E402

        cls.module = campaign_app
        cls.flask_app = campaign_app.app
        cls.client = cls.flask_app.test_client()
        # Avoid triggering real network / git operations on first request.
        cls.module.init_repo = lambda: None
        # Login once at the class level so test_client has a session cookie.
        cls.client.post(
            "/login",
            data={"password": "swing-shack-dev-2026"},
            follow_redirects=False,
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)
        os.environ.pop("DATA_DIR", None)

    def _call(self, qs):
        return self.client.get(f"/api/intel/ubersuggest/keyword_overview?{qs}")

    def test_default_loc_id_maps_to_us(self):
        captured = {}
        def fake_keyword_overview(keyword, *, location="ZA", lang="en"):
            captured["keyword"] = keyword
            captured["location"] = location
            captured["lang"] = lang
            return {"search_volume": 100}
        with patch("_lib.ubersuggest_mcp.keyword_overview", side_effect=fake_keyword_overview):
            resp = self._call("keyword=golf")
        self.assertEqual(resp.status_code, 200, resp.data)
        body = resp.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["location"], "US", body)
        self.assertEqual(captured["location"], "US")
        self.assertEqual(captured["keyword"], "golf")

    def test_loc_id_2076_maps_to_za(self):
        captured = {}
        def fake_keyword_overview(keyword, *, location="ZA", lang="en"):
            captured["location"] = location
            return {"search_volume": 200}
        with patch("_lib.ubersuggest_mcp.keyword_overview", side_effect=fake_keyword_overview):
            resp = self._call("keyword=golf&loc_id=2076")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.get_json()["location"], "ZA", resp.data)
        self.assertEqual(captured["location"], "ZA")

    def test_explicit_location_wins_over_loc_id(self):
        captured = {}
        def fake_keyword_overview(keyword, *, location="ZA", lang="en"):
            captured["location"] = location
            return {"search_volume": 300}
        with patch("_lib.ubersuggest_mcp.keyword_overview", side_effect=fake_keyword_overview):
            resp = self._call("keyword=golf&loc_id=2840&location=GB")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.get_json()["location"], "GB", resp.data)
        self.assertEqual(captured["location"], "GB")

    def test_unknown_loc_id_falls_back_to_za(self):
        captured = {}
        def fake_keyword_overview(keyword, *, location="ZA", lang="en"):
            captured["location"] = location
            return {"search_volume": 400}
        with patch("_lib.ubersuggest_mcp.keyword_overview", side_effect=fake_keyword_overview):
            resp = self._call("keyword=golf&loc_id=99999")
        self.assertEqual(resp.status_code, 200, resp.data)
        # Unknown loc_id falls back to "ZA" rather than crashing — keeps the
        # endpoint resilient for callers that pass stale / new IDs.
        self.assertEqual(captured["location"], "ZA")

    def test_missing_keyword_returns_400(self):
        resp = self._call("")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.get_json()["ok"])


if __name__ == "__main__":
    unittest.main()
