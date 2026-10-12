"""Organic posts must reach post_outcomes with their link, format, caption and likes.

On 2026-10-08 the ads creative loop could offer no organic reel: the Instagram
media list held five posts, and each row had lost its permalink, its media type
and its caption on the way to post_outcomes, so every post ranked as a
captionless image with no link.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import ads_creative, meta_live_fetch  # noqa: E402
from _lib.jobs.layer7 import post_outcomes  # noqa: E402


def _graph_post(pid, media_type, caption, reach, likes, saved=0, comments=0):
    return {"id": pid, "media_type": media_type, "caption": caption,
            "permalink": f"https://www.instagram.com/p/{pid}/",
            "timestamp": "2026-10-01T10:00:00+0000",
            "insights": {"data": [
                {"name": "reach", "values": [{"value": reach}]},
                {"name": "likes", "values": [{"value": likes}]},
                {"name": "saved", "values": [{"value": saved}]},
                {"name": "comments", "values": [{"value": comments}]}]}}


REEL = _graph_post("r1", "VIDEO", "Coaching with Cat: one lesson, one fix.\nBook online.", 1800, 90, 12, 4)
IMAGE = _graph_post("i1", "IMAGE", "New arrivals in store this week.", 900, 20)


class Row(unittest.TestCase):
    def test_keeps_what_post_outcomes_reads(self):
        row = meta_live_fetch._normalise_ig_post(REEL)
        self.assertEqual(row["permalink"], "https://www.instagram.com/p/r1/")
        self.assertEqual(row["media_type"], "VIDEO")
        self.assertEqual(row["format_type"], "reel")
        self.assertTrue(row["caption_preview"].startswith("Coaching with Cat"))
        self.assertEqual(row["metrics"], {"reach": 1800, "likes": 90, "comments": 4,
                                          "saved": 12, "shares": 0})

    def test_existing_keys_are_unchanged(self):
        row = meta_live_fetch._normalise_ig_post(REEL)
        for key in ("id", "postId", "timestamp", "captionPreview", "hook_text", "hook_id",
                    "topic_cluster", "reach", "likes", "comments", "saves", "shares",
                    "engagementRate", "saveRate", "shareRate", "followConversion"):
            self.assertIn(key, row)
        self.assertEqual((row["likes"], row["saves"], row["topic_cluster"]), (90, 12, "coaching"))
        self.assertEqual(row["engagementRate"], "5.89")

    def test_post_without_insights_or_caption(self):
        row = meta_live_fetch._normalise_ig_post({"id": "x", "media_type": "CAROUSEL_ALBUM"})
        self.assertEqual((row["reach"], row["format_type"], row["permalink"], row["caption_preview"]),
                         (0, "carousel", "", ""))


class ThroughToTheCreativeLoop(unittest.TestCase):
    def _row_for(self, graph_post):
        row = meta_live_fetch._normalise_ig_post(graph_post)
        return post_outcomes._build_outcome_row(row, brand_id="swing-shack", conversion_row=None,
                                                receipt=None, join_basis="ig_only")

    def test_outcome_row_is_a_reel_with_a_link_caption_and_score(self):
        out = self._row_for(REEL)
        self.assertEqual(out["format_type"], "reel")
        self.assertEqual(out["permalink"], "https://www.instagram.com/p/r1/")
        self.assertTrue(out["caption_preview"].startswith("Coaching with Cat"))
        self.assertEqual(out["reach"], 1800)
        self.assertGreater(out["score"], self._row_for(dict(REEL, insights={"data": []}))["score"])
        self.assertEqual(self._row_for(IMAGE)["format_type"], "image")

    def test_the_reel_can_now_be_offered_as_a_challenger(self):
        outcomes = [self._row_for(REEL), self._row_for(IMAGE)]
        pick = ads_creative._reel_challenger({"coaching"}, outcomes, used=set(), taken=set())
        self.assertEqual((pick["kind"], pick["permalink"]),
                         ("ORGANIC_REEL", "https://www.instagram.com/p/r1/"))
        self.assertIsNone(ads_creative._reel_challenger({"fitting"}, outcomes, set(), set()))


if __name__ == "__main__":
    unittest.main()
