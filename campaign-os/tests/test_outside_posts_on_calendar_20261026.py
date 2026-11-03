"""T9: posts made outside Campaign OS appear on the Plan month grid (2026-10-26)."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PORT", "0")

from _lib import outside_posts_sync as ops  # noqa: E402


class MatchLogicTests(unittest.TestCase):
    def test_postiz_id_wins_before_time_and_caption(self):
        idx = ops.MatchIndex(
            postiz_ids={"pz-99"},
            media_ids=set(),
            timed_captions=[],
        )
        obs = ops.ObservedPost(
            platform="instagram",
            kind="feed",
            external_id="111",
            published_at="2026-10-26T10:00:00+00:00",
            caption="Hello world",
            permalink="https://instagram.com/p/x/",
            thumbnail_url="https://cdn.example/thumb.jpg",
            postiz_post_id="pz-99",
        )
        self.assertTrue(ops.matches_campaign_os(obs, idx))

    def test_time_and_caption_match_within_thirty_minutes(self):
        when = dt.datetime(2026, 10, 26, 12, 0, tzinfo=dt.timezone.utc)
        idx = ops.MatchIndex(
            postiz_ids=set(),
            media_ids=set(),
            timed_captions=[(when, ops.normalize_caption("Same caption here"))],
        )
        obs = ops.ObservedPost(
            platform="instagram",
            kind="story",
            external_id="st-1",
            published_at="2026-10-26T12:20:00+00:00",
            caption="Same caption here",
            permalink="https://instagram.com/stories/x/",
            thumbnail_url="",
            postiz_post_id=None,
        )
        self.assertTrue(ops.matches_campaign_os(obs, idx))

    def test_outside_story_becomes_one_calendar_row(self):
        tmp = Path(tempfile.mkdtemp(prefix="cos-outside-cal-"))
        cal = tmp / "intelligence" / "marketing-calendar"
        cal.mkdir(parents=True)
        obs = ops.ObservedPost(
            platform="instagram",
            kind="story",
            external_id="17841400000000001",
            published_at="2026-10-26T08:15:00+00:00",
            caption="Morning story from the shop",
            permalink="https://www.instagram.com/stories/swing_shack/123/",
            thumbnail_url="https://cdn.example/story.jpg",
            postiz_post_id=None,
        )
        import _lib.marketing_calendar as mc

        with mock.patch.object(mc, "_CALENDAR_DIR", cal):
            first = ops.upsert_outside_calendar_item("swing-shack", obs)
            second = ops.upsert_outside_calendar_item("swing-shack", obs)
        self.assertEqual(first["action"], "created")
        self.assertIn(second["action"], ("noop", "updated"))
        lines = [json.loads(ln) for ln in (cal / "swing-shack.jsonl").read_text().splitlines() if ln.strip()]
        keys = {r.get("event_key") for r in lines}
        self.assertEqual(len(keys), 1)
        rec = lines[-1]
        self.assertEqual(rec.get("post_type"), ops.OUTSIDE_POST_TYPE)
        self.assertEqual(rec.get("status"), "approved")
        self.assertEqual(rec.get("permalink"), obs.permalink)


class PlanningMonthApiTests(unittest.TestCase):
    def setUp(self):
        import app as appmod
        from app import app as flask_app

        self.tmp = Path(tempfile.mkdtemp(prefix="cos-outside-month-"))
        cal = self.tmp / "intelligence" / "marketing-calendar"
        cal.mkdir(parents=True)
        self.cal = cal
        day = "2026-10-26"
        rec = {
            "event_key": "swing-shack:outside-instagram-story-abc",
            "brand_id": "swing-shack",
            "type": "moment",
            "status": "approved",
            "title": "Morning story from the shop",
            "event_date": day,
            "event_start": day,
            "event_end": day,
            "source_origin": "external",
            "source_type": "outside_posts_sync",
            "post_type": ops.OUTSIDE_POST_TYPE,
            "postiz_mode": "posted",
            "permalink": "https://www.instagram.com/stories/swing_shack/abc/",
            "thumbnail_url": "https://cdn.example/story.jpg",
            "outside_label": ops.OUTSIDE_LABEL,
            "lane": "human",
            "channel": "instagram",
            "revision": 1,
            "schema_version": 2,
        }
        import _lib.marketing_calendar as mc

        (cal / "swing-shack.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
        mc._CALENDAR_DIR = cal
        mc._CALENDAR_DIR_READY = True
        self.patches = [
            mock.patch("app._is_authed", lambda: True),
            mock.patch.object(appmod, "_read_planning", lambda _b: {"monthly_themes": [], "active_campaigns": [], "lane_system": []}),
            mock.patch("app._planning_dir", lambda: str(self.tmp / "planning")),
            mock.patch("app._read_important_dates", lambda _y: []),
            mock.patch("app._read_golf_moments", lambda _y: []),
            mock.patch("app._date_is_demo", lambda _d: False),
            mock.patch("app.important_key_dates", lambda _d: []),
            mock.patch("app._derive_default_phases", lambda _e: []),
            mock.patch("app.glob.glob", lambda _p: []),
            mock.patch.object(appmod, "DATA_DIR", str(self.tmp)),
            mock.patch.object(mc, "_CALENDAR_DIR", cal),
        ]
        for p in self.patches:
            p.start()
        self.client = flask_app.test_client()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_month_view_surfaces_outside_post_with_link_and_thumbnail(self):
        r = self.client.get("/api/planning/swing-shack/month?month=2026-10")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True)[:400])
        items = (r.get_json().get("days") or {}).get("2026-10-26") or []
        outside = [it for it in items if it.get("post_type") == ops.OUTSIDE_POST_TYPE]
        self.assertEqual(len(outside), 1, items)
        self.assertEqual(outside[0].get("status"), "POSTED")
        self.assertEqual(outside[0].get("permalink"), "https://www.instagram.com/stories/swing_shack/abc/")
        self.assertEqual(outside[0].get("thumbnail_url"), "https://cdn.example/story.jpg")
        self.assertEqual(outside[0].get("outside_label"), ops.OUTSIDE_LABEL)


class SyncJobTests(unittest.TestCase):
    def test_sync_skips_matched_and_writes_only_outside(self):
        obs = [
            ops.ObservedPost(
                platform="instagram",
                kind="feed",
                external_id="999",
                published_at="2026-10-26T09:00:00+00:00",
                caption="Internal post",
                permalink="https://instagram.com/p/internal/",
                thumbnail_url="",
                postiz_post_id="pz-internal",
            ),
            ops.ObservedPost(
                platform="instagram",
                kind="story",
                external_id="888",
                published_at="2026-10-26T11:00:00+00:00",
                caption="Phone story",
                permalink="https://instagram.com/stories/phone/",
                thumbnail_url="https://cdn.example/s.jpg",
                postiz_post_id=None,
            ),
        ]
        idx = ops.MatchIndex(postiz_ids={"pz-internal"}, media_ids=set(), timed_captions=[])
        tmp = Path(tempfile.mkdtemp(prefix="cos-outside-sync-"))
        cal = tmp / "intelligence" / "marketing-calendar"
        cal.mkdir(parents=True)
        import _lib.marketing_calendar as mc

        with mock.patch.object(ops, "fetch_observed_posts", return_value=obs), mock.patch.object(
            ops, "build_match_index", return_value=idx
        ), mock.patch.object(mc, "_CALENDAR_DIR", cal):
            out = ops.sync_brand("swing-shack", fetch_live=True)
        self.assertTrue(out["ok"])
        self.assertEqual(out["matched"], 1)
        self.assertEqual(out["outside_written"], 1)


if __name__ == "__main__":
    unittest.main()
