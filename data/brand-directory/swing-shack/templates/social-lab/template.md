# Swing Shack — Social Lab contest

## Intent

Giveaway / contest announcement: huge italic prize headline, accent stat lines
(dates, entry fee), fine-print rules, orange CTA above a full-bleed prize photo.

## Anatomy

- Black upper field over a vertical scrim into the prize photo (pack `photos/` library)
- Headline: Montserrat Black Italic (`display`), white, balanced wrap
- Subhead: `offer_subject`, ss_orange, right-aligned under headline
- Date: `offer_expiry`, ss_green
- Price: `price` + suffix ` ENTRY`
- Body: two explicit lines (`caption_body`, wrap `explicit`) — Montserrat ExtraLight Italic
- CTA: ss_orange, right-aligned

## Platforms

| Channel | Canvas | Notes |
|---|---|---|
| Instagram feed | `ig_post` 1080×1350 | extended black field so CTA sits on solid black |
| Instagram story | `ig_story` 1080×1920 | measured story layout |
| Facebook feed | `ig_post` via `channel_canvas` | 4:5 |
| Google Business | — | not supported (stacked contest card) |

## When to use

- `post_type`: `contest`, `giveaway`, `challenge`
- Or pin `template_id: ss-social-lab`

## Copy budget

- Headline: prize name (e.g. `Win a LAB OZ.1`)
- Body: exactly two lines separated by `\n` — do not rely on auto-wrap

## Photos

`photos/standin-lab-oz1-putter.jpg` is **prize-specific** — swap for each contest
or clone the pack. No per-post photo upload when `needs_photo: false`.

## Don't

- Use for generic venue posts
- Expect GBP landscape layout
