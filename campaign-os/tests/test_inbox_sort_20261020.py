"""Inbox sort: guess what a dropped file is, work out its folder and name, keep the plan (2026-10-20)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PORT", "0")

from _lib import inbox_sort as ib  # noqa: E402

SKUS = {"TS001": "Takomo SF002 wedge", "GDZGS001": "GripDrip Zen Sky"}


class NamingTests(unittest.TestCase):
    def test_facility_name_follows_the_pattern(self):
        r = ib.plan_name([], "IMG_1.jpg", "facility", date="2026-10-19", area="bays", what="Bay 3 evening")
        self.assertEqual(r, {"dest_folder": "Location/bays",
                             "new_name": "2026-10-19__bays__bay-3-evening__01.jpg"})

    def test_numbers_count_up_for_the_same_prefix(self):
        first = ib.plan_name([], "a.jpg", "facility", date="2026-10-19", area="bays", what="bay 3")
        again = ib.plan_name([{"new_name": first["new_name"]}], "b.jpg", "facility",
                             date="2026-10-19", area="bays", what="bay 3")
        self.assertTrue(again["new_name"].endswith("__02.jpg"))

    def test_product_uses_sku_and_view(self):
        r = ib.plan_name([], "IMG_4.JPG", "product", what="Front", sku="TS001", sku_to_product=SKUS)
        self.assertEqual(r, {"dest_folder": "Products", "new_name": "TS001__front.jpg"})

    def test_unknown_sku_is_refused(self):
        with self.assertRaises(ib.SortError):
            ib.plan_name([], "x.jpg", "product", what="front", sku="NOPE", sku_to_product=SKUS)

    def test_video_and_service_destinations(self):
        v = ib.plan_name([], "C0001.MOV", "video", date="2026-10-19", area="New Year Offer", what="swing slow motion")
        self.assertEqual(v["dest_folder"], "Video/1-raw")
        self.assertEqual(v["new_name"], "2026-10-19__new-year-offer__swing-slow-motion__01.mov")
        s = ib.plan_name([], "x.jpg", "service", date="2026-10-19", area="driver fitting", what="launch monitor")
        self.assertEqual(s["dest_folder"], "Services")

    def test_missing_parts_are_refused_in_plain_words(self):
        for kw in ({"area": "bays", "what": "x"},                      # no date
                   {"date": "2026-10-19", "area": "garden", "what": "x"},  # not an area
                   {"date": "2026-10-19", "area": "bays", "what": ""}):    # no description
            with self.assertRaises(ib.SortError):
                ib.plan_name([], "a.jpg", "facility", **kw)


class GuessTests(unittest.TestCase):
    def test_dates_from_camera_and_whatsapp_names(self):
        self.assertEqual(ib.date_from_name("PXL_20261019_083012.jpg"), "2026-10-19")
        self.assertEqual(ib.date_from_name("WhatsApp Image 2026-10-18 at 10.02.jpg"), "2026-10-18")
        self.assertIsNone(ib.date_from_name("IMG_4102.heic"))
        self.assertIsNone(ib.date_from_name("IMG_20261340.jpg"))

    def test_sku_named_file_is_a_product_and_video_is_a_video(self):
        g = ib.guess("ts001__Front.jpg", None, SKUS)
        self.assertEqual((g["kind"], g["sku"], g["view"]), ("product", "TS001", "front"))
        self.assertEqual(ib.guess("C0001.mp4", None, SKUS)["kind"], "video")
        self.assertIsNone(ib.guess("IMG_4102.heic", None, SKUS)["kind"])


class FilesTests(unittest.TestCase):
    def test_inbox_lists_images_on_disk_and_skipped_videos(self):
        root = Path(tempfile.mkdtemp(prefix="cos-inbox-"))
        (root / "Inbox").mkdir()
        (root / "Inbox" / "IMG_1.jpg").write_bytes(b"x")
        (root / "Products").mkdir()
        (root / "Products" / "TS001__front.jpg").write_bytes(b"x")
        manifest = {"images": {"Inbox/IMG_1.jpg": {"drive_id": "abc"}},
                    "skipped": [{"drive_id": "vid", "name": "C0001.mp4", "folder": "Inbox"},
                                {"drive_id": "o", "name": "C0002.mp4", "folder": "Video/1-raw"}]}
        files = {f["file"]: f for f in ib.inbox_files("stick", root, manifest)}
        self.assertEqual(sorted(files), ["Inbox/C0001.mp4", "Inbox/IMG_1.jpg"])
        self.assertEqual(files["Inbox/IMG_1.jpg"]["drive_id"], "abc")


class RouteTests(unittest.TestCase):
    def setUp(self):
        from app import app as flask_app
        from _lib import photo_map as pm
        from _lib import stock_pulse as sp
        tmp = Path(tempfile.mkdtemp(prefix="cos-inbox-route-"))
        (tmp / "images" / "Inbox").mkdir(parents=True)
        (tmp / "images" / "Inbox" / "PXL_20261019_083012.jpg").write_bytes(b"x")
        (tmp / "ingest-manifest.json").write_text(json.dumps(
            {"images": {"Inbox/PXL_20261019_083012.jpg": {"drive_id": "drv1"}}, "skipped": []}))
        self.map_file = tmp / "inbox-map.json"
        self.patches = [
            mock.patch("app._is_authed", lambda: True),
            mock.patch.object(pm, "images_dir", lambda b: tmp / "images"),
            mock.patch.object(sp, "load_snapshots", lambda b: []),
            mock.patch.object(ib, "_map_path", lambda b: self.map_file),
        ]
        for p in self.patches:
            p.start()
        self.client = flask_app.test_client()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_list_guess_plan_and_mark_moved(self):
        r = self.client.get("/api/photos/inbox?brand_id=stick").get_json()
        item = r["items"][0]
        self.assertEqual((item["drive_id"], item["guess"]["date"]), ("drv1", "2026-10-19"))
        body = {"brand_id": "stick", "file": item["file"], "kind": "facility", "date": "2026-10-19",
                "area": "bays", "what": "bay 3"}
        p = self.client.post("/api/photos/inbox", json=body).get_json()
        self.assertEqual(p["plan"]["new_name"], "2026-10-19__bays__bay-3__01.jpg")
        again = self.client.post("/api/photos/inbox", json=body).get_json()
        self.assertEqual(again["plan"]["new_name"], "2026-10-19__bays__bay-3__01.jpg")  # re-planning keeps number
        m = self.client.post("/api/photos/inbox", json={"brand_id": "stick", "file": item["file"], "status": "moved"})
        self.assertEqual(m.status_code, 200)
        self.assertEqual(ib.load("stick")[0]["status"], "moved")

    def test_bad_input_and_unknown_files_and_login(self):
        bad = self.client.post("/api/photos/inbox", json={
            "brand_id": "stick", "file": "Inbox/PXL_20261019_083012.jpg", "kind": "facility", "area": "bays", "what": "x"})
        self.assertEqual(bad.status_code, 400)
        missing = self.client.post("/api/photos/inbox", json={"brand_id": "stick", "file": "Inbox/nope.jpg", "kind": "video"})
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(self.client.get("/api/photos/inbox").status_code, 400)
        with mock.patch("app._is_authed", lambda: False):
            self.assertEqual(self.client.get("/api/photos/inbox?brand_id=stick").status_code, 401)


if __name__ == "__main__":
    unittest.main()
