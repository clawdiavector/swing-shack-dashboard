# Stick — Service start card

## Intent

Carousel **opening** tile for service lanes (coaching, fitting, equipment, apparel).
One layout: venue photo, navy service word, `@ stick` lockup, mint accent bar.

## Anatomy

- Full-bleed bright venue photo (light scrim optional)
- Partial white frame: 6px inset ~45px (coaching feed ref)
- Service word: Montserrat Black, navy `#073C52`, uppercase, 1–2 balanced lines
- Lockup: `@ stick`, centred, same navy
- Mint bar: token `mint` `#24FFAF`, ~65% width, left-aligned

## Platforms

| Channel | Canvas | Notes |
|---|---|---|
| Instagram feed | `ig_post` 1080×1350 | refs 1081×1300; block centred into 1350 |
| Instagram story | `ig_story` 1080×1920 | same block via `block_anchor: center` |
| Facebook feed | `ig_post` 1080×1350 | `channel_canvas`; not 1200×630 |
| Google Business | — | skip (stacked title does not read at 4:3) |

## When to use

- Tag carousel **start** rows with `post_type: service_start`
- Or pin `template_id` / `archetype_id: stick-service-start` on the calendar post
- One archetype covers all four service words on the refs: **COACHING**, **FITTINGS**,
  **APPAREL**, **EQUIPMENT** (see `cases.json` / compare golden)

## Headline routing (production copy)

`compose_visual_copy._service_carousel_headline()` picks the service word from pillar id or
caption keywords (`coaching` / `trackman` / `swing`, `fitting`, `apparel`, `equipment`).
There is no dedicated `stick-apparel` / `stick-equipment` pillar — retail carousels often sit
under `stick-retail`, so the **caption must mention "apparel" or "equipment"** (or set a
`compose_headline` sidecar) for the correct word. Archetype **selection** is unaffected:
`post_type: service_start` always selects this template.

Golden/compare fixtures use explicit `caption_hook` values (e.g. `FITTINGS` on the fitting ref);
that can differ from the brand-voice default (`CLUB FITTING` for fitting pillar posts).

## Copy budget

- `caption_hook` → service word (COACHING, FITTINGS, APPAREL, EQUIPMENT)
- `cta` → `@ stick` lockup (static; not the teal CTA band copy)
- Max ~40 chars total across zones

## Photos

`photos/stand-in-01..04.jpg` supplies stand-ins when the post has no draft photo (coaching,
fitting, apparel, equipment crops from refs). Replace with raw venue shots when available.
