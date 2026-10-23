"""A ready video can go to Instagram (feed, reel, story), Facebook or YouTube; each its own calendar record (2026-10-20)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PORT", "0")

from _lib import postiz_client as pz  # noqa: E402

REEL = "2026-10-19__new-year-offer__reel-9x16__v1"
STORY = "2026-10-19__new-year-offer__story-9x16__v1"
LISTING = [
    {"id": "v1abcdefghijkl", "name": REEL + ".mp4", "mime": "video/mp4", "folder": "Video/2-ready-to-publish"},
    {"id": "t1", "name": REEL + ".txt", "mime": "text/plain", "folder": "Video/2-ready-to-publish"},
    {"id": "s1abcdefghijkl", "name": STORY + ".mp4", "mime": "video/mp4", "folder": "Video/2-ready-to-publish"},
    {"id": "t2", "name": STORY + ".txt", "mime": "text/plain", "folder": "Video/2-ready-to-publish"},
]
INTEGRATIONS = [
    {"id": "ig1", "name": "Swing Shack", "identifier": "instagram"},
    {"id": "fb1", "name": "Swing Shack", "identifier": "facebook"},
    {"id": "yt1", "name": "Swing Shack", "identifier": "youtube"},
    {"id": "tt1", "name": "SwingShack", "identifier": "tiktok"},
]


class ChannelTests(unittest.TestCase):
    def setUp(self):
        import app as appmod
        from app import app as flask_app
        from _lib import google_drive as gd
        from _lib import marketing_calendar as mc
        appmod._VIDEO_LIST_CACHE.clear()
        tmp = Path(tempfile.mkdtemp(prefix="cos-videochan-"))
        (tmp / "intelligence" / "marketing-calendar").mkdir(parents=True)
        self.appmod, self.mc = appmod, mc
        self.env = mock.patch.dict(os.environ, {"POSTIZ_API_KEY_SWING_SHACK": "own"})
        self.env.start()
        self.patches = [
            mock.patch("app._is_authed", lambda: True),
            mock.patch.object(appmod, "_drive_listing", lambda brand: LISTING),
            mock.patch.object(appmod, "_drive_text", lambda fid: "Happy new year."),
            mock.patch.object(pz, "list_integrations", return_value=(INTEGRATIONS, None)),
            mock.patch.object(gd, "download_public_file", lambda fid, dest, **kw: (Path(dest).write_bytes(b"v"), Path(dest))[1]),
            mock.patch.object(pz, "upload_media", return_value=({"id": "m1", "path": "https://x/m.mp4"}, None)),
            mock.patch.object(mc, "_CALENDAR_DIR", tmp / "intelligence" / "marketing-calendar"),
            mock.patch.object(appmod, "_v26_actor_qualified", lambda: True),
        ]
        for p in self.patches:
            p.start()
        self.create = mock.patch.object(pz, "create_post", return_value=([{"postId": "pz1"}], None))
        self.create_mock = self.create.start()
        self.client = flask_app.test_client()

    def tearDown(self):
        self.create.stop()
        for p in self.patches:
            p.stop()
        self.env.stop()

    def send(self, file_id="v1abcdefghijkl", **extra):
        return self.client.post("/api/photos/videos/draft", json={"brand_id": "swing-shack", "file_id": file_id, **extra})

    def records(self):
        return {r["event_key"]: r for r in self.mc.latest_revisions(self.mc.list_records("swing-shack"))}

    def test_instagram_is_the_default_and_a_story_name_uses_the_story_type(self):
        self.send()
        self.assertEqual(self.create_mock.call_args.args[0], "ig1")
        self.assertEqual(self.create_mock.call_args.kwargs["platform_settings"], {"post_type": "post"})
        self.send(file_id="s1abcdefghijkl")
        self.assertEqual(self.create_mock.call_args.kwargs["platform_settings"], {"post_type": "story"})

    def test_facebook_uses_the_facebook_channel_with_no_instagram_settings(self):
        r = self.send(channel="facebook")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self.create_mock.call_args.args[0], "fb1")
        self.assertEqual(self.create_mock.call_args.kwargs["platform_settings"], {})
        self.assertEqual(r.get_json()["platform"], "Facebook")

    def test_youtube_gets_a_title_and_stays_private(self):
        r = self.send(channel="youtube")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(self.create_mock.call_args.args[0], "yt1")
        self.assertEqual(self.create_mock.call_args.kwargs["platform_settings"],
                         {"title": "New year offer", "type": "private", "tags": []})

    def test_each_channel_is_its_own_calendar_record_and_instagram_keeps_its_key(self):
        self.send()
        self.send(channel="facebook")
        recs = self.records()
        self.assertEqual(sorted(recs), ["swing-shack:video-v1abcdefghij", "swing-shack:video-v1abcdefghij-facebook"])
        self.assertEqual(recs["swing-shack:video-v1abcdefghij-facebook"]["primary_channel"], "facebook")
        self.assertIn("on Facebook", recs["swing-shack:video-v1abcdefghij-facebook"]["title"])
        self.assertNotIn("on ", recs["swing-shack:video-v1abcdefghij"]["title"])

    def test_unknown_or_unconnected_channels_are_refused_before_anything_is_sent(self):
        self.assertEqual(self.send(channel="tiktok").status_code, 400)  # not offered yet
        self.assertEqual(self.send(channel="myspace").status_code, 400)
        with mock.patch.object(pz, "list_integrations", return_value=([INTEGRATIONS[0]], None)):
            r = self.send(channel="facebook")
        self.assertEqual(r.status_code, 409)
        self.assertIn("Facebook", r.get_json()["error"])
        self.create_mock.assert_not_called()

    def test_empty_platform_settings_are_sent_as_given_not_replaced_by_the_default(self):
        with mock.patch.object(pz, "_request", return_value=({}, None)) as req:
            self.create.stop()
            try:
                pz.create_post("fb1", "hi", [], brand_id="swing-shack", platform_settings={}, draft=True)
            finally:
                self.create_mock = self.create.start()
        self.assertEqual(req.call_args.kwargs["json_body"]["posts"][0]["settings"], {})


if __name__ == "__main__":
    unittest.main()
