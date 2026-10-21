"""Studio-set posts: set choice, real pixels untouched, readable text, honest badges, soft light."""
import random
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageStat

from _lib import post_routes as pr
from _lib import post_studio as ps


def fake_cutout(w=300, h=900, colour=(190, 190, 195, 255)):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([w // 2 - 40, 0, w // 2 + 40, h], radius=30, fill=colour)
    d.ellipse([0, h - 260, w, h], fill=colour)
    return im.crop(im.getbbox())


def make_scenes(dirpath: Path, light=False):
    """Plain synthetic sets: one flat colour per file (no Krea needed in tests)."""
    for s in ps.load_sets():
        base = (225, 226, 230) if (light or s["ink"] == "dark") else (20, 50, 80)
        Image.new("RGB", (928, 1152), base).save(dirpath / s["file"])


def product(**kw):
    d = dict(sku="T1001", name="Takomo", cutout=fake_cutout(), category="irons", model_number="101U",
             in_stock=True, town="Paarl")
    d.update(kw)
    return pr.Product(**d)


class SetChoiceTests(unittest.TestCase):
    def test_sets_match_the_product_category(self):
        for s in ps.eligible_sets(product(category="bags")):
            self.assertIn("bags", s["suits"])
        self.assertTrue(ps.eligible_sets(product(category="balls")))

    def test_a_bag_is_never_put_on_a_small_pedestal(self):
        ids = {s["id"] for s in ps.eligible_sets(product(category="bags"))}
        self.assertNotIn(115, ids)  # the slim pedestal

    def test_set_is_not_repeated_while_others_are_free(self):
        mem = pr.RouteMemory()
        rng = random.Random(1)
        seen = []
        n = len(ps.eligible_sets(product()))
        for _ in range(min(6, n)):
            s = ps.pick_set(product(), mem, rng)
            self.assertNotIn(s["id"], seen)
            seen.append(s["id"])
            mem.add(pr.Plan({"id": 1}, "studio_set", s["id"], 1), "T1001")

    def test_all_set_files_in_the_manifest_have_unique_ids(self):
        ids = [s["id"] for s in ps.load_sets()]
        self.assertEqual(len(ids), len(set(ids)))


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cos-studio-"))
        make_scenes(self.tmp)
        self.ideas = pr.load_ideas("stick")
        self.idea = next(i for i in self.ideas if i["id"] == 6)  # "Take a look. Take it home."

    def render(self, p=None, set_id=101, seed=3, style="solid"):
        sm = next(s for s in ps.load_sets() if s["id"] == set_id)
        return ps.render_studio(p or product(), self.idea, sm, self.tmp, "stick", seed, word_style=style)

    def test_renders_at_canvas_size_with_checks(self):
        img, meta = self.render()
        self.assertEqual(img.size, pr.CANVAS)
        self.assertEqual(meta["route"], "studio_set")
        self.assertGreaterEqual(meta["checks"]["word_visible"], ps.WORD_VISIBLE_MIN)
        self.assertGreaterEqual(meta["checks"]["headline_contrast"], ps.CONTRAST_MIN)

    def test_the_real_product_pixels_are_not_repainted(self):
        # flat scene, no giant word under the product's centre: the output at the product's solid centre
        # must be the cut-out's own colour (film grain aside)
        img, meta = self.render(product(category="putters"), style="outline")
        cx = int(0.50 * pr.CANVAS[0])
        sample = img.crop((cx - 6, 700, cx + 6, 712)).convert("RGB")
        mean = ImageStat.Stat(sample).mean
        # the iron body is (190,190,195); a plinth shadow or tint would pull it far from this
        self.assertLess(abs(mean[0] - 190) + abs(mean[1] - 190) + abs(mean[2] - 195), 90)

    def test_headline_is_readable_on_light_and_dark_sets(self):
        for set_id in (101, 102):  # a dark set and a light set
            _, meta = self.render(set_id=set_id)
            self.assertGreaterEqual(meta["checks"]["headline_contrast"], ps.CONTRAST_MIN)

    def test_a_crushed_dark_scene_is_refused(self):
        for s in ps.load_sets():
            Image.new("RGB", (928, 1152), (0, 0, 0)).save(self.tmp / s["file"])
        with self.assertRaises(pr.LayoutFailed):
            self.render()

    def test_badge_needs_the_stock_list(self):
        _, meta = self.render(product(in_stock=False))
        self.assertEqual(meta["badge"], "")
        _, meta = self.render(product(in_stock=True, stock_status="new"))
        self.assertEqual(meta["badge"], "NEW IN")

    def test_logo_is_top_left_when_that_corner_is_free(self):
        _, meta = self.render()
        self.assertEqual(meta["logo_corner"], "tl")

    def test_giant_word_is_not_hidden_whatever_the_style(self):
        for style in ("tone", "solid", "outline"):
            _, meta = self.render(style=style)
            self.assertGreaterEqual(meta["checks"]["word_visible"], ps.WORD_VISIBLE_MIN)

    def test_the_post_is_not_crushed_dark(self):
        _, meta = self.render(set_id=101)
        self.assertGreaterEqual(meta["checks"]["mean_luma"], pr.LIGHT_CAPS["min_mean_luma"])


class EngineIntegrationTests(unittest.TestCase):
    def test_render_post_uses_the_studio_route_when_scenes_are_given(self):
        tmp = Path(tempfile.mkdtemp(prefix="cos-studio-"))
        make_scenes(tmp)
        bd = Path(tempfile.mkdtemp(prefix="cos-bd-"))
        for b in pr.load_backdrops():
            Image.new("RGB", (800, 1000), (120, 120, 130)).save(bd / b["file"])
        mem = pr.RouteMemory()
        img, meta = pr.render_post(product(), pr.load_ideas("stick"), pr.load_backdrops(), mem, 4, "stick", bd, scenes_dir=tmp)
        self.assertEqual(meta["route"], "studio_set")
        self.assertEqual(mem.items[-1]["route"], "studio_set")

    def test_without_scenes_the_old_routes_still_work(self):
        bd = Path(tempfile.mkdtemp(prefix="cos-bd-"))
        for b in pr.load_backdrops():
            Image.new("RGB", (800, 1000), (120, 120, 130)).save(bd / b["file"])
        img, meta = pr.render_post(product(), pr.load_ideas("stick"), pr.load_backdrops(), pr.RouteMemory(), 4, "stick", bd)
        self.assertNotEqual(meta["route"], "studio_set")


if __name__ == "__main__":
    unittest.main()
