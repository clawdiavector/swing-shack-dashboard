"""Stories (2026-10-20): Shared / Not-for-us marks, wider release words, stock check flags posts."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import story_marks, story_scout  # noqa: E402


class ReleaseWordTests(unittest.TestCase):
    def test_new_addition_and_lineup_posts_are_dropped(self):
        for text in ("Duro Sketch — One of two NEW additions to the Duro lineup",
                     "Just added to the range", "New colourway is here", "First look at the line-up"):
            self.assertIsNone(story_scout.classify(text)[0], text)

    def test_plain_vibe_still_passes(self):
        self.assertEqual(story_scout.classify("Sunday golf.")[0], "vibe")


class MarkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"DATA_DIR": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_mark_read_and_clear(self):
        k = story_marks.post_key("https://www.instagram.com/p/A/")
        story_marks.set_mark(k, "skipped")
        self.assertEqual(story_marks.read(), {k: "skipped"})
        self.assertEqual(k, story_marks.post_key("https://instagram.com/p/A"))
        story_marks.set_mark(k, "clear")
        self.assertEqual(story_marks.read(), {})

    def test_bad_input_is_refused(self):
        with self.assertRaises(story_marks.MarkError):
            story_marks.set_mark("nope", "shared")
        with self.assertRaises(story_marks.MarkError):
            story_marks.set_mark("post|x", "maybe")

    def test_old_idea_marks_are_dropped(self):
        story_marks.set_mark(story_marks.idea_key("stick", "2020-01-01", "daily", "A"), "shared")
        story_marks.set_mark(story_marks.post_key("https://instagram.com/p/B/"), "shared")
        self.assertEqual(list(story_marks.read()), ["post|https://instagram.com/p/B"])


class StockCheckTests(unittest.TestCase):
    NAMES = ["Vice Pro", "Vice Pro Plus", "Vice Drive", "Takomo 101 Irons", "Titleist Pro V1"]

    def _check(self, page_id, caption, names=None):
        post = {"page_id": page_id, "caption": caption}
        with mock.patch.object(story_scout, "_stock_names", return_value=self.NAMES if names is None else names):
            return story_scout.stock_check("stick", [post])[0]

    def test_stocked_model_matches(self):
        got = self._check("vice", "The Drive is built for distance off the tee")
        self.assertEqual((got["stock"], got["stock_name"]), ("match", "Vice Drive"))

    def test_unlisted_model_is_flagged_not_hidden(self):
        got = self._check("vice", "Duro Sketch is here")
        self.assertEqual(got["stock"], "none")

    def test_maker_not_on_list(self):
        self.assertEqual(self._check("avoda", "Wait for the results")["stock"], "brand-unlisted")

    def test_golf_moment_pages_and_no_list_are_unknown(self):
        self.assertEqual(self._check("pga-tour", "Big shot")["stock"], "unknown")
        self.assertEqual(self._check("vice", "Duro", names=[])["stock"], "unknown")


if __name__ == "__main__":
    unittest.main()
