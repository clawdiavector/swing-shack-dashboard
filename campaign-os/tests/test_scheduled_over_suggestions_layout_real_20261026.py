"""T10 fix — layout skip with week-board-shaped rows (template_id, no layout key)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _lib import calendar_suggestions as cs  # noqa: E402


def test_filter_layout_skip_reads_template_id_on_previous_day(monkeypatch):
    from _lib import product_post_templates as pt

    monkeypatch.setattr(pt, "layout_for", lambda n, hist: "one-hero" if len(hist) <= 1 else "type-hero")
    posts = {
        "2026-10-23": [
            {
                "calendar_id": "cal-takomo-101u",
                "title": "Takomo 101U",
                "state": "scheduled",
                "template_id": "swing-shack-one-hero-retail-v3",
            },
        ],
    }
    items = [
        {"key": "s1", "source": "stock", "title": "Odyssey Rossie", "date": "2026-10-24"},
        {"key": "s2", "source": "stock", "title": "FootJoy Pure Touch", "date": "2026-10-24"},
    ]
    out = cs.filter_suggestions_nearby_scheduled(items, posts, brand_id="swing-shack")
    assert [i["key"] for i in out] == ["s1"]
