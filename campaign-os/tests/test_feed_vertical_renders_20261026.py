"""T6 — story + TikTok + YouTube Shorts 9:16 renders from an approved feed post (2026-10-26)."""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
TOKEN = "test-job-token-not-a-secret"
BRAND = "swing-shack"


def _image(w: int = 1200, h: int = 1200) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (30, 80, 50)).save(buf, format="JPEG")
    return buf.getvalue()


def _day(offset: int = 2) -> str:
    return (datetime.now(ZoneInfo("Africa/Johannesburg")).date() + timedelta(days=offset)).isoformat()


class FeedVerticalRendersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="co-t6-vertical-"))
        cls._prev = {k: os.environ.get(k) for k in ("DATA_DIR", "PUBLISH_SANDBOX_DIR", "COS_JOB_TOKEN")}
        os.environ["DATA_DIR"] = str(cls.tmpdir)
        os.environ["PUBLISH_SANDBOX_DIR"] = str(cls.tmpdir / "publish-sandbox")
        os.environ["COS_JOB_TOKEN"] = TOKEN
        sys.path.insert(0, str(CAMPAIGN_OS))

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        os.environ["DATA_DIR"] = str(self.tmpdir)
        os.environ["PUBLISH_SANDBOX_DIR"] = str(self.tmpdir / "publish-sandbox")
        for child in self.tmpdir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        (self.tmpdir / "campaign-data.json").write_text(json.dumps({"campaigns": {}}))
        for name in list(sys.modules):
            if name.startswith("_lib.") and name != "_lib":
                del sys.modules[name]
        from _lib import publish_sandbox

        publish_sandbox.ensure_sandbox_layout()

    def test_fit_vertical_channels_are_9_16(self):
        from _lib.feed_vertical_renders import fit_for_channel_png
        from PIL import Image

        for channel in ("instagram_story", "tiktok", "youtube_shorts"):
            png, _note = fit_for_channel_png(_image(), channel)
            with Image.open(io.BytesIO(png)) as im:
                self.assertEqual(im.size, (1080, 1920), channel)

    def test_vertical_keeps_whole_feed_image(self):
        """4:5 post on 9:16: blurred fill, no crop, so edge pixels survive."""
        from _lib.feed_vertical_renders import fit_for_channel_png
        from PIL import Image

        src = Image.new("RGB", (1080, 1350), (240, 240, 240))
        for y in range(1350):
            src.putpixel((0, y), (255, 0, 0))
            src.putpixel((1079, y), (0, 0, 255))
        buf = io.BytesIO()
        src.save(buf, format="PNG")
        png, note = fit_for_channel_png(buf.getvalue(), "tiktok")
        self.assertIsNone(note)
        with Image.open(io.BytesIO(png)) as im:
            self.assertEqual(im.size, (1080, 1920))
            mid = 1920 // 2
            self.assertEqual(im.getpixel((0, mid))[0] > 200 and im.getpixel((0, mid))[2] < 60, True)
            self.assertEqual(im.getpixel((1079, mid))[2] > 200 and im.getpixel((1079, mid))[0] < 60, True)
            # the band above the post is the darkened fill, not the post itself
            self.assertLess(sum(im.getpixel((540, 40))), 3 * 200)

    def test_lodge_pass_through_adds_vertical_composed_urls(self):
        import app as app_module

        app_module.DATA_DIR = str(self.tmpdir)
        app_module.COS_JOB_TOKEN = TOKEN
        client = app_module.app.test_client(cos_anon=True)
        auth = {"Authorization": f"Bearer {TOKEN}", "X-Actor-Display-Name": "test"}
        body = {
            "brand": BRAND,
            "slug": "t6-vertical",
            "date": _day(),
            "caption": "Feed post with vertical companions",
            "image_base64": base64.b64encode(_image()).decode(),
            "channels": ["instagram", "facebook"],
            "created_by": "test",
        }
        r = client.post("/api/posts/lodge", json=body, headers=auth)
        self.assertEqual(r.status_code, 200, r.get_json())
        doc = r.get_json()
        images = doc.get("images") or {}
        for key in ("instagram", "instagram_story", "tiktok", "youtube_shorts"):
            self.assertIn(key, images, images)
        from _lib import unified_inbox
        from PIL import Image

        st = unified_inbox.post_state_for(BRAND, doc["calendar_id"])
        vertical = st.get("vertical_renders") or []
        self.assertEqual(len(vertical), 3)
        png = self.tmpdir / "draft-assets" / "images" / BRAND / "composed-t6-vertical-instagram_story.png"
        self.assertTrue(png.is_file())
        with Image.open(png) as im:
            self.assertEqual(im.size, (1080, 1920))

    def test_composed_url_for_youtube_uses_shorts_asset(self):
        from _lib.publish_sandbox import _composed_url_for_platform

        composed = {
            "instagram": "/brand-images/swing-shack/feed.png",
            "youtube_shorts": "/brand-images/swing-shack/shorts.png",
        }
        url = _composed_url_for_platform(platform="youtube", asset={"composed": composed}, sidecar=None)
        self.assertEqual(url, "/brand-images/swing-shack/shorts.png")


if __name__ == "__main__":
    unittest.main()
