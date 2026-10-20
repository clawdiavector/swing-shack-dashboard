"""Mark posted moves a video to Published; Edit caption changes the caption file; both through the Drive bridge (2026-10-20)."""
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

from _lib import drive_bridge as db  # noqa: E402

READY = "2026-10-19__new-year-offer__reel-9x16__v1"
LISTING = [
    {"id": "v1abcdefghijkl", "name": READY + ".mp4", "mime": "video/mp4", "folder": "Video/2-ready-to-publish"},
    {"id": "t1", "name": READY + ".txt", "mime": "text/plain", "folder": "Video/2-ready-to-publish"},
    {"id": "v2abcdefghijkl", "name": "2026-10-19__no-caption__reel-9x16__v1.mp4", "mime": "video/mp4", "folder": "Video/2-ready-to-publish"},
    {"id": "raw1", "name": "2026-10-18__bays__swing__01.mp4", "mime": "video/mp4", "folder": "Video/1-raw"},
    {"id": "pub1", "name": "2026-10-01__launch__feed-4x5__v2.mp4", "mime": "video/mp4", "folder": "Video/3-published"},
]
SAST = dt.timezone(dt.timedelta(hours=2))


class FakeResp:
    def __init__(self, data=None, bad=False):
        self._data, self._bad = data, bad

    def json(self):
        if self._bad:
            raise ValueError("html")
        return self._data


class BridgeClientTests(unittest.TestCase):
    def test_refuses_when_not_set_up(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DRIVE_BRIDGE_URL", None)
            os.environ.pop("DRIVE_BRIDGE_TOKEN", None)
            self.assertFalse(db.configured())
            with self.assertRaises(db.BridgeError):
                db.move_file("stick", "f1", "Video/3-published")

    def test_sends_the_token_brand_and_action_and_reads_the_answer(self):
        env = {"DRIVE_BRIDGE_URL": "https://script.example/exec", "DRIVE_BRIDGE_TOKEN": "sekret"}
        with mock.patch.dict(os.environ, env), \
                mock.patch("requests.post", return_value=FakeResp({"ok": True, "id": "f1"})) as post:
            out = db.move_file("swing-shack", "f1", "Video/3-published")
        self.assertTrue(out["ok"])
        body = post.call_args.kwargs["json"]
        self.assertEqual((body["token"], body["brand"], body["action"], body["dest_path"]),
                         ("sekret", "swing-shack", "move", "Video/3-published"))
        self.assertTrue(post.call_args.kwargs["allow_redirects"])

    def test_refusals_and_odd_answers_become_plain_errors(self):
        env = {"DRIVE_BRIDGE_URL": "https://script.example/exec", "DRIVE_BRIDGE_TOKEN": "sekret"}
        with mock.patch.dict(os.environ, env):
            with mock.patch("requests.post", return_value=FakeResp({"ok": False, "error": "folder not found: Video/3-published"})):
                with self.assertRaisesRegex(db.BridgeError, "folder not found"):
                    db.move_file("stick", "f1", "Video/3-published")
            with mock.patch("requests.post", return_value=FakeResp(bad=True)):
                with self.assertRaisesRegex(db.BridgeError, "unexpected"):
                    db.set_text("stick", "f1", "hi")


class RouteTests(unittest.TestCase):
    def setUp(self):
        import app as appmod
        from app import app as flask_app
        from _lib import marketing_calendar as mc
        appmod._VIDEO_LIST_CACHE.clear()
        tmp = Path(tempfile.mkdtemp(prefix="cos-videoposted-"))
        (tmp / "intelligence" / "marketing-calendar").mkdir(parents=True)
        self.appmod, self.mc = appmod, mc
        self.env = mock.patch.dict(os.environ, {"DRIVE_BRIDGE_URL": "https://script.example/exec", "DRIVE_BRIDGE_TOKEN": "t"})
        self.env.start()
        self.patches = [
            mock.patch("app._is_authed", lambda: True),
            mock.patch.object(appmod, "_drive_listing", lambda brand: LISTING),
            mock.patch.object(appmod, "_drive_text", lambda fid: "Happy new year." if fid == "t1" else None),
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
        self.env.stop()

    def post(self, path, **body):
        return self.client.post("/api/photos/videos/" + path, json={"brand_id": "swing-shack", **body})

    def book_video_moment(self):
        self.mc.upsert_event("swing-shack", {
            "event_key": "swing-shack:video-v1abcdefghij", "brand_id": "swing-shack", "type": "moment",
            "status": "approved", "title": "Video 09:00: new year offer", "event_date": self.day,
            "event_start": self.day, "event_end": self.day, "source_type": "operator",
            "source_origin": "internal_strategy", "created_by": "operator", "primary_channel": "instagram",
            "lane": "human", "postiz_mode": "schedule", "caption": "Happy new year."})

    # ---- Mark posted ----
    def test_mark_posted_moves_the_video_and_its_caption_and_marks_the_moment_posted(self):
        self.book_video_moment()
        with mock.patch.object(db, "move_file", return_value={"ok": True}) as move:
            r = self.post("posted", file_id="v1abcdefghijkl")
        out = r.get_json()
        self.assertEqual(r.status_code, 200, out)
        self.assertEqual([c.args for c in move.call_args_list],
                         [("swing-shack", "v1abcdefghijkl", "Video/3-published"), ("swing-shack", "t1", "Video/3-published")])
        self.assertEqual(out["moved"], [READY + ".mp4", READY + ".txt"])
        self.assertIsNone(out["calendar_error"], out)
        month = self.client.get("/api/planning/swing-shack/month?month=" + self.day[:7]).get_json()
        self.assertEqual({it["title"]: it["status"] for it in month["days"][self.day]}["Video posted: new year offer"], "POSTED")
        self.assertNotIn("Video posted: new year offer", [a["name"] for a in self.appmod._alerts_for_brand("swing-shack")])

    def test_mark_posted_without_a_caption_file_moves_just_the_video(self):
        with mock.patch.object(db, "move_file", return_value={"ok": True}) as move:
            r = self.post("posted", file_id="v2abcdefghijkl")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(move.call_count, 1)

    def test_mark_posted_refusals(self):
        with mock.patch.object(db, "move_file", return_value={"ok": True}) as move:
            self.assertEqual(self.post("posted", file_id="raw1").status_code, 404)      # raw is not ready
            self.assertEqual(self.post("posted", file_id="pub1").status_code, 404)      # already published
            self.assertEqual(self.post("posted", file_id="nope").status_code, 404)
            move.assert_not_called()
        with mock.patch.dict(os.environ, {"DRIVE_BRIDGE_URL": ""}):
            r = self.post("posted", file_id="v1abcdefghijkl")
        self.assertEqual(r.status_code, 409)
        self.assertIn("bridge", r.get_json()["error"])
        with mock.patch("app._is_authed", lambda: False):
            self.assertEqual(self.post("posted", file_id="v1abcdefghijkl").status_code, 401)
        self.assertEqual(self.client.post("/api/photos/videos/posted", json={"file_id": "x"}).status_code, 400)

    def test_a_bridge_failure_says_what_moved(self):
        calls = {"n": 0}

        def flaky(brand, fid, dest):
            calls["n"] += 1
            if calls["n"] == 2:
                raise db.BridgeError("folder not found: Video/3-published")
            return {"ok": True}

        with mock.patch.object(db, "move_file", flaky):
            r = self.post("posted", file_id="v1abcdefghijkl")
        out = r.get_json()
        self.assertEqual(r.status_code, 502)
        self.assertEqual(out["moved"], [READY + ".mp4"])

    # ---- Edit caption ----
    def test_edit_caption_changes_the_existing_file(self):
        with mock.patch.object(db, "set_text", return_value={"ok": True}) as st:
            r = self.post("caption", file_id="v1abcdefghijkl", caption="  New year, new swing.  ")
        self.assertEqual(r.status_code, 200, r.get_json())
        st.assert_called_once_with("swing-shack", "t1", "New year, new swing.")
        self.assertFalse(r.get_json()["created"])

    def test_edit_caption_creates_the_file_when_there_is_none(self):
        with mock.patch.object(db, "create_text", return_value={"ok": True}) as ct:
            r = self.post("caption", file_id="v2abcdefghijkl", caption="Fresh caption")
        self.assertEqual(r.status_code, 200)
        ct.assert_called_once_with("swing-shack", "Video/2-ready-to-publish",
                                   "2026-10-19__no-caption__reel-9x16__v1.txt", "Fresh caption")
        self.assertTrue(r.get_json()["created"])

    def test_edit_caption_refusals(self):
        self.assertEqual(self.post("caption", file_id="v1abcdefghijkl", caption="   ").status_code, 400)
        self.assertEqual(self.post("caption", file_id="v1abcdefghijkl", caption="x" * 2201).status_code, 400)
        self.assertEqual(self.post("caption", file_id="raw1", caption="hi").status_code, 404)
        with mock.patch.object(db, "set_text", side_effect=db.BridgeError("only .txt caption files can be changed")):
            r = self.post("caption", file_id="v1abcdefghijkl", caption="hi")
        self.assertEqual(r.status_code, 502)
        with mock.patch.dict(os.environ, {"DRIVE_BRIDGE_TOKEN": ""}):
            self.assertEqual(self.post("caption", file_id="v1abcdefghijkl", caption="hi").status_code, 409)

    # ---- the list tells the page what it can do ----
    def test_the_list_carries_the_caption_file_and_whether_the_bridge_is_set_up(self):
        r = self.client.get("/api/photos/videos?brand_id=swing-shack").get_json()
        self.assertTrue(r["bridge"])
        ready = {v["name"]: v for s in r["stages"] for v in s["videos"]}
        self.assertEqual(ready[READY + ".mp4"]["caption_file_id"], "t1")
        self.assertIn("/t1/view", ready[READY + ".mp4"]["caption_url"])
        self.assertIsNone(ready["2026-10-19__no-caption__reel-9x16__v1.mp4"]["caption_file_id"])
        with mock.patch.dict(os.environ, {"DRIVE_BRIDGE_URL": ""}):
            self.assertFalse(self.client.get("/api/photos/videos?brand_id=swing-shack").get_json()["bridge"])


if __name__ == "__main__":
    unittest.main()
