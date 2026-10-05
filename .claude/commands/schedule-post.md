---
description: Turn rendered images into real posts — caption, date, state, Review queue
allowed-tools: Bash(python3 campaign-os/scripts/render_post.py:*), Bash(python3 campaign-os/scripts/schedule_posts.py:*), Read, Write, Edit, Grep
argument-hint: "[batch file | brand + date]"
---

## The two steps

`render_post.py` makes the picture. `schedule_posts.py` makes it a **post** — the
thing that appears in Campaign OS with a caption and a date, in a state a human
can approve.

```bash
python3 campaign-os/scripts/render_post.py --batch data/post-batches/<batch>.json --out out/<batch>/ --publish
python3 campaign-os/scripts/schedule_posts.py --batch data/post-batches/<batch>.json
```

Images alone are invisible. A rendered PNG sitting on disk shows up nowhere in
the UI — that mistake cost a full round trip on 2026-10-05.

## How a post is actually represented

There is no separate inbox store. `intelligence.review_inbox()` reads
`campaign-data.json` and buckets each asset by its own `approvalStatus`:

| `approvalStatus` | Where it lands |
|---|---|
| `approved` | Approved queue |
| `rejected` | Rejected queue |
| anything else (`review`, `draft`) | **Pending review** — where a human approves |

A post is one asset row under `campaigns.<campaign_id>.assets.<asset_id>` with
four independent states:

| Field | Values | Means |
|---|---|---|
| `captionStatus` | `draft` / `ready` | is the copy written |
| `visualStatus` | `brief-written` / `composed` | is the image made |
| `approvalStatus` | `review` / `approved` / `rejected` | the Review queue |
| `publishStatus` | `planned` / `released` | may it go out |

**An agent adding a post leaves `approvalStatus=review` and
`publishStatus=planned`.** The work is done; a human still releases it. The
Review card says so explicitly: *"Approve marks the draft approved. It does not
go live."*

Override per post with `approval_status` / `publish_status` in the batch, or for
the whole run with `--approval-status` / `--publish-status`.

## Brand ownership — the trap

`review_inbox()` filters brand-scoped views through
`brands.json → brands.<brand>.campaign_ids`. **A campaign missing from that list
is treated as unowned and hidden**, so the post exists and still never appears.
Stick owned zero campaigns until 2026-10-05, which is why nothing Stick ever
showed. `schedule_posts.py` registers ownership automatically, seeding the
runtime `brands.json` from the bundled copy when absent — writing a fresh one
would shadow the bundled file and silently drop every campaign already owned.

## Batch fields

```json
{"brand": "stick", "slug": "mon-arrivals", "archetype": "stick-shop-corner",
 "channels": ["instagram"], "date": "2026-10-06",
 "photo": "data/brand-directory/stick/images/Products/x.jpg",
 "fields": {"caption_hook": "NEW IN"},
 "caption": "New in: ...\n\nBetter begins here.",
 "approval_status": "review", "publish_status": "planned"}
```

`date` is the day the post is for. `caption` is required — `schedule_posts.py`
skips a spec without one, because a post without copy is not a post.

Batches live in `data/post-batches/`, **not** `docs/` — `docs/` is in
`.dockerignore`, so anything there is invisible to the container and prod cannot
render it.

## Captions

Write them from `copy/headlines.md`, `copy/ctas.md` and `knowledge.json`
→ `verified_facts` only. Both brands set `rules.no_fabrication`, and Swing
Shack's bible says never invent prices or offers. Stick copy never mentions
Swing Shack or Bag Drop, per its `ctas.md`.

## On Railway

Same two commands with `DATA_DIR` pointed at the volume, over `railway ssh` from
the Mac (its CLI is authenticated; no password is involved):

```bash
railway ssh "cd /app/campaign-os && DATA_DIR=/data/campaign-os python3 scripts/render_post.py --batch /app/data/post-batches/<batch>.json --out /tmp/<batch> --publish"
railway ssh "cd /app/campaign-os && DATA_DIR=/data/campaign-os python3 scripts/schedule_posts.py --batch /app/data/post-batches/<batch>.json"
```

Re-running updates in place by `asset_id` rather than duplicating, so it is safe
to repeat after a copy or image change.
