# State of play — Campaign OS branches

**Dated snapshot:** 2026-09-22. This is **not** a roadmap — ordered program work lives in **agent-control** manifests and handoffs only (`AGENTS.md` §13).

Re-derive topology before trusting this page:

```bash
git fetch origin
git rev-list --left-right --count integrate/campaign-os-brand-lanes-v1...origin/main
git log -1 --oneline integrate/campaign-os-brand-lanes-v1 origin/main
```

## Branch SHAs (measured 2026-09-22)

| Ref | Role |
|---|---|
| `integrate/campaign-os-brand-lanes-v1` | Active integration branch for program work |
| `origin/main` | Production deploy target after Kyle merge |
| `feat/cos-dev-docs` | This documentation ticket |

At write time, `integrate/campaign-os-brand-lanes-v1` was **2 commits ahead / 72 commits behind** `origin/main` (merge-base drift — re-run the command above).

## What integrate carries that `main` does not (integrate-only)

- Entire **`web/`** tree — Vite + React Campaign Heroes desk SPA at **`/app`** (and friendly aliases `/daily` … `/other`).
- Dockerfile Node build stage; Flask routes serving `web/dist`.
- Heroes-related tests and doc updates in `AGENTS.md` / `RAILWAY.md`.

Verify: `git cat-file -e integrate/campaign-os-brand-lanes-v1:web/src/App.tsx && echo integrate-only`

## What `origin/main` has that integrate does not (main-only)

Whole subsystems absent from integrate until a foreman merge lands them, including:

| Path | Purpose |
|---|---|
| `campaign-os/_lib/jobs/layer2/data_archive.py` | L2 job — rotates stale `$DATA_DIR` JSON |
| `campaign-os/_lib/ops_watch.py` | Watch reporting into the app |
| `campaign-os/_lib/weekly_report_v3.py` | Weekly report V3.x |
| `campaign-os/_lib/creative_package.py` | Creative packages under `$DATA_DIR` |
| `campaign-os/_lib/reporting_editorial.py` | Editorial layer for reports |
| `campaign-os/_lib/jobs/freshness_heuristic.py` | Freshness scoring |
| `scripts/v25_daily_pull.py` | V2.5 daily IG sync |

Verify a main-only file: `git show origin/main:campaign-os/_lib/jobs/layer2/data_archive.py | head -1`

**Docs describe the union:** production behavior on `origin/main` plus integrate-only Heroes — not integrate alone.

## Brand-lanes program

**Done** — landed on `origin/main`. Do not describe brand-lanes as in-flight. Contract details: `agent-control/context/campaign-os-brand-lanes-program.md`.

## In-flight (not shipped)

| Work | Status |
|---|---|
| Heroes P0 ops (`ticket-20260922-cos-heroes-p0-ops`) | **in_progress** — native Ops rail in `web/` |
| Heroes P1–P6 | **pending_spawn** — sequential plan manifests in agent-control |
| Deploy overlay (`ticket-20260922-cos-deploy-overlay`) | **in-flight** — `app.py`, `_lib`, Dockerfile, tests |

Do not claim these as production-complete in docs or skills.

## Evaluation reference

Layer scorecard and gaps as of **2026-09-18**: `agent-control/context/campaign-os-state-evaluation-20260918.md` — cite by date, not as live truth.
