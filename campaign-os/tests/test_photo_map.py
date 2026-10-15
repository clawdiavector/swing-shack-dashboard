"""SKU-named product photos: attach, check, approve, and reach the planner."""
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cos-photomap-"))

from _lib import photo_map as pm  # noqa: E402
from _lib import stock_pulse as sp  # noqa: E402

HEADER = "Location,Product Name,Variant Choices,SKU,Movement Type,Quantity,Alert Level\n"


def results(*lines):
    rows = sp.parse_stock_csv(HEADER + "\n".join(f",{n},,{k},,{q},2" for n, k, q in lines))
    return sp.analyse([{"date": "2026-10-15", "rows": rows}])


class PhotoMapTests(unittest.TestCase):
    def setUp(self):
        self.brand = "pm-" + next(tempfile._get_candidate_names())
        self.dir = Path(tempfile.mkdtemp(prefix="cos-imgs-"))
        self.res = results(("Takomo SF002 wedge", "TS001", 7),
                           ("Odyssey Ai-One Rossie", "OAR001", 1),
                           ("GripDrip Zen Swing Grip - Sky", "GDZGS001", 15),
                           ("GripDrip Zen Swing Grip - Plum", "GDZGP001", 15))
        self.index = pm.sku_index(self.res)

    def drop(self, *names):
        for n in names:
            (self.dir / n).write_bytes(b"x")

    def test_sku_named_file_attaches_and_waits_for_a_check(self):
        self.drop("TS001__front.jpg")
        out = pm.scan(self.brand, self.index, self.dir)
        self.assertEqual(out["added"], ["TS001__front.jpg"])
        e = pm.load(self.brand)[0]
        self.assertEqual((e["sku"], e["status"], e["product"]), ("TS001", "needs-check", "Takomo SF002 wedge"))

    def test_words_in_a_filename_are_never_guessed(self):
        self.drop("takomo_sf002_wedge.jpg", "IMG_1894.jpeg")
        self.assertEqual(pm.scan(self.brand, self.index, self.dir)["added"], [])

    def test_case_and_punctuation_in_the_sku_do_not_matter(self):
        self.drop("ts-001__Side.JPG")
        self.assertEqual(pm.scan(self.brand, self.index, self.dir)["added"], ["ts-001__Side.JPG"])

    def test_unknown_sku_is_reported_not_attached(self):
        self.drop("ZZZ999__front.jpg")
        out = pm.scan(self.brand, self.index, self.dir)
        self.assertEqual((out["added"], out["unknown"]), ([], ["ZZZ999__front.jpg"]))

    def test_rescan_keeps_approvals(self):
        self.drop("TS001__front.jpg")
        pm.scan(self.brand, self.index, self.dir)
        self.assertTrue(pm.set_status(self.brand, "TS001__front.jpg", "approved"))
        self.assertEqual(pm.scan(self.brand, self.index, self.dir)["added"], [])
        self.assertEqual(pm.load(self.brand)[0]["status"], "approved")

    def test_a_colourway_photo_belongs_to_the_range(self):
        self.drop("GDZGP001__lineup.jpg")
        pm.scan(self.brand, self.index, self.dir)
        self.assertEqual(pm.load(self.brand)[0]["product"], "GripDrip grips")

    def test_only_approved_photos_reach_the_planner(self):
        self.drop("TS001__front.jpg", "OAR001__front.jpg")
        pm.scan(self.brand, self.index, self.dir)
        pm.set_status(self.brand, "TS001__front.jpg", "approved")
        products = [{"sku": "TS001"}, {"sku": "OAR001"}]
        self.assertEqual(pm.stamp_catalog(self.brand, products), 1)
        self.assertEqual(products[0]["reference_images"][0]["url"], f"/brand-images/{self.brand}/TS001__front.jpg")
        self.assertNotIn("reference_images", products[1])

    def test_status_for_a_product(self):
        self.drop("TS001__front.jpg")
        pm.scan(self.brand, self.index, self.dir)
        self.assertEqual(pm.status_for(pm.load(self.brand), ["TS001"]), "needs-check")
        pm.set_status(self.brand, "TS001__front.jpg", "approved")
        self.assertEqual(pm.status_for(pm.load(self.brand), ["TS001"]), "approved")
        pm.set_status(self.brand, "TS001__front.jpg", "rejected")
        self.assertEqual(pm.status_for(pm.load(self.brand), ["TS001"]), "")

    def test_shot_name_skips_skus_a_filename_cannot_hold(self):
        self.assertEqual(pm.shot_name(["LO|HCA(P001", "LOHCAP002"]), "LOHCAP002__front.jpg")
        self.assertIn("clean SKU", pm.shot_name(["SP?001"]))


if __name__ == "__main__":
    unittest.main()
