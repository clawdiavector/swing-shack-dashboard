"""Stories settings: clamping, daily Psycho Bunny on/off, stock story count and month-grid spacing (2026-10-19)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import story_settings as ss  # noqa: E402
from _lib import story_suggestion as sug  # noqa: E402
from _lib import calendar_suggestions as cs  # noqa: E402

_SAVED_DATA_DIR = os.environ.get("DATA_DIR")


def setUpModule():
    # Own data folder for this module only; restored afterwards so other tests are unaffected.
    os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="cos-story-settings-")


def tearDownModule():
    if _SAVED_DATA_DIR is None:
        os.environ.pop("DATA_DIR", None)
    else:
        os.environ["DATA_DIR"] = _SAVED_DATA_DIR


STICK_DAILY = ["psycho-bunny"]
DAY = date(2026, 10, 19)


def _line(name):
    return {"name": name, "reason": "", "idea": ""}


class CleanTests(unittest.TestCase):
    def test_defaults_when_nothing_saved(self):
        got = ss.clean({}, STICK_DAILY)
        self.assertEqual(got, {"daily_on": {"psycho-bunny": True}, "stock_stories": 1, "stock_every_days": 2})

    def test_out_of_range_values_are_clamped(self):
        got = ss.clean({"stock_stories": 9, "stock_every_days": 0}, STICK_DAILY)
        self.assertEqual((got["stock_stories"], got["stock_every_days"]), (3, 1))
        got = ss.clean({"stock_stories": -4, "stock_every_days": 99}, STICK_DAILY)
        self.assertEqual((got["stock_stories"], got["stock_every_days"]), (0, 7))

    def test_nonsense_falls_back_to_default(self):
        got = ss.clean({"stock_stories": "lots", "stock_every_days": None}, STICK_DAILY)
        self.assertEqual((got["stock_stories"], got["stock_every_days"]), (1, 2))

    def test_daily_on_only_keeps_known_daily_brands(self):
        got = ss.clean({"daily_on": {"psycho-bunny": False, "takomo": False}}, STICK_DAILY)
        self.assertEqual(got["daily_on"], {"psycho-bunny": False})


class WriteReadTests(unittest.TestCase):
    def test_write_then_read_round_trip_and_partial_update(self):
        ss.write("stick", {"stock_stories": 2, "daily_on": {"psycho-bunny": False}}, STICK_DAILY)
        got = ss.read("stick", STICK_DAILY)
        self.assertEqual((got["stock_stories"], got["daily_on"]["psycho-bunny"]), (2, False))
        ss.write("stick", {"stock_every_days": 5}, STICK_DAILY)
        got = ss.read("stick", STICK_DAILY)
        self.assertEqual((got["stock_stories"], got["stock_every_days"]), (2, 5))


class SuggestHonoursSettingsTests(unittest.TestCase):
    def test_psycho_bunny_gone_when_switched_off(self):
        off = {"daily_on": {"psycho-bunny": False}}
        self.assertFalse(any(s["kind"] == "daily" for s in sug.suggest("stick", DAY, off)))

    def test_psycho_bunny_back_when_on(self):
        on = {"daily_on": {"psycho-bunny": True}}
        self.assertTrue(any(s["kind"] == "daily" for s in sug.suggest("stick", DAY, on)))


class StockStoriesCountTests(unittest.TestCase):
    CANDS = [_line("A"), _line("B"), _line("C")]

    def test_count_is_respected(self):
        self.assertEqual(len(sug.stock_stories("stick", DAY, self.CANDS, 0)), 0)
        self.assertEqual(len(sug.stock_stories("stick", DAY, self.CANDS, 2)), 2)

    def test_never_more_than_there_are_lines(self):
        self.assertEqual(len(sug.stock_stories("stick", DAY, self.CANDS, 3)), 3)
        self.assertEqual(len(sug.stock_stories("stick", DAY, [_line("A")], 3)), 1)

    def test_two_stories_are_different_lines(self):
        got = sug.stock_stories("stick", DAY, self.CANDS, 2)
        self.assertNotEqual(got[0]["feature"], got[1]["feature"])


class MonthSpacingTests(unittest.TestCase):
    def test_every_day_spacing(self):
        items = cs.stock_items("stick", "2026-10", [_line("A"), _line("B")], {}, [], [],
                               date(2026, 10, 1), every=1)
        self.assertEqual([i["date"] for i in items], ["2026-10-01", "2026-10-02"])

    def test_every_five_days(self):
        items = cs.stock_items("stick", "2026-10", [_line("A"), _line("B")], {}, [], [],
                               date(2026, 10, 1), every=5)
        self.assertEqual([i["date"] for i in items], ["2026-10-01", "2026-10-06"])


if __name__ == "__main__":
    unittest.main()
