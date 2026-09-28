# Swing Shack — Lesson corner

## Intent

Promote beginner, junior, or ladies lesson programmes. Venue photo on the left,
dark panel with right-aligned lesson headline, coach credit, three service lines,
and booking CTA.

## Anatomy

- Full-bleed venue photo, scrim ~35% black, centre focus high (`focus_y` 0.42)
- Frame: 3px white at 21% alpha, inset 34px
- Logo: white Swing Shack lockup, top-right
- Panel: opaque `#070707`, bleeds right and bottom from y ≈ 689px
- Headline: lesson type + `LESSONS` — Montserrat Black Italic, 2 balanced lines, white
- Kicker: `CATHERINE LAU PGA PROFESSIONAL` — static
- Services: three fixed lines — accent rotates orange / blue / green from the headline
- CTA: three balanced lines — `BOOK ONLINE` / `OR MESSAGE US` / `FOR MORE INFO`

## Platforms

| Channel | Canvas | Notes |
|---|---|---|
| Instagram feed | `ig_post` 1080×1350 | refs 1081×1201; bottom block shifted +149px |
| Facebook feed | `ig_post` 1080×1350 | via `channel_canvas` |
| Story / GBP | — | not supported in v1 |

## When to use

- `post_type`: `lesson` on calendar records (beginner / junior / ladies)
- Or pin `template_id: ss-lesson-corner`

## Copy budget

- Headline = caption hook (e.g. `Beginner lessons`) — first word is the lesson segment
- CTA = booking line; defaults to three-line break above
- Coach name is static in v1

## Photos

`photos/` holds stand-in crops from reference posts plus did-you-know venue shots.
Replace with raw text-free venue photos when available.

## Don't

- Use for ladies clinic event invites (different archetype)
- Expect story or landscape GBP renders
