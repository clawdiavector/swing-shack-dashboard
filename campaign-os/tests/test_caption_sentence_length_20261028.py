"""T12 part 1: no more than 7 words per sentence (2026-10-28)."""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import caption_lint as cl  # noqa: E402


def _len_findings(brand, text, rules=None):
    r = cl.lint(brand, text, rules=rules, cross_brand=False)
    return [f for f in r["findings"] if f["code"] == "sentence-length"]


def test_both_bibles_carry_the_rule():
    for brand in ("stick", "swing-shack"):
        rules = cl.load_rules(brand)
        assert rules["max_words_per_sentence"] == 7
        assert rules["sentence_length_enforcement"] == "warn"


def test_long_sentence_warns_short_ones_pass():
    found = _len_findings("swing-shack", "New Odyssey putters just landed in store this week.\nRoll a few today.")
    assert len(found) == 1
    assert found[0]["level"] == cl.WARN
    assert "9 words" in found[0]["message"]
    assert _len_findings("swing-shack", "Fresh putters in. Roll a few today.") == []


def test_cta_and_signoff_lines_are_not_counted():
    rules = dict(cl.load_rules("stick"))
    rules["signoff"] = "See you at the shop, the whole Stick crew."
    rules["ctas_allowed"] = ["Book your free putter fitting at the shop this week"]
    text = ("Putters in. Roll a few.\n"
            "Book your free putter fitting at the shop this week\n"
            "See you at the shop, the whole Stick crew.")
    assert _len_findings("stick", text, rules) == []


def test_hard_when_bible_says_hard():
    rules = dict(cl.load_rules("stick"))
    rules["sentence_length_enforcement"] = "hard"
    found = _len_findings("stick", "This sentence has far too many words in it for us.", rules)
    assert found and found[0]["level"] == cl.HARD


def test_hashtags_and_handles_do_not_count():
    assert _len_findings("swing-shack", "Putters in. #SwingShack #Golf #Putting #Paarl @odyssey") == []
