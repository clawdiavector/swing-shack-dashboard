"""The visual analyzer's measurable half: the flaws found on 2026-10-21 must never come back."""
import random
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from _lib import post_qa as qa
from _lib import post_routes as pr
from _lib import post_studio as ps


def fake_cutout(w=300, h=900):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([w // 2 - 40, 0, w // 2 + 40, h], radius=30, fill=(190, 190, 195, 255))
    d.ellipse([0, h - 260, w, h], fill=(190, 190, 195, 255))
    return im.crop(im.getbbox())


def product(**kw):
    d = dict(sku="X1", name="Callaway", cutout=fake_cutout(), category="balls", model_number=None, in_stock=True, town="Paarl")
    d.update(kw)
    return pr.Product(**d)


def scenes(dirpath: Path):
    for s in ps.load_sets():
        Image.new("RGB", (928, 1152), (225, 226, 230) if s["ink"] == "dark" else (20, 50, 80)).save(dirpath / s["file"])


class CheckPostTests(unittest.TestCase):
    base = {"lift": 0, "word_visible": 1.0, "headline_overlap": 0.0, "headline_contrast": 150, "mean_luma": 120, "text_items": 2}

    def test_a_small_lift_is_a_hover(self):
        for lift in (20, 70, 99):
            self.assertTrue(any("hover" in p for p in qa.check_post({"checks": dict(self.base, lift=lift)}, "Takomo", ["x"])))

    def test_resting_or_clear_levitation_is_fine(self):
        for lift in (0, qa.LIFT_MIN, 140):
            self.assertFalse(any("hover" in p for p in qa.check_post({"checks": dict(self.base, lift=lift)}, "Takomo", ["x"])))

    def test_the_product_name_written_twice_is_a_fail(self):
        probs = qa.check_post({"checks": self.base}, "Psycho Bunny polo", ["Psycho Bunny. Obviously.", "Psycho Bunny polo. In store.", "PSYCHO BUNNY"])
        self.assertTrue(any("repeats" in p for p in probs))

    def test_name_once_is_fine(self):
        self.assertFalse(qa.check_post({"checks": self.base}, "Callaway Chrome Soft", ["Take a look.", "In store, Paarl.", "CALLAWAY"]))

    def test_text_budget(self):
        probs = qa.check_post({"checks": dict(self.base, text_items=4)}, "Takomo", ["x"])
        self.assertTrue(any("text budget" in p for p in probs))

    def test_hidden_word_low_contrast_and_dark_posts_fail(self):
        self.assertTrue(qa.check_post({"checks": dict(self.base, word_visible=0.5)}, "T", ["x"]))
        self.assertTrue(qa.check_post({"checks": dict(self.base, headline_contrast=30)}, "T", ["x"]))
        self.assertTrue(qa.check_post({"checks": dict(self.base, mean_luma=10)}, "T", ["x"]))


class StudioRulesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cos-qa-"))
        scenes(self.tmp)
        self.ideas = {i["id"]: i for i in pr.load_ideas("stick")}

    def test_categories_either_rest_or_levitate_clearly(self):
        for cat, (h, rot, lift) in ps.CATEGORY_LAYOUT.items():
            self.assertTrue(lift == 0 or lift >= qa.LIFT_MIN, cat)

    def test_the_giant_word_is_never_cropped_by_the_canvas(self):
        disp, shear, _ = pr.display_font("stick")
        for word in ("CALLAWAY", "PSYCHO BUNNY", "HERSCHEL", "SF002", "OZ.1", "G1"):
            canvas = Image.new("RGBA", pr.CANVAS, (0, 0, 0, 255))
            _, (x0, y0, x1, y1), _cells = ps.giant_word(canvas, word, "solid", 200, int(pr.CANVAS[0] * 0.9), (255, 255, 255), disp, shear)
            self.assertGreaterEqual(x0, 0, word)
            self.assertLessEqual(x1, pr.CANVAS[0], word)

    def test_a_hidden_letter_is_a_fail(self):
        base = {"lift": 0, "word_visible": 0.9, "word_min_letter": 0.3, "headline_overlap": 0.0, "headline_contrast": 150, "mean_luma": 120, "text_items": 2}
        self.assertTrue(any("letter" in p for p in qa.check_post({"checks": base}, "T", ["x"])))

    def test_every_letter_of_a_rendered_word_is_mostly_visible(self):
        sm = next(x for x in ps.load_sets() if x["id"] == 102)
        for seed in (1, 2, 3, 4):
            try:
                _, meta = ps.render_studio(product(name="Takomo", model_number="101U"), self.ideas[6], sm, self.tmp, "stick", seed)
            except pr.LayoutFailed:
                continue
            self.assertGreaterEqual(meta["checks"]["word_min_letter"], qa.LETTER_VISIBLE_MIN)

    def test_headline_keeps_a_gap_from_the_giant_word(self):
        sm = next(x for x in ps.load_sets() if x["id"] == 102)
        for seed in (1, 2, 3):
            try:
                _, meta = ps.render_studio(product(), self.ideas[6], sm, self.tmp, "stick", seed)
            except pr.LayoutFailed:
                continue
            self.assertLessEqual(meta["checks"]["headline_overlap"], qa.HEADLINE_OVERLAP_MAX)

    def test_headline_stays_off_the_block_in_a_set_that_marks_one(self):
        sm = next(x for x in ps.load_sets() if x["id"] == 119)   # concrete slab, object area marked
        o = sm["object"]
        W, H = pr.CANVAS
        for seed in (1, 2, 3):
            try:
                _, meta = ps.render_studio(product(), self.ideas[6], sm, self.tmp, "stick", seed)
            except pr.LayoutFailed:
                continue
            self.assertNotIn("@%d" % int(o[1] * H), meta["checks"]["headline_zone"])

    def test_a_range_post_may_use_a_lineup_idea_but_a_single_product_may_not(self):
        lineup = next(i for i in self.ideas.values() if i["id"] == 18)   # "Lineup."
        single = product(category="grips", name="Ripit")
        self.assertNotIn(18, {i["id"] for i in pr.eligible_ideas(list(self.ideas.values()), single)})
        grouped = product(category="grips", name="Ripit", group=[fake_cutout()] * 4)
        self.assertIn(18, {i["id"] for i in pr.eligible_ideas(list(self.ideas.values()), grouped)})

    def test_a_group_of_gloves_renders_as_one_range_and_is_flagged_when_it_is_copies(self):
        sm = next(x for x in ps.load_sets() if x["id"] == 102)
        g = product(category="gloves", name="Takomo", group=[fake_cutout(400, 600)] * 3, group_is_copies=True, model_number=None)
        for seed in (1, 2, 3, 4):
            try:
                _, meta = ps.render_studio(g, self.ideas[6], sm, self.tmp, "stick", seed)
            except pr.LayoutFailed:
                continue
            self.assertEqual(meta["group"], 3)
            self.assertTrue(meta["group_is_copies"])
            return
        self.fail("no seed rendered the group")

    def test_a_word_the_headline_already_says_is_not_used(self):
        idea = {"id": 1, "line": "Take a look at Callaway.", "requires": []}
        rng = random.Random(1)
        for _ in range(20):
            self.assertNotEqual(ps.choose_word(product(), idea, rng), "CALLAWAY")

    def test_brand_lines_do_not_get_the_brand_as_the_giant_word(self):
        idea = self.ideas[66]  # Psycho Bunny. Obviously.
        rng = random.Random(2)
        for _ in range(30):
            self.assertNotEqual(ps.choose_word(product(name="Psycho Bunny", category="apparel"), idea, rng), "PSYCHO BUNNY")

    def test_the_caption_does_not_repeat_the_name_when_the_word_says_it(self):
        idea = {"id": 6, "line": "Take a look. Take it home.", "requires": []}
        cap = ps.choose_caption(product(), "CALLAWAY", idea)
        self.assertEqual(cap, "In store, Paarl.")

    def test_a_resting_product_has_no_hover_and_a_levitating_one_a_clear_gap(self):
        sm = next(s for s in ps.load_sets() if s["id"] == 102)
        idea = self.ideas[6]
        _, meta = ps.render_studio(product(category="balls"), idea, sm, self.tmp, "stick", 3)
        self.assertEqual(meta["checks"]["lift"], 0)
        sm = next(s for s in ps.load_sets() if s["id"] == 101)
        _, meta = ps.render_studio(product(category="irons", name="Takomo"), idea, sm, self.tmp, "stick", 7)
        self.assertGreaterEqual(meta["checks"]["lift"], qa.LIFT_MIN)

    def test_a_product_is_never_shrunk_below_hero_size(self):
        sm = next(x for x in ps.load_sets() if x["id"] == 102)
        # an absurdly long headline on a big product forces shrinking; the engine must refuse, not shrink to nothing
        idea = {"id": 999, "line": "word " * 12, "requires": []}
        big = product(category="bags", cutout=fake_cutout(900, 900))
        try:
            _, meta = ps.render_studio(big, idea, sm, self.tmp, "stick", 3)
        except pr.LayoutFailed:
            return
        self.assertGreaterEqual(meta["checks"]["product_inside"], qa.INSIDE_MIN)

    def test_the_product_is_never_cropped_by_the_canvas(self):
        sm = next(x for x in ps.load_sets() if x["id"] == 102)
        _, meta = ps.render_studio(product(), self.ideas[6], sm, self.tmp, "stick", 5)
        self.assertGreaterEqual(meta["checks"]["product_inside"], qa.INSIDE_MIN)

    def test_a_rendered_post_has_at_most_three_text_items_and_passes_qa(self):
        sm = next(s for s in ps.load_sets() if s["id"] == 102)
        _, meta = ps.render_studio(product(), self.ideas[6], sm, self.tmp, "stick", 5)
        self.assertLessEqual(meta["checks"]["text_items"], qa.TEXT_BUDGET)
        self.assertTrue(meta["qa"]["passed"])

    def test_grounded_products_prefer_straight_on_sets(self):
        mem = pr.RouteMemory()
        rng = random.Random(1)
        base = dict(file="x.png", base=0.7, cx=0.5, ink="light", light="left", suits=["balls"])
        sets = [dict(base, id=900, view="front"), dict(base, id=901, view="top"), dict(base, id=902, view="top")]
        for _ in range(8):
            self.assertEqual(ps.pick_set(product(), mem, rng, sets)["id"], 900)

    def test_a_levitating_product_may_use_any_view(self):
        mem = pr.RouteMemory()
        rng = random.Random(3)
        base = dict(file="x.png", base=0.7, cx=0.5, ink="light", light="left", suits=["irons"])
        sets = [dict(base, id=900, view="front"), dict(base, id=901, view="top")]
        seen = {ps.pick_set(product(category="irons"), pr.RouteMemory(), random.Random(k), sets)["id"] for k in range(20)}
        self.assertEqual(seen, {900, 901})


if __name__ == "__main__":
    unittest.main()
