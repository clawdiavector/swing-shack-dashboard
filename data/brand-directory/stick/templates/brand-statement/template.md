# Stick — Brand statement

## Intent

Static brand-statement tile: a list of categories (4 single-word lines) or a 2–4 line
manifesto sentence over a solid navy field. Used to anchor brand recall in the calendar
between service offers.

## Anatomy

- Solid `navy_deep` field
- White stick logo, top-centre (~22% of canvas height)
- Thin white rule below logo
- 4–5 lines of mint `#24FFAF` Montserrat Black UPPERCASE, balanced wrap, centred
- Thin white rule above the tagline
- Italic tagline `better begins here`, bottom-centre

## Platforms

| Channel | Canvas | Notes |
|---|---|---|
| Instagram feed | `ig_post` 1080×1350 | refs are 1081×1201 — block is `block_anchor: center` |
| Instagram story | `ig_story` 1080×1920 | logo inside story safe zone, block re-centred |
| Facebook feed | `ig_post` 1080×1350 | via `channel_canvas` |
| Google Business | — | not supported: a 5-line stacked headline doesn't read at 4:3 |

## When to use

- `post_type`: `brand_statement` — drives selection via `selection` rule
- Or pin `template_id: stick-brand-statement` on the calendar post

## Copy budget

- Caption hook = the statement, lines split on `\n` (1–5 lines, ≤ ~16 chars per line)
- Category-list form: one word per line, UPPERCASE (FITTINGS / COACHING / EQUIPMENT / APPAREL)
- Sentence form: 4 short lines, no `?`, period at end of last line
- Below min_font_px 56: compose fails the zone rather than rendering unreadable type

## Don't

- Mix two accent colours in one post
- Use for service offers (pick `stick-service-frame` or `stick-service-square` instead)
- Put the logo in white-on-light — assets are light-only on the navy field
