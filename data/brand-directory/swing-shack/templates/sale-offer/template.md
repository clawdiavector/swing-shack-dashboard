# Swing Shack — Sale offer (Black Friday family)

## Intent

Story-native promo tile: kicker + huge discount headline + dates/subline + CTA.
Matches Content Bank `blackfriday copy*.jpg` (1081×1920).

## Anatomy

- Solid charcoal `#3A3A3A` field (master ref uses near-black variant)
- Frame: 5px white at 50%, inset 33px
- Logo: white lockup, top-right (story safe zone)
- Kicker: `BLACK FRIDAY SALE` — Montserrat ExtraLight Italic, white
- Headline: discount line from caption hook — Montserrat Black Italic, `ss_blue`
- Subline: optional dates/terms from caption body (uppercase)
- CTA: from caption CTA — orange `ss_orange`

## Platforms

| Channel | Canvas | Notes |
|---|---|---|
| Instagram story | `ig_story` 1080×1920 | Primary — refs are story-native |
| Instagram feed | `ig_post` 1080×1350 | via `channel_canvas` |
| Facebook feed | `ig_post` 1080×1350 | 4:5, not link canvas |
| Google Business | — | not supported (9:16 layout) |

## When to use

- `post_type`: `sale_offer`
- Or pin `template_id: ss-sale-offer` on the calendar post

## Copy budget

- Kicker: ≤ 22 chars (static default; override via future field if needed)
- Headline: ≤ 18 chars per line (e.g. `30% OFF`, `10% OFF`)
- Subline: ≤ 72 chars (dates + terms)
- CTA: ≤ 28 chars (e.g. `DM US FOR MORE INFO`)

## Don't

- Ship reference price-list copy as permanent fields — real offers come from caption
- Use on evergreen education posts (`tip` / `did_you_know`)
