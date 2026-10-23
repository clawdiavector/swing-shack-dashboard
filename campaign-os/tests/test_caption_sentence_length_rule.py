"""Sentence-length lint and prompt wiring for caption copy."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS / "scripts"))


def _codes(result: dict, level: str | None = None) -> set[str]:
    return {
        item["code"]
        for item in result.get("findings", [])
        if level is None or item.get("level") == level
    }


class CaptionSentenceLengthRuleTests(unittest.TestCase):
    def test_seven_words_per_sentence_passes(self):
        import caption_lint as L

        cap = "One two three four five six seven.\nBook a fitting at Stick.\nBetter begins here."
        res = L.lint("stick", cap, cross_brand=False)
        self.assertNotIn("sentence-length", _codes(res))

    def test_eight_words_warns_not_hard(self):
        import caption_lint as L

        cap = "One two three four five six seven eight.\nBook a fitting at Stick.\nBetter begins here."
        res = L.lint("stick", cap, cross_brand=False)
        self.assertIn("sentence-length", _codes(res, L.WARN))
        self.assertEqual(res["hard"], 0)

    def test_cta_line_is_excluded_from_sentence_word_count(self):
        import caption_lint as L

        cap = (
            "One two three four five six seven.\n"
            "Book a fitting at Stick with our team today.\n"
            "Better begins here."
        )
        res = L.lint("stick", cap, cross_brand=False)
        self.assertNotIn("sentence-length", _codes(res))

    def test_signoff_line_is_excluded_from_sentence_word_count(self):
        import caption_lint as L

        rules = L.load_rules("stick")
        rules["signoff"] = "Better starts with us today every day always."
        cap = (
            "One two three four five six seven.\n"
            "Book a fitting at Stick.\n"
            "Better starts with us today every day always."
        )
        res = L.lint("stick", cap, rules=rules, cross_brand=False)
        self.assertNotIn("sentence-length", _codes(res))

    def test_brand_bible_exposes_sentence_length_for_writer(self):
        from _lib.brand_bible import bible_copy_slice

        for brand in ("stick", "swing-shack"):
            with self.subTest(brand=brand):
                cs = (bible_copy_slice(brand, "caption") or {}).get("copy_system") or {}
                self.assertEqual(cs.get("max_words_per_sentence"), 7)

    def test_writer_prompt_includes_sentence_length_rule(self):
        from _lib.p11_context_engine import _build_llm_prompt, build_generation_context

        ctx = build_generation_context(
            brand_id="stick",
            user_brief="Iron fitting this week",
            template_id="fitting_headline",
            post_type="fitting_headline",
            lodge_title="Iron fitting this week",
        )
        self.assertTrue(ctx.get("ok"))
        route = {
            "mechanism": "observation",
            "brand_fit": 4,
            "rhetorical_structure_suggestion": "question",
            "rationale": "test",
        }
        system, user = _build_llm_prompt(ctx, route)
        joined = f"{system}\n{user}"
        self.assertIn("7 words", joined)
        self.assertIn("Do not count the CTA line or sign-off", joined)


if __name__ == "__main__":
    unittest.main()
