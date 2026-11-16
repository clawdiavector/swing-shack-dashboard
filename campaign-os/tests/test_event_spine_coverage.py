"""Every brand has an A/B/C date list for this year and next.

Swing Shack had no 2027 list and Bag Drop had none at all (found 9 Nov 2026),
so their dates never showed a tier and could not be planned from the spine."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib import campaign_brief as cb  # noqa: E402

PLANNING = Path(__file__).resolve().parents[2] / "data" / "brand-planning"
BRANDS = ("stick", "swing-shack", "bag-drop")
YEARS = (2026, 2027)
TIERS = {"A-PIN", "B-PIN", "C-PIN"}


def _load(brand, year):
    return json.loads((PLANNING / f"{brand}-events-{year}.json").read_text(encoding="utf-8"))


class SpineCoverage(unittest.TestCase):
    def test_every_brand_has_both_years(self):
        for brand in BRANDS:
            for year in YEARS:
                with self.subTest(brand=brand, year=year):
                    self.assertTrue((PLANNING / f"{brand}-events-{year}.json").is_file())

    def test_events_are_well_formed(self):
        for brand in BRANDS:
            for year in YEARS:
                events = _load(brand, year)["events"]
                self.assertTrue(events, f"{brand} {year} has no events")
                ids = [e["id"] for e in events]
                self.assertEqual(len(ids), len(set(ids)), f"{brand} {year} repeats an id")
                for e in events:
                    with self.subTest(brand=brand, year=year, id=e["id"]):
                        self.assertTrue(e["id"].endswith(str(year)))
                        self.assertIn(e["tier"], TIERS)
                        self.assertTrue(e["name"].strip())
                        start = dt.date.fromisoformat(e["start"])
                        end = dt.date.fromisoformat(e["end"])
                        self.assertLessEqual(start, end)
                        self.assertEqual(start.year, year)

    def test_each_new_list_has_every_tier(self):
        for brand, year in (("swing-shack", 2027), ("bag-drop", 2026), ("bag-drop", 2027)):
            tiers = {e["tier"] for e in _load(brand, year)["events"]}
            self.assertEqual(tiers, TIERS, f"{brand} {year}")

    def test_bag_drop_is_an_online_store(self):
        # Bag Drop sells demo and pre-owned gear online; it offers no fitting or
        # coaching, and the old "drop your bag at Swing Shack" service is not real.
        for year in YEARS:
            for e in _load("bag-drop", year)["events"]:
                with self.subTest(year=year, id=e["id"]):
                    self.assertNotIn("fitting", e.get("pillars", {}))
                    self.assertNotIn("coaching", e.get("pillars", {}))
                    text = json.dumps(e).lower()
                    self.assertNotIn("swingshack.co.za", text)
                    self.assertNotIn("thursday social", text)

    def test_new_dates_resolve_for_a_plan(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(cb, "DATA_DIR_DEFAULT", tmp), \
                patch.object(cb, "get_brief_opportunities", return_value=[]):
            for brand, key in (("swing-shack", "black-friday-2027"),
                               ("bag-drop", "black-friday-2026"),
                               ("bag-drop", "fathers-day-2027")):
                with self.subTest(brand=brand, key=key):
                    self.assertEqual(cb._resolve_opportunity(brand, key)["event_key"], key)


if __name__ == "__main__":
    unittest.main()
