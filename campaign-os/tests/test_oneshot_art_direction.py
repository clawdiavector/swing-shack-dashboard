"""One-shot art direction — scene recipes, type spec, and the shape of the wire prompt.

The contract here is the reference set: the hand prompts that rendered clean
text on Ideogram 3, Ideogram 4 and Recraft V4, versus the Campaign OS wire
that rendered garbled extra text on the same model and the same line.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

PHOTO_TYPES = ("fitting_headline", "coaching_promo", "service_hero")
COLLAGE_TYPES = ("zine_collage", "humour_card")
ALL_TYPES = PHOTO_TYPES + COLLAGE_TYPES


@pytest.fixture(autouse=True)
def _bundled(monkeypatch):
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))


def _wire(post_type: str, headline: str = "Hit more greens", kicker: str = "Book a fitting") -> str:
    from _lib.creative_director import _load_brand_context, compose_prompt
    from _lib.jobs.layer5.oneshot_art_direction import build_art_direction

    art = build_art_direction(
        brand_id="stick",
        post_type=post_type,
        headline=headline,
        kicker=kicker,
        palette=_load_brand_context("stick").get("palette") or {},
    )
    return compose_prompt(
        brand_id="stick",
        job=art.scene,
        literal_text=f"{headline}\n{kicker}".strip(),
        literal_text_spec=art.type_spec,
        brand_colours_inline=True,
        output_style=art.output_style,
        render_text=True,
        format_aspect="4:5",
    )["wire_prompt"]


@pytest.mark.parametrize("post_type", ALL_TYPES)
def test_every_oneshot_post_type_has_its_own_scene(post_type):
    """Not the one generic empty-bay sentence for everything."""
    from _lib.creative_director import _load_brand_context
    from _lib.jobs.layer5.oneshot_art_direction import build_art_direction

    art = build_art_direction(
        brand_id="stick",
        post_type=post_type,
        headline="Hit more greens",
        palette=_load_brand_context("stick").get("palette") or {},
    )
    assert art.scene_source == f"recipe:{post_type}"
    assert "empty premium indoor golf coaching bay" not in art.scene


def test_treatments_split_photo_from_collage():
    from _lib.jobs.layer5.oneshot_art_direction import treatment_for_post_type

    for pt in PHOTO_TYPES:
        assert treatment_for_post_type(pt) == "photo"
    for pt in COLLAGE_TYPES:
        assert treatment_for_post_type(pt) == "collage"


def test_collage_scene_names_its_cutouts_not_just_a_style_word():
    wire = _wire("humour_card")
    assert "Collage elements:" in wire
    assert "halftone" in wire
    # The collage treatment must not carry the photo treatment's single-frame
    # rule — a collage IS split panels.
    assert "not split panels" not in wire


def test_photo_scene_keeps_screens_dark():
    """The hardcoded TrackMan monitor is where the garbled on-screen text came from."""
    wire = _wire("coaching_promo")
    assert "no legible content on it" in wire


@pytest.mark.parametrize("post_type", ALL_TYPES)
def test_wire_is_one_art_director_paragraph(post_type):
    wire = _wire(post_type)
    assert "You are creating:" not in wire
    assert "[" not in wire                     # no [JOB]/[BRAND]/[NEGATIVE] labels
    assert "Philosophy:" not in wire
    assert "Composition rules:" not in wire
    assert "Lean toward:" not in wire
    assert "Colour anchor:" not in wire        # dangling label fragment
    assert "logo lockup" not in wire           # the job overlays the real asset
    assert "\n" not in wire


@pytest.mark.parametrize("post_type", ALL_TYPES)
def test_wire_carries_the_full_type_spec(post_type):
    """Size, case, colour hex, position, no-box — the way the winners spelled it."""
    wire = _wire(post_type)
    assert '"HIT MORE GREENS"' in wire          # quoted in the case we asked for
    assert '"BOOK A FITTING"' in wire
    assert "uppercase" in wire
    assert "#00B3BA" in wire or "#FFFFFF" in wire
    assert "character for character" in wire
    assert "No other text, no logo, no watermark." in wire
    assert "4:5 portrait aspect ratio." in wire


def test_photo_headline_only_still_gets_a_type_spec():
    wire = _wire("service_hero", headline="Your swing, decoded", kicker="")
    assert '"YOUR SWING, DECODED"' in wire
    assert "no background box behind the text" in wire


@pytest.mark.parametrize("post_type", ALL_TYPES)
def test_recipes_stay_inside_the_render_text_budget(post_type):
    """The trim loop cannot shrink these — JOB and LITERAL TEXT are both exempt."""
    from _lib.creative_director import _PROMPT_MAX_CHARS_RENDER_TEXT

    assert len(_wire(post_type)) <= _PROMPT_MAX_CHARS_RENDER_TEXT


def test_ai_logo_opt_in_flips_the_no_logo_clause():
    from _lib.jobs.layer5.oneshot_art_direction import build_art_direction

    off = build_art_direction(brand_id="stick", post_type="service_hero", headline="A")
    on = build_art_direction(
        brand_id="stick", post_type="service_hero", headline="A", ai_logo=True
    )
    assert "no logo," in off.output_style
    assert "no logo," not in on.output_style


def test_unknown_post_type_falls_back_to_the_callers_scene():
    from _lib.jobs.layer5.oneshot_art_direction import build_art_direction

    art = build_art_direction(
        brand_id="stick",
        post_type="something_new",
        headline="A",
        fallback_scene="Photoreal premium indoor golf studio mood.",
    )
    assert art.scene_source == "fallback:background_plate"
    assert art.scene.startswith("Photoreal premium indoor golf studio mood")
