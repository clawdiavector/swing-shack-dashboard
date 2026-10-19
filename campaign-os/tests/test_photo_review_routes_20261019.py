"""Product photo review routes: list what is waiting, approve and reject, brand required (2026-10-19)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PORT", "0")

from app import app as flask_app  # noqa: E402
from _lib import photo_map as pm  # noqa: E402


class PhotoReviewRouteTests(unittest.TestCase):
    def setUp(self):
        self.map_file = Path(tempfile.mkdtemp(prefix="cos-photo-review-")) / "photo-map.json"
        self.patches = [
            mock.patch.object(pm, "_map_path", lambda brand: self.map_file),
            mock.patch("app._is_authed", lambda: True),
        ]
        for p in self.patches:
            p.start()
        pm.add_entry("stick", "Products/TS001__front.jpg", "TS001", "Takomo SF002 wedge", "front")
        pm.add_entry("stick", "Products/OAR001__front.heic", "OAR001", "Odyssey Ai-One Rossie", "front")
        self.client = flask_app.test_client()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_list_returns_waiting_photos_with_urls_and_counts(self):
        r = self.client.get("/api/photos/review?brand_id=stick&status=needs-check").get_json()
        self.assertTrue(r["ok"])
        self.assertEqual(r["counts"]["needs-check"], 2)
        urls = {e["file"]: e["image_url"] for e in r["entries"]}
        self.assertEqual(urls["Products/TS001__front.jpg"], "/brand-images/stick/Products/TS001__front.jpg")

    def test_approve_then_reject_then_back(self):
        for status in ("approved", "rejected", "needs-check"):
            r = self.client.post("/api/photos/review", json={
                "brand_id": "stick", "file": "Products/TS001__front.jpg", "status": status})
            self.assertEqual(r.status_code, 200)
            e = [x for x in pm.load("stick") if x["sku"] == "TS001"][0]
            self.assertEqual((e["status"], e["reviewed_by"]), (status, "dashboard"))

    def test_approved_photo_counts_for_the_planner(self):
        self.client.post("/api/photos/review", json={
            "brand_id": "stick", "file": "Products/TS001__front.jpg", "status": "approved"})
        self.assertEqual(pm.status_for(pm.load("stick"), ["TS001"]), "approved")

    def test_brand_is_required_and_must_exist(self):
        self.assertEqual(self.client.get("/api/photos/review").status_code, 400)
        self.assertEqual(self.client.get("/api/photos/review?brand_id=../x").status_code, 400)
        self.assertEqual(self.client.get("/api/photos/review?brand_id=no-such-brand").status_code, 400)

    def test_bad_status_and_unknown_file_are_refused(self):
        r = self.client.post("/api/photos/review", json={"brand_id": "stick", "file": "a.jpg", "status": "maybe"})
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/photos/review", json={"brand_id": "stick", "file": "nope.jpg", "status": "approved"})
        self.assertEqual(r.status_code, 404)

    def test_scan_attaches_sku_named_files_from_the_volume(self):
        from _lib import stock_pulse as sp
        imgs = Path(tempfile.mkdtemp(prefix="cos-photo-scan-"))
        (imgs / "Products").mkdir()
        (imgs / "Products" / "ZZ001__front.jpg").write_bytes(b"x")
        (imgs / "Products" / "NOPE9__front.jpg").write_bytes(b"x")
        csv = ("Location,Product Name,Variant Choices,SKU,Movement Type,Quantity,Alert Level\n"
               ",Takomo Zed wedge,,ZZ001,,7,2\n")
        snaps = [{"date": "2026-10-19", "rows": sp.parse_stock_csv(csv)}]
        with mock.patch.object(sp, "load_snapshots", lambda b: snaps),                 mock.patch.object(pm, "images_dir", lambda b: imgs):
            r = self.client.post("/api/photos/scan", json={"brand_id": "stick"}).get_json()
        self.assertEqual((r["ok"], r["added"]), (True, 1))
        self.assertEqual(r["unknown"], ["Products/NOPE9__front.jpg"])
        e = [x for x in pm.load("stick") if x["sku"] == "ZZ001"][0]
        self.assertEqual((e["file"], e["status"]), ("Products/ZZ001__front.jpg", "needs-check"))

    def test_scan_without_a_stock_list_says_so(self):
        from _lib import stock_pulse as sp
        with mock.patch.object(sp, "load_snapshots", lambda b: []):
            r = self.client.post("/api/photos/scan", json={"brand_id": "stick"})
        self.assertEqual(r.status_code, 409)

    def test_login_required(self):
        with mock.patch("app._is_authed", lambda: False):
            self.assertEqual(self.client.get("/api/photos/review?brand_id=stick").status_code, 401)
            r = self.client.post("/api/photos/review", json={"brand_id": "stick", "file": "x", "status": "approved"})
            self.assertEqual(r.status_code, 401)
            self.assertEqual(self.client.post("/api/photos/scan", json={"brand_id": "stick"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
