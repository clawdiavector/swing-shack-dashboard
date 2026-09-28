# Shop corner (`stick-shop-corner`)

## Intent

Full-bleed shop interior or product-shelf photo with a half-width navy corner plate (bottom-left) carrying a mint uppercase service-category word, white `@`, and white stick wordmark. Sibling of `stick-venue-post` (opposite corner, no partner co-branding).

## When to use

- Calendar rows tagged **`post_type: shop_corner`**
- Or pin `template_id` / `archetype_id`: `stick-shop-corner`
- Channels: Instagram feed + story, Facebook (4:5 via `channel_canvas`), GBP listed on archetype

## Copy budget

| Field | Zone | Notes |
|---|---|---|
| `caption_hook` | `service_word` | One line, ≤ 16 chars, uppercase (`EQUIPMENT`, `FITTING`, etc.) |
| `cta` | — | Set by shared service-carousel helper; unused by zones |

`max_total_chars`: 20.

## Do

- Supply a real shop photo (`needs_photo: true`, full-bleed cover)
- Tag `post_type: shop_corner` for automatic selection

## Don't

- Expect right-corner plate in this archetype (refs with FITTING on the right are compare-only; spec fixes bottom-left)
- Reuse reference strings as production defaults without pillar routing
