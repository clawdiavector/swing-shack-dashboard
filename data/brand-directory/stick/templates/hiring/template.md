# Stick — Hiring card

## Intent

Staff hiring / vacancy carousel **cover slide**: six stacked colour bands (grey header,
navy headline field, teal role band, grey divider, navy brief, white swipe footer). No photo.
Carousel pager affordance (CTA + double-chevron asset).

## Anatomy

- `grey_light` header with centred navy `logo.png` wordmark
- `navy_deep` band with teal uppercase hook (`caption_hook`, e.g. WE'RE HIRING)
- `teal` band with white uppercase role (`qualifier`)
- `#E1E1E1` divider band
- `navy_deep` brief with white left-aligned body (`caption_body`)
- White footer: navy uppercase CTA (`cta`) right-aligned + chevron asset

## Platforms

| Channel | Canvas | Notes |
|---|---|---|
| Instagram feed | `ig_post` 1080×1350 | refs 1081×1351 |
| Facebook feed | `ig_post` 1080×1350 | via `channel_canvas` |

No story variant — carousel cover is feed-only.

## When to use

- `post_type`: **`hiring`** — selection rule → `stick-hiring`
- Or pin `template_id: stick-hiring` on the calendar post

## Copy budget

| field | zone | budget |
|---|---|---|
| `caption_hook` | headline | one short hook ≤ 18 chars, uppercase ("WE'RE HIRING" canonical) |
| `qualifier` | role | one role title ≤ 30 chars, uppercase |
| `caption_body` | brief | 4–8 lines, ≤ 34 chars per line, ≤ 240 chars total |
| `cta` | swipe | ≤ 30 chars, "SWIPE FOR MORE DETAILS" canonical |

`max_total_chars: 240` on the archetype covers the full card.

## Don't

- Use without a real `qualifier` — blank teal band signals incomplete sidecar
- Expect a photo slot — `needs_photo: false`
