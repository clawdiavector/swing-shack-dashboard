"""
Publishing a Google Business draft must use the draft's own brand: its own Postiz
key and its own Google channel. All Postiz keys could see Stick's workspace, so
"the first Google channel" meant a Swing Shack post would go to Stick's listing.

Run: python -m pytest campaign-os/tests/test_gbp_schedule_brand.py
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_gbp_reviewed_drafts import _draft, _write, gbp  # noqa: E402

STICK_CHANNEL = "cmu6pc3gp0btanl0yl50vl8pz"


class ScheduleBrandTests(unittest.TestCase):
    def setUp(self):
        import app as app_module  # noqa: PLC0415

        self.app_module = app_module
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "gmb-drafts"
        self.media = Path(self._tmp.name) / "media"
        self.root.mkdir()
        self.media.mkdir()
        (self.media / "p.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 32)
        self.pz = mock.MagicMock()
        self.pz.has_brand_key.return_value = True
        self.pz.list_integrations.return_value = ({"integrations": [{"id": STICK_CHANNEL, "providerIdentifier": "gmb"}]}, None)
        self.pz.upload_media.return_value = ({"id": "img-1"}, None)
        self.pz.create_post.return_value = ({"id": "post-1"}, None)
        self._patches = [
            mock.patch.object(app_module, "GMB_DRAFTS_DIR", str(self.root)),
            mock.patch.object(app_module, "ASSET_MEDIA_DIR", str(self.media)),
            mock.patch.object(app_module, "_postiz_lib", self.pz),
            mock.patch.object(app_module, "_POSTIZ_CLIENT_AVAILABLE", True),
        ]
        for p in self._patches:
            p.start()
        self.client = app_module.app.test_client()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()

    def _approved(self, brand, link):
        _write(self.root, _draft("d", brand=brand, link=link, status="approved", imageUrl=str(self.media / "p.jpg")))

    def test_stick_post_goes_out_with_sticks_key_and_channel(self):
        self._approved("stick", "https://stickgolf.co.za/")
        res = self.client.post("/api/intel/gmb/draft/d/schedule", json={})
        self.assertEqual(res.status_code, 200, res.get_json())
        kwargs = self.pz.create_post.call_args.kwargs
        self.assertEqual(kwargs["integration_id"], STICK_CHANNEL)
        self.assertEqual(kwargs["brand_id"], "stick")
        self.assertEqual(self.pz.upload_media.call_args.kwargs["brand_id"], "stick")
        self.pz.list_integrations.assert_called_once_with(brand_id="stick")

    def test_swing_shack_post_is_refused_when_its_channel_is_not_in_its_workspace(self):
        self._approved("swing-shack", "https://swingshack.co.za/bookings/")
        res = self.client.post("/api/intel/gmb/draft/d/schedule", json={})
        self.assertEqual(res.status_code, 400)
        self.assertIn("no GMB integration", res.get_json()["error"])
        self.pz.create_post.assert_not_called()

    def test_brand_without_its_own_postiz_key_is_refused(self):
        self.pz.has_brand_key.return_value = False
        self._approved("stick", "https://stickgolf.co.za/")
        res = self.client.post("/api/intel/gmb/draft/d/schedule", json={})
        self.assertEqual(res.status_code, 400)
        self.pz.create_post.assert_not_called()

    def test_a_draft_that_is_not_approved_is_still_refused(self):
        _write(self.root, _draft("d", brand="stick", link="https://stickgolf.co.za/", imageUrl=str(self.media / "p.jpg")))
        res = self.client.post("/api/intel/gmb/draft/d/schedule", json={})
        self.assertEqual(res.status_code, 409)
        self.pz.create_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
