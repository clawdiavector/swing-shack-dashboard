# Campaign OS — API module (bearer)

Base: `https://swing-shack-dashboard-production.up.railway.app`  
Auth: `Authorization: Bearer $COS_JOB_TOKEN` (from `~/.hermes/.env` on Mac/Linux watch host).

Never log token values.

## Ops / fleet

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/ops/layers` | Layer verdicts, queue payload, roster summary, inbox counts |
| GET | `/api/ops/agents` | Full agent roster + last heartbeat |
| POST | `/api/ops/agents/heartbeat` | Agent run telemetry |
| POST | `/api/ops/agents/enqueue` | Append manual queue row |
| GET | `/api/ops/agent-queue` | Queue rows (ops) |
| POST | `/api/ops/agent-queue/mark-done` | Complete a queue row |

**Session-only (bearer → 401):** `/api/ops/runbook`, HTML `/ops/jobs`.

### Enqueue body

```json
{"agent":"cos-scout","brand":"stick","reason":"migration dry-run"}
```

Creates row in `agent-queue.json` with id `manual-{brand}-{agent}-{reason}`.

## Jobs (L1)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/jobs/status` | All job verdicts |
| POST | `/api/jobs/run/<name>` | Fire one job |

CLI on Linux: `python3 agent-control/bin/campaign_os_jobs.py status|run|output …`

## Lodge one operator post (Foreman)

Kyle: “load a post for Thursday” / one post through Heroes. Full recipe:
[`operator-post.md`](operator-post.md).

Ask **brand** if omitted (`swing-shack` / `stick` / `bag-drop`). Never write
`campaign-data.json`. Path: `POST /api/calendar/v2/upsert` (status `approved`) →
enqueue `draft_caption` + `draft_image` (`reason: op-YYYY-MM-DD`). Do **not**
run `draft_assets` unless Kyle says run now. Review only when the pair is complete.

## Calendar scout (L3 — cos-scout)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/calendar/context/<brand_id>?horizon_days=120` | Brand pillars; `configured=false` → skip brand |
| GET | `/api/calendar/scout-health` | Fail-closed gate before external research |
| POST | `/api/calendar/v3/scout/upsert` | Idempotent candidate write (preferred) |

Brands with `calendar_config.json`: **stick**, **bag-drop**. **swing-shack** skips until L8/K10.

## Inbox (L4 — session only today)

| Method | Path | Auth |
|--------|------|------|
| GET | `/api/inbox/unified?brand=&status=pending` | session cookie |
| POST | `/api/inbox/unified/<id>/approve` | session |

**Gap:** cos-interpreter cannot POST proposals via bearer yet. Shadow mode: local JSON until `POST /api/inbox/proposals` (future ticket).

Triage uses **bearer** `GET /api/ops/layers` for inbox counts embedded in L4 layer — not full item list.

## Unified layers response (sketch)

```json
{
  "layers": {
    "L2": {"verdict": "OK", "queue_depth": 2},
    "L3": {"verdict": "OK", "agents_reporting": 5},
    "L4": {"verdict": "OK", "inbox_pending": 12}
  },
  "queue": {"schema": "campaign-os/agent-queue/v1", "rows": [...]}
}
```

## curl examples

```bash
# Roster
curl -sS -H "Authorization: Bearer $COS_JOB_TOKEN" \
  "$BASE/api/ops/agents" | jq '.agents[] | select(.id|startswith("cos-"))'

# Enqueue scout
curl -sS -X POST -H "Authorization: Bearer $COS_JOB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"agent":"cos-scout","brand":"stick","reason":"manual"}' \
  "$BASE/api/ops/agents/enqueue"

# Layers + queue
curl -sS -H "Authorization: Bearer $COS_JOB_TOKEN" \
  "$BASE/api/ops/layers" | jq '.layers.L3, .queue.rows | length'
```
