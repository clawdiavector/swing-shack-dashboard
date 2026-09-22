# Implement recipes

Paths are under the product repo unless noted. Jobs live in **`campaign-os/_lib/jobs/`** — not `campaign-os/jobs/`. There is no live Node agent fleet (`legacy/agents/` deleted t33).

## Run locally

```bash
export DATA_DIR=/tmp/campaign-os-scratch
export COS_JOB_TOKEN=dev-token   # any non-empty string; never commit real values
cd campaign-os && python3 app.py
# http://localhost:<runtime.ports.web from your job file>/
```

Tests (count, do not quote stale totals):

```bash
cd campaign-os && python3 -m pytest --collect-only -q
```

## Add a registered job

**When:** Repeatable batch work with ledger verdict and `$DATA_DIR` outputs.

**Where:** `campaign-os/_lib/jobs/<layer>/`, registry import, optional GH workflow.

**Steps:**

1. Copy an existing job in the same layer.
2. Define `JobSpec` (cadence, timeout, criticality, output paths, `brands` if needed).
3. Register in `registry.py` (and `app.py` only if following bootstrap pattern).
4. Add pytest under `campaign-os/tests/`.
5. Wire cron in `.github/workflows/` with bearer auth.
6. Verify: `/ops/jobs` or `GET /api/jobs/status`.

**Do not:** add daemons or JS agents under `scripts/`.

## Add a Mac agent (`cos-*`)

**When:** Recurring LLM interpret/scout work on Mac credentials.

**Where:** agent-control Hermes profile + skill doc; product heartbeat/queue APIs.

**Steps:**

1. Add profile under agent-control (foreman) — see `agent-control/context/campaign-os-developer-guide.md` foreman section.
2. Document id in skill `modules/agents.md`.
3. Implement skill; POST heartbeat each run.
4. Register cron on **Mac** with `enabled: false` until Kyle enables; verify with `hermes cron list`.
5. Consume queue: `GET /api/ops/layers` → work row → heartbeat → **`POST /api/ops/agent-queue/mark-done`**.

**Never** schedule `cos-*` or watch/digest on Linux omarchy (foreman only).

## Frontend change

**Heroes (`web/`):** React pages in `web/src/pages/`, shared chrome in `web/src/components/`. Run `npm run build` in `web/` or full Docker build.

**Classic `/`:** Edit `campaign-os/campaign-os.html` and linked assets — prefer small diffs; run existing pytest/HTML tests if touched.

**Rules:** No bearer token in browser JS. Read-only API exploration first. Do not delete classic HTML.

## Add an API route

**Where:** `campaign-os/app.py` (monolith) — spawn a focused writer ticket for large changes.

**Steps:**

1. Choose auth: session vs bearer vs both (match nearby routes).
2. Scope by brand where editorial data is brand-specific.
3. Add pytest in `campaign-os/tests/`.
4. Document in skill `modules/api.md` if ops-facing.

**Frozen:** do not modify `visibility_guard`.

## Foreman vs product

- **Product repo** — Flask, jobs, UI, `docs/dev/`.
- **agent-control** — manifests, tickets, Mac bridge, watch scripts.
- **Skill** — `~/.agents/skills/campaign-os/` — ops recipes; implement authority is this folder + product code.

Foreman does not edit product code directly — spawn a writer job.
