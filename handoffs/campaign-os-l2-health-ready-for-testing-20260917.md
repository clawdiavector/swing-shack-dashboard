# Ready for testing: Campaign OS L2 — Health + planning

**Date:** 2026-09-17  
**Job:** `job-20260917-campaign-os-l2-health-ready-for-testing` (Cursor, ready-for-testing)  
**Verify:** `job-20260917-campaign-os-l2-health-verify` (Pi muse-spark, read-only)  
**Verify verdict:** **PASS** — `20260917T094047-review-21b0df` @ `5a67b46`: 3 jobs registered, `/ops` ribbon + `GET /api/ops/layers` schema v1, session gate holds (`44p/0f` per verify record)  
**Plan:** `agent-control/handoffs/campaign-os-l2-health-plan-20260917.md` + `agent-control/handoffs/campaign-os-layers/L2-health.md`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-l2-health`  
**Merge target:** `integrate/campaign-os-option-c` — **do not** push `main` / `master` / `develop`.  
**Deploy:** **none** (RFT only; no Railway).

## One-line summary

L2 Health layer: three JobSpecs (`slot_planner`, `agent_queue_writer`, `review_sla`), `/ops` seven-tab ribbon, Health tab body, and dual-auth `GET /api/ops/layers` rollup (L1–L7). Verify **PASS**. Feat branch **on origin**.

## Branches + SHAs

| Item | Value |
|---|---|
| Code-complete SHA | `5a67b46e8f4dcee3bebca7d65aa1fbdd5576e8ba` |
| Short | `5a67b46` |
| Origin tip | `origin/feat/campaign-os-l2-health` @ `5a67b46` (pushed by integrate job) |
| Integrate tip at RFT | `origin/integrate/campaign-os-option-c` @ `ae97633` |
| RFT handoff commit | lands after this file (see git log) |

## Push state

| Branch | On origin? | Notes |
|---|---|---|
| `feat/campaign-os-l2-health` | **YES** @ `5a67b46` | Integrate job pushed merge tip 2026-09-17. RFT adds this handoff doc only. |

## RFT re-verify (this job)

Fresh pytest on scoped L2 suite (verification-before-completion):

```bash
cd campaign-os
python3 -m pytest tests/jobs/test_layer2_jobs.py tests/jobs/test_ops_layers_ribbon.py tests/jobs/test_ops_jobs_p1e.py -q
```

**Result:** `41 passed, 0 failed` (2026-09-17, RFT job).

Pi verify reported `44p/0f` on the review worktree at the same SHA — count delta is subtest/collection scope, not a product divergence.

## Done-when (L2-health.md)

| Criterion | Status | Evidence |
|---|---|---|
| `GET /api/ops/layers` returns L1–L7 rollup | **PASS** | `test_layers_api_schema`, `test_e2e_gate_flow` |
| `/ops` ribbon; Jobs = today’s jobs UI; Health tab | **PASS** | `test_ops_health_layer`, ribbon e2e in `test_e2e_gate_flow` |
| Jobs: `slot_planner`, `agent_queue_writer`, `review_sla` registered | **PASS** | `test_layer2_jobs.py`, `_lib/jobs/layer2/__init__.py` |
| Linux watch + digest only (no new Hermes agents) | **PASS (unchanged)** | No agent-control or cron edits in this slice |
| Health tab never SSHs to Mac | **PASS** | `loadHealth()` uses HTTP only (`/api/ops/layers`, freshness, calendar job-health) |

## Manual tests — `/ops?layer=health`

Environment: local worktree, `DATA_DIR` scratch, port from job file **`3552`**. Session login required (anon → `/login`). Never print secret values.

| # | Step | Expected |
|---|---|---|
| 1 | `GET /ops` without session | `302` → `/login` |
| 2 | Log in → `GET /ops` | `200`; seven-tab ribbon visible; Jobs tab active; “Schedule at a glance” unchanged |
| 3 | Click **Health** or open `/ops?layer=health` | `200`; `#layer-health` section visible (not hidden); L2 rollup chips load |
| 4 | Hover Health tab tooltip | One paragraph: factory health, freshness, queue, Linux watchdog note |
| 5 | `GET /api/ops/layers` with session | `200`; `schema == "campaign-os/ops-layers/v1"`; keys `L1`…`L7`; each has `label`, `verdict`, `href` |
| 6 | Bearer-only `GET /api/ops/layers` | `200` (dual-auth path) |
| 7 | Bearer-only `GET /ops` | `302` (page stays session-only) |
| 8 | Bearer-only `GET /api/ops/errors` (and runbook, llm-spend) | `401` — gate not widened beyond layers |
| 9 | Unknown layer `/ops?layer=nonsense` | `200`; falls back to Jobs view |
| 10 | `/ops/jobs` legacy URL | `200`; schedule UI still present (AC-4 regression) |

Automated coverage: `campaign-os/tests/jobs/test_ops_layers_ribbon.py::test_e2e_gate_flow` exercises steps 1–5 and 7–8 without a dev server.

Optional eyeball (port **3552**):

```bash
cd /home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-l2-health/campaign-os
DATA_DIR=/tmp/cos-l2-manual COS_JOB_TOKEN=local-dev PORT=3552 python3 app.py
# browser: http://127.0.0.1:3552/ops?layer=health
```

## Commits on feat (vs `integrate/campaign-os-option-c`)

1. `00c9c08` feat(ops): add L2 ribbon, Health tab, and layers API  
2. `c33acbd` feat(jobs): add L2 health JobSpecs for slot planning and queue SLA  
3. `5a67b46` merge(l2-ops): integrate L2 ribbon, Health tab, layers API into l2-health  

## Open Kyle items

1. **Land** — next job merges `feat/campaign-os-l2-health` → `integrate/campaign-os-option-c` (integration push OK; not `main`).
2. **Manual browser pass** — optional step 10 above on scratch `$DATA_DIR` before land if you want eyes on the ribbon.
3. **L3 queue consumers** — `agent-queue.json` rows are written but L3 agents tab is still `NEVER` / not built (expected).

## Suggested board / comment draft

Campaign OS L2 Health ready for testing. `feat/campaign-os-l2-health` @ `5a67b46` on origin. Pi verify **PASS** (3 L2 jobs, `/ops` ribbon, layers API v1, session gate). RFT re-verify **41p/0f** on scoped jobs tests. Manual checklist: `/ops?layer=health` (§ above). Target merge: `integrate/campaign-os-option-c`. No deploy. Suggested column: **Ready for testing**.

## Land (next job)

`job-20260917-campaign-os-l2-health-land` — merge feat → integrate locally, push `integrate/campaign-os-option-c` only.
