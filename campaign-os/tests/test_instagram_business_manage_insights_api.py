"""
test_instagram_business_manage_insights_api.py

LIVE API evidence for Meta App Review of the
instagram_business_manage_insights permission.

This is the Python test file (separate from the shell-friendly
scripts/test_instagram_business_manage_insights.py script) that
satisfies Meta's "Ensure that you have performed required API test calls"
check.

Runs in production. No mocking. The expectation is that the live token
has already been granted the permission being tested — if it hasn't,
calls 2 and 4 will return HTTP 400 with code 10/200 and the test
fails loudly with the exact upstream error.

Run with:
  python3 -m pytest campaign-os/tests/test_instagram_business_manage_insights_api.py -v
or
  python3 -m unittest campaign-os.tests.test_instagram_business_manage_insights_api
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v21.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

DEFAULT_IG_BUSINESS_ID = "17841456713897671"  # @swingshack IG Business account
DEFAULT_IG_MEDIA_ID = "17988987897030897"     # most recent Swing Shack IG post


def _read_token() -> str:
    tok = os.environ.get("META_SYSTEM_USER_TOKEN", "").strip()
    if tok:
        return tok
    cred_path = Path(
        "/Users/fivefriday/.openclaw-instance2/workspace/clients/swing-shack/credentials/meta-token.json"
    )
    if cred_path.is_file():
        try:
            data = json.loads(cred_path.read_text())
            return (data.get("access_token") or "").strip()
        except Exception:
            pass
    raise unittest.SkipTest(
        "META_SYSTEM_USER_TOKEN not set and no canonical credentials file"
    )


def _get(path: str, params: dict | None = None) -> tuple[int, dict]:
    """Returns (status_code, body_dict). Body is always a dict so callers
    can index it directly. Errors are surfaced via the status code."""
    qs = urlencode({"access_token": _read_token(), **(params or {})})
    url = f"{GRAPH_BASE}{path}?{qs}"
    req = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        body_raw = e.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body_raw)
        except Exception:
            body = {"_raw_error": body_raw}
        return e.code, body


class InstagramBusinessManageInsightsAPITests(unittest.TestCase):
    """Live API tests against the production IG Business account.

    These prove to Meta App Review that the app can call the
    instagram_business_manage_insights endpoints in production,
    with the grants being requested. Each call asserts HTTP 200
    + expected shape.
    """

    @classmethod
    def setUpClass(cls):
        cls.ig_biz_id = os.environ.get("TEST_IG_BIZ_ID", DEFAULT_IG_BUSINESS_ID)
        cls.ig_media_id = os.environ.get("TEST_IG_MEDIA_ID", DEFAULT_IG_MEDIA_ID)

    def test_01_account_info_instagram_basic(self):
        """GET /{ig_business_id}?fields=id,username,followers_count — instagram_basic.

        Proves we can read the IG Business account we manage.
        """
        status, body = _get(f"/{self.ig_biz_id}", {
            "fields": "id,username,followers_count,media_count,name",
        })
        self.assertEqual(status, 200, f"HTTP {status}: {body}")
        self.assertEqual(body["id"], self.ig_biz_id)
        self.assertEqual(body["username"], "swingshack")
        self.assertGreater(body["followers_count"], 0)
        self.assertGreater(body["media_count"], 0)

    def test_02_account_insights_instagram_business_manage_insights(self):
        """GET /{ig_business_id}/insights?metric=reach — instagram_business_manage_insights.

        The permission under review. Proves we can read aggregated
        account-level insights.
        """
        status, body = _get(f"/{self.ig_biz_id}/insights", {
            "metric": "reach",
            "period": "day",
            "metric_type": "total_value",
            "since": 1785135494,
            "until": 1787727494,
        })
        self.assertEqual(status, 200, f"HTTP {status}: {body}")
        self.assertIn("data", body)
        self.assertGreater(len(body["data"]), 0)
        # The reach data should have a numeric value
        first = body["data"][0]
        self.assertEqual(first["name"], "reach")
        # metric_type=total_value returns {"total_value": {"value": N}}
        # while period-only returns {"values": [{"value": N}]}. Accept either.
        self.assertTrue(
            ("values" in first and len(first["values"]) > 0)
            or ("total_value" in first and "value" in first["total_value"]),
            f"expected reach payload, got: {first}",
        )

    def test_03_recent_media_instagram_basic_plus_content_publish(self):
        """GET /{ig_business_id}/media — instagram_basic + instagram_content_publish.

        Proves we can list media published on the account.
        """
        status, body = _get(f"/{self.ig_biz_id}/media", {
            "fields": "id,caption,media_type,like_count,comments_count,timestamp",
            "limit": 3,
        })
        self.assertEqual(status, 200, f"HTTP {status}: {body}")
        self.assertIn("data", body)
        self.assertGreater(len(body["data"]), 0)
        first = body["data"][0]
        self.assertIn("id", first)
        self.assertIn("media_type", first)
        self.assertIn("timestamp", first)

    def test_04_media_insights_instagram_business_manage_insights(self):
        """GET /{ig_media_id}/insights — instagram_business_manage_insights (per-media).

        The permission under review, per-media variant. Proves we can
        read engagement metrics for individual posts.
        """
        status, body = _get(f"/{self.ig_media_id}/insights", {
            "metric": "reach,likes,saved,comments,shares,total_interactions",
            "period": "lifetime",
        })
        self.assertEqual(status, 200, f"HTTP {status}: {body}")
        self.assertIn("data", body)
        self.assertGreater(len(body["data"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
