"""TikTok sends through Postiz: its own settings, picked per post, never on by default."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _lib import onepost, postiz_client, publish_live, publish_sandbox


class TiktokSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old = {k: os.environ.get(k) for k in ("TIKTOK_POSTING_METHOD", "TIKTOK_PRIVACY_LEVEL")}
        for k in self._old:
            os.environ.pop(k, None)

    def tearDown(self) -> None:
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_tiktok_gets_its_own_settings(self) -> None:
        s = postiz_client.settings_for_provider("tiktok", "New Vice balls at Stick.\nDM us.")
        self.assertEqual(s["__type"], "tiktok")
        self.assertEqual(s["content_posting_method"], "UPLOAD")
        self.assertEqual(s["privacy_level"], "PUBLIC_TO_EVERYONE")
        self.assertEqual(s["autoAddMusic"], "no")
        for key in ("duet", "stitch", "comment", "brand_content_toggle", "brand_organic_toggle"):
            self.assertIsInstance(s[key], bool, key)
        self.assertEqual(s["title"], "New Vice balls at Stick.")

    def test_business_account_keeps_its_provider_type(self) -> None:
        s = postiz_client.settings_for_provider("tiktok-business", "Caption")
        self.assertEqual(s["__type"], "tiktok-business")

    def test_title_capped_at_90(self) -> None:
        s = postiz_client.settings_for_provider("tiktok", "x" * 200)
        self.assertLessEqual(len(s["title"]), 90)

    def test_method_and_privacy_from_env(self) -> None:
        os.environ["TIKTOK_POSTING_METHOD"] = "DIRECT_POST"
        os.environ["TIKTOK_PRIVACY_LEVEL"] = "SELF_ONLY"
        s = postiz_client.settings_for_provider("tiktok", "Caption")
        self.assertEqual(s["content_posting_method"], "DIRECT_POST")
        self.assertEqual(s["privacy_level"], "SELF_ONLY")

    def test_bad_env_values_fall_back_to_safe_defaults(self) -> None:
        os.environ["TIKTOK_POSTING_METHOD"] = "now"
        os.environ["TIKTOK_PRIVACY_LEVEL"] = "everyone"
        s = postiz_client.settings_for_provider("tiktok", "Caption")
        self.assertEqual(s["content_posting_method"], "UPLOAD")
        self.assertEqual(s["privacy_level"], "PUBLIC_TO_EVERYONE")

    def test_other_platforms_unchanged(self) -> None:
        self.assertEqual(postiz_client.settings_for_provider("instagram", "c"), {"post_type": "post"})
        self.assertEqual(postiz_client.settings_for_provider("facebook", "c"), {"post_type": "post"})


class TiktokChannelTests(unittest.TestCase):
    def test_tiktok_is_no_longer_coming_soon(self) -> None:
        self.assertNotIn("tiktok", onepost.COMING_SOON_CHANNELS)

    def test_tiktok_can_be_picked_for_both_brands(self) -> None:
        for brand in ("stick", "swing-shack"):
            self.assertIn("tiktok", onepost.brand_channels(brand), brand)
            self.assertEqual(onepost.normalize_picked_channels(["instagram", "tiktok"], brand),
                             ["instagram", "tiktok"])

    def test_tiktok_is_not_on_by_default(self) -> None:
        for brand in ("stick", "swing-shack"):
            self.assertNotIn("tiktok", onepost.default_channels(brand), brand)


class TiktokDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_env = {k: os.environ.get(k) for k in ("DATA_DIR", "PUBLISH_MODE")}
        os.environ["DATA_DIR"] = str(Path(self._tmp.name))
        os.environ["PUBLISH_MODE"] = "live"
        publish_sandbox.ensure_sandbox_layout()

    def tearDown(self) -> None:
        self._tmp.cleanup()
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _send(self, platform: str, integrations: list[dict]) -> mock.MagicMock:
        row = {
            "idempotency_key": f"qc-asset-1-{platform}",
            "post_id": "asset-1",
            "brand_id": "stick",
            "platform": platform,
            "channel": "postiz",
            "caption_preview": "Vice Pro Air at Stick.\nBetter begins here.",
            "human_approved": True,
            "human_approved_at": "2026-10-27T09:00:00+00:00",
            "would_publish_at": None,
            "status": "pending",
        }
        with mock.patch.object(publish_live, "create_post", return_value=({"id": "pz-1"}, None)) as cp, \
                mock.patch.object(publish_live, "_media_for_row", return_value=[]), \
                mock.patch.object(publish_live.post_links, "record_from_queue_row"):
            receipt, err = publish_live._dispatch_row_live(row, {"stick": integrations})
        self.assertIsNone(err)
        self.assertEqual(receipt["postiz_post_id"], "pz-1")
        return cp

    def test_tiktok_row_goes_to_the_tiktok_channel_with_tiktok_settings(self) -> None:
        ints = [
            {"id": "int-ig", "identifier": "instagram", "name": "Stick"},
            {"id": "int-tt", "identifier": "tiktok-business", "name": "stick Paarl"},
        ]
        cp = self._send("tiktok", ints)
        kw = cp.call_args.kwargs
        self.assertEqual(kw["integration_id"], "int-tt")
        self.assertEqual(kw["platform_settings"]["__type"], "tiktok-business")

    def test_instagram_row_unchanged(self) -> None:
        ints = [
            {"id": "int-tt", "identifier": "tiktok", "name": "SwingShack"},
            {"id": "int-ig", "identifier": "instagram", "name": "Stick"},
        ]
        cp = self._send("instagram", ints)
        kw = cp.call_args.kwargs
        self.assertEqual(kw["integration_id"], "int-ig")
        self.assertEqual(kw["platform_settings"], {"post_type": "post"})


if __name__ == "__main__":
    unittest.main()
