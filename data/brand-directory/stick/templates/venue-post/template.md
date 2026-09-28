# Stick — Venue post

## Intent

Full-bleed venue or lifestyle photography with a navy brand plate bottom-right:
optional partner lockup, optional short venue/vendor line, `@`, and stick wordmark.

## Anatomy

- Photo covers the canvas (`photo_full_bleed`, `block_anchor: bottom` on story)
- Navy plate: token `navy_deep`, lower-right (~x ≥ 0.50, y ≈ 0.69–0.88)
- `partner_logo`: PNG via `partner_logo_asset` field (not stick brand mark)
- `vendor_name`: single h3 line on plate (optional)
- Static `@` and stick logo in plate stack

## Platforms

| Channel | Canvas | Notes |
|---|---|---|
| Instagram feed | `ig_post` 1080×1350 | refs 1081×1351 |
| Instagram story | `ig_post` + bottom anchor | 1080×1920; plate pinned bottom |
| Facebook feed | `ig_post` 1080×1350 | `channel_canvas`; not 1200×630 |
| Google Business | listed on archetype | no dedicated refs |

## When to use

- Calendar **`subject: venue`**, or tag **`post_type: venue_post`**
- Or pin `archetype_id: stick-venue-post` / pack on the post row

## Copy budget

- `vendor_name`: ≤ 16 chars, ≤ 30 chars total across zones
- `partner_logo_asset`: brand-relative path when co-branding (compare-only strings stay in `cases.json`)

## Photos

`photos/` holds text-free crops from refs until raw venue shots land. Pass draft photo bytes at compose time when available.
