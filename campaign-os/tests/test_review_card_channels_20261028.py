"""Review draft cards get each brand's real channel list, so TikTok is pickable, not 'Coming later'."""
from __future__ import annotations

import unittest

from _lib import unified_inbox


class ReviewCardChannelsTests(unittest.TestCase):
    def _items(self):
        return [
            {"type": "draft_asset", "brand_id": "stick", "meta": {}},
            {"type": "publish_request", "brand_id": "swing-shack", "meta": {}},
            {"type": "calendar_candidate", "brand_id": "stick", "meta": {}},
        ]

    def test_draft_and_publish_items_get_the_brand_channels(self):
        items = self._items()
        unified_inbox._add_channel_options(items)
        stick, ss, cand = items
        self.assertIn("tiktok", stick["meta"]["channels_available"])
        self.assertNotIn("gbp", stick["meta"]["channels_available"])
        self.assertNotIn("tiktok", stick["meta"]["channels_coming"])
        self.assertIn("gbp", ss["meta"]["channels_available"])
        self.assertIn("tiktok", ss["meta"]["channels_available"])
        self.assertNotIn("channels_available", cand["meta"])

    def test_existing_values_are_kept(self):
        items = [{"type": "draft_asset", "brand_id": "stick", "meta": {"channels_available": ["instagram"]}}]
        unified_inbox._add_channel_options(items)
        self.assertEqual(items[0]["meta"]["channels_available"], ["instagram"])

    def test_unknown_brand_is_skipped(self):
        items = [{"type": "draft_asset", "brand_id": "nope", "meta": {}}]
        unified_inbox._add_channel_options(items)
        self.assertNotIn("channels_available", items[0]["meta"])


if __name__ == "__main__":
    unittest.main()
