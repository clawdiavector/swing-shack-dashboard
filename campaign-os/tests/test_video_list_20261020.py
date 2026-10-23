"""Video list: Drive Video/ folders by stage, name parts and captions (2026-10-20)."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PORT", "0")

from _lib import video_list as vl  # noqa: E402

READY = "2026-10-19__new-year-offer__reel-9x16__v1"
LISTING = [
    {"id": "r1", "name": "2026-10-18__bays__swing-slow-motion__01.mp4", "mime": "video/mp4", "folder": "Video/1-raw"},
    {"id": "v1", "name": READY + ".mp4", "mime": "video/mp4", "folder": "Video/2-ready-to-publish"},
    {"id": "t1", "name": READY + ".txt", "mime": "text/plain", "folder": "Video/2-ready-to-publish"},
    {"id": "v2", "name": "IMG_0001.mov", "mime": "video/quicktime", "folder": "Video/2-ready-to-publish"},
    {"id": "p1", "name": "2026-10-01__launch__feed-4x5__v2.mp4", "mime": "video/mp4", "folder": "Video/3-published"},
    {"id": "i1", "name": "1.jpg", "mime": "image/jpeg", "folder": "Products"},
    {"id": "x1", "name": "old.mp4", "mime": "video/mp4", "folder": "Other"},
]


class NameTests(unittest.TestCase):
    def test_ready_and_raw_names_are_read(self):
        a = vl.parse_name(READY + ".mp4")
        self.assertEqual((a["date"], a["topic"], a["format"], a["version"], a["follows_rules"]),
                         ("2026-10-19", "new-year-offer", "reel-9x16", "v1", True))
        b = vl.parse_name("2026-10-18__bays__swing-slow-motion__01.mp4")
        self.assertEqual((b["what"], b["number"], b["follows_rules"]), ("swing-slow-motion", "01", True))

    def test_other_names_are_flagged(self):
        for n in ("IMG_0001.mov", "2026-10-19__topic__reel-9x16.mp4", "2026-13-40__a__b__01.mp4",
                  "2026-10-19__a__nonsense__v1.mp4"):
            self.assertFalse(vl.parse_name(n)["follows_rules"], n)

    def test_stage_of_only_knows_the_three_video_folders(self):
        self.assertEqual(vl.stage_of("Video/2-ready-to-publish"), "2-ready-to-publish")
        self.assertIsNone(vl.stage_of("Video"))
        self.assertIsNone(vl.stage_of("Products"))
        self.assertIsNone(vl.stage_of("Video/other"))


class BuildTests(unittest.TestCase):
    def test_videos_group_by_stage_with_captions_for_ready_and_published_only(self):
        read = mock.Mock(side_effect=lambda fid: {"t1": "Happy new year from Stick."}.get(fid))
        out = vl.build(LISTING, read)
        by = {s["stage"]: s["videos"] for s in out["stages"]}
        self.assertEqual([len(by[k]) for k in ("1-raw", "2-ready-to-publish", "3-published")], [1, 2, 1])
        ready = {v["name"]: v for v in by["2-ready-to-publish"]}
        self.assertEqual(ready[READY + ".mp4"]["caption"], "Happy new year from Stick.")
        self.assertTrue(ready[READY + ".mp4"]["has_caption_file"])
        self.assertFalse(ready["IMG_0001.mov"]["has_caption_file"])
        self.assertIsNone(ready["IMG_0001.mov"]["caption"])
        self.assertEqual(ready[READY + ".mp4"]["url"], "https://drive.google.com/file/d/v1/view")
        read.assert_called_once_with("t1")  # raw and caption-less videos read nothing

    def test_images_and_files_outside_video_are_ignored(self):
        out = vl.build(LISTING, lambda fid: None)
        names = [v["name"] for s in out["stages"] for v in s["videos"]]
        self.assertNotIn("1.jpg", names)
        self.assertNotIn("old.mp4", names)

    def test_empty_caption_file_reads_as_no_caption_text(self):
        out = vl.build(LISTING, lambda fid: "")
        v = [x for s in out["stages"] for x in s["videos"] if x["name"] == READY + ".mp4"][0]
        self.assertTrue(v["has_caption_file"])
        self.assertIsNone(v["caption"])


class RouteTests(unittest.TestCase):
    def setUp(self):
        from app import app as flask_app
        import app as appmod
        appmod._VIDEO_LIST_CACHE.clear()
        self.appmod = appmod
        self.patches = [mock.patch("app._is_authed", lambda: True)]
        for p in self.patches:
            p.start()
        self.client = flask_app.test_client()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.appmod._VIDEO_LIST_CACHE.clear()

    def test_route_lists_videos_and_caches_the_drive_crawl(self):
        from _lib import google_drive as gd
        with mock.patch.object(gd, "list_public_folder", return_value=LISTING) as crawl, \
                mock.patch.object(self.appmod, "_drive_text", lambda fid: "caption " + fid):
            r = self.client.get("/api/photos/videos?brand_id=stick").get_json()
            self.client.get("/api/photos/videos?brand_id=stick")
            self.assertEqual(crawl.call_count, 1)
            self.client.get("/api/photos/videos?brand_id=stick&refresh=1")
            self.assertEqual(crawl.call_count, 2)
        self.assertTrue(r["ok"])
        self.assertEqual([s["label"] for s in r["stages"]], ["Raw", "Ready to publish", "Published"])

    def test_brand_login_and_drive_errors(self):
        from _lib import google_drive as gd
        self.assertEqual(self.client.get("/api/photos/videos").status_code, 400)
        with mock.patch.object(gd, "list_public_folder", side_effect=RuntimeError("down")):
            r = self.client.get("/api/photos/videos?brand_id=stick")
        self.assertEqual(r.status_code, 502)
        self.assertIn("Could not read Drive", r.get_json()["error"])
        with mock.patch("app._is_authed", lambda: False):
            self.assertEqual(self.client.get("/api/photos/videos?brand_id=stick").status_code, 401)

    def test_brand_without_a_drive_folder_says_so(self):
        r = self.client.get("/api/photos/videos?brand_id=takomo")
        self.assertIn(r.status_code, (400,))


if __name__ == "__main__":
    unittest.main()
