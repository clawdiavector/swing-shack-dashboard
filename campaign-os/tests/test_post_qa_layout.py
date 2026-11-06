"""Spacing between text groups and the logo's colour (Christelle, 2026-11-05): the Swing Shack hole story put
"LINK IN BIO" about 30 px under the offer, the same gap as inside the offer, and the logo came out grey
under charcoal text. Both must never come back."""
import unittest

from PIL import Image, ImageDraw

from _lib import post_qa as qa

STORY = (1080, 1920)


def logo(rgb, size=(200, 90)):
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle([10, 10, size[0] - 10, size[1] - 10], fill=tuple(rgb) + (255,))
    return im


class GroupGapTests(unittest.TestCase):
    def boxes(self, cta_gap):
        offer = (120, 1240, 960, 1370)
        cta_top = offer[3] + cta_gap
        return [("icon", (150, 520, 930, 1150)), ("offer", offer), ("cta", (85, cta_top, 995, cta_top + 40))]

    def test_the_hole_story_bug_fails(self):
        probs = qa.layout_problems(self.boxes(30), STORY)
        self.assertTrue(any("spacing" in p and "cta" in p for p in probs), probs)

    def test_a_medium_gap_passes(self):
        self.assertEqual(qa.layout_problems(self.boxes(96), STORY), [])

    def test_the_minimum_is_scaled_to_the_canvas_width(self):
        half = (540, 960)
        b = [("a", (0, 100, 100, 200)), ("b", (0, 200 + qa.GROUP_GAP_MIN // 2, 100, 300))]
        self.assertEqual(qa.layout_problems(b, half), [])
        self.assertTrue(qa.layout_problems(b, STORY))

    def test_groups_are_ordered_top_to_bottom_whatever_order_they_come_in(self):
        b = self.boxes(30)
        self.assertEqual(qa.layout_problems(b[::-1], STORY), qa.layout_problems(b, STORY))

    def test_side_by_side_groups_are_not_a_spacing_problem(self):
        # LINK IN BIO and the logo share a row; they never stack, so no vertical gap applies
        b = [("cta", (85, 1450, 400, 1490)), ("logo", (800, 1430, 995, 1510))]
        self.assertEqual(qa.layout_problems(b, STORY), [])

    def test_past_the_story_safe_zone_fails(self):
        b = [("cta", (85, 1520, 400, 1580))]
        probs = qa.layout_problems(b, STORY, safe_bottom=int(STORY[1] * 0.80))
        self.assertTrue(any("safe zone" in p for p in probs), probs)

    def test_check_post_reads_the_gaps(self):
        base = {"lift": 0, "word_visible": 1.0, "headline_overlap": 0.0, "headline_contrast": 150, "mean_luma": 120, "text_items": 2}
        self.assertTrue(any("spacing" in p for p in qa.check_post({"checks": dict(base, group_gap_min=30)}, "T", ["x"])))
        self.assertFalse(any("spacing" in p for p in qa.check_post({"checks": dict(base, group_gap_min=96)}, "T", ["x"])))


class LogoColourTests(unittest.TestCase):
    def test_a_grey_logo_under_charcoal_text_fails(self):
        self.assertGreater(qa.logo_colour_diff(logo((80, 80, 80)), (28, 28, 28)), qa.LOGO_COLOUR_TOL)

    def test_a_matching_logo_passes(self):
        self.assertLessEqual(qa.logo_colour_diff(logo((30, 29, 27)), (28, 28, 28)), qa.LOGO_COLOUR_TOL)

    def test_tint_logo_makes_it_the_text_colour_and_keeps_its_shape(self):
        src = logo((255, 255, 255))
        out = qa.tint_logo(src, (116, 204, 70))
        self.assertEqual(out.getchannel("A").tobytes(), src.getchannel("A").tobytes())
        self.assertEqual(qa.logo_colour_diff(out, (116, 204, 70)), 0)

    def test_check_post_reads_the_logo_colour(self):
        base = {"lift": 0, "word_visible": 1.0, "headline_overlap": 0.0, "headline_contrast": 150, "mean_luma": 120, "text_items": 2}
        self.assertTrue(any("logo" in p for p in qa.check_post({"checks": dict(base, logo_colour_diff=60)}, "T", ["x"])))
        self.assertFalse(any("logo" in p for p in qa.check_post({"checks": base}, "T", ["x"])))


if __name__ == "__main__":
    unittest.main()
