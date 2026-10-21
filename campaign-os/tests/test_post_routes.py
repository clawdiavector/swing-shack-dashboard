"""Route engine: choosing (ideas, routes, backdrops), the layout check, and the light caps."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from _lib import post_routes as pr


def fake_cutout(w=300, h=900, colour=(190, 190, 195, 255)):
    """A tall club-ish shape with a transparent surround."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([w // 2 - 40, 0, w // 2 + 40, h], radius=30, fill=colour)
    d.ellipse([0, h - 260, w, h], fill=colour)
    return im.crop(im.getbbox())


def make_backdrops(dirpath: Path):
    for b in pr.load_backdrops():
        tone = b["tone"]
        base = {"navy": (20, 50, 80), "dark": (40, 40, 44), "grass": (40, 90, 50), "metal": (150, 152, 156),
                "light": (225, 225, 228), "grey": (140, 140, 146)}[tone]
        Image.new("RGB", (800, 1000), base).save(dirpath / b["file"])


def product(**kw):
    d = dict(sku="T1001", name="Takomo", cutout=fake_cutout(), category="irons", model_number="101U",
             in_stock=True, town="Paarl")
    d.update(kw)
    return pr.Product(**d)


class IdeaSelectionTests(unittest.TestCase):
    def setUp(self):
        self.ideas = pr.load_ideas("stick")

    def test_only_ticked_yes_ideas_are_eligible(self):
        for i in pr.eligible_ideas(self.ideas, product()):
            self.assertEqual(i["status"], "yes")
            self.assertEqual(i["pool"], "product")

    def test_rejected_lines_never_appear(self):
        bad = {4, 31, 35, 36, 37, 21}
        ids = {i["id"] for i in pr.eligible_ideas(self.ideas, product())}
        self.assertFalse(bad & ids)

    def test_out_of_stock_product_gets_no_stock_dependent_line(self):
        for i in pr.eligible_ideas(self.ideas, product(in_stock=False)):
            self.assertNotIn("in_stock", i["requires"])

    def test_unverifiable_facts_are_excluded(self):
        for i in pr.eligible_ideas(self.ideas, product()):
            self.assertFalse(set(i["requires"]) & {"real_photo", "spec_fact", "service_fact", "operations_fact", "editorial_check"})

    def test_product_type_tags_are_respected(self):
        putter_only = [i for i in self.ideas if i["id"] == 77]  # "Dad is easy. Just add a putter."
        self.assertEqual(pr.eligible_ideas(putter_only, product(category="irons")), [])
        self.assertEqual(len(pr.eligible_ideas(putter_only, product(category="putters"))), 1)


class PairingTests(unittest.TestCase):
    def setUp(self):
        self.ideas = pr.load_ideas("stick")

    def ids(self, **kw):
        return {i["id"] for i in pr.eligible_ideas(self.ideas, product(**kw))}

    def test_lines_that_name_a_brand_stay_with_that_brand(self):
        self.assertNotIn(66, self.ids(name="L.A.B. Golf", category="putters"))
        self.assertIn(66, self.ids(name="Psycho Bunny", category="apparel"))

    def test_lineup_ideas_are_not_used_for_a_single_product(self):
        self.assertFalse({11, 12, 16, 17, 18, 19, 20} & self.ids())

    def test_style_lines_are_for_apparel(self):
        self.assertNotIn(61, self.ids(category="irons"))
        self.assertIn(61, self.ids(category="apparel", name="Psycho Bunny"))

    def test_just_landed_needs_the_stock_list_to_say_new(self):
        self.assertNotIn(1, self.ids())
        self.assertIn(1, self.ids(stock_status="new"))

    def test_back_in_stock_needs_the_stock_list_to_say_back(self):
        self.assertNotIn(9, self.ids(stock_status="new"))
        self.assertIn(9, self.ids(stock_status="back"))

    def test_new_brand_line_is_never_automatic(self):
        self.assertNotIn(7, self.ids(stock_status="new"))

    def test_number_lines_need_a_model_number(self):
        self.assertNotIn(60, self.ids(model_number=None))
        self.assertIn(60, self.ids(model_number="101U"))


class ChoosingTests(unittest.TestCase):
    def setUp(self):
        self.ideas = pr.load_ideas("stick")
        self.backdrops = pr.load_backdrops()

    def test_same_seed_same_plan(self):
        a = pr.choose(product(), self.ideas, self.backdrops, pr.RouteMemory(), 5)
        b = pr.choose(product(), self.ideas, self.backdrops, pr.RouteMemory(), 5)
        self.assertEqual((a.idea["id"], a.route, a.backdrop_id), (b.idea["id"], b.route, b.backdrop_id))

    def test_route_is_not_repeated_back_to_back(self):
        mem = pr.RouteMemory()
        last = None
        for seed in range(12):
            plan = pr.choose(product(), self.ideas, self.backdrops, mem, seed)
            if last:
                self.assertNotEqual(plan.route, last)
            mem.add(plan, "T1001")
            last = plan.route

    def test_idea_not_reused_until_the_pool_runs_out(self):
        pool = len(pr.eligible_ideas(self.ideas, product()))
        self.assertGreater(pool, 5)
        mem = pr.RouteMemory()
        seen = []
        for seed in range(pool):
            plan = pr.choose(product(), self.ideas, self.backdrops, mem, seed)
            self.assertNotIn(plan.idea["id"], seen)
            seen.append(plan.idea["id"])
            mem.add(plan, "T1001")

    def test_bag_never_lies_on_turf(self):
        self.assertNotIn("turf_shadow", pr.eligible_routes(product(category="bags")))

    def test_number_route_needs_a_model_number(self):
        self.assertNotIn("hero_number", pr.eligible_routes(product(model_number=None)))

    def test_backdrop_tone_matches_route(self):
        mem = pr.RouteMemory()
        import random
        rng = random.Random(3)
        tones = {b["id"]: b["tone"] for b in self.backdrops}
        for route in pr.ROUTE_IDS:
            self.assertIn(tones[pr.pick_backdrop(route, self.backdrops, mem, rng)], pr.ROUTE_TONES[route])


class LightCapTests(unittest.TestCase):
    def test_vignette_is_capped(self):
        flat = Image.new("RGB", (400, 400), (200, 200, 200))
        heavy = pr.soft_vignette(flat, 0.95)
        corner = np.asarray(heavy)[0, 0].mean()
        self.assertGreaterEqual(corner, 200 * (1 - pr.LIGHT_CAPS["vignette"]) - 2)

    def test_rim_light_is_capped(self):
        cv = Image.new("RGBA", (200, 200), (0, 0, 0, 255))
        cut = Image.new("RGBA", (60, 60), (255, 255, 255, 255))
        pr.rim(cv, cut, (70, 70), pr.WHITE, 10, 5.0)  # absurd request
        self.assertLess(np.asarray(cv)[60, 60, :3].max(), 255 * pr.LIGHT_CAPS["rim_white"] + 30)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cos-routes-"))
        make_backdrops(self.tmp)
        self.ideas = pr.load_ideas("stick")
        self.backdrops = pr.load_backdrops()

    def test_every_route_renders_and_passes_the_checks(self):
        for route in pr.ROUTE_IDS:
            plan = pr.choose(product(), self.ideas, self.backdrops, pr.RouteMemory(), 11)
            plan.route = route
            plan.backdrop_id = pr.pick_backdrop(route, self.backdrops, pr.RouteMemory(), __import__("random").Random(1))
            img, meta = pr.render_route(route, product(), plan, "stick", self.tmp)
            self.assertEqual(img.size, pr.CANVAS)
            self.assertGreaterEqual(meta["checks"]["mean_luma"], pr.LIGHT_CAPS["min_mean_luma"])
            self.assertLessEqual(meta["checks"].get("text_overlap", 0), pr.CHECKS["caption_overlap_max"])

    def test_hero_word_stays_readable(self):
        plan = pr.choose(product(), self.ideas, self.backdrops, pr.RouteMemory(), 2)
        plan.route, plan.backdrop_id = "crop_word", 20
        _, meta = pr.render_route("crop_word", product(), plan, "stick", self.tmp)
        self.assertGreaterEqual(meta["checks"]["word_visible"], pr.CHECKS["word_visible_min"]["crop_word"])

    def test_new_in_pill_only_when_the_stock_list_says_new(self):
        import re
        for status, expect in ((None, False), ("new", True)):
            p = product(stock_status=status)
            plan = pr.choose(p, self.ideas, self.backdrops, pr.RouteMemory(), 2)
            plan.route, plan.backdrop_id = "crop_word", 20
            img, _ = pr.render_route("crop_word", p, plan, "stick", self.tmp)
            pill = np.asarray(img.convert("RGB").crop((64, 170, 330, 240))).astype(int)
            teal = ((abs(pill[..., 0] - 0) < 40) & (abs(pill[..., 1] - 179) < 40) & (abs(pill[..., 2] - 186) < 40)).mean()
            self.assertEqual(teal > 0.15, expect)

    def test_hero_number_never_loses_a_character_off_the_edge(self):
        path, shear, _ = pr.display_font("stick")
        for num in ("101U", "SF002", "OZ.1", "2.0", "DF3"):
            s = pr.fit_size(num, int(pr.CANVAS[0] * pr.BLEED_MAX), path, shear, 1300)
            self.assertLessEqual(pr.text_layer(num, s, pr.WHITE, path, shear).width, int(pr.CANVAS[0] * pr.BLEED_MAX) + 6)

    def test_wide_and_tall_products_both_pass(self):
        for cut in (fake_cutout(900, 300), fake_cutout(300, 900), fake_cutout(500, 500)):
            p = product(cutout=cut, category="other")
            plan = pr.choose(p, self.ideas, self.backdrops, pr.RouteMemory(), 4)
            plan.route, plan.backdrop_id = "crop_word", 20
            img, _ = pr.render_route("crop_word", p, plan, "stick", self.tmp)
            self.assertEqual(img.size, pr.CANVAS)

    def test_captions_only_claim_stock_when_in_stock(self):
        self.assertEqual(pr.caption_for(product(in_stock=True)), "Takomo. In store, Paarl.")
        self.assertEqual(pr.caption_for(product(in_stock=False)), "Takomo.")

    def test_render_post_records_memory_and_lists_what_to_confirm(self):
        mem = pr.RouteMemory(self.tmp / "mem.json")
        img, meta = pr.render_post(product(), self.ideas, self.backdrops, mem, 9, "stick", self.tmp)
        self.assertEqual(len(mem.items), 1)
        self.assertIn("in_stock", meta["confirm_before_posting"])
        self.assertEqual(json.loads((self.tmp / "mem.json").read_text())[0]["sku"], "T1001")

    def test_a_too_dark_backdrop_is_swapped_for_a_lighter_one(self):
        # only backdrop 04 is black; the others are fine, so the post must still render
        Image.new("RGB", (800, 1000), (0, 0, 0)).save(self.tmp / "04.jpg")
        p = product(category="bags", model_number=None)
        mem = pr.RouteMemory()
        for seed in range(6):
            img, meta = pr.render_post(p, self.ideas, self.backdrops, mem, seed, "stick", self.tmp)
            self.assertNotEqual(meta["backdrop_id"], 4)

    def test_a_crushed_dark_backdrop_is_refused(self):
        for b in self.backdrops:
            Image.new("RGB", (800, 1000), (0, 0, 0)).save(self.tmp / b["file"])
        plan = pr.choose(product(), self.ideas, self.backdrops, pr.RouteMemory(), 3)
        plan.route, plan.backdrop_id = "crop_word", 20
        with self.assertRaises(pr.LayoutFailed):
            pr.render_route("crop_word", product(), plan, "stick", self.tmp)


if __name__ == "__main__":
    unittest.main()
