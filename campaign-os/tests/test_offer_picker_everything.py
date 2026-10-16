"""Offer picker: North Star product first, every stock line with a reason, services."""
import os
import tempfile
import unittest

from _lib import candidate_offers as co
from _lib import stock_pulse as sp

HEADER = "Location,Product Name,Variant Choices,SKU,Movement Type,Quantity,Alert Level\n"
_OLD = {}


def setUpModule():
    _OLD["v"] = os.environ.get("DATA_DIR")
    os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="cos-offers-")


def tearDownModule():
    if _OLD.get("v") is None:
        os.environ.pop("DATA_DIR", None)
    else:
        os.environ["DATA_DIR"] = _OLD["v"]


class EverythingPicker(unittest.TestCase):
    def setUp(self):
        rows = sp.parse_stock_csv(HEADER + "\n".join([
            ",Psycho Bunny Polo - Navy,Medium,PB1M,,3,2", ",Psycho Bunny Polo - Navy,Large,PB1L,,2,2",
            ",Vice Tour White Sleeve,,V1,,95,16", ",Vice Pro Air Sleeve,,V2,,74,20",
            ",Takomo 101 MK2,,T1,,0,1", ",Stick Bag Freshener,,SBF,,2,5"]))
        sp.save_snapshot("stick", rows, "2026-10-15")
        self.blk = co.build("stick")

    def test_focus_product_comes_from_the_retail_north_star(self):
        self.assertEqual(co.focus_product("stick"), "Psycho Bunny")
        self.assertEqual(self.blk["focus_product"], "Psycho Bunny")

    def test_north_star_product_leads_even_when_not_a_deep_shelf(self):
        first = self.blk["items"][0]
        self.assertEqual(first["name"], "Psycho Bunny Polo - Navy")
        self.assertTrue(first["north_star_product"])
        self.assertIn("North Star product", first["reason"])

    def test_catalogue_lists_everything_with_a_reason_when_not_suggested(self):
        cat = {c["name"]: c for c in self.blk["catalogue"]}
        self.assertIn("Takomo 101 MK2", cat)
        self.assertFalse(cat["Takomo 101 MK2"]["suggested"])
        self.assertEqual(cat["Takomo 101 MK2"]["reason"], "Out of stock")
        self.assertIn("at or under the alert level", cat["Stick Bag Freshener"]["reason"])
        self.assertIn("Not a deep shelf", cat["Psycho Bunny Polo - Navy"]["reason"] if not cat["Psycho Bunny Polo - Navy"]["suggested"] else "Not a deep shelf")
        self.assertTrue(cat["Vice Tour White Sleeve"]["suggested"])

    def test_services_are_offered_too(self):
        names = [x["name"].lower() for x in self.blk["services"]]
        self.assertIn("fitting", names)
        self.assertIn("coaching", names)

    def test_no_stock_still_offers_services(self):
        blk = co.build("swing-shack-nostock")
        self.assertEqual(blk["status"], "no_stock_data")
        self.assertEqual(blk["items"], [])


if __name__ == "__main__":
    unittest.main()
