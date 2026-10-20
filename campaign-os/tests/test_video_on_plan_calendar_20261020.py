"""A video sent to Postiz shows on the Plan month grid, using the real calendar store (2026-10-20)."""
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

from _lib import postiz_client as pz  # noqa: E402

READY = "2026-10-19__new-year-offer__reel-9x16__v1"
LISTING = [
    {"id": "v1abcdefghijkl", "name": READY + ".mp4", "mime": "video/mp4", "folder": "Video/2-ready-to-publish"},
    {"id": "t1", "name": READY + ".txt", "mime": "text/plain", "folder": "Video/2-ready-to-publish"},
]


class VideoOnPlanCalendarTests(unittest.TestCase):
    def setUp(self):
        import app as appmod
        from app import app as flask_app
        from _lib import google_drive as gd
        from _lib import marketing_calendar as mc
        appmod._VIDEO_LIST_CACHE.clear()
        tmp = Path(tempfile.mkdtemp(prefix="cos-videocal-"))
        (tmp / "intelligence" / "marketing-calendar").mkdir(parents=True)
        self.env = mock.patch.dict(os.environ, {"POSTIZ_API_KEY_SWING_SHACK": "own"})
        self.env.start()
        self.patches = [
            mock.patch("app._is_authed", lambda: True),
            mock.patch.object(appmod, "_drive_listing", lambda brand: LISTING),
            mock.patch.object(appmod, "_drive_text", lambda fid: "Happy new year." if fid == "t1" else None),
            mock.patch.object(pz, "list_integrations", return_value=([{"id": "ig1", "name": "Swing Shack", "identifier": "instagram"}], None)),
            mock.patch.object(gd, "download_public_file", lambda fid, dest, **kw: (Path(dest).write_bytes(b"v"), Path(dest))[1]),
            mock.patch.object(pz, "upload_media", return_value=({"id": "m1", "path": "https://x/m.mp4"}, None)),
            mock.patch.object(pz, "create_post", return_value=([{"postId": "pz1"}], None)),
            mock.patch.object(mc, "_CALENDAR_DIR", tmp / "intelligence" / "marketing-calendar"),
            # The write-gate wants a named person on the request; the page sends one (see the gate test below).
            mock.patch.object(appmod, "_v26_actor_qualified", lambda: True),
        ]
        for p in self.patches:
            p.start()
        self.client = flask_app.test_client()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.env.stop()

    def month_items(self, day):
        month = day[:7]
        r = self.client.get("/api/planning/swing-shack/month?month=" + month)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True)[:300])
        data = r.get_json()
        return [it for it in (data.get("days") or {}).get(day, [])]

    def test_a_scheduled_video_is_a_chip_on_its_day_and_a_draft_says_so(self):
        when = dt.datetime.now(dt.timezone.utc).replace(microsecond=0) + dt.timedelta(days=3)
        iso = when.isoformat().replace("+00:00", "Z")
        r = self.client.post("/api/photos/videos/draft", json={
            "brand_id": "swing-shack", "file_id": "v1abcdefghijkl", "mode": "schedule", "publish_at": iso})
        out = r.get_json()
        self.assertEqual(r.status_code, 200, out)
        self.assertIsNone(out["calendar_error"], out)
        sast = when.astimezone(dt.timezone(dt.timedelta(hours=2)))
        titles = [it["title"] for it in self.month_items(sast.date().isoformat())]
        self.assertIn("Video %s: new year offer" % sast.strftime("%H:%M"), titles)

    def test_without_a_named_person_the_calendar_refuses_but_postiz_keeps_the_post(self):
        with mock.patch.object(__import__("app"), "_v26_actor_qualified", lambda: False):
            r = self.client.post("/api/photos/videos/draft", json={
                "brand_id": "swing-shack", "file_id": "v1abcdefghijkl"})
        out = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(out["calendar_item"])
        self.assertIn("write-gate", out["calendar_error"])

    def test_sending_the_same_video_again_does_not_double_the_chip(self):
        for _ in range(2):
            r = self.client.post("/api/photos/videos/draft", json={
                "brand_id": "swing-shack", "file_id": "v1abcdefghijkl"})
            self.assertEqual(r.status_code, 200)
            self.assertIsNone(r.get_json()["calendar_error"], r.get_json())
        sast = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5)).astimezone(dt.timezone(dt.timedelta(hours=2)))
        titles = [it["title"] for it in self.month_items(sast.date().isoformat())]
        self.assertEqual(titles.count("Video draft: new year offer"), 1)


if __name__ == "__main__":
    unittest.main()
