# stick-service-square

Stick service-description square template — 1:1 (1081×1081).

## When to use

- pillar: any
- service category in {LAB, AVODA, COACHING, FITTING, CLUB FITTING, RE-GRIP}
- post_type: `service_square`
- needs_photo: false

## Variants

- **lab form** — `caption_hook` is a full sentence (4 lines, mixed case).
- **avoda form** — `caption_hook` first word is the SERVICE NAME (uppercase), tail is `stick`.

## Selection rule

- if `record.service_category` in {AVODA, WORKSHOP} → variant=avoda
- else → variant=lab (default)
- calendar `post_type: service_square` selects archetype `stick-service-square` (last-match rule)

## Platforms

- instagram (`ig_square` 1080×1080 via `channel_canvas`)
- facebook (`ig_square` — square crops well into FB feed)

## Frame note

Reference posts show a partial frame (~3 sides). v1 ships a full rectangular outline; partial-frame is a follow-up if Kyle wants pixel parity.
