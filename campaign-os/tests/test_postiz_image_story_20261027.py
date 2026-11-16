"""Send a finished 9:16 image to Postiz as an Instagram story (2026-10-27).

Postiz documents Instagram stories (settings post_type "story") and nothing for Facebook, so a Facebook
story is refused up front instead of going out as a feed post. Stories are never sent "now".
"""
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


def _image() -> str:
    d = Path(tempfile.mkdtemp(prefix="cos-story-"))
    f = d / "ss-1.jpg"
    f.write_bytes(b"\xff\xd8\xff")
    return str(f)


class StorySettingsTests(unittest.TestCase):
    def test_instagram_providers_get_the_story_type_and_their_own_name(self):
        self.assertEqual(pz.story_settings("instagram"), {"__type": "instagram", "post_type": "story"})
        self.assertEqual(pz.story_settings("Instagram-Standalone"),
                         {"__type": "instagram-standalone", "post_type": "story"})

    def test_other_channels_have_no_documented_story_type(self):
        for provider in ("facebook", "tiktok", "youtube", ""):
            self.assertIsNone(pz.story_settings(provider))


class CreateStoryTests(unittest.TestCase):
    def test_uploads_the_image_then_creates_one_story_post_with_no_caption(self):
        with mock.patch.object(pz, "upload_media", return_value=({"id": "m1", "path": "https://x/ss-1.jpg"}, None)) as up, \
             mock.patch.object(pz, "_request", return_value=({"ok": 1}, None)) as req:
            data, err = pz.create_story("ig1", "instagram", _image(), brand_id="swing-shack",
                                        publish_date="2099-01-01T15:30:00Z")
        self.assertIsNone(err)
        self.assertEqual(data, {"ok": 1})
        self.assertEqual(up.call_args.kwargs["brand_id"], "swing-shack")
        body = req.call_args.kwargs["json_body"]
        post = body["posts"][0]
        self.assertEqual(post["integration"], {"id": "ig1"})
        self.assertEqual(post["settings"], {"__type": "instagram", "post_type": "story"})
        self.assertEqual(post["value"][0]["content"], "")
        self.assertEqual(post["value"][0]["image"], [{"id": "m1", "path": "https://x/ss-1.jpg"}])
        self.assertEqual(body["type"], "draft")          # a draft unless told otherwise: nothing publishes by accident
        self.assertEqual(body["date"], "2099-01-01T15:30:00Z")

    def test_scheduled_story_is_never_sent_now(self):
        with mock.patch.object(pz, "upload_media", return_value=({"id": "m1", "path": "https://x/a.jpg"}, None)), \
             mock.patch.object(pz, "_request", return_value=({}, None)) as req:
            pz.create_story("ig1", "instagram", _image(), brand_id="stick", draft=False)
        body = req.call_args.kwargs["json_body"]
        self.assertEqual(body["type"], "schedule")
        self.assertTrue(body["date"])                     # the 5-minute minimum fills a missing time

    def test_facebook_is_refused_without_calling_postiz(self):
        with mock.patch.object(pz, "upload_media") as up, mock.patch.object(pz, "_request") as req:
            data, err = pz.create_story("fb1", "facebook", _image(), brand_id="swing-shack")
        self.assertIsNone(data)
        self.assertIn("story", err[1].lower())
        up.assert_not_called()
        req.assert_not_called()

    def test_a_failed_upload_stops_before_any_post_is_created(self):
        with mock.patch.object(pz, "upload_media", return_value=(None, ("502", "bad"))), \
             mock.patch.object(pz, "_request") as req:
            data, err = pz.create_story("ig1", "instagram", _image(), brand_id="stick")
        self.assertIsNone(data)
        self.assertEqual(err, ("502", "bad"))
        req.assert_not_called()


if __name__ == "__main__":
    unittest.main()
