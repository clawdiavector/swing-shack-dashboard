"""An outside post keeps its kind and platform through the calendar's row builder (2026-10-30).

On prod after PR #279 phone stories still counted as feed and some outside posts as TikTok:
the row builder drops media_kind and fills primary_channel itself, so the record's own
values have to be carried over.
"""
from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import clean_calendar as cc  # noqa: E402
from _lib import daily_target as dt  # noqa: E402


def built_row(**over):
    """What the row builder hands back for an outside record: no media_kind, its own channel guess."""
    row = {"calendar_id": "stick:outside-instagram-story-1", "post_type": cc.OUTSIDE_POST_TYPE,
           "state": "scheduled", "go_live_date": "2026-10-29", "title": "Instagram story",
           "primary_channel": "tiktok", "channels_picked": ["tiktok"]}
    row.update(over)
    return row


def record(media_kind="story", channel="instagram"):
    return {"post_type": cc.OUTSIDE_POST_TYPE, "media_kind": media_kind, "channel": channel,
            "primary_channel": channel, "permalink": "https://www.instagram.com/stories/stick.paarl/1"}


def slots(row, rec):
    return dt.slots_of(cc.post_entry(cc._with_record_fields(row, rec), "stick"))


def test_a_phone_story_counts_as_a_story_after_the_row_builder():
    assert slots(built_row(), record()) == ["ig_story"]


def test_the_records_own_platform_wins_over_the_builders_guess():
    assert slots(built_row(), record(media_kind="feed", channel="instagram")) == ["ig_feed"]
    assert slots(built_row(), record(media_kind="story", channel="facebook")) == ["fb_story"]


def test_an_outside_google_post_fills_the_google_slot():
    assert slots(built_row(), record(media_kind="feed", channel="gbp")) == ["google"]


def test_posts_campaign_os_made_keep_the_builders_channels():
    row = {"calendar_id": "stick:p1", "post_type": "product-arrival", "state": "scheduled",
           "go_live_date": "2026-10-29", "channels_picked": ["instagram", "facebook"]}
    rec = {"post_type": "product-arrival", "channel": "tiktok", "media_kind": "story"}
    assert slots(row, rec) == ["ig_feed", "fb_feed"]
