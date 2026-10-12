"""
Plan shows the operator's important dates and the scout's picks.

Found in the 2026-10-09 audit: the ~78 dates Christelle listed on
2026-09-29 reached only the Month grid, and agent suggestions never
reached Plan at all.

Run: python -m pytest campaign-os/tests/test_plan_extras.py
"""

import datetime as dt
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "campaign-os"))

import patch_important_dates_v211 as listed  # noqa: E402
from _lib.plan_extras import dates_to_note, scout_suggestions, tier_of  # noqa: E402

START = dt.date(2026, 10, 9)
END = dt.date(2027, 12, 31)
ALL_DATES = (
    listed.DATES_2026 + listed.DATES_2027 + listed.GOLF_MOMENTS_2026 + listed.GOLF_MOMENTS_2027
)


def _names(rows):
    return " | ".join(r["name"] for r in rows)


class DatesToNote(unittest.TestCase):
    def test_stick_sees_the_listed_dates_with_local_ones_marked(self):
        rows = dates_to_note("stick", ALL_DATES, START, END)
        names = _names(rows)
        for expected in ("Boland Park", "Wildeklawer", "Springboks", "Nedbank", "Cape Epic"):
            self.assertIn(expected, names)
        boland = next(r for r in rows if "SA v England ODI, Boland Park" in r["name"])
        self.assertTrue(boland["local"])
        self.assertTrue(boland["note_only"])
        self.assertEqual(boland["tier"], "A-PIN")
        self.assertEqual(boland["start"], "2027-01-10")
        self.assertEqual([r["start"] for r in rows], sorted(r["start"] for r in rows))

    def test_swing_shack_does_not_get_paarl_dates(self):
        rows = dates_to_note("swing-shack", ALL_DATES, START, END)
        names = _names(rows).lower()
        self.assertTrue(rows)
        for western_cape in ("paarl", "boland", "wildeklawer", "cape epic"):
            self.assertNotIn(western_cape, names)
        self.assertIn("springboks", names)
        self.assertFalse(any(r["local"] for r in rows))

    def test_a_date_already_on_the_calendar_is_not_repeated(self):
        plain = dates_to_note("stick", ALL_DATES, START, END)
        self.assertIn("Halloween", [r["name"] for r in plain])
        deduped = dates_to_note(
            "stick", ALL_DATES, START, END,
            already_named=["Halloween", "Black Friday + Cyber Monday"],
        )
        left = [r["name"] for r in deduped]
        self.assertNotIn("Halloween", left)
        self.assertNotIn("Black Friday", left)

    def test_dates_outside_the_window_are_left_out(self):
        rows = dates_to_note("stick", ALL_DATES, dt.date(2027, 3, 1), dt.date(2027, 3, 31))
        self.assertTrue(rows)
        self.assertTrue(all(r["end"] >= "2027-03-01" and r["start"] <= "2027-03-31" for r in rows))

    def test_tier_is_read_from_the_operators_note(self):
        self.assertEqual(tier_of("A-LOCAL tier Paarl sport; Proteas fixture."), "A-PIN")
        self.assertEqual(tier_of("B/C-tier shopping."), "B-PIN")
        self.assertEqual(tier_of("Rugby. Tier B."), "B-PIN")
        self.assertIsNone(tier_of("Humour-only moment per operator."))


class ScoutSuggestions(unittest.TestCase):
    TODAY = dt.date(2026, 10, 9)

    def test_probe_test_past_and_undated_rows_are_dropped(self):
        records = [
            {"calendar_id": "a", "title": "probe-cleanup", "event_date": "2026-12-31"},
            {"calendar_id": "b", "title": "TEST — DO NOT RELEASE", "event_date": "2026-10-13"},
            {"calendar_id": "c", "title": "Old tournament", "event_date": "2026-09-01"},
            {"calendar_id": "d", "title": "No date yet"},
            {"calendar_id": "e", "title": "Black Friday South Africa 2026", "event_date": "2026-11-27"},
            {"calendar_id": "f", "title": "TGL season opener", "event_start": "2026-12-28"},
        ]
        picks, count = scout_suggestions(records, self.TODAY)
        self.assertEqual([p["candidate_id"] for p in picks], ["e", "f"])
        self.assertEqual(count, 2)

    def test_repeats_of_a_title_are_listed_once_and_the_limit_holds(self):
        records = [
            {"calendar_id": f"r{i}", "title": "TGL season opener", "event_date": "2026-12-28"}
            for i in range(3)
        ] + [
            {"calendar_id": f"u{i}", "title": f"Moment {i}", "event_date": f"2026-11-{i + 10:02d}"}
            for i in range(8)
        ]
        picks, count = scout_suggestions(records, self.TODAY, limit=5)
        self.assertEqual(count, 9)
        self.assertEqual(len(picks), 5)
        self.assertEqual(picks[0]["title"], "Moment 0")


class SameEventTests(unittest.TestCase):
    def _row(self, name):
        return {"event_name": name, "start_date": "2026-11-01", "event_type": "SHOPPING"}

    def test_a_longer_name_holding_the_calendars_name_is_still_the_same_event(self):
        out = dates_to_note("stick", [self._row("Black Friday + Cyber Monday")], START, END,
                            already_named=["Black Friday"])
        self.assertEqual(out, [])

    def test_a_short_name_does_not_hide_other_dates(self):
        out = dates_to_note("stick", [self._row("Easter Monday"), self._row("Open Day")], START, END,
                            already_named=["Easter", "Fathers Day"])
        self.assertEqual({e["name"] for e in out}, {"Easter Monday", "Open Day"})


if __name__ == "__main__":
    unittest.main()
