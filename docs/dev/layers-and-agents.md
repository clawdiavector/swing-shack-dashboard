# Layers L1–L8 and Mac agents

Engineering ribbon is defined in `campaign-os/_lib/ops_layers.py` and exposed at **`GET /api/ops/layers`**.

**L8 (Calendar+)** exists in product UI and classic nav; it is **not** a key on `/api/ops/layers` — calendar features use dedicated calendar routes.

## Ribbon summary

| Layer | Ops tab | Primary mechanism |
|---|---|---|
| L1 Jobs | Jobs | Registered `JobSpec` jobs + GH Actions crons |
| L2 Health | Health | Watch/digest, queue, SLA rollup |
| L3 Interpret | Agents | Mac `cos-*` Hermes profiles + Railway queue writer |
| L4 Approve | Approve | Human inbox — session APIs |
| L5 Create | Create | Railway jobs (e.g. draft assets); gated by env flags |
| L6 Publish | Publish | `publish_dispatch` job — sandbox vs live is Kyle gate |
| L7 Learn | Learn | Outcome/recipe JSON jobs |
| L8 Calendar+ | (product) | UI / config — not on layers API |

Sequencing and gates: skill `modules/layers.md` (runtime cron state — check `hermes cron list`, do not trust static enabled tables).

## North Star ↔ ribbon (vision vs engineering)

`docs/MARKETING_OS_NORTH_STAR.md` is **product vision**, not an implement contract.

| North Star stage | Ribbon | Built? |
|---|---|---|
| DATA | L1 Jobs | Yes — use live job count command in [`jobs.md`](jobs.md) |
| INTERPRETATION + EXPLANATION | L2 / L3 | Partial — queue rows; autonomous consumer limited |
| RECOMMENDATION | L3 → L4 | Partial |
| (no stage) | **L4 Approve** | Yes — human gate |
| CREATION | L5 Create | Jobs exist; enqueue behind flags (see 2026-09-18 eval) |
| ACTION | L6 Publish | Sandbox path; live adapter stub / Kyle gate |
| RESULT + LEARNING | L7 Learn | Jobs run; closed loop incomplete |
| (no stage) | **L8 Calendar+** | Product UI only |

## Mac agent roster

Stable ids and profiles: `~/.agents/skills/campaign-os/modules/agents.md`. Daily SAST chain documented in `agent-control/context/campaign-os-l3-daily-chain.md`.

**L5 create work** is primarily **Railway jobs**, often woken by Mac **`campaign-os-l5-tick`** (`--no-agent`) — not the same as an LLM `cos-caption` agent profile.

## Heartbeat and queue

Every agent run should **`POST /api/ops/agents/heartbeat`** (bearer). Manual work enters via **`POST /api/ops/agents/enqueue`**.

**Queue consumption:**

1. `GET /api/ops/layers` — pending rows for your agent id.
2. Run the skill for `brand` / payload.
3. POST heartbeat citing the row.
4. **`POST /api/ops/agent-queue/mark-done`** — mark row complete (exists in product; do not assume auto-clear).

Full API table: skill `modules/api.md`.

## Open gaps (cite evaluation by date)

2026-09-18 evaluation (`agent-control/context/campaign-os-state-evaluation-20260918.md`): L6 live publish stub, L7 loop not closed, L5 behind enqueue flags, L3 queue without fully autonomous consumer. Re-check in code before claiming fixed.
