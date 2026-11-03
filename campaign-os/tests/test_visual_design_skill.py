"""The visual-design skill (Christelle's design rules, 2026-10-27) stays installed and agrees with post_qa.

The skill is what a Claude reads before designing a post; post_qa is what checks the result. If the numbers
in one change without the other, the designer and the checker disagree and posts bounce for no reason.
"""
import re
import unittest
from pathlib import Path

from _lib import post_qa as qa

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "plugins" / "campaign-os" / "skills" / "visual-design" / "SKILL.md"
README = ROOT / "plugins" / "campaign-os" / "README.md"


class VisualDesignSkill(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")

    def test_frontmatter_names_the_skill(self):
        head = self.text.split("---")[1]
        self.assertIn("name: visual-design", head)
        self.assertIn("description:", head)

    def test_listed_in_plugin_readme(self):
        self.assertIn("`visual-design`", README.read_text(encoding="utf-8"))

    def test_text_budget_matches_post_qa(self):
        self.assertIn("at most %d text levels" % qa.TEXT_BUDGET, self.text.lower())

    def test_float_gap_matches_post_qa(self):
        self.assertIn("%dpx" % qa.LIFT_MIN, self.text)

    def test_publish_bar_is_40_of_50(self):
        self.assertTrue(re.search(r"below 40\s*/\s*50", self.text))

    def test_points_at_rubric_and_checker(self):
        self.assertIn("docs/product-post-visual-rubric.md", self.text)
        self.assertIn("campaign-os/_lib/post_qa.py", self.text)
        self.assertTrue((ROOT / "docs" / "product-post-visual-rubric.md").exists())


if __name__ == "__main__":
    unittest.main()
