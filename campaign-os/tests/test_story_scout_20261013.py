"""Story scout (2026-10-13): picks specific posts worth reposting, drops what we should not share."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import story_scout  # noqa: E402

NOW = datetime(2026, 10, 13, 8, 0, tzinfo=timezone.utc)
PAGE = {"id": "vice", "name": "Vice"}


def _post(caption="", likes=100, comments=2, days=1, kind="IMAGE", link="https://www.instagram.com/p/A/"):
    ts = (NOW - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S+0000")
    return {"caption": caption, "like_count": likes, "comments_count": comments, "timestamp": ts,
            "media_type": kind, "permalink": link, "media_url": "https://cdn/x.jpg"}


class ClassifyTests(unittest.TestCase):
    def test_launches_sales_and_giveaways_are_dropped(self):
        for text in ("Your favorite ball is back with an all-new look", "The Off-White Tracer Collection",
                     "It all drops tomorrow", "Pre-order now", "20% off this weekend", "Use code VICE10",
                     "Giveaway! Tag a friend to win", "Loving this #ad", "Introducing the new driver"):
            self.assertIsNone(story_scout.classify(text)[0], text)

    def test_sad_or_divisive_news_is_dropped(self):
        for text in ("Rest in peace to a legend", "A tribute to a great", "The tour is banning members"):
            self.assertIsNone(story_scout.classify(text)[0], text)

    def test_vibe_product_and_story(self):
        self.assertEqual(story_scout.classify("")[0], "vibe")
        self.assertEqual(story_scout.classify("Sunday golf.")[0], "vibe")
        self.assertEqual(story_scout.classify("Smooth tempo with the new putter in hand, nothing else matters")[0], "product")
        self.assertEqual(story_scout.classify("x" * 200)[0], "story")


class RankTests(unittest.TestCase):
    def test_old_posts_and_dropped_kinds_are_excluded(self):
        posts = [_post("Sunday golf.", days=2), _post("Sunday golf.", days=30),
                 _post("Launching tomorrow", days=1), _post("Sunday", days=1, link="")]
        got = story_scout.rank_page(PAGE, posts, NOW)
        self.assertEqual(len(got), 1)

    def test_a_post_beating_the_pages_normal_ranks_first_and_vibe_gets_the_edge(self):
        posts = [_post("Sunday golf.", likes=400, link="https://www.instagram.com/p/BIG/")] + [
            _post("Sunday golf.", likes=100, link=f"https://www.instagram.com/p/{i}/") for i in range(5)]
        top = story_scout.pick(story_scout.rank_page(PAGE, posts, NOW))[0]
        self.assertTrue(top["url"].endswith("/BIG/"))
        self.assertEqual(top["kind"], "vibe")

    def test_one_page_cannot_fill_the_list(self):
        posts = [_post("Sunday golf.", likes=100 + i, link=f"https://www.instagram.com/p/{i}/") for i in range(6)]
        self.assertEqual(len(story_scout.pick(story_scout.rank_page(PAGE, posts, NOW))), story_scout.PER_PAGE)

    def test_viral_post_is_capped(self):
        posts = [_post("a", likes=10**7), _post("b", likes=10)]
        self.assertLessEqual(max(c["score"] for c in story_scout.rank_page(PAGE, posts, NOW)), 8 * 1.3)


class CandidatesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="co-scout-")
        self._prev = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = self.tmp
        self._fetch = story_scout._fetch
        self.calls = []

    def tearDown(self):
        story_scout._fetch = self._fetch
        if self._prev is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake(self, fail=()):
        def fetch(username):
            self.calls.append(username)
            if username in fail:
                raise RuntimeError("HTTP 400")
            ts = datetime.now(timezone.utc) - timedelta(days=1)
            return [{"caption": "Sunday golf.", "like_count": 50, "comments_count": 1,
                     "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S+0000"), "media_type": "IMAGE",
                     "permalink": f"https://www.instagram.com/p/{username}/"}]
        return fetch

    def test_swing_shack_never_gets_psycho_bunny_and_a_dead_page_is_reported(self):
        story_scout._fetch = self._fake(fail=("vicegolf",))
        r = story_scout.candidates("swing-shack", refresh=True)
        self.assertNotIn("psychobunny", self.calls)
        self.assertTrue(r["posts"])
        self.assertEqual(len(r["errors"]), 1)
        self.assertIn("Vice", r["errors"][0])

    def test_stick_includes_psycho_bunny(self):
        story_scout._fetch = self._fake()
        story_scout.candidates("stick", refresh=True)
        self.assertIn("psychobunny", self.calls)

    def test_cache_is_used_until_refresh(self):
        story_scout._fetch = self._fake()
        story_scout.candidates("stick", refresh=True)
        n = len(self.calls)
        story_scout.candidates("stick")
        self.assertEqual(len(self.calls), n)
        story_scout.candidates("stick", refresh=True)
        self.assertGreater(len(self.calls), n)

    def test_total_failure_keeps_the_last_good_list(self):
        story_scout._fetch = self._fake()
        good = story_scout.candidates("stick", refresh=True)
        story_scout._fetch = self._fake(fail=story_scout._handle and tuple(
            story_scout._handle(p["instagram"]) for p in
            story_scout.story_suggestion._load("stick")["retail"] + story_scout.story_suggestion._load("stick")["moments"]
            if p.get("instagram")))
        again = story_scout.candidates("stick", refresh=True)
        self.assertEqual(again["posts"], good["posts"])


class RouteTests(unittest.TestCase):
    def test_endpoint(self):
        tmp = tempfile.mkdtemp(prefix="co-scout-route-")
        os.environ["DATA_DIR"] = tmp
        os.environ["COS_JOB_TOKEN"] = "t"
        import app as app_module

        app_module.COS_JOB_TOKEN = "t"
        orig = story_scout._fetch
        story_scout._fetch = lambda username: []
        try:
            c = app_module.app.test_client(cos_anon=True)
            self.assertEqual(c.get("/api/stories/candidates?brand=stick").status_code, 401)
            h = {"Authorization": "Bearer t"}
            self.assertEqual(c.get("/api/stories/candidates", headers=h).status_code, 400)
            r = c.get("/api/stories/candidates?brand=stick", headers=h).get_json()
            self.assertTrue(r["ok"])
            self.assertEqual(r["posts"], [])
        finally:
            story_scout._fetch = orig
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
