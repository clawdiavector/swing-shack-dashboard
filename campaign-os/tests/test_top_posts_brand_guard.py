"""Top Instagram posts must not leak one brand's account under another brand."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parent.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

REGISTRY = {"brands": {
    "swing-shack": {"display_name": "Swing Shack", "instagram_handle": "@swingshack"},
    "stick": {"display_name": "Stick", "instagram_handle": "@stick.paarl"},
    "no-handle": {"display_name": "Nameless"},
}}
POSTS = {"ok": True, "posts": [{"id": "p1"}], "_meta": {"total_scanned": 1}}


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import app as app_module
    from _lib import insights_correlator as ic

    monkeypatch.setattr(app_module, "load_brands_registry", lambda: REGISTRY)
    monkeypatch.setattr(ic, "get_top_instagram_posts", lambda **kw: dict(POSTS))
    return app_module.app.test_client()


def test_swing_shack_keeps_its_posts(client):
    body = client.get("/api/insights/top-instagram-posts?brand_id=swing-shack").get_json()
    assert body["posts"] == POSTS["posts"]


def test_stick_gets_no_posts_and_a_plain_reason(client):
    body = client.get("/api/insights/top-instagram-posts?brand_id=stick").get_json()
    assert body["ok"] is True
    assert body["posts"] == []
    assert body["_meta"]["reason"] == "No Instagram data for Stick yet."
    assert body["data_source_brand_id"] is None


def test_brand_without_a_handle_gets_no_posts(client):
    body = client.get("/api/insights/top-instagram-posts?brand_id=no-handle").get_json()
    assert body["posts"] == []
    assert "Nameless" in body["_meta"]["reason"]
