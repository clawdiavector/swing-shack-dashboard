# Ready for testing: Campaign OS L3 — Interpret APIs + Agents tab

**Date:** 2026-09-17  
**Job:** `job-20260917-campaign-os-l3-interpret-ready-for-testing` (Cursor, ready-for-testing)  
**Verify:** `job-20260917-campaign-os-l3-interpret-verify` (Pi, read-only)  
**Verify verdict:** **PASS** — `20260917T100847-review-f5c932` @ `bccbb64`: heartbeat round-trip, enqueue, session gate; Agents tab renders all 11 card fields (`27p/0f` per verify record)  
**Plan:** `agent-control/handoffs/campaign-os-l3-interpret-plan-20260917.md` + `agent-control/handoffs/campaign-os-layers/L3-interpret.md`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-l3-interpret`  
**Merge target:** `integrate/campaign-os-option-c` — **do not** push `main` / `master` / `develop`.  
**Deploy:** **none** (RFT only; no Railway).

## One-line summary

L3 Interpret layer (product slice): dual-auth `POST /api/ops/agents/heartbeat`, `GET /api/ops/agents`, `POST /api/ops/agents/enqueue`; roster persisted under `$DATA_DIR/ops-agents/`; `/ops?layer=agents` roster cards; L3 rollup no longer `NEVER` when agents report. Verify **PASS**. Feat branch **on origin**.

## Branches + SHAs

| Item | Value |
|---|---|
| Code-complete SHA | `bccbb6423a048a9990c3be300b8ba86cebb0ba80` |
| Short | `bccbb64` |
| Origin tip | `origin/feat/campaign-os-l3-interpret` @ `bccbb64` (pushed by RFT job) |
| Integrate tip at RFT | `origin/integrate/campaign-os-option-c` @ `39b3903` |
| RFT handoff commit | lands after this file (see git log) |

## Push state

| Branch | On origin? | Notes |
|---|---|---|
| `feat/campaign-os-l3-interpret` | **YES** @ `bccbb64`+handoff | RFT pushes code tip then handoff doc. |

## RFT re-verify (this job)

Fresh pytest on scoped L3 suite (verification-before-completion):

```bash
cd campaign-os
python3 -m pytest tests/jobs/test_ops_agents.py tests/jobs/test_ops_layers_ribbon.py -q
```

**Result:** `44 passed, 0 failed` (2026-09-17, RFT job).

Pi verify reported `27p/0f` on `test_ops_agents.py` only at the same SHA — count delta is ribbon/layers tests included in RFT scope, not a product divergence.

## Done-when (L3-interpret.md — product writer scope)

| Criterion | Status | Evidence |
|---|---|---|
| `POST /api/ops/agents/heartbeat` live | **PASS** | `test_heartbeat_bearer_ok`, `test_heartbeat_roundtrip`, `test_heartbeat_writes_expected_file` |
| `GET /api/ops/agents` live | **PASS** | `test_agents_bearer_ok`, `test_roster_seeds_never_agents` |
| `POST /api/ops/agents/enqueue` live | **PASS** | `test_enqueue_bearer_ok`, `test_enqueue_appends_queue_row` |
| `/ops?layer=agents` roster cards (id, kind, last heartbeat, last action, last writes) | **PASS** | `test_ops_agents_layer_renders`, verify card-field assertion |
| Anon → 401 on all three APIs | **PASS** | `test_*_anon_401` |
| Bearer or session on APIs; `/ops` page session-only | **PASS** | `test_bearer_not_widened`, `test_ops_page_still_session_only` |
| Enqueue row survives `agent_queue_writer` daily run | **PASS** | `test_enqueue_row_survives_queue_writer` |
| L3 rollup reflects roster (not stub `NEVER`) | **PASS** | `test_layers_l3_reflects_roster`, `test_agents_stub_copy_gone` |

**Out of scope (mac-bridge / Kyle items — not RFT blockers):**

| Criterion | Status | Notes |
|---|---|---|
| `cos-*` Hermes profiles on Mac | **NOT STARTED** | tL3-4 mac-bridge job |
| `campaign-calendar-scout` on cos-scout | **NOT STARTED** | tL3-5 |
| Heidi Opportunity Scout disabled | **NOT STARTED** | tL3-6 needs Kyle K9 |
| Interpreter / triage agents | **NOT STARTED** | tL3-7 |

## Manual tests — `/ops?layer=agents`

Environment: local worktree, `DATA_DIR` scratch, port from job file **`3518`**. Session login required (anon → `/login`). Never print secret values.

| # | Step | Expected |
|---|---|---|
| 1 | `GET /ops?layer=agents` without session | `302` → `/login` |
| 2 | Log in → `GET /ops?layer=agents` | `200`; `#layer-agents` visible; `#agents-list` present |
| 3 | Click **Agents** ribbon tab | Roster cards for seeded `cos-*` agents (NEVER until first heartbeat) |
| 4 | `POST /api/ops/agents/heartbeat` with bearer | `200`; agent appears with fresh heartbeat on GET |
| 5 | `GET /api/ops/agents` with session | `200`; roster JSON with id, profile, kind, layer, last_heartbeat_at, last_action, last_writes |
| 6 | Bearer-only `GET /api/ops/agents` | `200` (dual-auth path) |
| 7 | Bearer-only `GET /ops?layer=agents` | `302` (page stays session-only) |
| 8 | Bearer-only `GET /api/ops/errors` | `401` — gate not widened beyond agents + layers |
| 9 | `POST /api/ops/agents/enqueue` with bearer | `200`; row appended to `agent-queue.json` with `status: pending` |
| 10 | `GET /api/ops/layers` after heartbeat | L3 verdict reflects roster (not `NEVER`) |

Automated coverage: `campaign-os/tests/jobs/test_ops_agents.py` exercises steps 4–9 without a dev server.

Optional eyeball (port **3518**):

```bash
cd /home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-l3-interpret/campaign-os
DATA_DIR=/tmp/cos-l3-manual COS_JOB_TOKEN=local-dev PORT=3518 python3 app.py
# browser: http://127.0.0.1:3518/ops?layer=agents
```

## Commits on feat (vs `integrate/campaign-os-option-c`)

1. `bccbb64` feat(ops): add L3 agents API, Agents tab, and queue enqueue

## Files touched (product)

| Path | Change |
|---|---|
| `campaign-os/_lib/ops_agents.py` | **new** — roster persistence, heartbeat, enqueue |
| `campaign-os/app.py` | three L3 routes; gate line extended for `/api/ops/agents` |
| `campaign-os/ops-jobs.html` | Agents tab body + `loadAgents()` |
| `campaign-os/_lib/ops_layers.py` | L3 rollup from roster |
| `campaign-os/_lib/jobs/layer2/agent_queue_writer.py` | preserve manual enqueue rows |
| `campaign-os/tests/jobs/test_ops_agents.py` | **new** — 27 tests |
| `campaign-os/tests/jobs/test_ops_layers_ribbon.py` | L3 stub assertion updated |
| `tests/ci-allowlist.txt` | allowlist new test file |

## Open Kyle items

1. **Land** — next job merges `feat/campaign-os-l3-interpret` → `integrate/campaign-os-option-c` (integration push OK; not `main`).
2. **Manual browser pass** — optional checklist above on scratch `$DATA_DIR` before land.
3. **Mac fleet (tL3-4+)** — create `cos-*` profiles via mac-bridge; crons **disabled** until verified; do not dual-write calendar with Heidi Opportunity Scout.

## Suggested board / comment draft

Campaign OS L3 Interpret ready for testing. `feat/campaign-os-l3-interpret` @ `bccbb64` on origin. Pi verify **PASS** (heartbeat round-trip, enqueue, session gate, Agents tab cards). RFT re-verify **44p/0f** on scoped agents + ribbon tests. Manual checklist: `/ops?layer=agents` (§ above). Target merge: `integrate/campaign-os-option-c`. No deploy. Mac profiles out of scope. Suggested column: **Ready for testing**.

## Land (next job)

`job-20260917-campaign-os-l3-interpret-land` — merge feat → integrate locally, push `integrate/campaign-os-option-c` only.
