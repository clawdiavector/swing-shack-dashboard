# Campaign OS — Lodge one post (Foreman)

Kyle says: “load a post for Thursday”, “put this on the calendar”, “book a fitting
Facebook post”.

**Contract:** calendar **and** Create queue. Action does **not** have to be
immediate. Never caption without image (Facebook / IG). Review is only for a
**complete** post.

Do it from a **fresh chat**. Do not continue a `campaign-data.json` shell.

## Ask first (minimum)

Operating brands: `swing-shack` · `stick` · `bag-drop`.

| If Kyle omitted | Ask (one short question) | Default if he still skips |
|---|---|---|
| **Brand** | “Which brand — Swing Shack, Stick, or Bag Drop?” | **Do not guess. Stop.** |
| Date | “Which day (YYYY-MM-DD)?” | tomorrow Africa/Johannesburg |
| What the post is | “One line: what’s the post about?” | required — stop if still empty |
| Channel | “IG, Facebook, or GBP?” | `instagram` |
| Caption | only if he wants **his** words | omit → Create writes caption |

Takomo = Stick (`product_brand: takomo`), not a brand.
Absurdity Mirror = Swing Shack **pillar**, not a brand.

## Never

- Edit `campaign-data.json` / campaign `assets` blocks.
- Enqueue `fill_slot`.
- Enqueue **caption without image** (Facebook / Instagram). Pair or stop.
- `POST /api/jobs/run/draft_assets` unless Kyle says **run now** / **cook it now**.
- Tell Kyle the draft is on **Review**. Lodge ≠ Review.
- Skip brand.

## Do (bearer `$COS_JOB_TOKEN`, never print it)

Base: `https://swing-shack-dashboard-production.up.railway.app`

`event_key` **must** start with `{brand}:` or upsert returns 500.
Example: `swing-shack:operator-2026-09-24-book-fitting`

### 1. Calendar moment (approved)

`POST /api/calendar/v2/upsert`

```json
{
  "brand_id": "<brand>",
  "record": {
    "event_key": "<brand>:operator-<YYYY-MM-DD>-<slug>",
    "type": "moment",
    "status": "approved",
    "title": "<one-line from Kyle>",
    "event_date": "2026-09-24",
    "event_start": "2026-09-24",
    "source_type": "operator",
    "created_by": "foreman",
    "verification_status": "unverified",
    "primary_channel": "<facebook|instagram|gbp>",
    "angle": "<caption or same one-liner>",
    "pillars": ["<pillar id if known, else omit>"]
  }
}
```

Response: top-level `record_calendar_id` (not `record.id`).

Item id: `calendar_candidate:<brand_id>:<record_calendar_id>`

### 2. Create queue — always a pair

Enqueue **both** in the same turn. `reason` carries the goes-out date so nearest
dates can be prioritised (`op-YYYY-MM-DD`, 64-char max).

Facebook / Instagram — two POSTs to `/api/ops/agents/enqueue`:

```json
{
  "agent": "cos-caption",
  "brand": "<brand>",
  "reason": "op-2026-09-24",
  "action": "draft_caption",
  "payload_ref": "inbox/calendar_candidate:<brand>:<calendar_id>",
  "dedupe_key": "cap-<calendar_id>"
}
```

```json
{
  "agent": "cos-image",
  "brand": "<brand>",
  "reason": "op-2026-09-24",
  "action": "draft_image",
  "payload_ref": "inbox/calendar_candidate:<brand>:<calendar_id>",
  "dedupe_key": "img-<calendar_id>"
}
```

If the **image** enqueue fails after caption succeeded: say **blocked**. Do not
tell Kyle it is queued. Do not run Create.

GBP only: `draft_gbp` (no image). Same `reason: op-YYYY-MM-DD`.

### 3. Confirm queue (do not cook)

`GET /api/ops/agent-queue?status=pending` — both rows `pending` for that
calendar_id.

Cooking is **Mac `campaign-os-l5-tick`** (~15 min) + daily GH cron. Nearest
`event_date` first once the job sorts that way (see remarks). Until then, tick
still wakes `draft_assets` on any pending pair.

### 4. Hand back

Pipe table: brand, date, channel, calendar_id, queue (caption+image pending).

Tell Kyle:

- On the calendar **and** in the Create queue.
- Not on Review yet. Review = complete post (caption **and** image).
- Machines pick it up; closer dates first.
- Approve on Review later ≠ live.

Do **not** send him to `/calendar/lanes` (Strategic / Herman). Classic month:
**Other → Month grid** (`/calendar`) if he wants the moment on a calendar UI.

## Run now (only if Kyle asks)

Then `POST /api/jobs/run/draft_assets?all=1&reason=operator-post`.

If the job lands caption without image: **blocked / still cooking** — do not
point at Review.

## If upsert 401 / 400 / 500

Say **blocked**. Do not patch `campaign-data.json`. On 500
`event_key must be prefixed with '{brand}:'`, retry once with the prefix.

## Related

- Heroes loop: Calendar (plan) → **queue** → Create (machines) → Review (complete) → Shelf → Publish sandbox.
- Empty-day `fill_slot` is not this path.
- Product gaps (Heroes cooking queue, date-priority sort, Review gate): `agent-control/handoffs/campaign-os-operator-create-queue-remarks-20260923.md`
