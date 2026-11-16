"""Reshares count towards the daily placement counter (2026-10-30).

A reshare is a link on the story-reposts list that a person marked done: an Instagram post shared to the
Instagram story, or a Facebook post shared to the Facebook story. Each is one placement for its brand on the
day it was shared (South African date), in the matching story slot. Open and removed links count for nothing.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import clean_calendar as cc  # noqa: E402
from _lib import daily_target as dt  # noqa: E402
from _lib import story_queue as sq  # noqa: E402


def item(brand="swing-shack", url="https://instagram.com/p/AAA", status="done", done_at="2026-10-30T10:05:00+02:00", iid="x"):
    return {"id": iid, "brand": brand, "url": url, "note": "", "added_by": "", "added_at": "2026-10-30T08:00:00+02:00",
            "status": status, "done_at": done_at if status == "done" else None}


def write_queue(tmp_path, monkeypatch, items):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "story-queue.json").write_text(json.dumps(items), encoding="utf-8")


def test_shares_are_the_done_links_of_one_brand_in_range_by_the_platform_they_were_shared_to(tmp_path, monkeypatch):
    write_queue(tmp_path, monkeypatch, [
        item(iid="a"),                                                              # Instagram, done 30 Oct
        item(iid="b", url="https://facebook.com/swingshack/posts/1"),               # Facebook, done 30 Oct
        item(iid="c", status="open"),                                               # not shared yet
        item(iid="d", status="removed"),                                            # taken off the list
        item(iid="e", brand="stick"),                                               # another brand
        item(iid="f", done_at="2026-11-02T09:00:00+02:00"),                         # another day, still in range
        item(iid="g", done_at="2026-12-01T09:00:00+02:00"),                         # outside the month
        item(iid="h", url="https://fb.watch/xyz"),                                  # Facebook video link
    ])
    out = sq.shares("swing-shack", date(2026, 10, 1), date(2026, 11, 30))
    got = sorted((s["date"], s["slot"]) for s in out)
    assert got == [("2026-10-30", "fb_story"), ("2026-10-30", "fb_story"), ("2026-10-30", "ig_story"),
                   ("2026-11-02", "ig_story")]


def test_shares_is_empty_when_there_is_no_list(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert sq.shares("stick", date(2026, 10, 1), date(2026, 10, 31)) == []


def test_day_progress_counts_reshares_as_made_story_placements():
    split = dt.target_for("swing-shack")
    shares = [{"date": "2026-10-30", "slot": "ig_story"}, {"date": "2026-10-30", "slot": "ig_story"},
              {"date": "2026-10-30", "slot": "fb_story"}]
    days = dt.day_progress([], split, date(2026, 10, 30), date(2026, 10, 31), shares=shares)
    d = days["2026-10-30"]
    slots = {s["slot"]: s for s in d["slots"]}
    assert (slots["ig_story"]["done"], slots["fb_story"]["done"]) == (2, 1)
    assert slots["ig_story"]["reshared"] == 2 and slots["fb_story"]["reshared"] == 1
    assert d["done"] == 3 and d["reshared"] == 3
    assert days["2026-10-31"]["done"] == 0 and days["2026-10-31"]["reshared"] == 0


def test_reshares_add_to_scheduled_stories_and_stop_at_the_slot_target():
    split = {"ig_story": 3, "fb_story": 1}
    scheduled = [{"view": "scheduled", "channels": ["instagram"], "format": "story", "date": "2026-10-30",
                  "making": False, "kind": "post"}] * 2
    shares = [{"date": "2026-10-30", "slot": "ig_story"}] * 4
    d = dt.day_progress(scheduled, split, date(2026, 10, 30), date(2026, 10, 30), shares=shares)["2026-10-30"]
    ig = {s["slot"]: s for s in d["slots"]}["ig_story"]
    assert ig["done"] == 6 and ig["reshared"] == 4          # all are shown...
    assert d["done"] == 3                                    # ...but a slot never counts past its target


def test_existing_callers_without_shares_are_unchanged():
    split = dt.target_for("stick")
    d = dt.day_progress([], split, date(2026, 11, 3), date(2026, 11, 3))["2026-11-03"]
    assert d["done"] == 0 and d["reshared"] == 0


def test_month_view_counts_the_reshares_in_each_days_target(tmp_path, monkeypatch):
    write_queue(tmp_path, monkeypatch, [item(iid="a"), item(iid="b"), item(iid="c", url="https://facebook.com/x/posts/9")])
    monkeypatch.setattr(cc, "post_rows", lambda brand, month: [])
    monkeypatch.setattr(cc, "comments_by_key", lambda brand: {})
    view = cc.month_view("swing-shack", "2026-10", ideas=[])
    day = view["targets"]["2026-10-30"]
    slots = {s["slot"]: s for s in day["slots"]}
    assert slots["ig_story"]["done"] == 2 and slots["fb_story"]["done"] == 1
    assert day["reshared"] == 3
    # reshares are a count on the counter, not calendar entries
    assert not [e for e in view["entries"] if "instagram.com" in str(e.get("title", ""))]
