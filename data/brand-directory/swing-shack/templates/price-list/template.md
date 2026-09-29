# Swing Shack — ss-price-list (coaching rate card)

## Intent

Session / package pricing on a dimmed venue photo. Two-column rows (label + price)
with the same chrome as ss-price-package — for coaching menus and rate cards.

## Anatomy

- Full-bleed venue photo from shared library, scrim ~78–82% black
- Frame: 6px white, inset 34px
- Logo: white lockup, top-left
- Title: Montserrat Black Italic, balanced wrap (≤2 lines), **accent drives title colour only**
- Dividers: grey bands at y ~526 and ~965 (post canvas)
- Rows: up to 4 explicit-wrap lines — labels (Montserrat Italic 400) left, prices (display) right
- Prices + CTA: fixed **ss_green**; labels + URL: white
- Footer URL: static `www.swingshack.co.za`

## Platforms

| Channel | Canvas | Notes |
|---|---|---|
| Instagram feed | `ig_post` 1080×1350 | measured from coachinpackages_post |
| Instagram story | `ig_story` 1080×1920 | `canvas_overrides.ig_story`; block centred |
| Facebook feed | `ig_post` 1080×1350 | via `channel_canvas` |

## When to use

- `post_type`: `price_list`, `package_list`, or `rate_card`
- Or pin `template_id: ss-price-list` on the calendar post

## Copy budget

- Title: `caption_hook`, ≤2 balanced lines, `max_total_chars` 120
- Rows: `compose_price_labels` and `compose_price_values` on the calendar sidecar —
  pipe- or newline-separated, **4 rows max** (`max_lines: 4`)
- CTA: single line footer call to action
- `accent`: optional; rotates **title** colour among ss_green / ss_orange / ss_blue / ss_purple

## Sidecar requirement

Compose reads row copy from the calendar record sidecar keys
`compose_price_labels` and `compose_price_values`. There is no authoring UI yet —
posts must be hand-tagged with those fields or compose will fail with missing text.

## Photos

Background uses `templates/did-you-know/photos` when no post photo is attached.
Prefer raw text-free venue shots over stand-in crops.

## Don't

- Mix a second accent on prices or CTA — references are blue title + green prices
- Use for membership / single-price packages (see ss-price-package)
- Put reference campaign copy in committed template fields — real copy comes from the calendar
