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
    def test_swing_shack_never_suggests_psycho_bunny(self):
        for d in _days():
            s = story_suggestion.suggest("swing-shack", d)
            self.assertNotEqual(s["repost_from"]["id"], "psycho-bunny")

    def test_brand_without_a_page_is_never_suggested(self):
        for brand in ("stick", "swing-shack"):
            for d in _days():
                s = story_suggestion.suggest(brand, d)
                self.assertNotEqual(s["repost_from"]["id"], "ripit")
                self.assertTrue(s["repost_from"]["instagram"] or s["repost_from"]["facebook"])

    def test_days_alternate_and_every_stocked_brand_comes_up(self):
        for brand, expect in (("stick", {"takomo", "vice", "lab", "psycho-bunny", "avoda", "vessel"}),
                              ("swing-shack", {"takomo", "vice", "lab", "avoda", "vessel"})):
            got = [story_suggestion.suggest(brand, d) for d in _days()]
            self.assertEqual({s["kind"] for s in got}, {"retail", "service"})
            self.assertTrue(expect <= {s["repost_from"]["id"] for s in got})
            for a, b in zip(got, got[1:]):
                self.assertNotEqual(a["kind"], b["kind"])

    def test_service_day_pairs_with_a_fitting_brand(self):
        seen = {}
        for d in _days():
            s = story_suggestion.suggest("swing-shack", d)
            if s["kind"] == "service":
                seen[s["feature"]] = s["repost_from"]["id"]
        self.assertEqual(seen["Putter fitting"], "lab")

    def test_same_day_same_answer_and_unknown_brand(self):
        d = date(2026, 10, 12)
        self.assertEqual(story_suggestion.suggest("stick", d), story_suggestion.suggest("stick", d))
        self.assertIsNone(story_suggestion.suggest("nope", d))


class SuggestionRouteTests(unittest.TestCase):
    def test_endpoint(self):
        os.environ.setdefault("COS_JOB_TOKEN", "t")
        import app as app_module

        app_module.COS_JOB_TOKEN = "t"
        c = app_module.app.test_client(cos_anon=True)
        self.assertEqual(c.get("/api/stories/suggestion").status_code, 401)
        r = c.get("/api/stories/suggestion", headers={"Authorization": "Bearer t"}).get_json()
        self.assertEqual({s["brand"] for s in r["suggestions"]}, {"swing-shack", "stick"})
        one = c.get("/api/stories/suggestion?brand=stick", headers={"Authorization": "Bearer t"}).get_json()
        self.assertEqual(len(one["suggestions"]), 1)


if __name__ == "__main__":
    unittest.main()
