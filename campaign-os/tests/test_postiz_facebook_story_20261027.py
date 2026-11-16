"""Facebook Page stories through Postiz (2026-10-27).

Postiz's public docs list no Facebook story, but its Facebook provider reads settings.post_type == "story"
and publishes through photo_stories (checked in postiz-app main, libraries/.../facebook.provider.ts). Instagram
stays on create_story; this is a separate call so the Instagram rules and tests do not move.
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
    d = Path(tempfile.mkdtemp(prefix="cos-fbstory-"))
    f = d / "st-1.jpg"
    f.write_bytes(b"\xff\xd8\xff")
    return str(f)


class FacebookStoryTests(unittest.TestCase):
    def test_settings_name_facebook_and_the_story_type(self):
        self.assertEqual(pz.facebook_story_settings(), {"__type": "facebook", "post_type": "story"})

    def test_uploads_then_creates_one_facebook_story_draft_with_no_caption(self):
        with mock.patch.object(pz, "upload_media", return_value=({"id": "m9", "path": "https://x/st-1.jpg"}, None)) as up, \
             mock.patch.object(pz, "_request", return_value=({"ok": 1}, None)) as req:
            data, err = pz.create_facebook_story("fb1", _image(), brand_id="stick",
                                                 publish_date="2099-01-01T15:30:00Z")
        self.assertIsNone(err)
        self.assertEqual(data, {"ok": 1})
        self.assertEqual(up.call_args.kwargs["brand_id"], "stick")
        body = req.call_args.kwargs["json_body"]
        post = body["posts"][0]
        self.assertEqual(post["integration"], {"id": "fb1"})
        self.assertEqual(post["settings"], {"__type": "facebook", "post_type": "story"})
        self.assertEqual(post["value"][0]["content"], "")
        self.assertEqual(post["value"][0]["image"], [{"id": "m9", "path": "https://x/st-1.jpg"}])
        self.assertEqual(body["type"], "draft")
        self.assertEqual(body["date"], "2099-01-01T15:30:00Z")

    def test_a_scheduled_facebook_story_is_never_sent_now(self):
        with mock.patch.object(pz, "upload_media", return_value=({"id": "m9", "path": "https://x/a.jpg"}, None)), \
             mock.patch.object(pz, "_request", return_value=({}, None)) as req:
            pz.create_facebook_story("fb1", _image(), brand_id="swing-shack", draft=False)
        body = req.call_args.kwargs["json_body"]
        self.assertEqual(body["type"], "schedule")
        self.assertTrue(body["date"])

    def test_a_failed_upload_stops_before_any_post_is_created(self):
        with mock.patch.object(pz, "upload_media", return_value=(None, ("502", "bad"))), \
             mock.patch.object(pz, "_request") as req:
            data, err = pz.create_facebook_story("fb1", _image(), brand_id="stick")
        self.assertIsNone(data)
        self.assertEqual(err, ("502", "bad"))
        req.assert_not_called()


if __name__ == "__main__":
    unittest.main()
