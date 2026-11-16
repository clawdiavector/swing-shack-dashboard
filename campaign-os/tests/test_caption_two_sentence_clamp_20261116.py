"""Captions died with "no survivors" (2026-11-16).

The writer prompt asks for at most 2 sentences AND at most 7 words a sentence.
The model wrote 3 or 4 short sentences, and the 2-sentence gate rejected 9 to
11 of every 12 candidates. Extra sentences are now cut before the gate runs.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("PORT", "0")

from _lib import p11_context_engine as p11  # noqa: E402

# Real rejected bodies from prod, 16 Nov 2026.
THREE = "Buying clubs without a fitting is risky. Fit first, buy second. Your swing deserves better."
FOUR = (
    "Fitted clubs improve your game. Off-the-rack won't cut it. Fit first, buy second. "
    "Discover the difference with a proper fitting."
)


class ClampTests(unittest.TestCase):
    def test_three_sentences_become_two(self):
        body, dropped = p11._clamp_caption_sentences(THREE)
        self.assertEqual(body, "Buying clubs without a fitting is risky. Fit first, buy second.")
        self.assertEqual(dropped, 1)

    def test_four_sentences_become_two(self):
        body, dropped = p11._clamp_caption_sentences(FOUR)
        self.assertEqual(body, "Fitted clubs improve your game. Off-the-rack won't cut it.")
        self.assertEqual(dropped, 2)

    def test_two_sentences_are_left_alone(self):
        text = "Fit first. Buy second."
        self.assertEqual(p11._clamp_caption_sentences(text), (text, 0))

    def test_empty_is_safe(self):
        self.assertEqual(p11._clamp_caption_sentences(""), ("", 0))
        self.assertEqual(p11._clamp_caption_sentences(None), ("", 0))

    def test_question_and_exclamation_count_as_sentence_ends(self):
        body, dropped = p11._clamp_caption_sentences("Still guessing? Stop. Get fitted!")
        self.assertEqual(body, "Still guessing? Stop.")
        self.assertEqual(dropped, 1)

    def test_prices_and_web_addresses_are_not_split(self):
        text = "Fittings from R1.500 at shop.stickgolf.co.za today. Book one."
        self.assertEqual(p11._clamp_caption_sentences(text), (text, 0))


class GateAfterClampTests(unittest.TestCase):
    def test_gate_rejects_the_raw_body_and_passes_the_clamped_one(self):
        raw = {"caption_body": THREE, "poster_hook": "FIT FIRST", "cta_line": ""}
        self.assertEqual(p11._check_locale(raw)["reason"], "caption_body_over_2_sentences")
        body, _ = p11._clamp_caption_sentences(THREE)
        self.assertTrue(p11._check_locale({**raw, "caption_body": body})["passed"])

    def test_gate_itself_is_unchanged(self):
        # The 2-sentence rule and the 220-character rule still hard-fail.
        self.assertFalse(p11._check_locale({"caption_body": "One. Two. Three."})["passed"])
        self.assertEqual(p11._check_locale({"caption_body": "x" * 221})["reason"], "caption_body_over_220")


if __name__ == "__main__":
    unittest.main()
