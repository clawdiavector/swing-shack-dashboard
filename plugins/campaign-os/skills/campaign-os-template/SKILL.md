---
name: campaign-os-template
description: >-
  Turn a batch of real brand post images into a pixel-accurate Campaign OS compose template
  (archetype + template pack) — group by filename, map platforms, measure layout/fonts/colours,
  extract logo, write archetype JSON, render and compare against references, wire selection.
  Use when Kyle drops example posts and says make a template, template these, match these posts,
  or when adding a new post style for stick, swing-shack or another brand.
---

# Campaign OS template from reference images

Deterministic path: the image is drawn by PIL from measured JSON — no AI on pixels. Accuracy
comes from **measuring the references**, vendoring the **real font**, and **matching line breaks**.
Worked example: swing-shack `ss-did-you-know` (branch `feat/ss-did-you-know-template`, pack
`data/brand-directory/swing-shack/templates/did-you-know/`). Write-up:
`~/finder-workspace/repos/work/agent-control/context/campaign-os-template-authoring.md` *(Kyle’s desk only — the method below is self-contained without it)*.

Scripts: `~/.agents/skills/campaign-os-template/scripts/` (Pillow + numpy; fonttools for fonts).
Engine options: [reference.md](reference.md).

## Rules

- One brand at a time — never mix Stick and Swing Shack in a batch or a table.
- Services/posters only unless Kyle asks for retail.
- Work in a worktree off `integrate/campaign-os-brand-lanes-v1`; push `feat/*` only. `main` = Kyle names it.
- Real copy comes from the caption (`caption_hook`, `cta`) — never ship reference text as fields.
- New image per iteration (timestamped names) — the image viewer caches same-name files.

## Workflow

```
- [ ] 1 Group     group_images.py → confirm groups with Kyle (merge same-look stems)
- [ ] 2 Platforms decide canvases per group (table below)
- [ ] 3 Measure   measure_refs.py on every ref → frame, lines, cap, pitch, accents, logo
- [ ] 4 Zoom      crop+NEAREST upscale one headline + logo to see effects (outline, shadow)
- [ ] 5 Font      identify family; fetch OFL cut; font_fit.py → size + h_scale
- [ ] 6 Assets    extract_logo.py from flattest ref; photo library (raw venue shots)
- [ ] 7 Archetype add to archetypes.json + palette tokens + fonts.json roles
- [ ] 8 Render    compare_sheet.py → fix → repeat until line breaks + colours match
- [ ] 9 Pack      templates/<slug>/{references,assets,photos,golden,spec.json,template.md}
- [ ] 10 Select   selection rule (post_type_in / pillar_in) + pinned template_id path
- [ ] 11 Test     new test file + schema/selection/compose tests; full suite vs base
- [ ] 12 Ship     commit, push feat/*, update taxonomy handoff, show Kyle the compare sheet
```

### 1 Group

```bash
S=~/.agents/skills/campaign-os-template/scripts
python3 $S/group_images.py --src "<dump>/<Brand>/Services" --out /tmp/tpl/<brand> --clean
```

Stems strip `copy N`, trailing digits and `_post/_story`, so `coaching_post2` + `coaching_story`
→ `coaching`. Open `_overview.jpg`; different stems with the same look (coaching + fitting
promo) are **one** template. One-off event designs (Ryder Cup, Black Friday one-offs) are not templates.

### 2 Platforms

| Ref size | Canvas | Note |
|---|---|---|
| 1081×1351 | `ig_post` | native |
| 1081×1201 | `ig_post` | old crop — same pixel block, `block_anchor: center` re-centres |
| 1081×1921 | `ig_story` | `canvas_overrides.ig_story` (logo inside y ≥ 0.16 safe zone) |
| FB | `channel_canvas: {facebook: ig_post}` | 4:5 posters, not 1200×630 |
| GBP 4:3 | only if the layout reads landscape | stacked 3–4 line headlines don't |

If a group has only one size, build the base canvas from it and derive the rest.

### 3–4 Measure and zoom

```bash
python3 $S/measure_refs.py refs/*.jpg --json /tmp/tpl/measured.json
```

Gives frame inset/stroke, coloured text lines (y, x, cap, pitch), white text rows (kicker,
logo, URL), median accent hex. Check the consistency line — if cap/x0 agree across refs the
layout is fixed; if the line count changes, see how the block moves (centre vs top anchor).
Zoom (`crop(...).resize(..., NEAREST)`) to read effects: outline echo offset, stroke, shadow.

### 5 Font

Guess the family from letterforms (Montserrat Black/ExtraBold, italic?), fetch the Google OFL
variable font and instance the weights (reference.md). Then:

```bash
python3 $S/font_fit.py --cap 127 --word WRONG=663 --word FLEX=418 --font A.ttf --font B.ttf
```

Lowest spread wins; `size` → `max_font_px`, mean scale → `h_scale` (designers squash ~0.85–0.9).
Measured word widths include outline echoes — subtract the echo offset.

### 6 Assets

```bash
python3 $S/extract_logo.py <ref-with-flat-bg>.jpg --box x0,y0,x1,y1 --out <pack>/assets/logo-white.png --scale 2
```

Photo backgrounds need raw, text-free venue photos in `<pack>/photos/`. If none exist, crop
text-free regions from existing posts as **stand-ins** and ask Kyle for raw shots.

### 7 Archetype

Copy `ss-did-you-know` in swing-shack `archetypes.json` as the starting shape. Convert px →
fractions of the **target** canvas (refs at 1081×1201 map into 1080×1350 with the block
centred). Put measured accents in `palette/brand.json` `tokens`; font files in `fonts.json` `roles`.
Missing engine capability → add it generically in `archetype_compose.py` (see reference.md
for what exists: cover photo + scrim, frame, h_scale, echo, colour_options, attach_above,
balanced wrap, channel_canvas).

### 8 Render loop

```bash
# cases.json: one object per sorted ref — that ref's headline/cta/accent
python3 $S/compare_sheet.py --repo <worktree> --brand <brand> --archetype <id> \
  --refs <pack>/references --cases cases.json --out /tmp/tpl/cmp
```

Priority when fixing: **line breaks** → text size/width → colour → vertical position → effects.
Clipped glyphs at the right edge usually mean a layer narrower than the unsquashed text.

### 9–12 Pack, select, test, ship

- Pack: copy refs to `references/ref-0N.jpg`, `spec.json` (archetype + `measured_from`,
  `reference_size`), `template.md` (intent, anatomy, platforms, copy budget, when to use),
  goldens via a `tools/render_<slug>.py`.
- Selection: rule `{"when": {"post_type_in": [...]}, "use": "<id>"}`; pinned `template_id` on the
  calendar record always wins. Tell Kyle which `post_type` to tag.
- Tests: copy `campaign-os/tests/test_ss_did_you_know_template.py` pattern (canvases, wrap
  breaks, no clipping, deterministic accent, selection via monkeypatched `_moment_context`).
  Run it + `test_stick_service_frame_renderer.py` + `tests/jobs/test_archetype_schema_v2.py`
  + `test_archetype_selection.py`. Full suite: diff failures against the base checkout.
- Revert data files the test suite rewrites (`feedback/image-performance.json`,
  `product-library.json`) before committing.
- Update `agent-control/handoffs/campaign-os-template-taxonomy-review-20260927.md` "Built:" line.

## Runtime wiring (calendar + review)

- Candidate create does **not** auto-set `template_id` — there is no `enrich_compose_template_fields`
  in the repo. Compose template comes from pinned `template_id` / `archetype_id` on the record, else
  `select_archetype()` (`selection.rules` last-match-wins, then `selection.default`). See
  `data/brand-directory/_system/POST_TYPE_SELECTION.md`.
- Brand API routes today: `/api/brands`, `/<brand_id>`, `/<brand_id>/bootstrap`, `/<brand_id>/select`,
  `/active` — no dedicated compose-templates list route.
- Change + redraw: `POST /api/drafts/<id>/recompose` with **`archetype_id`** (not `template_id`);
  body fields are `headline`, `cta`, `archetype_id`. Unknown id hard-fails. Does not sync the calendar
  row; no `regenerate_photo` flag on this route.

## Batch mode

For several groups of one brand: steps 1–2 once, then 3–8 per group. Engine features are
shared, so after the first template most groups are measure → JSON → render. Spawn one writer
per template only if they don't both edit `archetype_compose.py`; archetypes.json edits are
serial (single file).
