# Plan — Stick stick-service-square (service_square) 2026-09-27

Orchestrator-adopted plan (Claude plan pane w6H:p7N went `done` mid-exploration without writing — `herdr agent prompt` re-prompt returned `done` in 1s with no output, same shape as the stick-statement precedent; this handoff was written by the orchestrator).

## Problem

Brand: **stick**. Build a Campaign OS archetype `stick-service-square` from Content Bank refs. Two distinct 1081×1081 square compositions form a 1:1 pair:

- `lab@stick copy 4.jpg` — chevrons TOP-LEFT, partial frame on TOP-RIGHT corner, centred 4-line descriptive headline.
- `avoda@stick copy 2.jpg` — chevrons TOP-RIGHT, partial frame on TOP-LEFT corner, big "SERVICE / @ / stick" two-line lockup.

Both share: 1081×1081 canvas, light blue→grey gradient field, dark navy `#053260` decorative chevrons + thin partial frame, no logo, no photo. `post_type: service_square`. Pack slug: `service-square`.

Refs:

- `/home/kyle/Downloads/Content Bank-20260925T133008Z-1-001/Content Bank/Stick/Services/lab@stick copy 4.jpg` (1081×1081)
- `/home/kyle/Downloads/Content Bank-20260925T133008Z-1-001/Content Bank/Stick/Services/avoda@stick copy 2.jpg` (1081×1081)

## Anatomy (measured + visual)

`measure_refs.py` → `/tmp/tpl/stick-square/measured.json` (accent `#053260` on both; both refs use a light gradient field that the script does not classify as colour-line so we visually extract):

- **Canvas**: 1081×1081 square (1:1). New canonical canvas for stick: `ig_square` (or reuse `ig_post` with canvas_overrides if the engine does not support a new canvas yet — implementer decides).
- **Background**: light blue→light grey vertical gradient. Pick two existing tokens (or add `gradient_sky` + `gradient_fog`); for a v1 use the closest existing palette tokens or fall back to `#D6E4EC` → `#EAEEF1`.
- **Chevrons** (zone `chevrons`): three `>>>` shapes in `#053260`. Position: top-left (~0.03, 0.05) for the "lab" form, mirrored top-right for the "avoda" form. Implement as a new asset `templates/service-square/assets/chevrons.png` (PNG, transparent bg, ~280×100px, navy `#053260`) drawn as three right-pointing chevrons with even spacing.
- **Frame** (zone `frame`): `kind: decorative, shape: frame` with `inset_px: 56`, `stroke_px: 4`, `colour: navy_deep` (#073C52) **OR** a new partial frame — engine only supports a full-rectangle outline, so for v1 use full rectangle and accept slight visual difference from ref (refs show only ~3 sides of the frame); the partial-frame treatment is a follow-up if Kyle pushes.
- **Body (lab form)** — zone `headline_centre`: 4-line centred text, font_role `display` (Montserrat-Black 900), navy `#053260`, `text_transform: none` (refs are mixed case), `max_lines: 4`, `max_chars_per_line: 22`, `line_height: 1.1`, `align: center`. Source: `caption_hook`.
- **Body (avoda form)** — zone `headline_lockup`: a two-zone layout —
  - `service_word`: TOP-LEFT, very large Montserrat-Black uppercase, navy. Source: `caption_hook` first word (e.g. "COACHING"), `text_transform: uppercase`, font_role `display` size ~280px.
  - `at_lockup`: BOTTOM-RIGHT, large italic-feeling word, navy. Source: `venue_name` or `caption_hook` tail (e.g. "stick"), `text_transform: none`, font_role `h1` (Montserrat-Black 72). Rendered in italic via existing display weights (no italic weight vendored; approximate by tilting in PIL or ship upright and document the gap).
  - `at_glyph`: a faded grey `#C9CFD3` `@` glyph between the two (~y 0.45, x 0.55), font_role `h1` ~250px, `colour: grey_light`, static text.
- **Footer**: none (no logo, no tagline, no CTA).
- **No photo**: `applies_to.needs_photo: false`.

Colour tokens to add (palette/brand.json):

```json
"gradient_sky": "#D6E4EC",
"gradient_fog": "#EAEEF1",
"navy_alt": "#053260"
```

`navy_alt` already exists per palette/brand.json — reuse.

Fonts (existing in typography/fonts.json): no new role needed. Use:

- `display` (Montserrat-Black 900) for headline_centre + service_word
- `h1` (Montserrat-Black 900, 72px) for at_lockup + at_glyph

Engine delta — if implementer confirms the engine's `decorative/frame` zone renders a full rectangle (it does), ship v1 with a full rectangle. For the partial-frame on refs, implementer can either (a) add a new `decorative/partial_frame` engine zone with `sides: ["top","right","bottom"]` and `inset_px: 56`, or (b) accept the difference and document it. v1 path: full rectangle + add a note in template.md.

## Edits

### 1. `data/brand-directory/stick/visual-spec/archetypes.json`

Append a 5th archetype `stick-service-square`. Required zones (all key/rect/values below in **fraction-of-canvas** at 1081×1081):

```jsonc
{
  "id": "stick-service-square",
  "name": "Service square — chevrons + decorative frame, 1:1 navy text-only (centred or split lockup)",
  "description": "1081×1081 square. Light blue→grey gradient field. Dark navy decorative chevrons (>>>) in one corner (top-left for 'lab'/centred form, mirrored for 'avoda'/split lockup) and a thin navy rectangular frame at ~56px inset. Two compositional variants selected via selection rule: (a) lab form — centred 4-line caption_hook in navy Montserrat Black mixed case; (b) avoda form — large UPPERCASE service word top-left + faded '@' glyph centre-right + large 'stick' word bottom-right. No photo. Used for service-description posts (LAB, AVODA, COACHING, FITTING, etc.).",
  "canvas": "ig_square",
  "block_anchor": "center",
  "applies_to": {
    "channels": ["instagram", "facebook"],
    "record_types": ["moment", "evergreen"],
    "needs_photo": false
  },
  "background": {
    "kind": "gradient",
    "gradient": {
      "from": "gradient_sky",
      "to": "gradient_fog",
      "direction": "to-bottom"
    }
  },
  "zones": {
    "chevrons": {
      "rect": {"x0": 0.03, "y0": 0.04, "x1": 0.32, "y1": 0.14},
      "kind": "image",
      "source": "asset",
      "asset": "chevrons.png",
      "fit": "aspect_fit",
      "align": "left",
      "valign": "top",
      "corner": "top_left",
      "mirror_corners": ["top_right"]
    },
    "frame": {
      "rect": {"x0": 0.05, "y0": 0.04, "x1": 0.95, "y1": 0.96},
      "kind": "decorative",
      "shape": "frame",
      "inset_px": 56,
      "stroke_px": 4,
      "colour": "navy_alt",
      "alpha": 1.0
    },
    "headline_centre": {
      "rect": {"x0": 0.12, "y0": 0.36, "x1": 0.88, "y1": 0.66},
      "kind": "text",
      "source": "caption_hook",
      "font_role": "display",
      "max_lines": 4,
      "max_chars_per_line": 22,
      "line_height": 1.10,
      "text_transform": "none",
      "align": "center",
      "valign": "middle",
      "colour": "navy_alt",
      "variant": "lab",
      "min_font_px": 56
    },
    "service_word": {
      "rect": {"x0": 0.05, "y0": 0.32, "x1": 0.95, "y1": 0.50},
      "kind": "text",
      "source": "caption_hook_first_word",
      "font_role": "display",
      "max_lines": 1,
      "max_chars_per_line": 14,
      "text_transform": "uppercase",
      "align": "left",
      "valign": "top",
      "colour": "navy_alt",
      "variant": "avoda",
      "min_font_px": 160
    },
    "at_glyph": {
      "rect": {"x0": 0.50, "y0": 0.38, "x1": 0.85, "y1": 0.62},
      "kind": "text",
      "source": "static",
      "text": "@",
      "font_role": "h1",
      "text_transform": "none",
      "align": "center",
      "valign": "middle",
      "colour": "grey_light",
      "variant": "avoda",
      "min_font_px": 200
    },
    "at_lockup": {
      "rect": {"x0": 0.30, "y0": 0.55, "x1": 0.95, "y1": 0.86},
      "kind": "text",
      "source": "caption_hook_tail",
      "font_role": "h1",
      "max_lines": 1,
      "max_chars_per_line": 8,
      "text_transform": "none",
      "align": "right",
      "valign": "bottom",
      "colour": "navy_alt",
      "variant": "avoda",
      "min_font_px": 200
    }
  },
  "logo_anchor": null,
  "safe_zone": {"x0": 0.07, "y0": 0.06, "x1": 0.93, "y1": 0.94},
  "max_total_chars": 80
}
```

Update `canvases` block — add `ig_square` if the engine supports new canvas entries (it reads `w/h` per canvas_id from `doc.canvases`). The engine currently builds the base canvas from `archetype.canvas` which must be present in `doc.canvases`; implementer adds:

```jsonc
"ig_square": {
  "w": 1080,
  "h": 1080,
  "aspect": "1:1",
  "channels": ["instagram", "facebook"],
  "safe_zone": {"x0": 0.07, "y0": 0.06, "x1": 0.93, "y1": 0.94}
}
```

If the engine hard-rejects unknown canvases, fall back to `canvas: "ig_post"` with a `canvas_overrides.ig_square` block on the archetype and document the gap.

### 2. `data/brand-directory/stick/palette/brand.json`

Add gradient tokens:

```jsonc
"gradient_sky": "#D6E4EC",
"gradient_fog": "#EAEEF1"
```

(`navy_alt` `#053260` and `grey_light` `#D1D1D1` already exist.)

### 3. Engine delta — `campaign-os/_lib/archetype_compose.py`

If `variant: lab` / `variant: avoda` are not currently honoured by the composer, implementer should:

- Skip zones whose `variant` does not match `doc.variant` (default `doc.variant == "lab"` if unspecified).
- Treat `source: caption_hook_first_word` / `caption_hook_tail` as derived fields (split `caption_hook` on first whitespace; first = first_word, rest = tail). Add a helper in `archetype_compose._content_for_source` for these two new sources.
- Treat `mirror_corners` on the chevrons zone by reflecting the rendered chevron image horizontally and pasting at the mirrored rect (`x1 -> 1.0 - x0` etc.). v1 path: ship `corner: top_left` only and document that `top_right` mirroring is a follow-up.

### 4. New pack — `data/brand-directory/stick/templates/service-square/`

```
templates/service-square/
  references/
    ref-lab.jpg       (symlink or copy of lab@stick copy 4.jpg)
    ref-avoda.jpg     (symlink or copy of avoda@stick copy 2.jpg)
  assets/
    chevrons.png      (new — see Anatomy)
  photos/             (empty — no_photo archetype)
  golden/
    render-lab.png    (compose a sample post via the engine)
    render-avoda.png  (compose a sample post via the engine)
    compare-sheet.png (compare_sheet.py output)
  spec.json           (mirrors the archetype block from archetypes.json)
  template.md         (platforms + post_type + selection rule)
```

`spec.json` is the same dict as the new archetype entry (drop the `applies_to.needs_photo` nesting quirks — copy the stick-service-frame `spec.json` shape exactly).

`template.md` minimum content (mirror stick-service-frame template.md):

```markdown
# stick-service-square

Stick service-description square template — 1:1 (1081×1081).

## When to use
- pillar: any
- service category in {LAB, AVODA, COACHING, FITTING, CLUB FITTING, RE-GRIP}
- post_type: service_square
- needs_photo: false

## Variants
- lab form — caption_hook is a full sentence (4 lines, mixed case).
- avoda form — caption_hook first word is the SERVICE NAME (uppercase), tail is "stick".

## Selection rule
- if record.service_category in {"AVODA", "WORKSHOP"} -> variant=avoda
- else -> variant=lab (default)

## Platforms
- instagram (ig_square)
- facebook (ig_square — IG square crops well into FB)
```

### 5. Tests — `campaign-os/tests/`

Add `test_stick_service_square.py` covering:

- archetype JSON parses, contains `stick-service-square`
- canvas `ig_square` present
- chevrons asset exists
- spec.json round-trips with archetype
- compose a sample lab form + sample avoda form via the engine; PNG bytes non-empty; compare against `golden/render-lab.png` / `golden/render-avoda.png` for byte hash stability (skip if env lacks PIL).
- selection rule: pick lab vs avoda from a sample record

Add the family + schema spot checks to `tests/test_archetype_schema.py` and `tests/test_compose_visual.py` if they iterate over `archetypes.json` (they likely do — confirm during implement).

## Done criteria (from manifest)

- [ ] archetype `stick-service-square` in visual-spec/archetypes.json
- [ ] compare golden JPG in template pack (`golden/compare-sheet.png`)
- [ ] pytest family + schema spot checks pass
- [ ] template.md documents platforms + post_type
