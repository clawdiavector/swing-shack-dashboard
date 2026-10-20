"""Send a ready video to Postiz as a DRAFT only, on the brand's own account (2026-10-20)."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PORT", "0")

from _lib import postiz_client as pz  # noqa: E402

READY = "2026-10-19__new-year-offer__reel-9x16__v1"
LISTING = [
    {"id": "v1", "name": READY + ".mp4", "mime": "video/mp4", "folder": "Video/2-ready-to-publish"},
    {"id": "t1", "name": READY + ".txt", "mime": "text/plain", "folder": "Video/2-ready-to-publish"},
    {"id": "v2", "name": "2026-10-19__x__reel-9x16__v1.mp4", "mime": "video/mp4", "folder": "Video/2-ready-to-publish"},
    {"id": "raw", "name": "2026-10-18__bays__swing__01.mp4", "mime": "video/mp4", "folder": "Video/1-raw"},
]
INTEGRATIONS = [{"id": "ig1", "name": "Swing Shack", "identifier": "instagram"},
                {"id": "fb1", "name": "Swing Shack", "identifier": "facebook"}]


class ClientTests(unittest.TestCase):
    def test_draft_flag_sets_the_draft_type_and_default_is_unchanged(self):
        with mock.patch.object(pz, "_request", return_value=({}, None)) as req:
            pz.create_post("ig1", "hi", [], brand_id="swing-shack", draft=True)
            self.assertEqual(req.call_args.kwargs["json_body"]["type"], "draft")
            pz.create_post("ig1", "hi", [], brand_id="swing-shack")
            self.assertEqual(req.call_args.kwargs["json_body"]["type"], "now")
            pz.create_post("ig1", "hi", [], brand_id="swing-shack", publish_date="2026-10-21T08:00:00Z")
            self.assertEqual(req.call_args.kwargs["json_body"]["type"], "schedule")

    def test_brand_key_ignores_the_shared_key(self):
        with mock.patch.dict(os.environ, {"POSTIZ_API_KEY": "shared"}, clear=False):
            os.environ.pop("POSTIZ_API_KEY_SWING_SHACK", None)
            self.assertFalse(pz.has_brand_key("swing-shack"))
            os.environ["POSTIZ_API_KEY_SWING_SHACK"] = "own"
            self.assertTrue(pz.has_brand_key("swing-shack"))
            self.assertFalse(pz.has_brand_key(None))

    def test_upload_sends_the_real_mime_type(self):
        import tempfile
        d = Path(tempfile.mkdtemp(prefix="cos-pz-"))
        f = d / "clip.mp4"
        f.write_bytes(b"x")
        seen = {}

        class Resp:
            def read(self):
                return b'{"id": "m1", "path": "https://x/clip.mp4"}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_open(req, timeout=0):
            seen["body"] = req.data
            return Resp()

        with mock.patch("urllib.request.urlopen", fake_open):
            data, err = pz.upload_media(str(f), brand_id="swing-shack")
        self.assertIsNone(err)
        self.assertIn(b"Content-Type: video/mp4", seen["body"])


class RouteTests(unittest.TestCase):
    def setUp(self):
        import app as appmod
        from app import app as flask_app
        appmod._VIDEO_LIST_CACHE.clear()
        self.appmod = appmod
        self.env = mock.patch.dict(os.environ, {"POSTIZ_API_KEY_SWING_SHACK": "own"})
        self.env.start()
        self.patches = [
            mock.patch("app._is_authed", lambda: True),
            mock.patch.object(appmod, "_drive_listing", lambda brand: LISTING),
            mock.patch.object(appmod, "_drive_text", lambda fid: "Happy new year." if fid == "t1" else None),
        ]
        for p in self.patches:
            p.start()
        self.client = flask_app.test_client()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.env.stop()

    def post(self, file_id="v1", brand="swing-shack"):
        return self.client.post("/api/photos/videos/draft", json={"brand_id": brand, "file_id": file_id})

    def test_creates_a_draft_with_caption_and_media_on_the_instagram_channel(self):
        from _lib import google_drive as gd

        def fake_download(fid, dest, **kw):
            Path(dest).write_bytes(b"video")
            return Path(dest)

        with mock.patch.object(pz, "list_integrations", return_value=(INTEGRATIONS, None)), \
                mock.patch.object(gd, "download_public_file", fake_download), \
                mock.patch.object(pz, "upload_media", return_value=({"id": "m1", "path": "https://x/m.mp4"}, None)) as up, \
                mock.patch.object(pz, "create_post", return_value=({"ok": 1}, None)) as create:
            r = self.post()
        self.assertEqual(r.status_code, 200, r.get_json())
        args, kwargs = create.call_args
        self.assertEqual(args[0], "ig1")
        self.assertEqual(args[1], "Happy new year.")
        self.assertEqual(args[2], [{"id": "m1", "path": "https://x/m.mp4"}])
        self.assertIs(kwargs["draft"], True)
        self.assertEqual(kwargs["brand_id"], "swing-shack")
        self.assertEqual(kwargs["platform_settings"], {"post_type": "post"})
        self.assertEqual(up.call_args.kwargs["brand_id"], "swing-shack")

    def test_refuses_without_the_brands_own_key(self):
        with mock.patch.dict(os.environ, {"POSTIZ_API_KEY": "shared"}):
            os.environ.pop("POSTIZ_API_KEY_SWING_SHACK", None)
            r = self.post()
        self.assertEqual(r.status_code, 409)
        self.assertIn("no Postiz key", r.get_json()["error"])

    def test_only_ready_videos_with_a_caption_and_an_instagram_channel(self):
        with mock.patch.object(pz, "list_integrations", return_value=(INTEGRATIONS, None)):
            self.assertEqual(self.post("raw").status_code, 404)     # raw is not ready
            self.assertEqual(self.post("nope").status_code, 404)    # not in Drive
            self.assertEqual(self.post("v2").status_code, 409)      # no caption file
        with mock.patch.object(pz, "list_integrations", return_value=([INTEGRATIONS[1]], None)):
            r = self.post()
        self.assertEqual(r.status_code, 409)
        self.assertIn("Instagram", r.get_json()["error"])

    def test_postiz_errors_are_passed_on_and_login_is_required(self):
        from _lib import google_drive as gd
        with mock.patch.object(pz, "list_integrations", return_value=(INTEGRATIONS, None)), \
                mock.patch.object(gd, "download_public_file", lambda fid, dest, **kw: (Path(dest).write_bytes(b"v"), Path(dest))[1]), \
                mock.patch.object(pz, "upload_media", return_value=(None, ("400", "bad file"))):
            r = self.post()
        self.assertEqual(r.status_code, 502)
        with mock.patch("app._is_authed", lambda: False):
            self.assertEqual(self.post().status_code, 401)
        self.assertEqual(self.client.post("/api/photos/videos/draft", json={"file_id": "v1"}).status_code, 400)

    def test_story_format_uses_the_story_post_type(self):
        from _lib import google_drive as gd
        listing = [dict(e) for e in LISTING]
        listing[0]["name"] = "2026-10-19__new-year-offer__story-9x16__v1.mp4"
        listing[1]["name"] = "2026-10-19__new-year-offer__story-9x16__v1.txt"
        with mock.patch.object(self.appmod, "_drive_listing", lambda brand: listing), \
                mock.patch.object(pz, "list_integrations", return_value=(INTEGRATIONS, None)), \
                mock.patch.object(gd, "download_public_file", lambda fid, dest, **kw: (Path(dest).write_bytes(b"v"), Path(dest))[1]), \
                mock.patch.object(pz, "upload_media", return_value=({"id": "m", "path": "p"}, None)), \
                mock.patch.object(pz, "create_post", return_value=({}, None)) as create:
            self.post()
        self.assertEqual(create.call_args.kwargs["platform_settings"], {"post_type": "story"})

    def test_channels_route_follows_the_brand_and_refuses_the_shared_key(self):
        with mock.patch.object(pz, "list_integrations", return_value=(INTEGRATIONS, None)) as li:
            r = self.client.get("/api/postiz/channels?brand_id=swing-shack")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(li.call_args.kwargs["brand_id"], "swing-shack")
        with mock.patch.dict(os.environ, {"POSTIZ_API_KEY": "shared"}):
            os.environ.pop("POSTIZ_API_KEY_SWING_SHACK", None)
            r = self.client.get("/api/postiz/channels?brand_id=swing-shack")
        self.assertEqual(r.status_code, 409)


if __name__ == "__main__":
    unittest.main()
