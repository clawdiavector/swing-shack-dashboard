"""Plan month: T9 outside posts are not also drawn as scheduled posts (2026-10-27)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _lib import calendar_suggestions as cs  # noqa: E402


def test_posts_by_day_skips_outside_posts(monkeypatch):
    def fake_week_board(**_kw):
        return {"days_list": [{"date": "2026-10-26", "posts": [
            {"calendar_id": "a", "title": "Vice Pro Air (outside)", "state": "booked",
             "post_type": "posted-outside-campaign-os"},
            {"calendar_id": "b", "title": "Spring at Stick", "state": "booked"},
        ]}]}

    import _lib.unified_inbox as ui

    monkeypatch.setattr(ui, "week_board", fake_week_board)
    out = cs.posts_by_day_for_month("stick", "2026-10")
    assert [p["calendar_id"] for p in out["2026-10-26"]] == ["b"]
