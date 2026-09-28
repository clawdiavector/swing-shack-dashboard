# Stick service frame

## Intent

Navy/teal service promo tile: uppercase headline, two-line CTA on a full-bleed teal band, wordmark + tagline footer. No hero photo.

## Anatomy

- Horizontal navy gradient field (`#073D55` → `#063443`)
- Headline (Montserrat Black, up to 3 lines, size-to-fit)
- Teal band (`#00B3BA`) with mixed-weight CTA (Light + ExtraBold emphasis on `FREE`)
- Footer: white wordmark (asset) left, tagline lockup (asset) right

## When to use

- Service moments and evergreen posts for fitting, coaching, lab, equipment
- Channels: Instagram feed/story, Facebook, GBP

## Platforms

- **Instagram feed (`ig_post`)** — zones in base `spec.json` (1080×1350), measured from `ref-01`…`ref-04`.
- **Instagram story (`ig_story`)** — uses `canvas_overrides.ig_story` with story-measured zone rects
  (`ref-05` club assessment story, `ref-06` swing assessment story). Do not rely on `block_anchor`
  auto-shift for story; overrides pin headline ≈ y0 0.266 and teal band ≈ y0 0.496 on 1080×1920.
- **Facebook** — same 4:5 feed canvas as Instagram post (`channel_canvas` default).

## Character budgets

- Headline (`caption_hook`): ~36 chars, 3 lines max
- CTA: ~40 chars, 2 lines; include `FREE` for emphasis styling

## Do

- Keep headline factual and uppercase-friendly
- Use the real wordmark/tagline assets (not live text)
- Match measured zones in `spec.json`

## Don't

- Drop in a photo (this archetype is `needs_photo: false`)
- Substitute web fonts at render time (vendored Montserrat only)
- Hard-code tagline copy in compose fields
