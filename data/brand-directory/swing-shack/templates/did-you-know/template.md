# Swing Shack — Did you know?

## Intent

Myth-buster / tip tile. A short yes-no question in huge italic type over a dimmed
venue photo. Stops the scroll, then the caption answers it.

## Anatomy

- Full-bleed venue photo, centre-cropped, darkened (scrim 62% → 72% black)
- Frame: 8px white at 50%, inset 35px
- Logo: white Swing Shack lockup, top-right
- Kicker: `DID YOU KNOW?` — Montserrat ExtraLight Italic, 90% width, white, 33px above the headline
- Headline: the question — Montserrat Black Italic, cap 127px, pitch 146px, 85% width,
  3–4 balanced lines, outline echo offset right/up
- Accent (headline fill + echo stroke): one of green `#74CB46`, orange `#E27123`,
  blue `#64A3F0`, purple `#8F4BFA` — set `accent`, else picked from the headline

## Platforms

| Channel | Canvas | Notes |
|---|---|---|
| Instagram feed | `ig_post` 1080×1350 | refs are 1081×1201; same block, re-centred |
| Instagram story | `ig_story` 1080×1920 | block centred, logo inside story safe zone |
| Facebook feed | `ig_post` 1080×1350 | 4:5 via `channel_canvas`; not the 1200×630 link canvas |
| Google Business | — | not supported: a 4-line stacked headline doesn't read at 4:3 |

## When to use

- `post_type`: `tip`, `did_you_know`, `myth` — fitting / coaching education
- Or pin `template_id: ss-did-you-know` on the calendar post

## Copy budget

- Headline = caption hook up to the first `?` — 2–6 words, ≤ ~30 chars, ends with `?`
- Longer questions shrink to 120px min, then fail (pick another template)

## Photos

`photos/` is the library used when the post has no photo. It holds three
**stand-in** crops from existing posts — replace with raw venue photos
(no text, landscape or portrait, dark-ish interiors).

## Don't

- Put the answer in the image — the caption carries it
- Mix two accents in one post
- Use on product / retail posts
