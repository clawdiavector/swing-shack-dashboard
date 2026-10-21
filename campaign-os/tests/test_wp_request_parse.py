"""geo_audit._wp_request must hand back the WordPress body as parsed JSON.

_http already parses JSON, so parsing it again failed and wrapped a truncated
copy in {"raw": ...}. seo_meta_publish.fetch_page then saw a dict, not a list,
and every page read as "not found". Found 2026-10-21 on the live dry run.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from _lib import geo_audit, publish_v1, seo_meta_publish, wp_publisher  # noqa: E402

TARGET = {"wp_api_base": "https://example.test/wp-json/wp/v2"}


def _patch(monkeypatch, status, body):
    monkeypatch.setattr(publish_v1, "load_publishing_target", lambda brand: TARGET)
    monkeypatch.setattr(wp_publisher, "_wp_auth_header", lambda target: "Basic x")
    monkeypatch.setattr(wp_publisher, "_http", lambda *a, **k: (status, body))


def test_list_body_comes_back_as_a_list(monkeypatch):
    _patch(monkeypatch, 200, [{"id": i} for i in range(600)])
    r = geo_audit._wp_request("swing-shack", "GET", "/pages")
    assert r["ok"] and isinstance(r["data"], list) and len(r["data"]) == 600


def test_dict_body_comes_back_as_a_dict(monkeypatch):
    _patch(monkeypatch, 200, {"id": 7, "meta": {}})
    assert geo_audit._wp_request("swing-shack", "GET", "/pages/7")["data"] == {"id": 7, "meta": {}}


def test_text_body_that_is_json_is_parsed(monkeypatch):
    _patch(monkeypatch, 200, '[{"id": 1}]')
    assert geo_audit._wp_request("swing-shack", "GET", "/pages")["data"] == [{"id": 1}]


def test_non_json_body_is_kept_as_truncated_raw(monkeypatch):
    _patch(monkeypatch, 200, "<html>" + "x" * 900)
    r = geo_audit._wp_request("swing-shack", "GET", "/pages")
    assert set(r["data"]) == {"raw"} and len(r["data"]["raw"]) == 500


def test_fetch_page_finds_a_published_page_through_the_real_client(monkeypatch):
    _patch(monkeypatch, 200, [{"id": 2255, "slug": "membership", "status": "publish", "link": "https://x/membership/"}])
    page = seo_meta_publish.fetch_page(seo_meta_publish.default_wp("swing-shack"), "membership")
    assert page and page["id"] == 2255
