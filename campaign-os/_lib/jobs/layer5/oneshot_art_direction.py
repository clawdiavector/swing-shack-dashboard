"""One-shot art direction — the scene and type spec a render-text model actually reads.

Written against the hand prompts that produced clean posters on Ideogram 3,
Ideogram 4 and Recraft V4 (Kyle's reference set, 2026-10-02/05). Two shapes
came back clean, and both are reproduced here:

  photo   — a specific shot. Hero subject, named lighting, a photographic
            style phrase, shallow depth of field. Then the type spelled out:
            size, case, colour hex, position, "no background box".
  collage — a named collage style, the base and accent colours, an explicit
            list of collage elements, then sticker-style type.

What lost, every time, was the generic scene ("empty premium indoor golf
coaching bay, TrackMan launch monitor glow") plus a bare literal line and no
type direction. A text-strong model given a vague plate and an unstyled
string invents typography to fill the frame.

Scenes live here and not in `image_draft_context.background_plate_scene_prompt`
on purpose — that function feeds the template/overlay path, where the image is
a plate under deterministic text and must stay quiet. Here the image IS the
poster.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Keep the bottom-right quiet for the logo overlay `_overlay_logo_on_file`
# composites after generation. Deliberately does not say "logo" or "lockup":
# naming the logo in a render-text prompt is an invitation to draw one, and
# the old placement sentence did exactly that while the job overlaid the real
# asset on top anyway.
_CLEAR_CORNER = "Keep the bottom-right corner clear and uncluttered."

_PHOTO_STYLE = (
    "premium sports-apparel campaign photography, photo-real, shallow depth of field"
)

# Non-text safety for photo treatments. Shorter than the old
# _RENDER_TEXT_SCENE_SUFFIX — only the two clauses that earned their place:
# the single-frame rule, and the screens-are-dark rule that stops a model
# treating a named monitor as a second surface to put text on.
_PHOTO_SAFETY = (
    "Single unified photograph, not split panels. Any screen or monitor in shot is "
    "dark, with no legible content on it."
)

_COLLAGE_STYLE = (
    "bold editorial collage, torn paper layers, halftone dot texture, taped edges, "
    "rough cutout borders, sticker details, cheeky insider golf energy, "
    "phone-readable at a glance"
)

PHOTO_TREATMENT = "photo"
COLLAGE_TREATMENT = "collage"

# post_type → treatment. Keys are the one-shot allowlist in
# `marketing_calendar.ONESHOT_ALLOWED_POST_TYPES`; anything outside it never
# reaches this module (render_mode_for_record gates it upstream).
TREATMENT_BY_POST_TYPE = {
    "fitting_headline": PHOTO_TREATMENT,
    "coaching_promo": PHOTO_TREATMENT,
    "service_hero": PHOTO_TREATMENT,
    "zine_collage": COLLAGE_TREATMENT,
    "humour_card": COLLAGE_TREATMENT,
}

# Hero subject + lighting per post type. One concrete shot each — the thing
# the camera is actually pointed at — not a description of the room.
_PHOTO_SUBJECTS = {
    "fitting_headline": (
        "a rack of irons catching a hard rim light down the shafts, "
        "a fitting bay falling away into shadow behind them"
    ),
    "coaching_promo": (
        "a single figure in dark athletic wear seen from behind at the top of a "
        "backswing, rim light along the shoulders and the shaft, the bay dark "
        "around them"
    ),
    "service_hero": (
        "a row of indoor hitting bays receding into darkness, one bay lit, a ball "
        "teed on green turf inside that pool of light"
    ),
}
_PHOTO_SUBJECT_FALLBACK = (
    "a single golf club on green turf catching a hard rim light, the room falling "
    "away into shadow behind it"
)

# Collage elements per post type. The reference collage named its cutouts
# explicitly ("a black-and-white cutout photo of a bucket of range balls, torn
# strips of navy and teal paper, a halftone dot pattern burst, a small circular
# sticker badge with jagged edge") — a style word alone is not enough.
_COLLAGE_ELEMENTS = {
    "zine_collage": (
        "a black-and-white cutout photo of a golf ball on a tee, torn strips of "
        "navy and teal paper, a halftone dot pattern burst, a small circular "
        "sticker badge with a jagged edge"
    ),
    "humour_card": (
        "a black-and-white cutout photo of a bucket of range balls, torn strips of "
        "navy and teal paper, a halftone dot pattern burst, a small circular "
        "sticker badge with a jagged edge"
    ),
}
_COLLAGE_ELEMENT_FALLBACK = (
    "a black-and-white cutout photo of a golf club head, torn strips of navy and "
    "teal paper, a halftone dot pattern burst, a small circular sticker badge with "
    "a jagged edge"
)


@dataclass
class OneshotArtDirection:
    """Everything the one-shot wire prompt needs, already art-directed."""

    treatment: str
    scene: str
    type_spec: str
    output_style: str
    post_type: str
    scene_source: str


def treatment_for_post_type(post_type: Any) -> str:
    return TREATMENT_BY_POST_TYPE.get(
        str(post_type or "").strip().lower(), PHOTO_TREATMENT
    )


def _role(palette: dict, role: str, default_hex: str, default_name: str) -> tuple[str, str]:
    entry = palette.get(role) if isinstance(palette, dict) else None
    if isinstance(entry, dict):
        hexed = str(entry.get("hex") or "").strip()
        name = str(entry.get("name") or "").strip()
        if hexed:
            return name or default_name, hexed
    return default_name, default_hex


def _palette_roles(palette: dict) -> dict[str, tuple[str, str]]:
    """(name, hex) for the three roles the poster actually uses."""
    return {
        "field": _role(palette, "primary", "#073C52", "deep navy"),
        "accent": _role(palette, "accent", "#00B3BA", "teal"),
        "type": _role(palette, "neutral_light", "#FFFFFF", "white"),
    }


def _brand_display_name(brand_id: str) -> str:
    return " ".join(part.capitalize() for part in str(brand_id or "").split("-") if part)


def _quoted(line: str) -> str:
    """Uppercase, quoted, ready to drop into the type spec.

    The type direction says "uppercase", and the instruction right after it
    says "character for character" — so the quoted characters have to already
    be the characters we want. The reference prompts quoted their lines in
    caps for the same reason. The as-authored casing is kept on the sidecar's
    `literal_text`.
    """
    return '"' + line.replace('"', "'").strip().upper() + '"'


def _sentence(text: str) -> str:
    """Close a clause that ends on a quoted line without doubling punctuation."""
    stripped = text.rstrip()
    if stripped.endswith('"') and stripped[-2:-1] in ".!?":
        return stripped
    return stripped if stripped.endswith(".") else stripped + "."


def _photo_scene(post_type: str, roles: dict[str, tuple[str, str]]) -> str:
    subject = _PHOTO_SUBJECTS.get(post_type, _PHOTO_SUBJECT_FALLBACK)
    field_name, field_hex = roles["field"]
    accent_name, accent_hex = roles["accent"]
    return (
        f"Dark moody indoor golf studio, {subject}, {accent_name} {accent_hex} "
        f"accent lighting over a {field_name} {field_hex} field, {_PHOTO_STYLE}. "
        f"{_PHOTO_SAFETY} {_CLEAR_CORNER}"
    )


def _collage_scene(post_type: str, roles: dict[str, tuple[str, str]], brand_id: str) -> str:
    elements = _COLLAGE_ELEMENTS.get(post_type, _COLLAGE_ELEMENT_FALLBACK)
    field_name, field_hex = roles["field"]
    accent_name, accent_hex = roles["accent"]
    type_name, type_hex = roles["type"]
    return (
        f"4:5 portrait social media campaign still for {_brand_display_name(brand_id)}, a modern golf "
        f"performance brand. Style: {_COLLAGE_STYLE}. Base colour {field_name} "
        f"{field_hex}, accent {accent_name} {accent_hex}, {type_name} {type_hex} "
        f"paper cutout elements. Collage elements: {elements}. {_CLEAR_CORNER}"
    )


def _photo_type_spec(
    headline: str,
    kicker: str,
    roles: dict[str, tuple[str, str]],
) -> str:
    accent_name, accent_hex = roles["accent"]
    type_name, type_hex = roles["type"]
    head = (
        f"large bold uppercase text in {accent_name} {accent_hex} reading "
        f"{_quoted(headline)}"
    )
    if kicker:
        opener = (
            f"Centred near the top, small {type_name} {type_hex} uppercase text in a "
            f"light sans-serif reading {_quoted(kicker)}, and directly below it, {head}, "
            "both centred"
        )
    else:
        opener = f"Centred near the top, {head}, centred"
    return (
        f"{opener}, generous letter spacing, no background box behind the text, "
        "text sits directly on the photo. Render this text character for character "
        "and nothing else."
    )


def _collage_type_spec(
    headline: str,
    kicker: str,
    roles: dict[str, tuple[str, str]],
) -> str:
    type_name, type_hex = roles["type"]
    spec = _sentence(
        f"Large bold {type_name} {type_hex} uppercase headline text in torn-paper-sticker "
        f"style, top-left, reading {_quoted(headline)}"
    )
    if kicker:
        spec += " " + _sentence(
            f"Below it, smaller {type_name} sticker-style text reading {_quoted(kicker)}"
        )
    return spec + " Render this text character for character and nothing else."


def _output_style(treatment: str, *, ai_logo: bool) -> str:
    # One closing sentence, same as the reference prompts. `no logo` holds
    # unless the operator explicitly opted into an AI-rendered mark.
    logo_clause = "" if ai_logo else " no logo,"
    kind = "A single photograph." if treatment == PHOTO_TREATMENT else "A single collage still."
    return f"{kind} No other text,{logo_clause} no watermark. 4:5 portrait aspect ratio."


def build_art_direction(
    *,
    brand_id: str,
    post_type: Any,
    headline: str,
    kicker: str = "",
    ai_logo: bool = False,
    palette: dict | None = None,
    fallback_scene: str = "",
) -> OneshotArtDirection:
    """Scene + type spec for one one-shot card.

    `fallback_scene` is used when the post type has no recipe here — the
    caller's existing background-plate scene, so an unmapped type still
    generates rather than failing.
    """
    pt = str(post_type or "").strip().lower()
    treatment = treatment_for_post_type(pt)
    roles = _palette_roles(palette or {})

    known = pt in _PHOTO_SUBJECTS or pt in _COLLAGE_ELEMENTS
    if not known and fallback_scene.strip():
        scene = fallback_scene.strip()
        scene_source = "fallback:background_plate"
    elif treatment == COLLAGE_TREATMENT:
        scene = _collage_scene(pt, roles, brand_id)
        scene_source = f"recipe:{pt or 'default'}"
    else:
        scene = _photo_scene(pt, roles)
        scene_source = f"recipe:{pt or 'default'}"

    if treatment == COLLAGE_TREATMENT:
        type_spec = _collage_type_spec(headline, kicker, roles)
    else:
        type_spec = _photo_type_spec(headline, kicker, roles)

    return OneshotArtDirection(
        treatment=treatment,
        scene=scene,
        type_spec=type_spec,
        output_style=_output_style(treatment, ai_logo=ai_logo),
        post_type=pt,
        scene_source=scene_source,
    )
