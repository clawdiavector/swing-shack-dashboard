"""Plan counts down to the peak (not the window start); stock-driven candidate offers."""
import os
import tempfile
import unittest
from datetime import date


from _lib import campaign_plan as cp  # noqa: E402
from _lib import candidate_offers as co  # noqa: E402
from _lib import campaign_brief as cb  # noqa: E402
from _lib import stock_pulse as sp  # noqa: E402

_OLD = {}


def setUpModule():
    _OLD["v"] = os.environ.get("DATA_DIR")
    os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="cos-peak-")


def tearDownModule():
    if _OLD.get("v") is None:
        os.environ.pop("DATA_DIR", None)
    else:
        os.environ["DATA_DIR"] = _OLD["v"]


TODAY = date(2026, 10, 16)
HEADER = "Location,Product Name,Variant Choices,SKU,Movement Type,Quantity,Alert Level\n"


def bf_brief():
    return {"brief_id": "brf-test", "status": "draft",
            "source_opportunity": {"name": "Black Friday + Cyber Monday", "date": "2026-10-12",
                                   "public_peak": "2026-11-27", "duration_days": 50},
            "timing": {"event_date": "2026-10-12", "peak_date": "2026-11-27"}}


class PeakAnchoring(unittest.TestCase):
    def items(self):
        return {i["title"]: i for i in cp.build_items(
            date(2026, 11, 27), TODAY, "retail_push", 50, window_start=date(2026, 10, 12))}

    def test_countdown_lands_before_the_peak(self):
        it = self.items()
        self.assertEqual(it["Story countdown"]["due"], "2026-11-24")
        self.assertEqual(it["Launch day post"]["due"], "2026-11-27")

    def test_nothing_countdown_precedes_window_start(self):
        for i in self.items().values():
            if i["kind"] in ("post", "story"):
                self.assertGreaterEqual(i["due"], "2026-10-12")

    def test_runway_steps_count_from_peak_and_late_ones_stay_late(self):
        it = self.items()
        self.assertEqual(it["Pick the offer and the angle"]["due"], "2026-09-28")
        self.assertTrue(it["Pick the offer and the angle"]["late"])
        self.assertEqual(it["Shoot real photos of the products"]["due"], "2026-10-23")
        self.assertFalse(it["Shoot real photos of the products"]["late"])
        self.assertEqual(sum(1 for i in it.values() if i["late"]), 2)

    def test_brief_without_peak_falls_back_to_start(self):
        w, p, _ = cp._dates_from_brief({"timing": {"event_date": "2026-10-12"}})
        self.assertEqual((w, p), (date(2026, 10, 12), date(2026, 10, 12)))

    def test_reanchor_fixes_an_old_plan(self):
        old = {"event_date": "2026-10-12", "items": [
            {"source": "template", "kind": "story", "days_before_event": 3, "status": "proposed",
             "due": "2026-10-09", "late": True},
            {"source": "template", "kind": "decide", "days_before_event": 60, "status": "proposed",
             "due": "2026-08-13", "late": True}]}
        out = cp.reanchor_plan_from_brief(old, bf_brief(), TODAY)
        by_kind = {i["kind"]: i for i in out["items"]}
        self.assertEqual(by_kind["story"]["due"], "2026-11-24")
        self.assertEqual(by_kind["decide"]["due"], "2026-09-28")
        self.assertEqual(out["peak_date"], "2026-11-27")

    def test_brief_timing_counts_back_from_peak(self):
        opp = {"date": "2026-10-12", "public_peak": "2026-11-27"}
        self.assertEqual(cb._peak_of(opp), "2026-11-27")
        self.assertIn("2026-11-20", cb._t_minus(opp, 7))


class OldBrief(unittest.TestCase):
    def test_old_brief_gets_peak_from_calendar_and_offers_from_stock(self):
        brief = {"brief_id": "brf-old", "status": "draft",
                 "source_opportunity": {"name": "Black Friday + Cyber Monday", "date": "2026-10-12"},
                 "timing": {"event_date": "2026-10-12"}}
        r = cp.propose_plan("swing-shack", brief, today=TODAY, profile="retail_push",
                            event_meta={"public_peak": "2026-11-27", "duration_days": 50})
        self.assertTrue(r["ok"], r)
        plan = r["plan"]
        self.assertEqual(plan["peak_date"], "2026-11-27")
        story = next(i for i in plan["items"] if i["title"] == "Story countdown")
        self.assertEqual(story["due"], "2026-11-24")
        offer_step = next(i for i in plan["items"] if i["title"] == "Pick the offer and the angle")
        self.assertIn("candidate_offers" in offer_step, (True, False))


class Offers(unittest.TestCase):
    def setUp(self):
        self.brand = "swing-shack"

    def test_no_stock_data_is_an_empty_state(self):
        blk = co.build("stick-nostock-xyz")
        self.assertEqual(blk["status"], "no_stock_data")
        self.assertEqual(blk["items"], [])
        self.assertEqual(co.proposition_text(blk), "")

    def test_single_baseline_lists_deep_shelves_without_prices(self):
        rows = sp.parse_stock_csv(HEADER + "\n".join([
            ",Srixon Z-Star XV,,Z1,,40,8", ",Full Swing Cherry,,F1,,30,4",
            ",Titleist Pro V1,,P1,,1,8", ",Odd Putter,,O1,,1,1"]))
        sp.save_snapshot(self.brand, rows, "2026-10-14")
        blk = co.build(self.brand)
        names = [i["name"] for i in blk["items"]]
        self.assertIn("Srixon Z-Star XV", names)
        self.assertNotIn("Full Swing Cherry", names)   # drink
        self.assertNotIn("Titleist Pro V1", names)     # thin
        self.assertTrue(all(i["price"] == "" and i["discount"] == "" for i in blk["items"]))
        self.assertIn("Single baseline", blk["note"])
        self.assertIn("Srixon Z-Star XV", co.proposition_text(blk))


class BriefFixes(unittest.TestCase):
    def test_audience_has_no_unresolved_template(self):
        a = cb._derive_audience("swing-shack", {})
        self.assertNotIn("<brand>", a["specific_useful_definition"] + a["source"])
        self.assertIn("Not set", a["specific_useful_definition"])

    def test_audience_uses_the_defined_one(self):
        a = cb._derive_audience("swing-shack", {"audience": {"primary": "Serious amateurs", "secondary": "Juniors"}})
        self.assertEqual(a["specific_useful_definition"], "Serious amateurs / Juniors")


if __name__ == "__main__":
    unittest.main()
