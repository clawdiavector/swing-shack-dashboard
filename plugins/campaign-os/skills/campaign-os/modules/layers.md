# Campaign OS — Layers module

Eight layers. Each has jobs, Mac agents (L3+), and an `/ops` tab.

## Stack

| Layer | Tab | Mac agents | Writes |
|-------|-----|--------------|--------|
| **L1 Data** | Jobs | — (GH Actions + Railway jobs) | `$DATA_DIR` JSON |
| **L2 Health** | Health | — (Mac watch/digest `--no-agent`) | slot planner, queue, SLA |
| **L3 Interpret** | Agents | cos-foreman, cos-scout, cos-reactive, cos-interpreter, cos-triage | calendar candidates, proposals |
| **L4 Approve** | Approve | — (human + inbox UI) | approve/reject/edit |
| **L5 Create** | Create | cos-caption, cos-image, cos-gbp (later) | drafts → inbox |
| **L6 Publish** | Publish | — (Railway job only) | sandbox or live receipts |
| **L7 Learn** | Learn | cos-learn (later), pi-score | outcome briefs |
| **L8 Calendar+** | (product UI) | — | calendar_config, holidays — **not** on `GET /api/ops/layers` |

## Sequencing

```text
L1 soak + L2 Health     → done (ticket)
L3 API + Mac fleet      → API done; Mac cron state is runtime (`hermes cron list`)
L4 inbox                → done (PR #20 merged)
L5 create               → in progress
L6 sandbox publish      → queued after L4
L6 live publish         → Kyle keys + PUBLISH_MODE=live
```

## Hard rules

- Agents **never publish** (L6 is a Railway job after `human_approved`).
- **One scout writer** — Heidi Opportunity Scout **or** cos-scout, never both on schedule.
- Calendar writes use existing `/api/calendar/v3/scout/*` — no second store.
- Watch/digest (`campaign-os-watch`, `campaign-os-digest`) run on the **Mac** only. Linux desk is foreman — never schedule those crons on omarchy.

## Keys

L3 scout for stick/bag-drop needs **no** Postiz/YouTube/Windsor keys. Blocked without keys: L1 metric jobs, L6 live, GBP polish.
