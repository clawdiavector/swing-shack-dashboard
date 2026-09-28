# Stick — Service end card

## Intent

Carousel **closing** tile for service lanes (coaching, fitting, equipment, apparel).
Gradient field, navy service word, composited `@ stick` lockup, mint panel with a service tagline.

## Anatomy

- Vertical gradient `#D4DEDD` → `#FFFFFF` (no photo)
- Partial white frame: top bar (alpha fade left→right) + right bar
- Service word: Montserrat Black, `navy_alt`, uppercase, one line shrink-to-fit
- Lockup: PNG asset (`assets/lockup-at-stick.png`) — white `@` + navy wordmark
- Mint panel: token `mint` `#24FFAF`, tagline in `qualifier` (1–4 lines, sentence case)

## Platforms

| Channel | Canvas | Notes |
|---|---|---|
| Instagram story | `ig_story` 1080×1920 | native |
| Facebook | `ig_story` 1080×1920 | `channel_canvas`; story-shaped end slide |

No feed 4:5 or GBP refs — do not guess.

## When to use

- Tag carousel **end** rows with `post_type: service_end`
- Or pin `template_id` / `archetype_id: stick-service-end` on the calendar post

## Copy budget

- `caption_hook` → service word: **one word**, ≤ 16 chars
- `qualifier` → tagline: ≤ 4 lines, ~24 chars per line, ~90 chars total, sentence case, ends with `.`
- `compose_qualifier` on the sidecar overrides; `_service_end_tagline()` fills defaults per pillar
- `cta` is unused (lockup is an asset)
- `max_total_chars`: 140
