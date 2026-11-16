"""A brand with its own Instagram file gets its own top posts (6 Nov 2026).

Since 18 Sep, meta_refresh writes brands/<brand>/ig-analytics.json. On live, Stick's
file holds Stick's posts, but What worked lately still said "No Instagram data for
Stick yet." because the route only trusted the shared @swingshack store. A brand
with no file of its own still gets nothing (test_top_posts_brand_guard.py).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parent.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

REGISTRY = {"brands": {
    "swing-shack": {"display_name": "Swing Shack", "instagram_handle": "@swingshack"},
    "stick": {"display_name": "Stick", "instagram_handle": "@stick.paarl"},
}}
RECENT = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S+0000")


def _posts(prefix: str) -> dict:
    return {"updated": RECENT, "posts": [
        {"id": f"{prefix}{i}", "timestamp": RECENT, "engagementRate": str(i + 1),
         "permalink": f"https://www.instagram.com/p/{prefix}{i}/", "captionPreview": f"{prefix} post {i}"}
        for i in range(4)
    ]}


@pytest.fixture()
def data(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("BUNDLED_DATA_DIR", raising=False)
    (tmp_path / "ig-analytics.json").write_text(json.dumps(_posts("ss")), encoding="utf-8")
    own = tmp_path / "brands" / "stick" / "ig-analytics.json"
    own.parent.mkdir(parents=True)
    own.write_text(json.dumps(_posts("stick")), encoding="utf-8")
    return tmp_path


def test_correlator_reads_the_brands_own_posts(data):
    from _lib import insights_correlator as ic

    out = ic.get_top_instagram_posts(brand_id="stick", limit=3)
    links = [p["permalink"] for p in out["posts"]]
    assert links and all("/p/stick" in link for link in links)
    assert out["_meta"]["source"] == "brands/stick/ig-analytics.json"


def test_route_shows_stick_its_own_posts(data, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "load_brands_registry", lambda: REGISTRY)
    body = app_module.app.test_client().get("/api/insights/top-instagram-posts?brand_id=stick&limit=3").get_json()
    assert body["ok"] is True
    assert body["data_source_brand_id"] == "stick"
    links = [p["permalink"] for p in body["posts"]]
    assert links and all("/p/stick" in link for link in links)
