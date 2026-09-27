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

## Copy budget

- `caption_hook` → service word (e.g. COACHING, CLUB FITTING)
- `cta` → `@ stick` lockup (static; not the teal CTA band copy)
- Max ~40 chars total across zones

## Photos

`photos/` supplies stand-ins when the post has no draft photo. Replace with raw venue shots when available.
