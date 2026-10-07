# `render_batch` — deterministic scheduling without the Railway CLI

## The problem it solves

`compose_post_for_channels()` writes to `$DATA_DIR/draft-assets/`. In production
`$DATA_DIR` is the Railway volume, so a post composed on a laptop has its bytes on
the wrong disk and can never appear in the live Review queue.

Until this job, the only route to production was:

```bash
railway ssh "cd /app/campaign-os && python3 scripts/render_post.py --batch ... --publish"
railway ssh "cd /app/campaign-os && python3 scripts/schedule_posts.py --batch ..."
```

That needs the Railway CLI (one machine), a batch file already baked into the image
(so a merge to `main`), and therefore a second person. Scheduling one post was a
two-person, two-step, deploy-gated operation.

## The shape of the fix

Two things were already true and simply hadn't been joined:

- `/api/calendar/v2/upsert` is in `DUAL_AUTH_PATHS` — writable with a bearer token.
- `upsert_event` keeps record fields it does not recognise.
- `/api/jobs/run/<name>` is bearer-triggerable.

So the render spec rides on the calendar record, and a job composes it server-side.

```
operator (any machine, bearer token)          production
───────────────────────────────────           ──────────
POST /api/calendar/v2/upsert      ──────────▶  record + render_spec
POST /api/jobs/run/render_batch   ──────────▶  compose_post_for_channels()
                                                 ├─ PNG + publish JPEG → volume
                                                 └─ asset row → campaign-data.json
                                               Review queue  (review/planned)
                                                      │
                                               human approves (session login)
```

No model, no credits, ~200ms per channel, byte-identical to a local render of the
same archetype and fields.

## Where it lives

| | |
|---|---|
| Job | `campaign-os/_lib/jobs/layer5/render_batch.py` |
| Registration | `campaign-os/_lib/jobs/layer5/__init__.py` |
| Description | `campaign-os/_lib/jobs/descriptions.py` |
| Operator guide | the `schedule-from-anywhere` skill |

It reuses `render_post.py` for photo selection and publishing, and
`schedule_posts.py` for the asset shape the Review queue reads — imported rather
than copied, so there is one definition of each. `campaign-os/` ships whole in the
Docker image, so `scripts/` is importable in production.

## Idempotency

The latch is `$DATA_DIR/render-batch-latch.json`: `event_key` → a short hash of the
`render_spec` it was last composed from.

The calendar itself **cannot** hold the latch. `upsert_event` only writes a new
revision when a field in `MATERIAL_FIELDS` changes, so a status flag written back
to the record silently no-ops. Hashing the spec also gives the behaviour an
operator expects: edit the spec and it re-renders, leave it and a re-run is free.

## One change to shared code

`render_spec` was added to `MATERIAL_FIELDS` in `marketing_calendar.py`, with a
`render_change` change_type. Without it, editing a caption on a lodged record is
treated as no change at all and the post keeps the old copy — a silent wrong
answer. Records that carry no `render_spec` compare `None` to `None` and are
unaffected.

## Failure behaviour

- `best_effort=False` — a composer failure is a real failure. An operator is
  waiting on a post, and a silent LATE verdict would read as "nothing to do".
- One bad record never stops the batch; it lands in `problems` with its reason and
  the rest still render.
- A record with no caption is skipped, matching `schedule_posts.py` — a post
  without copy would sit in Review as an un-approvable stub.
- If the asset row writes but the latch does not, the only cost is a harmless
  re-render next run.

## Verified

- Round trip: lodge → run → PNG + publish JPEG on the volume, asset row
  `review/planned`, `renderMode: deterministic-template`.
- Re-run with no change → `rendered: 0`.
- Edit the caption, upsert, re-run → `rendered: 1`.
- `pytest tests/` — 65 failed / 42 passed both with and without this change
  (the 65 are pre-existing legacy frontend tests).
- `verify_specs.py` — 10 passed / 4 failed, unchanged.

## What it deliberately does not do

Approve. `/api/review/*` is session-cookie only, and that is correct: releasing a
post to a brand's audience should take a human with a login.
