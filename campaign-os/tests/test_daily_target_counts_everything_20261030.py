"""Everything that really went out counts towards the 20 a day (Christelle, 2026-10-30).

Stories staff post from a phone, stories queued straight in Postiz and TikToks sent through
Postiz all fill their own slot on the daily target, not the feed slots or nothing at all.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path
from unittest import mock

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import clean_calendar as cc  # noqa: E402
from _lib import daily_target as dt  # noqa: E402
from _lib import outside_posts_sync as ops  # noqa: E402


def outside_row(media_kind="story", channel="instagram", **extra):
    """A calendar record written by outside_posts_sync for a post made outside Campaign OS."""
    row = {
        "calendar_id": f"stick:outside-{channel}-{media_kind}-123",
        "post_type": cc.OUTSIDE_POST_TYPE,
        "state": "scheduled",
        "go_live_date": "2026-10-29",
        "title": "Instagram story",
        "media_kind": media_kind,
        "channel": channel,
        "primary_channel": channel,
        "permalink": "https://www.instagram.com/stories/stick.paarl/1",
    }
    row.update(extra)
    return row


# ── the calendar reads an outside post as what it really was ───────────────


def test_a_phone_story_fills_the_instagram_story_slot():
    e = cc.post_entry(outside_row(), "stick")
    assert e["format"] == "story"
    assert e["channels"] == ["instagram"]
    assert dt.slots_of(e) == ["ig_story"]


def test_an_outside_post_keeps_only_its_own_platform():
    # Records from before this fix carry Instagram and Facebook from the default pick.
    row = outside_row(media_kind="feed", channel="facebook", channels_picked=["instagram", "facebook"])
    e = cc.post_entry(row, "stick")
    assert e["channels"] == ["facebook"]
    assert dt.slots_of(e) == ["fb_feed"]


def test_an_outside_facebook_story_reel_and_tiktok_fill_their_slots():
    assert dt.slots_of(cc.post_entry(outside_row(channel="facebook"), "stick")) == ["fb_story"]
    assert dt.slots_of(cc.post_entry(outside_row(media_kind="reel"), "stick")) == ["reel"]
    assert dt.slots_of(cc.post_entry(outside_row(media_kind="feed", channel="tiktok"), "stick")) == ["tiktok"]


def test_phone_stories_count_as_done_on_their_day():
    entries = [cc.post_entry(outside_row(calendar_id=f"stick:outside-{i}"), "stick") for i in range(3)]
    day = dt.day_progress(entries, dt.target_for("stick"), date(2026, 10, 29), date(2026, 10, 29))["2026-10-29"]
    story = next(s for s in day["slots"] if s["slot"] == "ig_story")
    assert story["done"] == 3
    assert day["done"] == 3


# ── the sync keeps what went out through Postiz ────────────────────────────


def postiz_obs(pid, target="instagram", kind="story", when="2026-10-29T08:00:00+00:00", caption=""):
    return ops.ObservedPost(platform="postiz", kind=kind, external_id=pid, published_at=when,
                            caption=caption, permalink="", thumbnail_url="", postiz_post_id=pid,
                            target=target)


def meta_story(mid, when):
    return ops.ObservedPost(platform="instagram", kind="story", external_id=mid, published_at=when,
                            caption="", permalink=f"https://www.instagram.com/stories/swingshack/{mid}",
                            thumbnail_url="")


def test_a_postiz_row_says_where_it_went_and_what_it_was():
    obs = ops._observed_from_postiz({
        "id": "pz-7", "publishDate": "2026-10-29T08:00:00Z", "content": "<p>Hi</p>",
        "settings": {"post_type": "story"}, "_postiz_provider": "instagram-standalone",
    })
    assert (obs.platform, obs.target, obs.kind) == ("postiz", "instagram", "story")
    tiktok = ops._observed_from_postiz({"id": "pz-8", "publishDate": "2026-10-29T08:00:00Z",
                                        "_postiz_provider": "tiktok-business"})
    assert (tiktok.target, tiktok.kind) == ("tiktok", "feed")


def run_sync(observed, index=None):
    tmp = Path(tempfile.mkdtemp(prefix="cos-count-everything-"))
    cal = tmp / "intelligence" / "marketing-calendar"
    cal.mkdir(parents=True)
    import _lib.marketing_calendar as mc

    index = index or ops.MatchIndex(postiz_ids=set(), media_ids=set(), timed_captions=[])
    with mock.patch.object(ops, "fetch_observed_posts", return_value=observed), mock.patch.object(
        ops, "build_match_index", return_value=index
    ), mock.patch.object(mc, "_CALENDAR_DIR", cal):
        out = ops.sync_brand("swing-shack", fetch_live=True)
        rows = [r for r in mc.latest_revisions(mc.list_records("swing-shack") or [])
                if r.get("post_type") == ops.OUTSIDE_POST_TYPE]
    return out, rows


def test_postiz_stories_and_tiktoks_land_once_and_phone_stories_still_land():
    observed = [
        postiz_obs("pz-story", when="2026-10-29T08:00:00+00:00"),
        # Meta shows the same story Postiz sent, a minute later and with no caption.
        meta_story("ig-from-postiz", "2026-10-29T08:01:00+00:00"),
        postiz_obs("pz-tiktok", target="tiktok", kind="feed", caption="Fitting day"),
        # A story someone posted from the shop phone, nowhere near a Postiz send.
        meta_story("ig-phone", "2026-10-29T13:30:00+00:00"),
    ]
    out, rows = run_sync(observed)
    assert out["ok"]
    assert out["outside_written"] == 3
    got = sorted((r.get("primary_channel"), r.get("media_kind")) for r in rows)
    assert got == [("instagram", "story"), ("instagram", "story"), ("tiktok", "feed")]


def test_a_postiz_send_campaign_os_made_is_not_written_again():
    index = ops.MatchIndex(postiz_ids={"pz-ours"}, media_ids=set(), timed_captions=[])
    out, rows = run_sync([postiz_obs("pz-ours")], index)
    assert out["outside_written"] == 0
    assert rows == []


def test_google_posts_from_postiz_are_left_to_the_google_queue():
    # The approve-once Google queue already shows these on the calendar.
    out, rows = run_sync([postiz_obs("pz-gbp", target="gbp", kind="feed", caption="Open today")])
    assert out["outside_written"] == 0
    assert rows == []
