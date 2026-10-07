---
name: schedule-from-anywhere
description: >-
  Put a finished post on the live Campaign OS calendar, on This week and on the
  shelf ready to release, from any machine with only a COS_JOB_TOKEN — no Railway
  CLI, no Mac, no push to main, no image credits. Works for a finished image made
  in Claude (Ideogram, Krea, a designer's file) or a measured template. Load when
  asked to schedule, lodge, book, post or publish something, or when a local image
  or render needs to reach production.
---

# Schedule a post from anywhere

One command. Works from Windows, macOS, Linux.

```bash
python campaign-os/scripts/lodge_post.py \
  --brand swing-shack --slug spoon-wrong-clubs --date 2026-10-09 \
  --image path/to/spoon-wrong-clubs.jpg \
  --caption-file caption.txt \
  --by christelle
```

It prints the state and the links:

```
lodged   swing-shack:spoon-wrong-clubs  for 2026-10-09
state    scheduled — On the shelf
image    instagram  https://…/brand-images/swing-shack/composed-spoon-wrong-clubs-instagram.png
image    facebook   https://…/brand-images/swing-shack/composed-spoon-wrong-clubs-facebook.png
release  https://…/app/shelf  (click Release now)
week     https://…/app/week
```

**Then a person opens the Shelf and clicks Release now.** That click is the only
human gate and is deliberately not automated. Nothing goes out before it.

Needs `COS_JOB_TOKEN` in the environment (ask Kyle). `COS_BASE_URL` overrides the
production URL. Standard library only, nothing to install.

## What the one call does

`POST /api/posts/lodge` (`campaign-os/_lib/post_lodge.py`):

1. writes the image to the Railway volume, `$DATA_DIR/operator-uploads/<brand>/`
2. books a calendar moment for the date, carrying a `render_spec`
3. runs `render_batch` for that one record. A finished image is sized per channel
   and placed as-is; a template is composed. It writes the sidecar that puts it on
   This week.
4. approves the draft through the same path as Review's Approve button, which
   queues one publish row per channel (Instagram + Facebook by default)

The post then shows on This week and on the Shelf as **Scheduled — On the shelf**.

## Before you lodge

- **Caption:** read `brand-voice-truth` first. Swing Shack and Stick both forbid
  invented prices or offers.
- **Image:** JPEG, PNG or WebP, up to 20 MB. Square or 4:5 portrait is ideal.
  Anything taller than 4:5 or wider than 1.91:1 is centre-cropped to fit
  Instagram's feed, and the output says `note … cropped` — **look at the image
  links when you see that**, because a crop can clip baked-in type.
- **Date:** today or later, Johannesburg time. That is the go-live day.
- **Slug:** lowercase-hyphenated. It names the post. **Lodging the same slug again
  replaces the picture or caption in the same slot**, and an identical re-lodge
  does nothing, so it is safe to retry. A post that has already been released is
  refused; use a new slug.

## Options

| Flag | Use |
|---|---|
| `--image FILE` | a finished picture, placed with nothing drawn on top |
| `--archetype ID --field k=v …` | compose from a measured template instead (`/render-post --list`) |
| `--caption "…"` or `--caption-file F` | the post copy (required) |
| `--channels instagram,facebook` | default is the brand's own publish channels |
| `--title "…"` | calendar title; default is the caption's first line |
| `--no-approve` | stop in Review instead of the shelf, for someone else to approve |
| `--by NAME` | who lodged it; recorded on the post |

## Calling the API directly

```bash
curl -sS -X POST "$BASE/api/posts/lodge" \
  -H "Authorization: Bearer $COS_JOB_TOKEN" \
  -H "X-Actor-Display-Name: christelle" \
  -F brand=swing-shack -F slug=spoon-wrong-clubs -F date=2026-10-09 \
  -F "caption=<caption.txt" -F image=@spoon-wrong-clubs.jpg
```

JSON works too, with `image_base64` instead of the file. The `X-Actor-Display-Name`
header is required: the calendar's V2.6 write gate only books an approved slot for
a named person, and the route refuses without it.

## Why this replaced the two-call flow

The old recipe (`/api/calendar/v2/upsert` with a `render_spec`, then
`/api/jobs/run/render_batch`) had four silent failures. All are fixed in the code
above, and the old calls still work:

- It only composed templates and could not carry a finished image.
- The upsert sent `status: approved` without `X-Actor-Display-Name`, which the V2.6
  write gate rejects in production.
- `render_batch` wrote no draft sidecar, so the post sat in Review and This week
  read "Nothing going out".
- `render_batch` never registered the `<brand>-calendar` campaign in `brands.json`,
  so brand-scoped Review views hid the post.

## Related

`/render-post` to preview a template locally first · `brand-voice-truth` before
writing the caption · `krea-lab` for genuinely new art. Measure a look that keeps
winning into a template with `campaign-os-template` so it graduates down.
