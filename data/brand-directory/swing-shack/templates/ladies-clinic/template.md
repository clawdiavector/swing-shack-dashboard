# Swing Shack — Ladies clinic (2-page invite card)

## Intent

One **`clinic_invite`** archetype renders **two pages** (`multi_render: page1, page2`):

| Page | Ref | Content |
|---|---|---|
| page1 | ladiesclinic-100 | Logo, kicker, magenta `LADIES CLINIC` + echo, date/time, hollow host, chevron right |
| page2 | ladiesclinic2-100 | Body copy, magenta CTA (flat), booking lines, chevron left |

Shared: 34px inset frame (3px white @ 55% alpha), photo + scrim, accent `ss_clinic_magenta` `#C921F2`.

## Compose fields

| Field | Page | Source helper |
|---|---|---|
| `headline` | 1 | `_event_headline` |
| `event_date` | 1 | `_event_date` (ISO → long form) |
| `event_host` | 1 | `_event_host` (stroke-only zone) |
| `body_text` | 2 | `_body_text` |
| `cta_lockup` | 2 | `_cta_lockup` |
| `booking_url` | 2 | `_booking_url` |

All text zones are **`optional: true`** — missing caption data drops the zone (no invented copy).

Pass **`render_page`: `page1` | `page2`** for single-page renders. `compose_post_for_channels` emits `instagram` (page1) and `instagram__page2`.

## Platforms

| Channel | Canvas |
|---|---|
| Instagram / Facebook | `ig_post` 1080×1350, `block_anchor: center` |

## When to use

- `post_type`: `clinic_invite`
- Or pin `template_id: ss-ladies-clinic`

## Don't

- Collapse both refs into one layout or `variant` toggles
- Use `ss-lesson-corner` for clinic invites
