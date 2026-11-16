"""Feed rotation for stock suggestions (2026-11-02): each line gets a job, jobs and makers
take turns, no Mondays, new stock is announced, and a product featured in the last four
weeks is not offered again."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import calendar_suggestions as cs  # noqa: E402
from _lib import stock_pulse as sp  # noqa: E402


def _line(name, status="heavy"):
    return {"name": name, "reason": "", "idea": "", "status": status, "qty": 12}


class JobTests(unittest.TestCase):
    def test_job_follows_stock_status(self):
        self.assertEqual(cs.feed_job(_line("A", "new")), "new_in")
        self.assertEqual(cs.feed_job(_line("A", "back")), "new_in")
        self.assertEqual(cs.feed_job(_line("A", "stuck")), "move_pile")
        self.assertEqual(cs.feed_job(_line("A", "still")), "move_pile")
        self.assertEqual(cs.feed_job(_line("A", "heavy")), "tip")
        self.assertEqual(cs.feed_job(_line("A", "steady")), "tip")

    def test_items_carry_job_label_and_best_time(self):
        cands = [_line("Vice Pro Air", "new"), _line("Ping Anser 2D", "stuck"), _line("Odyssey Rossie", "heavy")]
        items = cs.stock_items("stick", "2026-10", cands, {}, [], [], date(2026, 10, 16))
        got = {i["title"]: (i["job"], i["job_label"], i["best_time"]) for i in items}
        self.assertEqual(got["Vice Pro Air"], ("new_in", "New in", "09:00-12:00"))
        self.assertEqual(got["Ping Anser 2D"], ("move_pile", "Move the pile", "after 18:00"))
        self.assertEqual(got["Odyssey Rossie"], ("tip", "Tip with a product", "09:00-12:00"))


class RotationTests(unittest.TestCase):
    def test_jobs_and_makers_take_turns(self):
        cands = [
            _line("Titleist Pro V1", "stuck"),
            _line("Titleist Pro V1x", "stuck"),
            _line("Ping Anser 2D", "heavy"),
            _line("Vice Pro Air", "new"),
        ]
        order = [c["name"] for c in cs.rotate_feed(cands)]
        self.assertEqual(order, ["Titleist Pro V1", "Ping Anser 2D", "Titleist Pro V1x", "Vice Pro Air"])

    def test_nothing_is_lost_when_no_turn_is_possible(self):
        cands = [_line("Titleist A", "stuck"), _line("Titleist B", "stuck"), _line("Titleist C", "stuck")]
        self.assertEqual([c["name"] for c in cs.rotate_feed(cands)], ["Titleist A", "Titleist B", "Titleist C"])

    def test_same_category_does_not_follow_itself(self):
        cands = [
            {**_line("Titleist Pro V1"), "category": "balls"},
            {**_line("Srixon Z-Star"), "category": "balls"},
            {**_line("Ping Anser 2D"), "category": "putters"},
        ]
        order = [c["name"] for c in cs.rotate_feed(cands)]
        self.assertEqual(order, ["Titleist Pro V1", "Ping Anser 2D", "Srixon Z-Star"])


class DayTests(unittest.TestCase):
    def test_no_stock_suggestion_on_a_monday(self):
        cands = [_line(n) for n in ("Titleist Pro V1", "Ping Anser 2D", "Odyssey Rossie", "Vice Pro Air",
                                    "FootJoy Pure Touch", "Srixon Z-Star", "Mileseey Pro", "Takomo 301")]
        items = cs.stock_items("stick", "2026-11", cands, {}, [], [], date(2026, 11, 2))  # a Monday
        dates = [date.fromisoformat(i["date"]) for i in items]
        self.assertTrue(dates)
        self.assertTrue(all(d.weekday() != 0 for d in dates))
        self.assertEqual(dates[0], date(2026, 11, 4))

    def test_recent_products_are_left_out(self):
        cands = [_line("Titleist Pro V1"), _line("Ping Anser 2D")]
        items = cs.stock_items("stick", "2026-10", cands, {}, [], [], date(2026, 10, 16),
                               recent_titles=["Titleist Pro V1"])
        self.assertEqual([i["title"] for i in items], ["Ping Anser 2D"])


class BundleTests(unittest.TestCase):
    def test_product_posted_last_month_waits_four_weeks(self):
        posts = {"2026-10": {"2026-10-20": [{"title": "Titleist Pro V1", "state": "posted"}]}}
        original = cs.posts_by_day_for_month
        cs.posts_by_day_for_month = lambda brand_id, month: posts.get(month, {})
        try:
            bundle = cs.month_suggestions_bundle(
                "stick", "2026-11", date(2026, 11, 3), [], lambda r: False, [], {}, [],
                [_line("Titleist Pro V1"), _line("Ping Anser 2D")], 2,
            )
        finally:
            cs.posts_by_day_for_month = original
        titles = [i["title"] for i in bundle["items"] if i["source"] == "stock"]
        self.assertNotIn("Titleist Pro V1", titles)
        self.assertIn("Ping Anser 2D", titles)
        self.assertEqual(bundle["posts_by_day"], {})  # the look-back is not drawn on this month


class FeedCandidateTests(unittest.TestCase):
    def _r(self, name, status, **kw):
        base = {"name": name, "status": status, "not_for_feed": False, "folded_into_range": False,
                "deep_shelf": False, "days_still": 0, "qty": 5, "alert": 2}
        return {**base, **kw}

    def test_new_and_back_lines_are_announced_first(self):
        results = [
            self._r("Stuck One", "stuck", days_still=40),
            self._r("New One", "new"),
            self._r("Back One", "back"),
            self._r("Water", "new", not_for_feed=True),
        ]
        self.assertEqual([r["name"] for r in sp.feed_candidates(results)], ["New One", "Back One", "Stuck One"])


if __name__ == "__main__":
    unittest.main()
