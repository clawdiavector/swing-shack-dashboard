"""Stock-list suggestions on the month grid, the Different product swap, the daily
Psycho Bunny story and the stock story (2026-10-16)."""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import calendar_suggestions as cs  # noqa: E402
from _lib import story_suggestion  # noqa: E402
from _lib import stock_pulse as sp  # noqa: E402


def _line(name, reason="12 on the shelf against an alert level of 3", idea=""):
    return {"name": name, "reason": reason, "idea": idea, "status": "heavy", "qty": 12}


CANDS = [_line("Titleist Pro V1"), _line("Ping Anser 2D"), _line("FootJoy Pure Touch"), _line("Odyssey Rossie")]
TODAY = date(2026, 10, 16)


class StockItemsTests(unittest.TestCase):
    def _items(self, decisions=None, approved=(), taken=(), cands=CANDS, today=TODAY):
        return cs.stock_items("stick", "2026-10", cands, decisions or {}, list(approved), list(taken), today)

    def test_one_line_every_other_day_from_today(self):
        items = self._items()
        self.assertEqual([i["date"] for i in items], ["2026-10-16", "2026-10-18", "2026-10-20", "2026-10-22"])
        self.assertTrue(all(i["source"] == "stock" and i["kind"] == "stock" for i in items))
        self.assertEqual(items[0]["title"], "Titleist Pro V1")  # most urgent first

    def test_no_past_days_and_no_other_month(self):
        self.assertEqual(self._items(today=date(2026, 10, 30))[0]["date"], "2026-10-30")
        self.assertEqual(self._items(today=date(2026, 11, 2)), [])

    def test_days_taken_by_other_suggestions_are_skipped(self):
        dates = [i["date"] for i in self._items(taken=["2026-10-18"])]
        self.assertNotIn("2026-10-18", dates)
        self.assertIn("2026-10-16", dates)

    def test_rejected_approved_and_swapped_lines_are_left_out(self):
        decisions = {
            cs.stock_key("Titleist Pro V1", "2026-10"): {"decision": "rejected"},
            cs.stock_key("Ping Anser 2D", "2026-10"): {"decision": "swapped"},
        }
        titles = [i["title"] for i in self._items(decisions=decisions, approved=["FootJoy Pure Touch"])]
        self.assertEqual(titles, ["Odyssey Rossie"])

    def test_swap_gives_the_same_day_the_next_line(self):
        first = self._items()[0]
        decisions = {first["key"]: {"decision": "swapped"}}
        after = self._items(decisions=decisions)
        self.assertEqual(after[0]["date"], first["date"])
        self.assertEqual(after[0]["title"], "Ping Anser 2D")

    def test_each_month_has_its_own_key(self):
        self.assertNotEqual(cs.stock_key("Titleist Pro V1", "2026-10"), cs.stock_key("Titleist Pro V1", "2026-11"))

    def test_reason_and_idea_become_the_why(self):
        item = cs.stock_items("stick", "2026-10", [_line("X", "Unchanged at 9 for 30 days", "Show it.")],
                              {}, [], [], TODAY)[0]
        self.assertEqual(item["why"], "Unchanged at 9 for 30 days. Show it.")


class CandidatesTests(unittest.TestCase):
    def test_push_then_heavy_each_name_once(self):
        results = [
            {"name": "A", "status": "stuck", "not_for_feed": False, "days_still": 40, "qty": 5,
             "deep_shelf": False, "alert": None, "folded_into_range": False},
            {"name": "B", "status": "heavy", "not_for_feed": False, "days_still": 0, "qty": 30,
             "deep_shelf": True, "alert": 3, "folded_into_range": False},
            {"name": "A", "status": "heavy", "not_for_feed": False, "days_still": 0, "qty": 30,
             "deep_shelf": True, "alert": 3, "folded_into_range": False},
            {"name": "Drink", "status": "heavy", "not_for_feed": True, "days_still": 0, "qty": 99,
             "deep_shelf": True, "alert": 3, "folded_into_range": False},
        ]
        self.assertEqual([r["name"] for r in sp.candidates(results)], ["A", "B"])

    def test_no_saved_list_gives_no_candidates(self):
        self.assertEqual(sp.candidates([]), [])


class StockStoryTests(unittest.TestCase):
    def test_rotates_by_day_and_has_no_repost_link(self):
        a = story_suggestion.stock_story("stick", date(2026, 10, 16), CANDS)
        b = story_suggestion.stock_story("stick", date(2026, 10, 17), CANDS)
        self.assertEqual(a["kind"], "stock")
        self.assertIsNone(a["repost_from"])
        self.assertNotEqual(a["feature"], b["feature"])

    def test_nothing_without_a_list(self):
        self.assertIsNone(story_suggestion.stock_story("stick", date(2026, 10, 16), []))


class DailyPsychoBunnyTests(unittest.TestCase):
    def test_stick_features_psycho_bunny_every_day(self):
        for d in range(1, 61):
            day = date.fromordinal(date(2026, 10, 1).toordinal() + d)
            got = [s for s in story_suggestion.suggest("stick", day) if s["kind"] == "daily"]
            self.assertEqual(len(got), 1)
            self.assertEqual(got[0]["repost_from"]["id"], "psycho-bunny")

    def test_psycho_bunny_is_not_also_in_the_rotation(self):
        for d in range(1, 61):
            day = date.fromordinal(date(2026, 10, 1).toordinal() + d)
            for s in story_suggestion.suggest("stick", day):
                if s["kind"] != "daily":
                    self.assertNotEqual(s["repost_from"]["id"], "psycho-bunny")

    def test_swing_shack_has_no_daily_slot(self):
        for d in range(1, 31):
            day = date.fromordinal(date(2026, 10, 1).toordinal() + d)
            self.assertFalse(any(s["kind"] == "daily" for s in story_suggestion.suggest("swing-shack", day)))


if __name__ == "__main__":
    unittest.main()
