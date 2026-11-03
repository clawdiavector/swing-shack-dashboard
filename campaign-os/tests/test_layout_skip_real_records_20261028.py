"""T10 AC-4b on real calendar rows (2026-10-28).

Real week_board posts carry no template_id or layout. The layout now comes from the
calendar record (retail lodges record render_spec.product_layout), so the "same
layout twice in a row" skip engages on real data.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _lib import calendar_suggestions as cs  # noqa: E402
from _lib import retail_campaign as rc  # noqa: E402

REAL_RECORD = {
    "calendar_id": "cal-takomo-101u",
    "event_key": "swing-shack:retail-takomo-101u-20261023",
    "post_type": "operator-image",
    "render_spec": {"slug": "retail-takomo-101u-20261023", "image": "x.png", "product_layout": "one-hero"},
}


def test_layout_from_record_reads_image_lodge_layout():
    assert rc._layout_from_record(REAL_RECORD) == "one-hero"
    assert rc._layout_from_record({"post_type": "ss-did-you-know"}) == ""


def test_posts_by_day_gets_layout_from_record(monkeypatch):
    from _lib import marketing_calendar, unified_inbox

    def fake_week_board(**_kw):
        return {"days_list": [{"date": "2026-10-23", "posts": [
            {"calendar_id": "cal-takomo-101u", "title": "Takomo 101U", "state": "scheduled",
             "post_type": "operator-image"}]}]}

    monkeypatch.setattr(unified_inbox, "week_board", fake_week_board)
    monkeypatch.setattr(marketing_calendar, "canonical_records", lambda brand_id, *a, **k: [REAL_RECORD])
    posts = cs.posts_by_day_for_month("swing-shack", "2026-10")
    assert posts["2026-10-23"][0]["layout"] == "one-hero"


def test_skip_engages_on_real_shaped_rows(monkeypatch):
    from _lib import marketing_calendar, product_post_templates as pt, unified_inbox

    monkeypatch.setattr(pt, "layout_for", lambda n, hist: "one-hero" if len(hist) <= 1 else "type-hero")
    monkeypatch.setattr(unified_inbox, "week_board", lambda **_kw: {"days_list": [{"date": "2026-10-23", "posts": [
        {"calendar_id": "cal-takomo-101u", "title": "Takomo 101U", "state": "scheduled"}]}]})
    monkeypatch.setattr(marketing_calendar, "canonical_records", lambda brand_id, *a, **k: [REAL_RECORD])
    posts = cs.posts_by_day_for_month("swing-shack", "2026-10")
    items = [
        {"key": "s1", "source": "stock", "title": "Odyssey Rossie", "date": "2026-10-24"},
        {"key": "s2", "source": "stock", "title": "FootJoy Pure Touch", "date": "2026-10-24"},
    ]
    out = cs.filter_suggestions_nearby_scheduled(items, posts, brand_id="swing-shack")
    assert [i["key"] for i in out] == ["s1"]


def test_suggestions_survive_calendar_read_error(monkeypatch):
    from _lib import marketing_calendar

    def boom(*_a, **_k):
        raise OSError("disk")

    monkeypatch.setattr(marketing_calendar, "canonical_records", boom)
    assert cs._record_layouts("swing-shack") == {}
