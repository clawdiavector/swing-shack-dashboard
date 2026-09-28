# Swing Shack — Ladies clinic (invite carousel)

## Intent

Two-slide ladies clinic invite: **invite** (date, host, title) and **detail** (body, urgency, booking).

## Anatomy

### Invite slide (`variant: invite`)

- Full-bleed venue photo + scrim, 4px white frame inset 33px
- Logo top-left, kicker `INVITES YOU TO OUR`
- Title: clinic name — magenta `#C921F2` with outline echo
- Date/time line (white), host line (magenta)

### Detail slide (`variant: detail`)

- Same frame/photo treatment
- Centred body copy, magenta urgency pair, booking block

## Platforms

| Channel | Canvas | Notes |
|---|---|---|
| Instagram feed | `ig_post` 1080×1350 | refs 1081×1201; `block_anchor: center` |
| Facebook feed | `ig_post` | via `channel_canvas` |

## When to use

- `post_type`: `clinic_invite` on calendar records
- Or pin `template_id: ss-ladies-clinic`
- Set `variant` to `invite` or `detail` in compose fields (carousel slots)

## Copy budget

| Field | Invite | Detail |
|---|---|---|
| `caption_hook` | Clinic title | Body paragraph |
| `qualifier` | Date/time | Urgency lines |
| `cta` | Host credit | Booking / URL / DM |

## Photos

`photos/` uses stand-in range shots; replace with text-free venue photos when available.

## Don't

- Use `ss-lesson-corner` for clinic event invites
- Omit `variant` — defaults to lab variant filter; always pass `invite` or `detail`
