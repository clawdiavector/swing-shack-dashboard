# Swing Shack — Zen venue promo

## Intent

Venue-feature tile for simulator bays and in-store experiences. A static kicker +
accent question + optional benefit subline over a dark venue photo.

## Anatomy

- Full-bleed venue photo, centre-cropped (no scrim on the reference photo)
- Frame: 3px white at 55%, inset 34px
- Kicker: `HAVE YOU TRIED THE` — Montserrat ExtraLight Italic, white, 21px above headline
- Headline: feature name + `?` — Montserrat Black Italic, flat accent fill (no echo)
- Subline: benefit line — same light italic as kicker; omitted when no `compose_qualifier`

## Platforms

| Channel | Canvas | Notes |
|---|---|---|
| Instagram feed | `ig_post` 1080×1350 | ref 1081×1201; `block_anchor: center` |
| Instagram story | `ig_story` 1080×1920 | text block shifted into story safe band |
| Facebook feed | `ig_post` 1080×1350 | 4:5 via `channel_canvas` |

## When to use

- `post_type`: `venue_promo`
- Or pin `template_id: ss-zen-venue-promo` on the calendar post

## Copy budget

- Headline = caption hook — feature name ending with `?` (e.g. `Zen Swing Stage?`)
- Subline = `compose_qualifier` sidecar when the three-line sandwich is wanted
- Kicker is static boilerplate for venue-feature promos

## Photos

`photos/` holds stand-in venue shots when the post has no uploaded photo.
