"""Weekly stock list -> feed time: snapshots, still/heavy/thin, photo matching."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cos-stock-"))

from _lib import stock_pulse as sp  # noqa: E402

HEADER = "Location,Product Name,Variant Choices,SKU,Movement Type,Quantity,Alert Level\n"


def snap(date, *lines):
    return {"date": date, "rows": sp.parse_stock_csv(HEADER + "\n".join(lines))}


def row(name, sku, qty, alert="", variant=""):
    return f",{name},{variant},{sku},,{qty},{alert}"


def by_name(results):
    return {r["name"]: r for r in results}


class ParseTests(unittest.TestCase):
    def test_excel_sep_line_is_dropped(self):
        rows = sp.parse_stock_csv("sep=,\n" + HEADER + row("Ball A", "A1", 5, 2))
        self.assertEqual([r["name"] for r in rows], ["Ball A"])

    def test_bom_and_sep(self):
        rows = sp.parse_stock_csv("﻿sep=,\n" + HEADER + row("Ball A", "A1", 5, 2))
        self.assertEqual(len(rows), 1)

    def test_importer_recognises_file_with_sep_line(self):
        from _lib.stock_importer import preview_smart_import
        out = preview_smart_import("sep=,\n" + HEADER + row("Ball A", "A1", 5, 2), store_brand="swing-shack")
        self.assertTrue(out["format_recognised"])


class StatusTests(unittest.TestCase):
    def test_single_snapshot_statuses(self):
        res = by_name(sp.analyse([snap(
            "2026-10-14",
            row("Out Ball", "O1", 0, 8),
            row("Bad Count", "B1", -1, 6),
            row("Thin Ball", "T1", 6, 8),
            row("Deep Ball", "D1", 40, 8),
            row("One Off Putter", "P1", 1, 1),
            row("SS Still water", "W1", 0, 20),
        )]))
        self.assertEqual(res["Out Ball"]["status"], "out")
        self.assertEqual(res["Bad Count"]["status"], "error")
        self.assertEqual(res["Thin Ball"]["status"], "low")
        self.assertEqual(res["Deep Ball"]["status"], "heavy")
        self.assertGreater(res["Deep Ball"]["feed_boost"], 0)
        self.assertLess(res["Thin Ball"]["feed_boost"], 0)
        # an alert level of 1 is how a one-off is held, not a reorder trigger
        self.assertEqual(res["One Off Putter"]["status"], "steady")
        self.assertTrue(res["SS Still water"]["not_for_feed"])

    def test_variants_roll_up_and_name_thin_sizes(self):
        res = by_name(sp.analyse([snap(
            "2026-10-14",
            row("Glove", "G-S", 0, 3, "Small"),
            row("Glove", "G-M", 8, 3, "Medium"),
            row("Glove", "G-L", 2, 3, "Large"),
        )]))
        self.assertEqual(res["Glove"]["qty"], 10)
        self.assertEqual(res["Glove"]["thin_variants"], ["Small", "Large"])

    def test_still_and_stuck_need_history(self):
        history = [
            snap("2026-09-16", row("Stuck Ball", "S1", 20, 8), row("Moving Ball", "M1", 20, 8),
                 row("Still Ball", "T1", 20, 8)),
            snap("2026-09-30", row("Stuck Ball", "S1", 20, 8), row("Moving Ball", "M1", 15, 8),
                 row("Still Ball", "T1", 18, 8)),
            snap("2026-10-14", row("Stuck Ball", "S1", 20, 8), row("Moving Ball", "M1", 12, 8),
                 row("Still Ball", "T1", 18, 8), row("Fresh Ball", "F1", 10, 4)),
        ]
        res = by_name(sp.analyse(history))
        self.assertEqual(res["Stuck Ball"]["status"], "stuck")
        self.assertEqual(res["Stuck Ball"]["days_still"], 28)
        self.assertEqual(res["Still Ball"]["status"], "still")
        self.assertEqual(res["Still Ball"]["days_still"], 14)
        self.assertEqual(res["Moving Ball"]["status"], "selling")
        self.assertEqual(res["Fresh Ball"]["status"], "new")
        self.assertEqual([r["name"] for r in sp.push_list(list(res.values()))], ["Stuck Ball", "Still Ball"])

    def test_single_snapshot_never_claims_still(self):
        res = sp.analyse([snap("2026-10-14", row("Ball", "B1", 20, 8))])
        self.assertEqual(sp.push_list(res), [])


class StampTests(unittest.TestCase):
    def test_record_and_stamp_writes_boost_onto_catalog(self):
        brand = "stamp-test"
        sp.save_snapshot(brand, sp.parse_stock_csv(HEADER + row("Ball", "B1", 20, 8)), "2026-09-16")
        products = [{"sku": "B1", "name": "Ball"}, {"sku": "ZZ", "name": "Not in file"}]
        out = sp.record_and_stamp(brand, HEADER + row("Ball", "B1", 20, 8), products, on="2026-10-14")
        self.assertEqual(out["snapshots"], 2)
        self.assertEqual(products[0]["stock_status"], "stuck")
        self.assertEqual(products[0]["feed_boost"], sp.FEED_BOOST["stuck"])
        self.assertNotIn("feed_boost", products[1])


class ExclusionTests(unittest.TestCase):
    def test_drinks_food_and_fitting_parts_are_left_out(self):
        for name in ["Full Swing Cherry Pop", "SS Still water", "Mitsubishi Tensei White",
                     "Fujikura speeder Driver Shafts", "Biltong Pack"]:
            self.assertTrue(sp.excluded_reason(name), name)

    def test_sold_as_is_stays_in_including_putters_with_a_shaft_name(self):
        for name in ["L.A.B Putter: Link 2.2 Accra Shaft", "Srixon Z- Star XV", "GripDrip Zen Swing Grip - Sky"]:
            self.assertEqual(sp.excluded_reason(name), "", name)

    def test_excluded_never_pushed_or_boosted(self):
        history = [snap("2026-09-16", row("Full Swing Cherry Pop", "D1", 20, 6)),
                   snap("2026-10-14", row("Full Swing Cherry Pop", "D1", 20, 6))]
        res = sp.analyse(history)
        self.assertEqual(sp.push_list(res), [])
        self.assertEqual(res[0]["feed_boost"], 0)
        self.assertEqual(sp.heavy_shelf(res), [])


class RangeAndNewTests(unittest.TestCase):
    GRIPS = [("GripDrip Zen Swing Grip - Sky", "Z1"), ("GripDrip Zen Swing Grip - Plum", "Z2"),
             ("GripDrip Par 3 Swing Grip", "P3")]

    def week(self, date, qtys, extra=()):
        lines = [row(n, k, q, "") for (n, k), q in zip(self.GRIPS, qtys)]
        return snap(date, *lines, *extra)

    def test_grips_fold_into_one_brand_range(self):
        res = sp.analyse([self.week("2026-10-14", [15, 15, 8])])
        ranges = [r for r in res if r.get("is_range")]
        self.assertEqual([r["name"] for r in ranges], ["GripDrip grips"])
        self.assertEqual(ranges[0]["qty"], 38)
        self.assertEqual(sp.push_list(res), [])
        self.assertTrue(all(r.get("folded_into_range") for r in res if r["name"].startswith("GripDrip Zen")))

    def test_range_goes_still_as_a_whole(self):
        res = sp.analyse([self.week("2026-09-16", [15, 15, 8]), self.week("2026-09-30", [15, 15, 8]),
                          self.week("2026-10-14", [15, 15, 8])])
        rng = next(r for r in res if r.get("is_range"))
        self.assertEqual(rng["status"], "stuck")
        self.assertEqual([r["name"] for r in sp.push_list(res)], ["GripDrip grips"])

    def test_one_colourway_selling_keeps_range_moving(self):
        res = sp.analyse([self.week("2026-09-16", [15, 15, 8]), self.week("2026-10-14", [12, 15, 8])])
        rng = next(r for r in res if r.get("is_range"))
        self.assertEqual(rng["status"], "steady")

    def test_new_line_is_announced_then_ages_out(self):
        base = [self.week("2026-09-16", [15, 15, 8]), self.week("2026-09-30", [15, 15, 8],
                [row("Titleist Pro V2 2026", "NEW1", 12, 4)])]
        res = {r["name"]: r for r in sp.analyse(base)}
        self.assertEqual(res["Titleist Pro V2 2026"]["status"], "new")
        self.assertGreater(res["Titleist Pro V2 2026"]["feed_boost"], 0)
        later = base + [self.week("2026-10-28", [15, 15, 8], [row("Titleist Pro V2 2026", "NEW1", 12, 4)]),
                        self.week("2026-11-18", [15, 15, 8], [row("Titleist Pro V2 2026", "NEW1", 12, 4)])]
        res = {r["name"]: r for r in sp.analyse(later)}
        self.assertNotEqual(res["Titleist Pro V2 2026"]["status"], "new")

    def test_new_colourway_marks_the_range_new(self):
        res = sp.analyse([self.week("2026-09-16", [15, 15, 8]),
                          self.week("2026-10-14", [15, 15, 8], [row("GripDrip Zen Swing Grip - Mint", "Z9", 7)])])
        rng = next(r for r in res if r.get("is_range"))
        self.assertEqual(rng["status"], "new")

    def test_first_list_marks_nothing_new(self):
        res = sp.analyse([self.week("2026-10-14", [15, 15, 8])])
        self.assertFalse([r for r in res if r["status"] == "new"])

    def test_back_in_stock(self):
        res = sp.analyse([snap("2026-09-16", row("Ball", "B1", 0, 8)), snap("2026-10-14", row("Ball", "B1", 20, 8))])
        self.assertEqual(res[0]["status"], "back")

    def test_stamp_gives_every_colourway_the_range(self):
        brand = "range-stamp"
        lines = [row(n, k, q) for (n, k), q in zip(self.GRIPS, [15, 15, 8])]
        csv = HEADER + chr(10).join(lines)
        products = [{"sku": k, "name": n} for n, k in self.GRIPS]
        sp.record_and_stamp(brand, csv, products, on="2026-10-14")
        self.assertTrue(all(p["range_name"] == "GripDrip grips" for p in products))


class PhotoTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="cos-photos-"))
        for n in ["srixon-zstar-xv.jpg", "srixon_z-star_9.jpg", "SRIXON_BAG.jpg", "IMG_1894.jpeg"]:
            (self.dir / n).write_bytes(b"x")

    def test_exact_needs_make_and_model(self):
        self.assertEqual(sp.match_photos("Srixon Z- Star XV", self.dir)["match"], "exact")

    def test_wrong_model_is_not_exact(self):
        m = sp.match_photos("Srixon Z-Star Diamond 3 - White", self.dir)
        self.assertNotEqual(m["match"], "exact")

    def test_same_family_other_model_is_only_a_candidate(self):
        m = sp.match_photos("Srixon Q-Star 5", self.dir)
        self.assertEqual(m["exact"], [])
        self.assertEqual(m["match"], "candidate")

    def test_model_named_photo_without_the_make_is_only_a_candidate(self):
        (self.dir / "genesonic1.jpg").write_bytes(b"x")
        m = sp.match_photos("Mileseey GeneSonic Pro", self.dir)
        self.assertEqual(m["exact"], [])
        self.assertEqual([Path(c).name for c in m["candidates"]], ["genesonic1.jpg"])

    def test_maker_only_photo_is_none(self):
        self.assertEqual(sp.match_photos("Srixon Soft Feel 14", self.dir)["match"], "none")

    def test_numbers_do_not_match_camera_files(self):
        m = sp.match_photos("Srixon Z star 9 - White", self.dir)
        self.assertEqual([Path(p).name for p in m["exact"]], ["srixon_z-star_9.jpg"])


if __name__ == "__main__":
    unittest.main()
