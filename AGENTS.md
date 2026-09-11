# AGENTS.md — Campaign OS / swing-shack-dashboard

Standing instructions for any agent (human or automated) touching this repo.

## 1. What this repo is

Flask cockpit (`campaign-os/app.py`, count with `wc -l` / `@app.route` — do not freeze numbers) serving one SPA
(`campaign-os/campaign-os.html`, **44 sections / 45 nav keys**). The Flask app **is** production.

`legacy/agents/` is a retired Node tree — dead, kept for evidence. See `legacy/README.md`.

## 2. Branches — READ BEFORE YOU COMMIT

- **Canonical:** `main`.
- **Active program work lands on `integrate/campaign-os-option-c`**, never `main`, until Kyle merges at program end.
- **NEVER** push `main` / `master` / `develop` without Kyle naming that branch in-session.
- `feat/asset-state-engine` is dead history — do not push it, do not believe docs that cite it.
- Doc: `context/protected-branch-push.md` in the agent-control repo.

## 3. Paths

| Name | Meaning |
|---|---|
| `CAMPAIGN_OS_ROOT` | This repo root |
| `$DATA_DIR` | Runtime truth (Railway: `/data/campaign-os`) |
| `data/` | **Seed data only** — read-only, human-committed. No automation writes it, ever |

Never `/Users/fivefriday/...` — that is a dead Mac path in old docs.

## 4. Running it locally

- Port comes from your job file's `runtime.ports.web`. **Never** hardcode 8765 or 8080.
- Set `DATA_DIR` to a scratch directory.
- Set `COS_JOB_TOKEN` to any non-empty string for job endpoints.

## 5. How production boots

- Root `Dockerfile` (`python:3.12-slim-bookworm`) + `railway.json` (builder `DOCKERFILE`,
  startCommand `python app.py`, healthcheck `/api/health`).
- There is no other build config. `Procfile` / `runtime.txt` / `campaign-os/railway.json` were deleted 2026-09-09 and must not return.
- Details: `RAILWAY.md`.

## 6. The jobs (replaces the retired Node fleet)

There are **no agents** in the live product. There are **three registered jobs** under
`campaign-os/_lib/jobs/{spec,registry,runner,ledger}.py`:

| Job | Cadence | Criticality | Writes (`$DATA_DIR`-relative) |
|---|---|---|---|
| `meta_refresh` | 12h | HIGH | `ig-analytics.json`, `ig-business-analytics.json`, `facebook-analytics.json`, `facebook-business-analytics.json` |
| `gbp_tick` | 24h | MEDIUM | `gbp-daily-plans/` |
| `freshness_scan` | 24h | LOW (`best_effort`) | `freshness.json` |

Endpoints (bearer `COS_JOB_TOKEN` **or** session):

- `POST /api/jobs/run/<name>`
- `GET /api/jobs/status`
- `GET /api/jobs/digest`

Ledger: `$DATA_DIR/job-runs.jsonl` — one entry row + one exit row per `run_id`.
Verdicts: `OK` \| `LATE` \| `FAILED` \| `STUCK` \| `NEVER`.

Adding a job = a `JobSpec` in `_lib/jobs/`, **not** a folder of JS under `legacy/agents/`.

## 7. Monitoring — silence means healthy

- Hermes cron `campaign-os-watch` (15m, `--no-agent`) prints **nothing** when every verdict is OK.
- Hermes cron `campaign-os-digest` (07:00 daily, `--no-agent`) **always** prints the full table.
- A **missing** 07:00 digest means the watchdog is down. It does **not** mean all clear.
- Manual check, any time:

```bash
curl -H "Authorization: Bearer $COS_JOB_TOKEN" <prod>/api/jobs/status
```

**Cron host default (P0c, Kyle override window):** Linux desk box — **exactly one host**. Do not also run these crons on the Mac.

## 8. Standing rules

- No Postiz publish from an agent.
- No direct writes to `campaign-data.json`.
- `visibility_guard` is **FROZEN** — do not modify.
- No automation commits to `data/` — not a test fixture, not "just this once".
- Never print a secret value. Presence checks only (`[ -n "$X" ]`).

## 9. Stale docs — do not follow

| Path | Why |
|---|---|
| `docs/nightshift-prompt.md` | Wrong branch, wrong path, wrong port — quarantined |
| `docs/archive/CAMPAIGN_OS_STATUS*.md` | Archived 2026-09-11; superseded by this file + `RAILWAY.md` |
| `legacy/agents/{registry.json,README.md}` | Three inventories, all wrong |
| Anything citing port 8765, a trycloudflare URL, "23 intel endpoints", or "5 agents" | Drift |

## 10. Agent-control binding

`workspace_id` / `project_id` live in the **agent-control** repo, not here.
Spawn profile: `profiles/campaign-os-ticket.yaml`. Ticket manifests: `manifests/`.
This repo does not define its own permission model — the profile points back at **section 8**.

## 11. Pages vs Railway

Railway is the product. The GitHub Pages cockpit (`.github/workflows/deploy.yml`) is legacy static output.
Do not "fix" Pages to match Railway unless Kyle asks.

## 12. Tests

```bash
cd campaign-os && python3 -m pytest --collect-only -q
```

Count it; do not quote a stale number. There is no CI merge gate today (t28 adds one in P1).

## 13. Where the plan lives

agent-control: `manifests/campaign-os-master-plan-20260910.yaml` (ordered task list) and
`handoffs/campaign-os-*.md`. **This repo carries no roadmap. Do not start one.**

---

## Appendix A — Layer 1 salvage (t20 → t29)

Canonical machine-readable salvage of Layer 1 `inputs{}` / `outputs{}` / `criticality`:

**`docs/layer1-salvage-20260911.yaml`**

Captured from the five Layer 1 manifests before `agents/` moved to `legacy/agents/`.
Survives t33 deletion of `legacy/agents/`. Consumer: t29 (map → ~7 Python JobSpecs).
Do not re-derive from `legacy/agents/` — that tree is frozen evidence only.