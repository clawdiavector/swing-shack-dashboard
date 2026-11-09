"""Live-disk photos reach the Visual Library grid as small previews, not full files.

200 Shot List photos are about 630 MB at full size. /brand-images/<brand>/<path>?w=N
returns a cached JPEG no wider than N, and the grid entry points at it.
"""
import io
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import quote

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "campaign-os"))

import app as app_module  # noqa: E402
from itsdangerous import URLSafeTimedSerializer  # noqa: E402

SESSION_SECRET = "campaign-os-dev-secret-change-me"
BRAND = "zz-live-thumb-brand"
PHOTO = "Shot List/IMG 0002.jpg"


class LiveThumbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        img = self.tmp / "brand-directory" / BRAND / "images" / PHOTO
        img.parent.mkdir(parents=True)
        Image.new("RGB", (2000, 1500), (0, 61, 84)).save(img, "JPEG")
        img.with_name(img.stem + ".visual-dna.json").write_text("{}", encoding="utf-8")
        patcher = mock.patch.object(app_module, "DATA_DIR", str(self.tmp))
        patcher.start()
        self.addCleanup(patcher.stop)
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self.client.set_cookie("cos_session", URLSafeTimedSerializer(SESSION_SECRET).dumps({"v": 1}))

    def test_w_returns_a_small_jpeg(self):
        resp = self.client.get(f"/brand-images/{BRAND}/{quote(PHOTO)}?w=400")
        self.assertEqual(resp.status_code, 200)
        im = Image.open(io.BytesIO(resp.data))
        self.assertEqual(im.format, "JPEG")
        self.assertEqual(im.size, (400, 300))

    def test_without_w_the_original_is_served(self):
        resp = self.client.get(f"/brand-images/{BRAND}/{quote(PHOTO)}")
        self.assertEqual(Image.open(io.BytesIO(resp.data)).size, (2000, 1500))

    def test_grid_entry_uses_the_small_preview(self):
        resp = self.client.get(f"/api/visual-library/{BRAND}/images")
        entry = {i["filename"]: i for i in resp.get_json()["images"]}[PHOTO]
        self.assertEqual(entry["url"], f"/brand-images/{BRAND}/{quote(PHOTO)}")
        self.assertEqual(entry["thumbnail_data_url"], f"/brand-images/{BRAND}/{quote(PHOTO)}?w=480")


if __name__ == "__main__":
    unittest.main()
