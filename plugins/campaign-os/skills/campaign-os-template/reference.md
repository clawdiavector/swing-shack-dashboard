# Compose engine reference (archetype JSON)

Engine: `campaign-os/_lib/archetype_compose.py` · selection: `campaign-os/_lib/archetypes.py` ·
schema: `campaign-os/_lib/archetype_schema_data.json` (validated by `tests/jobs/test_archetype_schema_v2.py`).
File: `data/brand-directory/<brand>/visual-spec/archetypes.json`. Rects are **fractions** of the
target canvas (x of width, y of height). Worked example: `ss-did-you-know` (swing-shack).

## Canvases (per brand doc)

| id | px | channels |
|---|---|---|
| `ig_post` | 1080×1350 | instagram |
| `ig_story` | 1080×1920 | instagram_story |
| `fb_post` | 1200×630 | facebook (link-style; usually wrong for posters) |
| `gbp_post` | 1200×900 | gbp (L5 auto-create skips gbp; recompose includes it) |

Archetype keys: `canvas` (measured base), `block_anchor: center` (taller canvas shifts all
zones by half the extra height), `canvas_overrides.<canvas>` (**replaces** the zone map for
that canvas — give every zone), `channel_canvas: {"facebook": "ig_post"}` (post FB as 4:5),
`applies_to.channels` (compose skips channels not listed — list only platforms that read well).

## Background

| kind | keys |
|---|---|
| `solid` | `fill` token/#hex |
| `gradient` | `gradient: {direction: horizontal\|vertical, from, to}` |
| `photo_full_bleed` + `cover: true` | photo centre-cropped to cover; `library` (brand-relative dir, used when no photo, picked by `photo_seed`/headline hash), `focus_y`, `scrim: {rect, from_alpha, to_alpha}` darkening |
| `photo_full_bleed` (no cover) | legacy: photo pasted via a `photo` image zone |

`applies_to.needs_photo: false` + library = no AI photo stage (deterministic, real venue shots).

## Zones

| kind | keys |
|---|---|
| `text` | `source` (caption_hook, cta, static+`text`, …), `font_role`, `max_font_px`, `min_font_px`, `max_lines`, `line_height` (× font size), `text_transform`, `text_origin_x` (px), `align`, `valign` top\|middle\|bottom, `colour` or `colour_options` [tokens] (+ fields.accent), `tracking_em`, `emphasis_words` + `emphasis_font_role`, `wrap: balanced`, `h_scale`, `echo {dx_em, dy_em, stroke_em, shadow_alpha}`, `attach_above {zone, gap_px}` |
| `image` | `source: asset` + `asset` (brand-relative path), `fit: aspect_fit`, `align`, `valign`; `source: photo` |
| `band` | `fill` — solid rectangle |
| `decorative` + `shape: frame` | `inset_px`, `stroke_px`, `colour`, `alpha` — border that ignores rect |
| `logo` | brand root `logo.png` (prefer an `image` asset zone with the template's own logo) |

Notes:
- `max_font_px` beats the fonts.json role size (roles are per brand; zones differ).
- `wrap: balanced` = use as many lines as allowed, minimise widest line — matches designer
  breaks (GOLF / CAN / FEEL / SIMPLER?). Default wrap is greedy by width.
- `h_scale` < 1 squashes horizontally about `text_origin_x`; widths for fitting are divided by it.
- `attach_above` zones draw after others; `anchor_bottom = headline_top - gap_px`.
- Cap height ≈ 0.70 × font px for Montserrat; `line_height = pitch_px / font_px`.

## Fonts / palette

- `typography/fonts.json` → `roles.<role>.file` (brand-relative TTF). Only schema roles:
  display, h1, h2, h3, body, caption, cta.
- Vendor OFL fonts: variable TTF from `github.com/google/fonts/raw/main/ofl/<family>/`, then
  `fonttools varLib.instancer -q Family[wght].ttf wght=900 -o Family-Black.ttf`. Copy `OFL.txt`.
- `palette/brand.json` → `tokens: {name: "#hex"}` (measured accents).
- Assets resolve DATA_DIR → bundled → repo `data/` (`_resolve_brand_relative`), so repo files work on Railway.

## Selection

`selection.rules[]` evaluated in order, **last match wins**; `when` keys: `pillar_in`,
`has_product_item`, `subject`, `post_type_in`. A calendar record's `template_id` (or
`archetype_id`) pins the archetype outright. Context comes from `_moment_context` (calendar record
`pillar_id`, `post_type`, `template_id`, `product_ids`).

## Schema / test limits

- `test_at_most_four_archetypes_per_brand` — max 4 per brand; raise it (schema `maxItems` + test) before a 5th.
- Enums: zone `kind` (text, image, logo, band, decorative), `source`, `font_role`, `valign`, gradient `direction`.
- Full suite has ~160 pre-existing failures — compare failure lists against the base checkout, not zero.
