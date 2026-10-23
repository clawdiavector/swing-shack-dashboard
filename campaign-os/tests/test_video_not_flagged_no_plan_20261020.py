"""A video already in Postiz is not an approved date with no plan, and reads as scheduled (2026-10-20)."""
from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PORT", "0")

SAST = dt.timezone(dt.timedelta(hours=2))


class VideoNoPlanAlertTests(unittest.TestCase):
    def setUp(self):
        import app as appmod
        from app import app as flask_app
        from _lib import marketing_calendar as mc
        tmp = Path(tempfile.mkdtemp(prefix="cos-videoalert-"))
        (tmp / "intelligence" / "marketing-calendar").mkdir(parents=True)
        self.appmod, self.mc = appmod, mc
        self.patches = [
            mock.patch("app._is_authed", lambda: True),
            mock.patch.object(mc, "_CALENDAR_DIR", tmp / "intelligence" / "marketing-calendar"),
            mock.patch.object(appmod, "_v26_actor_qualified", lambda: True),
        ]
        for p in self.patches:
            p.start()
        self.client = flask_app.test_client()
        self.day = (dt.datetime.now(SAST) + dt.timedelta(days=4)).date().isoformat()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def book(self, key, title, **extra):
        rec = {"event_key": "swing-shack:" + key, "brand_id": "swing-shack", "type": "moment",
               "status": "approved", "title": title, "event_date": self.day, "event_start": self.day,
               "event_end": self.day, "source_type": "operator", "source_origin": "internal_strategy",
               "created_by": "operator", "primary_channel": "instagram", "lane": "human", **extra}
        self.mc.upsert_event("swing-shack", rec)

    def alert_names(self):
        return [a["name"] for a in self.appmod._alerts_for_brand("swing-shack")]

    def test_a_plain_approved_date_is_flagged(self):
        self.book("some-date", "Some approved date")
        self.assertIn("Some approved date", self.alert_names())

    def test_a_video_in_postiz_is_not_flagged_as_having_no_plan(self):
        self.book("video-abc", "Video 09:00: test", postiz_mode="schedule", media_kind="video")
        self.assertNotIn("Video 09:00: test", self.alert_names())

    def test_a_postiz_draft_is_not_flagged_either(self):
        self.book("video-def", "Video draft: test", postiz_mode="draft", media_kind="video")
        self.assertNotIn("Video draft: test", self.alert_names())

    def test_a_booked_video_counts_as_content_for_a_date_just_after_it(self):
        self.book("video-ghi", "Video 09:00: test", postiz_mode="schedule")
        later = (dt.datetime.now(SAST) + dt.timedelta(days=9)).date().isoformat()
        rec = {"event_key": "swing-shack:later-date", "brand_id": "swing-shack", "type": "moment", "status": "approved",
               "title": "Later date", "event_date": later, "event_start": later, "event_end": later,
               "source_type": "operator", "source_origin": "internal_strategy", "created_by": "operator",
               "primary_channel": "instagram", "lane": "human"}
        self.mc.upsert_event("swing-shack", rec)
        self.assertNotIn("Later date", self.alert_names())  # video is within 10 days before it

    def test_the_month_grid_marks_it_scheduled_or_draft_and_leaves_others_approved(self):
        self.book("video-abc", "Video 09:00: test", postiz_mode="schedule")
        self.book("video-def", "Video draft: other", postiz_mode="draft")
        self.book("some-date", "Some approved date")
        r = self.client.get("/api/planning/swing-shack/month?month=" + self.day[:7])
        self.assertEqual(r.status_code, 200)
        by_title = {it["title"]: it["status"] for it in r.get_json()["days"][self.day]}
        self.assertEqual(by_title["Video 09:00: test"], "SCHEDULED")
        self.assertEqual(by_title["Video draft: other"], "DRAFT")
        self.assertEqual(by_title["Some approved date"], "APPROVED")


if __name__ == "__main__":
    unittest.main()
