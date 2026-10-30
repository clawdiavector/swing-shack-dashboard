"""The three content formulas (poster, post, reel; Christelle, 2026-10-29/30) are part of the skills a Claude
loads when it makes content, not just pages in the wiki.

The wiki only suggests pages; skills are what actually load. If a skill stops pointing at its formula, or a
formula's numbers drift from the rules it scores, content quietly stops being checked against it.
"""
import re
import unittest
from pathlib import Path

from _lib import post_qa as qa

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "plugins" / "campaign-os" / "skills"
FORMULAS = SKILLS / "visual-design" / "formulas.md"
VISUAL = SKILLS / "visual-design" / "SKILL.md"
CAROUSEL = SKILLS / "campaign-os-carousel" / "SKILL.md"
REEL = SKILLS / "reel-formula" / "SKILL.md"
README = ROOT / "plugins" / "campaign-os" / "README.md"


def read(path):
    return path.read_text(encoding="utf-8")


class PosterAndPostFormulas(unittest.TestCase):
    def setUp(self):
        self.text = read(FORMULAS)

    def test_poster_formula_line(self):
        self.assertIn("Poster = Message × (Hierarchy + Contrast + Order + Space + Depth)", self.text)

    def test_post_formula_line(self):
        self.assertIn("Post = Gates × Idea × Craft × Sell", self.text)

    def test_post_bar_matches_visual_design_score(self):
        self.assertTrue(re.search(r"below 40\s*/\s*50", read(VISUAL)))
        self.assertTrue(re.search(r"40\s*/\s*50", self.text))

    def test_text_levels_match_post_qa(self):
        self.assertIn("%d text levels" % qa.TEXT_BUDGET, self.text)

    def test_visual_design_points_at_formulas(self):
        self.assertIn("formulas.md", read(VISUAL))

    def test_carousel_points_at_formulas(self):
        self.assertIn("visual-design/formulas.md", read(CAROUSEL))


class ReelFormulaSkill(unittest.TestCase):
    def setUp(self):
        self.text = read(REEL)

    def test_frontmatter_names_the_skill(self):
        head = self.text.split("---")[1]
        self.assertIn("name: reel-formula", head)
        self.assertIn("description:", head)
        for word in ("reel", "story", "video ad"):
            self.assertIn(word, head.lower())

    def test_reel_formula_line(self):
        self.assertIn("Reel = Native × (Hook + Story + Rhythm + Sound + Brand) × Ask", self.text)

    def test_safe_zones_reels_and_stories(self):
        self.assertIn("35%", self.text)  # Reels bottom
        self.assertIn("20%", self.text)  # Stories bottom
        self.assertIn("14%", self.text)  # top, both

    def test_points_at_wiki_page(self):
        self.assertIn("research/reel-formula-2026-10-30", self.text)

    def test_listed_in_plugin_readme(self):
        self.assertIn("`reel-formula`", read(README))


if __name__ == "__main__":
    unittest.main()
