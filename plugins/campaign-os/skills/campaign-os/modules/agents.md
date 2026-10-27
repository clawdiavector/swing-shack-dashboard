# Campaign OS — Agents module

Mac Hermes fleet on `fives-mac-mini`. Heartbeat + queue contract.

## Roster (roadmap §7)

### L3 — daily SAST chain (after L1 07:00 / L2 07:15)

| id | profile | layer | trigger | primary skill | writes |
|----|---------|-------|---------|---------------|--------|
| cos-foreman | cos-foreman | all | daily 07:25 + 15m watch | campaign-os | dispatches, layer rollup |
| cos-scout | cos-scout | L3 | daily 07:40 | campaign-calendar-scout | calendar v3 upsert |
| cos-reactive | cos-reactive | L3 | daily 07:45 | (Reactive Watch clone) | calendar alerts |
| cos-interpreter | cos-interpreter | L3 | daily 08:10 (after reco+scout) | cos-interpreter-proposal | proposals → inbox |
| cos-triage | cos-triage | L3 | daily 08:30 | cos-triage-telegram-brief | Telegram brief (read-only) |
| pi-score | pi-score | L3/L7 | one-shot | stub | scores one pack, exits |

### L5 create (Railway + Mac tick)

L5 draft/QC work is primarily **Railway jobs** (e.g. `draft_assets`), often woken by Mac **`campaign-os-l5-tick`** (`--no-agent`) — not the same as standalone LLM agent profiles `cos-caption` / `cos-image` / `cos-gbp`.

### Phase D — L7 (not created yet)

cos-learn, pi-qc

**Heidi** — operator orchestrator; does **not** own cos-* crons. Opportunity Scout still **ON** until Kyle **K9**.

## Heartbeat (every run)

```http
POST https://swing-shack-dashboard-production.up.railway.app/api/ops/agents/heartbeat
Authorization: Bearer $COS_JOB_TOKEN
Content-Type: application/json

{"id":"cos-scout","profile":"cos-scout","kind":"hermes","layer":"L3",
 "status":"OK","action":"upserted 3 candidates for stick",
 "writes":["calendar/stick"],"skill":"campaign-calendar-scout"}
```

`status`: OK | LATE | FAILED | NEVER (use OK/FAILED on runs).

## Queue consumption

**Producer (Railway):** `agent_queue_writer` job → `$DATA_DIR/agent-queue.json`  
**Manual enqueue:**

```http
POST /api/ops/agents/enqueue
{"agent":"cos-scout","brand":"stick","reason":"manual"}
```

**Consumer (Mac):** On invoke (cron when enabled, or Kyle/Foreman manual):

1. `GET /api/ops/layers` — bearer; read `layers.L2.queue` or embedded `queue.rows`.
2. Filter rows where `status=pending` and `agent=<this-agent-id>`.
3. Execute skill for `brand` + `action` + `payload_ref`.
4. POST heartbeat with `action` citing row id.
5. **`POST /api/ops/agent-queue/mark-done`** — mark the row complete (bearer or session).

**cos-foreman** may dispatch siblings: read pending rows for all agents, tell Kyle which to run, or enqueue via POST.

**Lodge one post:** `modules/operator-post.md`. Ask brand if Kyle did not name one. Calendar **and** Create queue (caption+image pair). Do not hand back Review. Never insert campaign `assets` into `campaign-data.json`.

## Monitoring (what exists today)

| Signal | Where |
|--------|--------|
| Agent last run | `GET /api/ops/agents` → `last_heartbeat_at`, `last_status`, `last_action`, `last_writes` |
| Layer rollup | `GET /api/ops/layers` → L3 verdict from roster |
| Queue depth | `GET /api/ops/layers` → L2 `queue_depth` |
| Inbox counts | `GET /api/ops/layers` → L4 inbox summary (bearer) |
| Job health | Mac `watch_campaign_os.py` (15m) — **not** per-agent |
| Telegram | Mac digest 07:00; cos-triage brief (Mac, when enabled) |

## Calendar morning message (for the Telegram brief)

`GET /api/jobs/morning-message?brand=all` (or `stick`, `swing-shack`, `bag-drop`) with the job bearer token
(`COS_JOB_TOKEN`) returns plain text ready to send, plus counts:

```json
{"ok": true, "date": "2026-10-15", "text": "Good morning. Calendar check, Thu 15 Oct. ...",
 "screaming": 1, "overdue": 2, "due_today": 0}
```

The text lists, per brand: approved dates that are close and have nothing ready (the red alerts), plan steps that are
overdue, and plan steps due today. It says "Nothing needs you today." when there is nothing. It sends nothing itself:
the agent that sends the Telegram brief (cos-triage, or the 07:00 Mac digest) reads it and adds `text` to its message.
Not wired into a cron yet; that is a Mac change for Kyle. Built from `_lib/plan_todo.py` and `_lib/calendar_alerts.py`.

## Foreman weekly messages (Monday and Tuesday)

Same shape as the morning message: bearer `GET`, plain `text`, sends nothing itself. `brand=all` means the two facilities
(Swing Shack, Stick); Bag Drop only when asked for by name.

| When | Route | Says |
|---|---|---|
| Monday 09:00 SAST | `/api/jobs/weekly-selling-message` | what is on each facility's calendar Mon to Sun (approved entries) |
| Tuesday | `/api/jobs/weekly-report-message` | the `/weekly-report?brand=` page link per facility (`links` + `text`); needs a Campaign OS login, the page redirects to sign-in |

Not wired into a cron yet; that is a Mac change for Kyle. Built from `_lib/plan_todo.py`.

## Calendar evening message (foreman end-of-day)

`GET /api/jobs/evening-message?brand=all` (or per brand) with the job bearer returns plain
text for the 18:00 SAST Telegram report:

```json
{"ok": true, "date": "2026-10-26", "text": "Stick, today\nCreated 3 · Approved 2 · ...",
 "counts": {"created": 3, "approved": 2, "released": 2, "on_social": 1},
 "pending_approval": 2}
```

Per brand: today's created / approved / released / on-social counts, rest-of-week ready/planned
(with gap labels), then what is waiting for approval and a one-tap Approve drafts link.
Built from `_lib/foreman_eod.py` and the same calendar join as the week board. Not on a Mac cron
yet — wire alongside the morning message when Kyle sets send time and recipients.

No dedicated Mac LaunchAgent poller yet — agents run on cron (disabled) or manual Hermes invoke.

## Cron ids (Mac — check runtime, not this table)

Cron **enabled/disabled** state is runtime — run **`hermes cron list`** on the Mac; do not trust a static enabled column.

| profile | id | schedule (SAST) |
|---------|-----|-----------------|
| cos-foreman | 559904319b7d | daily 07:25 |
| cos-scout | 44aeb2102e77 | daily 07:40 |
| cos-reactive | 92b55965a117 | daily 07:45 |
| cos-interpreter | f1d1b2c924f3 | daily 08:10 |
| cos-triage | 57f72826459b | daily 08:30 |

Heidi Opportunity Scout: `473abd04e621` — separate from cos-scout until Kyle K9.
