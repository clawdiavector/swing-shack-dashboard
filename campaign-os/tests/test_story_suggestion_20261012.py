"""Daily story suggestion (2026-10-12): what to feature and which stocked brand to repost from."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import story_suggestion  # noqa: E402


def _days(n=60):
    start = date(2026, 10, 12)
    return [start + timedelta(days=i) for i in range(n)]


class SuggestionTests(unittest.TestCase):
    def test_each_day_has_a_service_and_a_different_retail_brand(self):
        for brand in ("stick", "swing-shack"):
            for d in _days():
                got = {s["kind"]: s for s in story_suggestion.suggest(brand, d)}
                expect = {"service", "retail", "moment"} | ({"daily"} if brand == "stick" else set())
                self.assertEqual(set(got), expect)
                self.assertNotEqual(got["service"]["repost_from"]["id"], got["retail"]["repost_from"]["id"])

    def test_swing_shack_never_suggests_psycho_bunny(self):
        for d in _days():
            for s in story_suggestion.suggest("swing-shack", d):
                self.assertNotEqual(s["repost_from"]["id"], "psycho-bunny")

    def test_brand_without_a_page_is_never_suggested(self):
        for brand in ("stick", "swing-shack"):
            for d in _days():
                for s in story_suggestion.suggest(brand, d):
                    self.assertNotEqual(s["repost_from"]["id"], "ripit")
                    self.assertTrue(s["repost_from"]["instagram"] or s["repost_from"]["facebook"])

    def test_every_stocked_brand_comes_up(self):
        for brand, expect in (("stick", {"takomo", "vice", "lab", "psycho-bunny", "avoda", "vessel"}),
                              ("swing-shack", {"takomo", "vice", "lab", "avoda", "vessel"})):
            seen = {s["repost_from"]["id"] for d in _days() for s in story_suggestion.suggest(brand, d)}
            self.assertTrue(expect <= seen)

    def test_service_pairs_with_a_fitting_brand(self):
        seen = {}
        for d in _days():
            for s in story_suggestion.suggest("swing-shack", d):
                if s["kind"] == "service":
                    seen[s["feature"]] = s["repost_from"]["id"]
        self.assertEqual(seen["Putter fitting"], "lab")

    def test_golf_moment_appears_once_pages_are_listed(self):
        real = story_suggestion._load
        fake = dict(real("swing-shack"), moments=[
            {"id": "gsa", "name": "Golf South Africa", "instagram": "https://www.instagram.com/x/", "facebook": None},
            {"id": "nopage", "name": "No page", "instagram": None, "facebook": None}])
        story_suggestion._load = lambda brand: fake
        try:
            got = story_suggestion.suggest("swing-shack", date(2026, 10, 12))
        finally:
            story_suggestion._load = real
        moment = [s for s in got if s["kind"] == "moment"]
        self.assertEqual([m["feature"] for m in moment], ["Golf South Africa"])
        self.assertEqual({s["kind"] for s in got}, {"service", "retail", "moment"})

    def test_same_day_same_answer_and_unknown_brand(self):
        d = date(2026, 10, 12)
        self.assertEqual(story_suggestion.suggest("stick", d), story_suggestion.suggest("stick", d))
        self.assertEqual(story_suggestion.suggest("nope", d), [])


class SuggestionRouteTests(unittest.TestCase):
    def test_endpoint(self):
        os.environ.setdefault("COS_JOB_TOKEN", "t")
        import app as app_module

        app_module.COS_JOB_TOKEN = "t"
        c = app_module.app.test_client(cos_anon=True)
        self.assertEqual(c.get("/api/stories/suggestion").status_code, 401)
        r = c.get("/api/stories/suggestion", headers={"Authorization": "Bearer t"}).get_json()
        self.assertEqual({s["brand"] for s in r["suggestions"]}, {"swing-shack", "stick"})
        # 6 from the rotation, plus Stick's daily Psycho Bunny slot (2026-10-16).
        self.assertEqual(len(r["suggestions"]), 7)
        one = c.get("/api/stories/suggestion?brand=stick", headers={"Authorization": "Bearer t"}).get_json()
        self.assertEqual(len(one["suggestions"]), 4)  # service, retail, moment, daily Psycho Bunny


if __name__ == "__main__":
    unittest.main()
