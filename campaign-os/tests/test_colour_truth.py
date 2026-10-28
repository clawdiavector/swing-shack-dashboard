"""Colour truth: AI product images are checked against the maker's official listing (2026-10-28).

Christelle's rule: the target colour is measured as a hex from the maker's own product
listing for the exact colourway, not estimated from our shoot photos (shop light tints
them). These tests pin the maths and the Shopify parsing; nothing here touches the network.
"""

from __future__ import annotations

import importlib
import io
import json
import unittest

from PIL import Image, ImageDraw


def _ct():
    return importlib.reload(importlib.import_module("_lib.colour_truth"))


def _jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class TestColourMaths(unittest.TestCase):
    def test_white_and_black_hex_to_lab(self):
        ct = _ct()
        L, a, b = ct.hex_to_lab("#ffffff")
        self.assertAlmostEqual(L, 100.0, places=1)
        self.assertAlmostEqual(a, 0.0, delta=0.05)
        self.assertAlmostEqual(b, 0.0, delta=0.05)
        self.assertEqual(ct.hex_to_lab("#000000"), (0.0, 0.0, 0.0))

    def test_lab_round_trips_to_hex(self):
        ct = _ct()
        for h in ("#1a2b3c", "#4169e1", "#808080", "#ff0000"):
            self.assertEqual(ct.lab_to_hex(ct.hex_to_lab(h)), h)

    def test_ciede2000_matches_sharma_reference_pairs(self):
        # Sharma, Wu & Dalal (2005) test data, pairs 1 and 7.
        ct = _ct()
        self.assertAlmostEqual(ct.delta_e2000((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485)), 2.0425, places=4)
        self.assertAlmostEqual(ct.delta_e2000((50.0, 0.0, 0.0), (50.0, -1.0, 2.0)), 2.3669, places=4)

    def test_verdict_thresholds(self):
        ct = _ct()
        self.assertEqual(ct.verdict(0.0), "PASS")
        self.assertEqual(ct.verdict(5.0), "PASS")
        self.assertEqual(ct.verdict(5.01), "CHECK")
        self.assertEqual(ct.verdict(10.0), "CHECK")
        self.assertEqual(ct.verdict(10.01), "FAIL")


class TestMeasure(unittest.TestCase):
    def test_box_median_ignores_a_small_logo(self):
        ct = _ct()
        img = Image.new("RGB", (100, 100), "#22335a")
        ImageDraw.Draw(img).rectangle((45, 45, 52, 52), fill="#ff00ff")  # badge
        m = ct.measure_box(img, (10, 10, 90, 90))
        self.assertEqual(m["hex"], "#22335a")

    def test_plain_background_product_is_found_without_a_box(self):
        ct = _ct()
        img = Image.new("RGB", (300, 400), "#d9d9d9")  # official listing grey
        ImageDraw.Draw(img).rectangle((80, 90, 220, 330), fill="#3b5998")
        m = ct.measure_on_plain_background(img)
        self.assertEqual(m["hex"], "#3b5998")

    def test_compare_identical_is_zero_and_pass(self):
        ct = _ct()
        r = ct.compare("#3b5998", "#3b5998")
        self.assertEqual(r["delta_e"], 0.0)
        self.assertEqual(r["verdict"], "PASS")

    def test_compare_judges_colour_apart_from_light(self):
        # Hard window light lifts a black shirt to dark grey: same fabric, lighter.
        ct = _ct()
        r = ct.compare("#1d1d1e", "#3a3a3b")
        self.assertLessEqual(r["delta_e_colour"], 1.0)
        self.assertGreater(r["delta_e"], 5.0)
        self.assertEqual(r["verdict"], "PASS")
        # A purple cast at the same lightness is a colour change.
        self.assertNotEqual(ct.compare("#1d1d1e", "#2a1d33")["verdict"], "PASS")

    def test_big_lightness_gap_is_flagged_for_a_look(self):
        # White drawn as mid grey: hue unchanged, but too far off to pass unseen.
        ct = _ct()
        self.assertEqual(ct.compare("#f2f5fc", "#9a9da3")["verdict"], "CHECK")

    def test_compare_far_colours_fail(self):
        ct = _ct()
        self.assertEqual(ct.compare("#1f2a44", "#000000")["verdict"], "FAIL")  # navy drawn as black


class TestShopifyListing(unittest.TestCase):
    PAGE = "https://psychobunny.com/products/mens-classic-polo-b6k001arpc-001-black?variant=1"

    def test_product_json_url(self):
        ct = _ct()
        self.assertEqual(ct.product_json_url(self.PAGE),
                         "https://psychobunny.com/products/mens-classic-polo-b6k001arpc-001-black.json")

    def test_target_from_page_reads_colour_name_and_measures_front_image(self):
        ct = _ct()
        product = {"product": {
            "title": "MEN'S CLASSIC POLO - B6K001ARPC",
            "options": [{"name": "Size", "values": ["S", "M"]}, {"name": "Color", "values": ["001 BLACK"]}],
            "images": [{"position": 2, "src": "https://cdn.example/back.jpg"},
                       {"position": 1, "src": "https://cdn.example/front.jpg"}],
        }}
        shirt = Image.new("RGB", (300, 400), "#d9d9d9")
        ImageDraw.Draw(shirt).rectangle((80, 90, 220, 330), fill="#141414")
        calls = []

        def fetch(url):
            calls.append(url)
            if url.endswith(".json"):
                return json.dumps(product).encode()
            return _jpeg(shirt)

        t = ct.target_from_page(self.PAGE, fetch=fetch)
        self.assertEqual(t["colour_name"], "001 BLACK")
        self.assertEqual(t["image_url"], "https://cdn.example/front.jpg")
        self.assertEqual(t["hex"], "#141414")
        self.assertEqual(t["page_url"], self.PAGE)
        self.assertIn("https://cdn.example/front.jpg", calls)

    def test_page_with_no_colour_option_is_refused(self):
        ct = _ct()
        product = {"product": {"title": "X", "options": [{"name": "Size", "values": ["S"]}],
                               "images": [{"position": 1, "src": "https://cdn.example/a.jpg"}]}}
        with self.assertRaises(ValueError):
            ct.target_from_page(self.PAGE, fetch=lambda url: json.dumps(product).encode())


if __name__ == "__main__":
    unittest.main()
