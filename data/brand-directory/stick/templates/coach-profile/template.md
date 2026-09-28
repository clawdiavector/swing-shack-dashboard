# Coach profile (`stick-coach-profile`)

## Intent

Staff / coach introduction card: portrait photo, teal name band, navy credential lines, light footer with stick lockup. Feed 4:5 and story 9:16 (story adds photo height above a fixed lower block).

## When to use

- Calendar rows tagged **`post_type: staff_profile`**
- Or pin `template_id` / `archetype_id`: `stick-coach-profile`
- Channels: Instagram feed + story, Facebook (maps to feed canvas)

## Copy budget

| Field | Zone | Notes |
|---|---|---|
| `caption_hook` | `name` | Coach display name (1–2 lines, uppercase) |
| `caption_body` line 1 | `kicker` | Optional availability line on teal |
| `caption_body` lines 2–4 | `bio_1` … `bio_3` | Credential lines on navy panel |
| `cta` | — | Omit (footer is logo-only) |

## Do

- Supply a portrait photo (`needs_photo: true`)
- Use `\n` in `caption_body` for kicker + bio lines
- Keep story safe zone in mind (footer lockup above ~84% canvas height)

## Don't

- Reuse reference face strings as production compose defaults
- Expect GBP 4:3 — portrait stack does not read landscape
