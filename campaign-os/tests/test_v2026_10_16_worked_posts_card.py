"""
test_v2026_10_16_worked_posts_card.py

Regression tests for the What worked > posts card sentence (plain_english):
  - "1 comment" / "1 like" are singular, not "1 comments"
  - no stray trailing comma when a post has likes but no comments
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str((_Path(__file__).resolve().parent / '.').resolve()))

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

import test_v2026_08_07_insights_v2 as _insights  # noqa: E402


class WorkedPostsSentenceTests(_insights.InsightsV2ApiTests):
    # Same isolation as TopInstagramPostsTests, copied so the inherited
    # tests in that class are not collected a second time here.
    def _isolate_bundled(self):
        bundled_dir = Path(tempfile.mkdtemp(prefix="test-bundled-"))
        orig_bundled = os.environ.get("BUNDLED_DATA_DIR")
        os.environ["BUNDLED_DATA_DIR"] = str(bundled_dir)
        return bundled_dir, orig_bundled

    def _restore_bundled(self, bundled_dir, orig_bundled):
        shutil.rmtree(bundled_dir, ignore_errors=True)
        if orig_bundled is not None:
            os.environ["BUNDLED_DATA_DIR"] = orig_bundled
        else:
            os.environ.pop("BUNDLED_DATA_DIR", None)

    def _top_sentence(self, post):
        bundled_dir, orig_bundled = self._isolate_bundled()
        try:
            ig = {
                "updated": "2026-10-16T10:00:00Z",
                "posts": [
                    dict(post, id="ig-top", engagementRate=8.0, media_type="IMAGE",
                         permalink="https://www.instagram.com/p/top"),
                    {"id": "ig-low", "caption": "low", "engagementRate": 1.0,
                     "like_count": 3, "comments_count": 0, "media_type": "IMAGE"},
                ],
            }
            (self.tmpdir / "instagram.json").write_text(json.dumps(ig))
            r = self.client.get("/api/insights/top-instagram-posts?limit=8")
            self.assertEqual(r.status_code, 200)
            return r.get_json()["posts"][0]["plain_english"]
        finally:
            self._restore_bundled(bundled_dir, orig_bundled)

    def test_single_like_and_single_comment_are_singular(self):
        sentence = self._top_sentence({"like_count": 1, "comments_count": 1})
        self.assertTrue(sentence.endswith("1 like, 1 comment."), sentence)

    def test_no_trailing_comma_when_no_comments(self):
        sentence = self._top_sentence({"like_count": 15, "comments_count": 0})
        self.assertTrue(sentence.endswith("15 likes."), sentence)
        self.assertNotIn(",.", sentence)

    def test_plural_counts_with_thousands_separator(self):
        sentence = self._top_sentence({"like_count": 1200, "comments_count": 7})
        self.assertTrue(sentence.endswith("1,200 likes, 7 comments."), sentence)
