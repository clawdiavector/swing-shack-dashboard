"""Daily posting target on the clean calendar: 20 placements a day per brand, split by platform,
and how much of each day is made (scheduled) or waiting for a yes."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import clean_calendar as cc  # noqa: E402
from _lib import daily_target as dt  # noqa: E402


def entry(view="scheduled", channels=("instagram",), fmt="feed", day="2026-11-03", making=False, kind="post"):
    return {"view": view, "channels": list(channels), "format": fmt, "date": day, "making": making, "kind": kind}


def test_target_is_twenty_for_stick_and_swing_shack_and_none_for_bag_drop():
    for brand in ("stick", "swing-shack"):
        split = dt.target_for(brand)
        assert sum(split.values()) == 20
        assert split == {"ig_story": 9, "fb_story": 4, "ig_feed": 2, "fb_feed": 1, "reel": 1, "google": 1, "tiktok": 2}
    assert dt.target_for("bag-drop") is None


def test_each_channel_of_a_post_fills_its_own_slot():
    assert dt.slots_of(entry(channels=("instagram", "facebook"))) == ["ig_feed", "fb_feed"]
    assert dt.slots_of(entry(channels=("instagram",), fmt="story")) == ["ig_story"]
    assert dt.slots_of(entry(channels=("facebook",), fmt="story")) == ["fb_story"]
    assert dt.slots_of(entry(channels=("gbp",))) == ["google"]
    assert dt.slots_of(entry(channels=("tiktok",), fmt="reel")) == ["tiktok"]
    # a Reel shared to Instagram and Facebook is one Reel
    assert dt.slots_of(entry(channels=("instagram", "facebook"), fmt="reel")) == ["reel"]
    # ideas and to-dos are not made yet
    assert dt.slots_of(entry(kind="idea", view="ideas")) == []
    assert dt.slots_of(entry(kind="task", view="todo")) == []


def test_day_progress_counts_made_and_waiting_and_shows_gaps():
    split = dt.target_for("stick")
    entries = [
        entry(fmt="story"), entry(fmt="story"),                      # 2 IG stories scheduled
        entry(view="approval", channels=("instagram", "facebook")),  # feed post waiting for a yes
        entry(view="approval", making=True, channels=("gbp",)),      # Google post still being made
        entry(kind="idea", view="ideas"),                            # ignored
        entry(day="2026-11-04", fmt="story"),                        # another day
    ]
    days = dt.day_progress(entries, split, date(2026, 11, 3), date(2026, 11, 4))
    d = days["2026-11-03"]
    assert d["target"] == 20
    assert d["done"] == 2
    assert d["waiting"] == 3
    slots = {s["slot"]: s for s in d["slots"]}
    assert (slots["ig_story"]["done"], slots["ig_story"]["target"]) == (2, 9)
    assert slots["ig_feed"]["waiting"] == 1 and slots["fb_feed"]["waiting"] == 1
    assert slots["google"]["waiting"] == 1
    assert slots["tiktok"]["done"] == 0
    assert [s["slot"] for s in d["slots"]] == list(split)
    assert all(s["label"] for s in d["slots"])
    assert days["2026-11-04"]["done"] == 1


def test_an_overfilled_slot_does_not_hide_the_gaps():
    split = dt.target_for("stick")
    entries = [entry(channels=("gbp",)) for _ in range(5)]
    d = dt.day_progress(entries, split, date(2026, 11, 3), date(2026, 11, 3))["2026-11-03"]
    assert d["done"] == 1
    assert {s["slot"]: s["done"] for s in d["slots"]}["google"] == 5


def test_calendar_entries_carry_channels_and_format():
    post = cc.post_entry({"calendar_id": "c1", "state": "scheduled", "go_live_date": "2026-11-03",
                          "channels_picked": ["instagram", "facebook"], "post_type": "story"}, "stick")
    assert post["channels"] == ["instagram", "facebook"] and post["format"] == "story"
    feed = cc.post_entry({"calendar_id": "c2", "state": "draft_ready", "go_live_date": "2026-11-03",
                          "primary_channel": "instagram"}, "stick")
    assert feed["channels"] == ["instagram"] and feed["format"] == "feed"
    rows = [{"id": "p1", "state": "QUEUE", "publishDate": "2026-11-03T08:00:00Z",
             "integration": {"providerIdentifier": "instagram"}, "settings": {"post_type": "story"}, "content": "Hi"},
            {"id": "p2", "state": "QUEUE", "publishDate": "2026-11-03T08:00:00Z",
             "integration": {"providerIdentifier": "tiktok-business"}, "settings": {"__type": "tiktok"}, "content": "Hi"}]
    pz = cc.postiz_entries(rows, "stick", linked_ids=set(), month="2026-11")
    assert [(e["channels"], e["format"]) for e in pz] == [(["instagram"], "story"), (["tiktok"], "feed")]
    g = cc.gbp_entries([{"id": "g1", "status": "approved", "approvedAt": "x"}], "stick", first_slot=date(2026, 11, 3))
    assert g[0]["channels"] == ["gbp"]


def test_month_view_has_a_target_for_every_day(monkeypatch):
    monkeypatch.setattr(cc, "post_rows", lambda brand, month: [])
    monkeypatch.setattr(cc, "comments_by_key", lambda brand: {})
    extras = [{"key": "postiz:p1", "kind": "postiz", "view": "scheduled", "making": False, "date": "2026-11-03",
               "title": "Story", "channels": ["instagram"], "format": "story"}]
    view = cc.month_view("stick", "2026-11", [], extras)
    assert len(view["targets"]) == 30
    assert view["targets"]["2026-11-03"]["done"] == 1
    assert view["targets"]["2026-11-01"]["done"] == 0
    assert cc.month_view("bag-drop", "2026-11", [], [])["targets"] == {}
