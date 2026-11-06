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
  spacing      text groups stacked on each other keep a clear gap, never the same tight gap as inside a group
  logo         the logo is the same colour as the text around it (tint it with tint_logo)
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

LIFT_MIN = 100                 # px: below this a floating product looks like it is hovering by mistake
WORD_VISIBLE_MIN = 0.85
LETTER_VISIBLE_MIN = 0.55      # no single letter of the giant word may be mostly hidden
INSIDE_MIN = 0.985             # the product is never cropped by the canvas edge
MIN_SCALE = 0.72               # the product may shrink to make room, but not below this share of its size
HEADLINE_OVERLAP_MAX = 0.03
CONTRAST_MIN = 70              # text colour against the pixels behind it
TEXT_BUDGET = 3
MIN_MEAN_LUMA = 38
GROUP_GAP_MIN = 60             # px at 1080 wide between stacked text groups (icon, offer, CTA row); scaled to the canvas
LOGO_COLOUR_TOL = 24           # max channel difference between the logo's ink and the text colour

Box = Tuple[float, float, float, float]


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
    if c.get("word_min_letter", 1.0) < LETTER_VISIBLE_MIN:
        problems.append("word: a letter is %.0f%% hidden" % (100 * (1 - c.get("word_min_letter", 0))))
    if c.get("headline_overlap", 0) > HEADLINE_OVERLAP_MAX:
        problems.append("headline: overlaps the product or the word")
    if c.get("headline_contrast", 255) < CONTRAST_MIN:
        problems.append("headline: contrast %.0f is too low" % c.get("headline_contrast", 0))
    if c.get("mean_luma", 255) < MIN_MEAN_LUMA:
        problems.append("light: post is crushed dark")
    if c.get("group_gap_min", GROUP_GAP_MIN) < GROUP_GAP_MIN:
        problems.append("spacing: text groups only %dpx apart (min %d)" % (c["group_gap_min"], GROUP_GAP_MIN))
    if c.get("logo_colour_diff", 0) > LOGO_COLOUR_TOL:
        problems.append("logo: colour is %.0f off the text colour" % c["logo_colour_diff"])
    return problems


def _x_overlap(a: Box, b: Box) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0])


def layout_problems(groups: Iterable[Tuple[str, Box]], canvas: Sequence[int], safe_bottom: Optional[float] = None) -> List[str]:
    """Spacing check on measured boxes (x0, y0, x1, y1) of each text group, e.g. [("offer", box), ("cta", box)].

    A group is checked against the nearest group above it that it shares columns with; groups side by side
    on one row (LINK IN BIO and the logo) never stack, so no gap applies to them."""
    gs = sorted(groups, key=lambda g: g[1][1])
    gap_min = GROUP_GAP_MIN * canvas[0] / 1080
    problems: List[str] = []
    for i, (name, b) in enumerate(gs):
        above = [(n, a) for n, a in gs[:i] if _x_overlap(a, b) and a[1] < b[1]]
        if above:
            n, a = max(above, key=lambda g: g[1][3])
            gap = b[1] - a[3]
            if gap < gap_min:
                problems.append("spacing: %s sits %dpx under %s (min %dpx)" % (name, gap, n, gap_min))
        if safe_bottom is not None and b[3] > safe_bottom:
            problems.append("spacing: %s ends at %dpx, past the safe zone at %dpx" % (name, b[3], safe_bottom))
    return problems


def logo_colour_diff(logo, text_rgb: Sequence[int]) -> float:
    """Largest channel difference between the logo's solid ink and the text colour."""
    px = [p[:3] for p in logo.convert("RGBA").getdata() if p[3] > 200]
    if not px:
        return 0.0
    mean = [sum(c[k] for c in px) / len(px) for k in range(3)]
    return max(abs(mean[k] - text_rgb[k]) for k in range(3))


def tint_logo(logo, rgb: Sequence[int]):
    """The logo in exactly `rgb`, keeping its shape (alpha)."""
    from PIL import Image
    src = logo.convert("RGBA")
    out = Image.new("RGBA", src.size, tuple(int(v) for v in rgb[:3]) + (0,))
    out.putalpha(src.getchannel("A"))
    return out
