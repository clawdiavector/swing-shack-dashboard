"""T10 — scheduled posts above suggestions; nearby product and layout skips."""
from __future__ import annotations

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _lib import calendar_suggestions as cs  # noqa: E402


def test_primary_post_states():
    assert cs.is_primary_post("scheduled")
    assert cs.is_primary_post("draft_ready")
    assert cs.is_primary_post("released")
    assert not cs.is_primary_post("candidate")
    assert not cs.is_primary_post("gap")
    assert not cs.is_primary_post("")


def test_filter_stock_skips_same_product_within_seven_days():
    posts = {
        "2026-10-20": [{"title": "Titleist Pro V1", "state": "scheduled"}],
    }
    items = [
        {"key": "a", "source": "stock", "title": "Titleist Pro V1", "date": "2026-10-24"},
        {"key": "b", "source": "stock", "title": "Ping Anser 2D", "date": "2026-10-24"},
        {"key": "c", "source": "date", "title": "Holiday", "date": "2026-10-24"},
    ]
    out = cs.filter_suggestions_nearby_scheduled(items, posts, brand_id="stick")
    assert [i["key"] for i in out] == ["b", "c"]


def test_filter_stock_keeps_product_outside_window():
    posts = {
        "2026-10-01": [{"title": "Titleist Pro V1", "state": "lodged"}],
    }
    items = [{"key": "a", "source": "stock", "title": "Titleist Pro V1", "date": "2026-10-24"}]
    out = cs.filter_suggestions_nearby_scheduled(items, posts, brand_id="stick")
    assert out == items


def test_swing_shack_skips_stock_when_layout_matches_previous_day(monkeypatch):
    from _lib import product_post_templates as pt

    monkeypatch.setattr(pt, "layout_for", lambda n, hist: "one-hero" if len(hist) <= 1 else "type-hero")
    posts = {
        "2026-10-23": [{"title": "Takomo", "state": "scheduled", "layout": "one-hero"}],
    }
    items = [
        {"key": "s1", "source": "stock", "title": "Odyssey Rossie", "date": "2026-10-24"},
        {"key": "s2", "source": "stock", "title": "FootJoy Pure Touch", "date": "2026-10-24"},
    ]
    out = cs.filter_suggestions_nearby_scheduled(items, posts, brand_id="swing-shack")
    assert [i["key"] for i in out] == ["s1"]


def test_month_bundle_shape(monkeypatch):
    monkeypatch.setattr(
        cs,
        "posts_by_day_for_month",
        lambda brand_id, month: {"2026-10-24": [{"title": "Vice Pro Air", "state": "draft_ready", "calendar_id": "c1"}]},
    )
    bundle = cs.month_suggestions_bundle(
        "stick",
        "2026-10",
        date(2026, 10, 20),
        [],
        lambda r: False,
        [],
        {},
        [],
        [],
        2,
    )
    assert "2026-10-24" in bundle["posts_by_day"]
    assert bundle["posts_by_day"]["2026-10-24"][0]["title"] == "Vice Pro Air"
