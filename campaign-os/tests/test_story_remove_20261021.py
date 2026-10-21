"""Stories (2026-10-21): an accidental Add can be undone with Remove."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import story_queue  # noqa: E402


class RemoveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"DATA_DIR": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_removed_item_leaves_both_lists_and_can_be_added_again(self):
        item, _ = story_queue.add("stick", "https://www.instagram.com/p/A/", "x")
        story_queue.set_status(item["id"], "removed")
        got = story_queue.list_items("stick")
        self.assertEqual((got["open"], got["done_today"]), ([], []))
        again, created = story_queue.add("stick", "https://www.instagram.com/p/A/", "x")
        self.assertTrue(created)
        self.assertNotEqual(again["id"], item["id"])

    def test_unknown_status_still_refused(self):
        item, _ = story_queue.add("stick", "https://www.instagram.com/p/B/", "")
        with self.assertRaises(story_queue.StoryError):
            story_queue.set_status(item["id"], "gone")


if __name__ == "__main__":
    unittest.main()
