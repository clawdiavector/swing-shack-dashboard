"""The visual analyzer's measurable half: checks every product post for the flaws we keep finding.

Each flaw below was found by looking at real output (Christelle, 2026-10-21). The checks cannot judge
taste, but they stop the same mistakes from reaching her. The rubric for the human (or vision model)
pass is docs/product-post-visual-rubric.md.

  hover        a product either rests (lift 0) or levitates clearly (a gap of LIFT_MIN or more)
  repeats      the product's name appears once in text at most (giant word, headline, caption)
  text budget  at most three pieces of text (giant word, headline, caption) plus the logo
  word         the giant word stays readable (not hidden behind the product)
  headline     the headline has contrast and stays off the product and the giant word
  light        the post is not crushed dark
"""
from __future__ import annotations

from typing import List

LIFT_MIN = 100                 # px: below this a floating product looks like it is hovering by mistake
WORD_VISIBLE_MIN = 0.85
INSIDE_MIN = 0.985             # the product is never cropped by the canvas edge
MIN_SCALE = 0.72               # the product may shrink to make room, but not below this share of its size
HEADLINE_OVERLAP_MAX = 0.03
CONTRAST_MIN = 70              # text colour against the pixels behind it
TEXT_BUDGET = 3
MIN_MEAN_LUMA = 38


def name_repeats(name: str, texts: List[str]) -> int:
    """How many separate pieces of text contain the product's brand word."""
    key = (name or "").split()[0].lower() if name else ""
    if not key:
        return 0
    return sum(1 for t in texts if t and key in t.lower())


def check_post(meta: dict, product_name: str, texts: List[str]) -> List[str]:
    c = meta.get("checks", {})
    problems: List[str] = []
    lift = c.get("lift", 0)
    if 0 < lift < LIFT_MIN:
        problems.append("hover: lift %dpx is neither resting nor clearly levitating" % lift)
    if name_repeats(product_name, texts) > 1:
        problems.append("repeats: the product name is written %d times" % name_repeats(product_name, texts))
    if c.get("text_items", 0) > TEXT_BUDGET:
        problems.append("text budget: %d pieces of text (max %d)" % (c.get("text_items", 0), TEXT_BUDGET))
    if c.get("word_visible", 1.0) < WORD_VISIBLE_MIN:
        problems.append("word: giant word only %.0f%% visible" % (100 * c.get("word_visible", 0)))
    if c.get("headline_overlap", 0) > HEADLINE_OVERLAP_MAX:
        problems.append("headline: overlaps the product or the word")
    if c.get("headline_contrast", 255) < CONTRAST_MIN:
        problems.append("headline: contrast %.0f is too low" % c.get("headline_contrast", 0))
    if c.get("mean_luma", 255) < MIN_MEAN_LUMA:
        problems.append("light: post is crushed dark")
    return problems
