# Stick — Service end card

## Intent

Carousel **closing** tile for service lanes (coaching, fitting, equipment, apparel).
One layout: light venue photo, navy service word, `@ stick` lockup, large mint panel with static **END**.

## Anatomy

- Full-bleed venue photo (upper frame, light scrim optional)
- Partial white frame: 6px inset ~35px
- Service word: Montserrat Black, navy `#073C52`, uppercase, 1–2 balanced lines
- Lockup: `@ stick`, centred, same navy
- Mint panel: token `mint` `#24FFAF`, ~91% width, static **END** centred on panel
- White footer band below mint block

## Platforms

| Channel | Canvas | Notes |
|---|---|---|
| Instagram story | `ig_story` 1080×1920 | native refs 1081×1920 |
| Facebook | `ig_story` 1080×1920 | `channel_canvas`; story-shaped end slide |
| Instagram feed 4:5 | — | no refs — skip v1 |
| Google Business | — | skip (portrait END block) |

## When to use

- Tag carousel **end** rows with `post_type: service_end`
- Or pin `template_id` / `archetype_id: stick-service-end` on the calendar post

## Copy budget

- `caption_hook` → service word (e.g. COACHING, CLUB FITTING)
- `cta` → `@ stick` lockup (not booking CTA copy)
- **END** is static in the archetype — not LLM body copy
- Max ~48 chars across dynamic zones

## Photos

`photos/` supplies stand-ins when the post has no draft photo. Replace with raw venue shots when available.
