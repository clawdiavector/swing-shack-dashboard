"""
test_worked_lately_media.py

The "What worked lately" card needs each top Instagram post to carry a link,
an image and its real format:
  - the live fetch asks Graph for thumbnail_url / media_url and stores them
  - a store that only has format_type (reel / carousel / static) is not
    labelled IMAGE for every post
  - a post with no permalink gets one from meta-post-index.json by media id
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def _post(post_id: str, rate: str, **extra) -> dict:
    return {
        "id": post_id,
        "postId": post_id,
        "timestamp": "2026-09-01T10:00:00+0000",
        "captionPreview": f"caption {post_id}",
        "engagementRate": rate,
        "likes": 10,
        "comments": 1,
        "reach": 500,
        **extra,
    }


class WorkedLatelyMediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        env = {"DATA_DIR": str(self.data), "BUNDLED_DATA_DIR": str(self.data)}
        patcher = patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def _write(self, name: str, obj: dict) -> None:
        (self.data / name).write_text(json.dumps(obj), encoding="utf-8")

    def _top(self) -> list[dict]:
        from _lib import insights_correlator as ic

        return ic.get_top_instagram_posts(limit=5)["posts"]

    def test_format_type_decides_media_type_when_media_type_is_missing(self):
        self._write(
            "ig-analytics.json",
            {
                "posts": [
                    _post("1", "6.0", format_type="reel"),
                    _post("2", "5.0", format_type="carousel"),
                    _post("3", "4.0", format_type="static"),
                    _post("4", "3.0"),
                ]
            },
        )
        types = {p["id"]: p["media_type"] for p in self._top()}
        self.assertEqual(
            types,
            {"1": "VIDEO", "2": "CAROUSEL_ALBUM", "3": "IMAGE", "4": "IMAGE"},
        )

    def test_stored_media_type_is_kept(self):
        self._write(
            "ig-analytics.json",
            {"posts": [_post("1", "6.0", media_type="VIDEO", format_type="static")]},
        )
        self.assertEqual(self._top()[0]["media_type"], "VIDEO")

    def test_missing_permalink_is_filled_from_the_meta_index(self):
        self._write("ig-analytics.json", {"posts": [_post("111", "6.0"), _post("222", "5.0")]})
        self._write(
            "meta-post-index.json",
            {
                "external_publications": {
                    "111": {"permalink": "https://www.instagram.com/reel/abc/", "media_type": "VIDEO"}
                }
            },
        )
        posts = {p["id"]: p for p in self._top()}
        self.assertEqual(posts["111"]["permalink"], "https://www.instagram.com/reel/abc/")
        self.assertEqual(posts["111"]["media_type"], "VIDEO")
        self.assertEqual(posts["222"]["permalink"], "")

    def test_meta_index_wrapped_in_an_index_key_is_read(self):
        self._write("ig-analytics.json", {"posts": [_post("111", "6.0")]})
        self._write(
            "meta-post-index.json",
            {"index": {"external_publications": {"111": {"permalink": "https://www.instagram.com/p/xyz/"}}}},
        )
        self.assertEqual(self._top()[0]["permalink"], "https://www.instagram.com/p/xyz/")

    def test_a_stored_permalink_is_not_overwritten(self):
        self._write(
            "ig-analytics.json",
            {"posts": [_post("111", "6.0", permalink="https://www.instagram.com/p/own/")]},
        )
        self._write(
            "meta-post-index.json",
            {"external_publications": {"111": {"permalink": "https://www.instagram.com/p/other/"}}},
        )
        self.assertEqual(self._top()[0]["permalink"], "https://www.instagram.com/p/own/")

    def test_missing_meta_index_is_fine(self):
        self._write("ig-analytics.json", {"posts": [_post("111", "6.0")]})
        self.assertEqual(self._top()[0]["permalink"], "")

    def test_live_fetch_stores_image_fields(self):
        from _lib import meta_live_fetch

        row = meta_live_fetch._normalise_ig_post(
            {
                "id": "9",
                "caption": "hello",
                "media_type": "VIDEO",
                "permalink": "https://www.instagram.com/reel/q/",
                "thumbnail_url": "https://cdn.example/thumb.jpg",
                "media_url": "https://cdn.example/video.mp4",
                "timestamp": "2026-09-01T10:00:00+0000",
            }
        )
        self.assertEqual(row["thumbnail_url"], "https://cdn.example/thumb.jpg")
        self.assertEqual(row["media_url"], "https://cdn.example/video.mp4")
        self.assertEqual(row["permalink"], "https://www.instagram.com/reel/q/")

    def test_top_posts_report_when_the_instagram_store_was_written(self):
        self._write(
            "ig-analytics.json",
            {"updated": "2026-10-19T11:50:00Z", "posts": [_post("1", "6.0")]},
        )
        from _lib import insights_correlator as ic

        meta = ic.get_top_instagram_posts(limit=5)["_meta"]
        self.assertEqual(meta["fetched_at"], "2026-10-19T11:50:00Z")

    def test_live_fetch_asks_graph_for_the_image_fields(self):
        source = (CAMPAIGN_OS / "_lib" / "meta_live_fetch.py").read_text(encoding="utf-8")
        self.assertIn("permalink,thumbnail_url,media_url,timestamp", source)


if __name__ == "__main__":
    unittest.main()
