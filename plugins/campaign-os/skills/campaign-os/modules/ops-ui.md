# Campaign OS — Ops UI module

Prod: https://swing-shack-dashboard-production.up.railway.app/ops/jobs  
Campaigner desk (new): `/app/daily` — Daily / Review / Create / Calendar / Publish / Results / Other.  
Classic `/` is still `campaign-os.html`. Session login required for pages. Bearer works for JSON APIs listed in `api.md`.

## Ribbon tabs

| Query | Layer | What you see |
|-------|-------|--------------|
| `/ops/jobs` | L1 | Job cards, run now, JSON outputs |
| `/ops?layer=health` | L2 | Watch/digest health, slot planner, queue depth |
| `/ops?layer=agents` | L3 | cos-* cards: last heartbeat, status, action, writes |
| `/ops?layer=approve` | L4 | Unified inbox — candidates, proposals, drafts |
| `/ops?layer=create` | L5 | Create tab (building) |
| `/ops?layer=publish` | L6 | Publish sandbox/live chip (future) |
| `/ops?layer=learn` | L7 | Learn summary (future) |

Deep links: `/ops?layer=agents&agent=cos-scout` (scroll/highlight card).

## Agents tab (L3)

Each card shows: id, profile, kind, layer, schedule, enabled, last_heartbeat_at, last_status, last_action, last_writes, skill.

Healthy fleet: all expected agents reporting OK or LATE (not NEVER). Crons may still be disabled — NEVER on schedule is OK if manual smoke passed.

## Approve tab (L4)

Unified inbox item types: `calendar_candidate`, `proposal`, `draft_asset`, `publish_request`.

Christelle workflow: 15 min/day approve/edit/reject. Agents never publish from here.

## Health tab (L2)

Shows layer verdicts from `GET /api/ops/layers`. Queue depth increments when enqueue or `agent_queue_writer` adds rows.

## Mac Hermes (not in UI)

- `campaign-os-watch` — 15m job verdict poll → Telegram on change
- `campaign-os-digest` — 07:00 daily summary

These run on **fives-mac-mini** only. They monitor **jobs**, not individual Hermes agent runs. Agent monitoring = L3 Agents tab + heartbeat API.
