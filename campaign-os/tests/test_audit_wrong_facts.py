"""
Regression tests for the wrong facts found in the 2026-10-09 audit.

- A Google Business post mixed three partner brands: a Vessel headline, an
  L.A.B Golf link and #TakomoAtStick.
- Generated headlines called every brand's audience "Johannesburg golfers".
  Stick is in Paarl.
- Stick's 2027 calendar had Heritage Day on Women's Day, and called the
  Ryder Cup a major.

Run: python -m pytest campaign-os/tests/test_audit_wrong_facts.py
"""

import json
import sys
import unittest
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "campaign-os"))

from _lib import gbp_daily_poster as gbp  # noqa: E402
from _lib import intelligence  # noqa: E402


class GbpOnePartnerBrandPerPost(unittest.TestCase):
    KEYWORDS = [
        "takomo paarl", "club fitting paarl", "golf lessons paarl", "vice golf balls",
        "psycho bunny golf", "l.a.b putter fitting", "golf shop paarl", "golf bag",
    ]

    def test_composed_posts_never_mix_partner_brands(self):
        composed = 0
        for day in range(1, 29):
            for keyword in self.KEYWORDS:
                post = gbp.compose_post("stick", keyword, f"2026-10-{day:02d}")
                if "error" in post:
                    continue
                composed += 1
                subject = gbp.partner_brands_in(post["keyword"], post["headline_source"])
                extras = gbp.partner_brands_in(post["cta"], post["cta_url"], *post["hashtags"])
                self.assertLessEqual(extras, subject, post)
        self.assertGreater(composed, 100)

    def test_keyword_brand_is_not_swapped_for_another(self):
        for day in range(1, 29):
            post = gbp.compose_post("stick", "takomo paarl", f"2026-10-{day:02d}")
            named = gbp.partner_brands_in(post["headline_source"], post["cta"], post["cta_url"])
            self.assertLessEqual(named, {"takomo"}, post)

    def test_integrity_check_rejects_the_audited_post(self):
        post = {
            "keyword": "takomo paarl",
            "headline_source": "Vessel. The bag that earns its place.",
            "title": "Vessel. The bag that earns its place.",
            "body": "takomo paarl, explained. Or fixed. We do both.",
            "cta": "See why L.A.B Golf earned its place",
            "cta_url": "https://stickgolf.co.za/l-a-b-golf-at-stick/",
            "hashtags": ["#TakomoAtStick", "#BetterBeginsHere"],
        }
        ok, violations = gbp.integrity_check(post, "stick")
        self.assertFalse(ok)
        self.assertIn("mixed_partner_brand:lab", violations)


class HeadlinesNameNoCity(unittest.TestCase):
    def test_generated_headlines_have_no_johannesburg(self):
        pool = {
            "golf_news": [{"title": f"news {i}"} for i in range(5)],
            "reddit_pain_points": [{"pain_point": f"pain {i}"} for i in range(5)],
        }
        original = intelligence._signal_pool
        intelligence._signal_pool = lambda: pool
        try:
            headlines = [h["headline"] for h in intelligence.generate_headlines(10)["headlines"]]
        finally:
            intelligence._signal_pool = original
        self.assertTrue(headlines)
        for headline in headlines:
            self.assertNotRegex(headline, r"(?i)johannesburg|jhb|joburg")
            self.assertEqual(headline[0], headline[0].upper())


class Stick2027Calendar(unittest.TestCase):
    def setUp(self):
        path = REPO / "data" / "brand-planning" / "stick-events-2027.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.events = {e["id"]: e for e in doc["events"]}

    def test_heritage_day_is_24_september(self):
        event = self.events["heritage-day-2027"]
        self.assertEqual(event["start"], "2027-09-24")
        self.assertEqual(event["public_peak"], "2027-09-24")
        self.assertEqual(date.fromisoformat(event["start"]).strftime("%a"), "Fri")
        self.assertIn("Fri 24 Sep 2027", event["name"])

    def test_ryder_cup_is_not_called_a_major(self):
        push = self.events["ryder-cup-2027"]["commercial_push"]
        self.assertNotIn("Odd-year Major", push)
        self.assertIn("not a major", push)


if __name__ == "__main__":
    unittest.main()
