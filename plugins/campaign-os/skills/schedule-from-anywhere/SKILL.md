---
name: schedule-from-anywhere
description: >-
  Put a finished, template-rendered post on the live Campaign OS calendar and into
  the Review queue from any machine, using only a COS_JOB_TOKEN — no Railway CLI,
  no Mac, no push to main, no image credits. Load when asked to schedule, lodge,
  book or publish a post, or when a local render needs to reach production.
---

# Schedule a post from anywhere

Two bearer-authenticated calls. Works from Windows, Linux or a phone.

```
1. POST /api/calendar/v2/upsert        → lodge the record, with a render_spec
2. POST /api/jobs/run/render_batch     → compose it on the volume, into Review
```

A human then approves in the Review queue. That step needs a session login and is
deliberately not automatable.

## Why this exists

`compose_post_for_channels()` writes to `$DATA_DIR/draft-assets/`. In production
that is the Railway volume, so **a post rendered on a laptop can never reach the
live queue** — the bytes are on the wrong disk. Before `render_batch`, the only
route was `railway ssh` from the single machine holding the Railway CLI, which
made scheduling one post a two-person job.

The calendar was already bearer-writable and `/api/jobs/run/*` was already
bearer-triggerable. This joins them.

## Step 1 — lodge the record

`event_key` **must** start with `{brand}:` or the upsert returns 500.

```bash
curl -sS -X POST "$BASE/api/calendar/v2/upsert" \
  -H "Authorization: Bearer $COS_JOB_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "brand_id": "swing-shack",
    "record": {
      "event_key": "swing-shack:operator-2026-10-06-spoon-wrong-clubs",
      "type": "moment",
      "status": "approved",
      "title": "You wouldn'\''t dig with a spoon",
      "event_date": "2026-10-06",
      "event_start": "2026-10-06",
      "source_type": "operator",
      "source_origin": "internal_strategy",
      "created_by": "<your name>",
      "primary_channel": "instagram",
      "render_spec": {
        "archetype": "ss-fitting-headline",
        "slug": "spoon-wrong-clubs",
        "channels": ["instagram"],
        "fields": {
          "caption_hook": "YOU WOULDN'\''T DIG WITH A SPOON.",
          "service_lockup": "WHY PLAY THE WRONG CLUBS?"
        },
        "caption": "You wouldn'\''t dig with a spoon. So why play the wrong clubs?\n\nFit first. Hit second.",
        "date": "2026-10-06"
      }
    }
  }'
```

`source_origin` is an enum — **`external`, `deterministic_calendar` or
`internal_strategy`**. `operator` is not valid and returns a 400-level error with
the valid list.

## Step 2 — render it

```bash
curl -sS -X POST "$BASE/api/jobs/run/render_batch?brand=swing-shack" \
  -H "Authorization: Bearer $COS_JOB_TOKEN"
```

Returns `rendered`, `skipped`, the asset ids and any `problems`. The post appears
in Review as `review/planned`.

Omit `?brand=` to sweep all three brands.

## The render_spec contract

| Key | Required | Notes |
|---|---|---|
| `archetype` | yes | Must be a measured template — `/render-post --list` |
| `slug` | yes | Drives the filenames and the asset id |
| `caption` | yes | No caption, no post. It is skipped with a reason |
| `channels` | no | Defaults to the archetype's own |
| `fields` | no | The archetype's text zones |
| `photo` | no | Defaults to one from the template pack |
| `date` | no | Falls back to the record's `event_date` |

## Idempotency — and how to change a post

The latch is `$DATA_DIR/render-batch-latch.json`, mapping `event_key` to a hash of
the `render_spec` it was last composed from.

- **Re-run with nothing changed** → renders 0. Free and safe; run it as often as
  you like.
- **Edit the `render_spec` and upsert again** → the hash moves, and it re-renders
  with the new copy.

That second behaviour needed `render_spec` added to the calendar's
`MATERIAL_FIELDS`. Without it `upsert_event` treats a copy edit as a no-op and
silently keeps the old caption — which is worth knowing if you ever add another
field the renderer reads.

## When this is the wrong tool

- **No measured template for the look.** `render_batch` only composes archetypes.
  Genuinely new art goes through Krea — see `krea-lab` — and the winner should then
  be measured into a template with `campaign-os-template` so it graduates down.
- **A one-shot image with the type baked in.** This path composes from a template;
  it does not pass a finished image through.
- **You want it approved too.** Approval is a human action behind a session login,
  by design. This gets it to Review, not past it.

## Related

`/render-post` to preview locally first · `brand-voice-truth` before writing the
caption · `campaign-os` → `modules/operator-post.md` for the older lodge-and-let-
agents-draft flow, which costs credits and does not use your template.
