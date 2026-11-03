"""T11 fix — on_social_today uses Postiz/Meta read-back, not sandbox receipts."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from unittest import mock

import pytest

CAMPAIGN_OS = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, CAMPAIGN_OS)

from _lib import foreman_eod as feod  # noqa: E402

TODAY = dt.date(2026, 10, 26)
TS_TODAY = "2026-10-26T14:00:00.000Z"
TS_YDAY = "2026-10-25T14:00:00.000Z"


def _plant_receipts(tmp_path, monkeypatch, rows):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sandbox = tmp_path / "publish-sandbox"
    sandbox.mkdir(parents=True)
    (sandbox / "receipts.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )


def test_on_social_ignores_sandbox_receipts_uses_postiz(tmp_path, monkeypatch):
    _plant_receipts(
        tmp_path,
        monkeypatch,
        [
            {"brand_id": "stick", "mode": "sandbox", "dispatched_at": TS_TODAY},
            {"brand_id": "stick", "mode": "live", "dispatched_at": TS_TODAY, "postiz_post_id": "live1"},
        ],
    )
    published = {
        "id": "cm-post-1",
        "state": "PUBLISHED",
        "publishDate": TS_TODAY,
        "group": "grp-1",
    }

    with mock.patch.object(feod, "_postiz_published_today", return_value=1):
        assert feod.on_social_today("stick", TODAY) == 1


def test_postiz_counts_published_today_only():
    def fake_list_integrations(*, brand_id=None):
        return ([{"id": "ig-int"}], None)

    def fake_list_posts(integration_id, **kwargs):
        assert kwargs.get("state") == "PUBLISHED"
        return (
            [
                {"id": "a", "state": "PUBLISHED", "publishDate": TS_TODAY, "group": "g1"},
                {"id": "b", "state": "PUBLISHED", "publishDate": TS_YDAY, "group": "g2"},
                {"id": "c", "state": "DRAFT", "publishDate": TS_TODAY},
            ],
            None,
        )

    with mock.patch(
        "_lib.postiz_client.postiz_status", lambda brand_id=None: {"api_key_present": True}
    ), mock.patch("_lib.postiz_client.list_integrations", fake_list_integrations), mock.patch(
        "_lib.postiz_client.list_posts", fake_list_posts
    ):
        assert feod._postiz_published_today("stick", TODAY) == 1


def test_on_social_falls_back_to_meta_when_postiz_unconfigured():
    ig_resp = {
        "data": [
            {"id": "1", "timestamp": TS_TODAY},
            {"id": "2", "timestamp": TS_YDAY},
        ],
        "_meta": {"ig_account_id": "17841400000000000"},
    }

    with mock.patch(
        "_lib.postiz_client.postiz_status", lambda brand_id=None: {"api_key_present": False}
    ), mock.patch(
        "_lib.meta_api.load_brand_integration",
        return_value={"ig_business_account_id": "17841400000000000", "configured": True},
    ), mock.patch("_lib.meta_api.list_recent_posts_for_brand", return_value=ig_resp):
        assert feod.on_social_today("stick", TODAY) == 1
