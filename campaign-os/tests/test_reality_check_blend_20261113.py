"""Christelle, 13 Nov 2026: anything placed into a generated scene must look part of the photo,
never "plopped on top". The reality-check skill is what loads before a real-looking image is shown,
so the rule has to live there as its own check, with the parts she named."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "plugins" / "campaign-os" / "skills" / "reality-check" / "SKILL.md"


class BlendCheck(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding="utf-8")

    def test_ten_checks_with_blend_last(self):
        self.assertIn("## The ten checks", self.text)
        self.assertIn("10. **Blend.**", self.text)

    def test_blend_names_what_to_match(self):
        block = self.text.split("10. **Blend.**", 1)[1].split("Then look", 1)[0].lower()
        for part in ("light direction", "colour temperature", "contact shadow", "depth of field",
                     "grain", "logo and print", "harmonise"):
            self.assertIn(part, block, part)

    def test_description_triggers_on_plopped(self):
        head = self.text.split("---", 2)[1]
        self.assertIn("blend", head)
        self.assertIn("plopped", head)


if __name__ == "__main__":
    unittest.main()
