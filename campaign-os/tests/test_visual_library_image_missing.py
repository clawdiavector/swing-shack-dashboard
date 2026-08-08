"""Regression test for the visual_library 'image_missing' flag.

When a DNA record is shipped under one brand (e.g. swing-shack) but the
underlying .png/.jpg file is NOT on disk under any brand directory (Railway
volume state - raw images are gitignored), the API should flag the entry
with image_missing=true and null out `url` so the front-end skips the
doomed 404 network request and renders the DNA-coloured placeholder.
"""
import os, sys, unittest, shutil, tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "campaign-os"))

from app import app, BUNDLED_DATA_DIR  # noqa: E402
from itsdangerous import URLSafeTimedSerializer  # noqa: E402

SESSION_SECRET = "campaign-os-dev-secret-change-me"


class VisualLibraryImageMissingTests(unittest.TestCase):
    """Verify the image_missing flag is set correctly based on disk state."""

    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        s = URLSafeTimedSerializer(SESSION_SECRET)
        self.client.set_cookie("cos_session", s.dumps({"v": 1}))
        self._takomo_png = Path(BUNDLED_DATA_DIR) / "brand-directory" / "takomo" / "images" / "takomo.png"
        self._backup = None
        if self._takomo_png.exists():
            self._backup = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            shutil.copy2(self._takomo_png, self._backup.name)

    def tearDown(self):
        if self._backup is not None:
            shutil.copy2(self._backup.name, self._takomo_png)
            os.unlink(self._backup.name)

    def _fetch_swing_shack(self):
        resp = self.client.get("/api/visual-library/swing-shack/images")
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()

    def _takomo_entry(self, payload):
        for img in payload.get("images", []):
            if img.get("filename") == "takomo.png":
                return img
        return None

    def test_local_disk_present_url_populated(self):
        if not self._takomo_png.exists():
            self.skipTest("takomo.png not present on disk to test the happy path")
        payload = self._fetch_swing_shack()
        entry = self._takomo_entry(payload)
        self.assertIsNotNone(entry)
        self.assertFalse(entry.get("image_missing"))
        self.assertTrue(entry.get("url"))

    def test_railway_like_state_url_null_and_flag_true(self):
        bd = Path(BUNDLED_DATA_DIR) / "brand-directory"
        removed = []
        for brand_dir in bd.iterdir():
            cand = brand_dir / "images" / "takomo.png"
            if cand.exists():
                removed.append(cand)
                cand.unlink()
        try:
            payload = self._fetch_swing_shack()
            entry = self._takomo_entry(payload)
            self.assertIsNotNone(entry)
            self.assertTrue(entry.get("image_missing"))
            self.assertIsNone(entry.get("url"))
        finally:
            for cand in removed:
                if self._backup is not None:
                    shutil.copy2(self._backup.name, cand)

    def test_other_images_unaffected(self):
        bd = Path(BUNDLED_DATA_DIR) / "brand-directory"
        removed = []
        for brand_dir in bd.iterdir():
            cand = brand_dir / "images" / "takomo.png"
            if cand.exists():
                removed.append(cand)
                cand.unlink()
        try:
            payload = self._fetch_swing_shack()
            images = payload.get("images", [])
            takomo = [i for i in images if i.get("filename") == "takomo.png"]
            others = [i for i in images if i.get("filename") != "takomo.png"]
            self.assertEqual(len(takomo), 1)
            self.assertTrue(takomo[0].get("image_missing"))
            healthy = [i for i in others if not i.get("image_missing")]
            self.assertGreater(len(healthy), 0.9 * len(others))
        finally:
            for cand in removed:
                if self._backup is not None:
                    shutil.copy2(self._backup.name, cand)


if __name__ == "__main__":
    unittest.main()
