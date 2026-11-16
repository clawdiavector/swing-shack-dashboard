"""The Visual Library shows photos the Drive ingest scanned onto the live disk.

On Railway the ingest writes each photo and its .visual-dna.json under
DATA_DIR/brand-directory/<brand>/images/<folder>/, but the live
visual-dna-index.json there has no by_filename list. The library only read the
bundled index, so the Stick Shot List (516) and Bag Drop (191) never showed.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "campaign-os"))

import app as app_module  # noqa: E402
from itsdangerous import URLSafeTimedSerializer  # noqa: E402

SESSION_SECRET = "campaign-os-dev-secret-change-me"
NEW_BRAND = "zz-live-only-brand"
STICK_PHOTO = "Shot List/IMG 0001.jpg"
NEW_PHOTO = "webp edits/DS adapt LS 9/bagdrop74.webp"


def _dna(rel):
    return {
        "schema_version": "1",
        "image_path": rel,
        "layer1_metadata": {"orientation": "portrait", "width_px": 800, "height_px": 1000},
        "layer9_palette": {"dominant_colors": [{"hex": "#003d54"}]},
        "layer4_products": {"detected_brands": ["Titleist"]},
        "layer6_ocr": {"lines": ["shotlistword"]},
    }


def _put(root, brand, rel):
    img = root / "brand-directory" / brand / "images" / rel
    img.parent.mkdir(parents=True, exist_ok=True)
    img.write_bytes(b"\xff\xd8\xff\xe0fake")
    dna = img.with_name(img.stem + ".visual-dna.json")
    dna.write_text(json.dumps(_dna(rel)), encoding="utf-8")
    # The live index only has product tags, never by_filename.
    (root / "brand-directory" / brand / "visual-dna-index.json").write_text(
        json.dumps({"by_product": {}, "tagged_count": 1}), encoding="utf-8")


class VisualLibraryLivePhotosTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        _put(self.tmp, "stick", STICK_PHOTO)
        _put(self.tmp, NEW_BRAND, NEW_PHOTO)
        patcher = mock.patch.object(app_module, "DATA_DIR", str(self.tmp))
        patcher.start()
        self.addCleanup(patcher.stop)
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self.client.set_cookie("cos_session", URLSafeTimedSerializer(SESSION_SECRET).dumps({"v": 1}))

    def _images(self, brand):
        resp = self.client.get(f"/api/visual-library/{brand}/images?limit=500")
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True)[:300])
        return {i["filename"]: i for i in resp.get_json()["images"]}

    def test_stick_shot_list_photo_is_in_the_grid(self):
        entry = self._images("stick").get(STICK_PHOTO)
        self.assertIsNotNone(entry)
        self.assertFalse(entry["image_missing"])
        self.assertEqual(entry["url"], f"/brand-images/stick/{quote(STICK_PHOTO)}")
        self.assertEqual(entry["products"], ["Titleist"])

    def test_bundled_stick_photos_still_listed(self):
        bundled = json.loads((Path(app_module.BUNDLED_DATA_DIR) / "brand-directory" / "stick"
                              / "visual-dna-index.json").read_text(encoding="utf-8"))
        names = self._images("stick")
        for fn in bundled.get("by_filename", {}):
            dna = Path(bundled["by_filename"][fn].get("dna_path", ""))
            stem = Path(fn).stem
            if dna.exists() or (Path(app_module.BUNDLED_DATA_DIR) / "brand-directory" / "stick"
                                / "images" / f"{stem}.visual-dna.json").exists():
                self.assertIn(fn, names)

    def test_brand_with_only_live_photos_has_a_library(self):
        self.assertIn(NEW_PHOTO, self._images(NEW_BRAND))

    def test_stats_count_live_photos(self):
        resp = self.client.get(f"/api/visual-library/{NEW_BRAND}/stats")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["total_images"], 1)
        self.assertEqual(body["products"], {"Titleist": 1})

    def test_detail_opens_a_live_photo(self):
        resp = self.client.get(f"/api/visual-library/{NEW_BRAND}/image/{quote(NEW_PHOTO)}")
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True)[:300])
        self.assertEqual(resp.get_json()["filename"], NEW_PHOTO)

    def test_search_finds_a_live_photo(self):
        resp = self.client.get("/api/visual-library/search?q=shotlistword&brand=stick")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(STICK_PHOTO, [r["filename"] for r in resp.get_json()["results"]])

    def test_brands_lists_a_live_only_brand(self):
        resp = self.client.get("/api/visual-library/brands")
        counts = {b["brand"]: b["image_count"] for b in resp.get_json()["brands"]}
        self.assertEqual(counts.get(NEW_BRAND), 1)


if __name__ == "__main__":
    unittest.main()
