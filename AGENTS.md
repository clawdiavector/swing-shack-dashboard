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

## 6. The jobs (this replaced the "74 agents")

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

(Host that runs the crons: open decision — exactly one host; record when chosen.)

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

Machine-readable salvage of `inputs{}` / `outputs{}` / `criticality` from the five Layer 1
manifests, captured **before** `agents/` moved to `legacy/agents/`. Survives t33 deletion of
`legacy/agents/`. Consumer: t29 (map → ~7 Python JobSpecs).

```yaml
# Salvaged from agents/<name>/manifest.json before the move to legacy/agents/ (t20).
# Consumer: t29 (map 5 Layer 1 manifests -> ~7 Python JobSpecs). Survives t33.
version: 1
salvaged_at: 2026-09-11
salvaged_from: agents/{data_harvester,insight_analyst,taskmaster,memory_keeper,pulse_keeper}/manifest.json
note: |
  outputs[] are recorded with their ORIGINAL repo-relative "data/" prefix.
  In the job registry these become $DATA_DIR-relative JobSpec.writes (drop the "data/" prefix) —
  data/ is seed-only since t09. The rewrite is t29's call, not a transcription detail.
  Every Layer 1 manifest declares criticality: HIGH. That is uncalibrated (74 of 74 agents say HIGH
  or MEDIUM with no LOW anywhere), so it is preserved as manifest_criticality and must be
  re-derived in t29 rather than copied into JobSpec.criticality.

agents:
  data_harvester:
    manifest_criticality: HIGH
    runs_on: [daily_pipeline]
    scripts_count: 9
    inputs:
      credentials/instagram-api-token.json: Instagram API token
      credentials/gcp-service-account.json: GA4/GSC service account
    outputs:
      data/ig-analytics.json: Instagram analytics
      data/ga4-report.json: GA4 web analytics
      data/seo-rankings.json: SEO rankings
      data/reddit-trends.json: Reddit trends
      data/golf-news.json: Golf news
      data/youtube-trends.json: YouTube trends
      data/website-insights.json: Website insights
      data/seo-audit.json: SEO audit
      data/geo-audit.json: Geo audit
    ga4_risk: true
    proposed_jobs: [meta_refresh, golf_news, reddit_trends, seo_rankings, ga4_report, youtube_trends]
    unaccounted_outputs: [data/website-insights.json, data/seo-audit.json, data/geo-audit.json]

  insight_analyst:
    manifest_criticality: HIGH
    runs_on: [daily_pipeline]
    scripts_count: 9
    inputs:
      data/ig-analytics.json: IG posts and engagement
      data/ga4-report.json: Web traffic data
      data/seo-rankings.json: SEO rankings
      data/hook-bank.json: Hook performance history
      data/recommendation-scores.json: Prior recommendation scores
    outputs:
      data/hook-bank.json: Updated hook bank
      data/anomaly-alerts.json: Anomaly detections
      data/missed-opportunities.json: Missed opportunities
      data/funnel-leaks.json: Funnel leak analysis
      data/conversion-attribution.json: Conversion attribution
      data/retargeting-recommendations.json: Retargeting recs
      data/recommendation-scores.json: Recommendation scores
      data/recommendation-outcomes.json: Recommendation outcomes
    proposed_jobs: [insights]
    t29_note: Nine scripts / eight outputs as one job will likely breach JobSpec.timeout_seconds: 60 — consider splitting.

  taskmaster:
    manifest_criticality: HIGH
    runs_on: [daily_pipeline]
    scripts_count: 13
    inputs:
      data/post-plan.json: Post plan
      data/missed-opportunities.json: Opportunities
      data/retargeting-recommendations.json: Retargeting recs
      data/experiment-queue.json: Experiments
      data/hook-bank.json: Hook bank
    outputs:
      data/post-plan.json: Post plan
      data/sales-priority.json: Sales priority
      data/daily-task-cards.json: Task cards
      data/approval-queue.json: Approval queue
      data/deadline-risk.json: Deadline risks
      data/blockers.json: Blockers
      data/capacity-shift.json: Capacity shifts
      data/asset-needs.json: Asset needs
      data/owner-workload.json: Owner workload
      data/experiment-queue.json: Experiments
      data/scaling-recommendations.json: Scale recommendations
      data/kill-list.json: Kill list
    proposed_jobs: []
    t29_note: |
      No P1 port named yet. SPA reads daily-task-cards.json and post-plan.json.
      Either a seventh job or consciously dropped — t29 must say which.

  memory_keeper:
    manifest_criticality: HIGH
    runs_on: [daily_pipeline, manual_trigger]
    scripts_count: 1
    inputs:
      data/system-health.json: System health
      data/agent-scorecards.json: Agent scores
      data/recommendation-scores.json: Rec scores
      data/recommendation-outcomes.json: Rec outcomes
      memory/index.json: Prior memory index
    outputs:
      memory/daily/YYYY-MM-DD.json: Daily learning log
      memory/index.json: Updated memory index
      memory/wins/YYYY-MM-DD.json: Win records
      memory/losses/YYYY-MM-DD.json: Loss records
      memory/bugs/YYYY-MM-DD.json: Bug records
    superseded_by: job_ledger
    proposed_jobs: []

  pulse_keeper:
    manifest_criticality: HIGH
    runs_on: [daily_pipeline, manual_trigger]
    scripts_count: 3
    inputs:
      logs/daily-run.log: Pipeline execution log
      data/build-meta.json: Build metadata
      data/dashboard-summary.json: Dashboard summary
      data/system-health.json: Prior health state
    outputs:
      data/system-health.json: System health report
      data/agent-scorecards.json: Agent scorecards
      memory/daily/YYYY-MM-DD.json: Daily learning log
    superseded_by: job_ledger
    proposed_jobs: []
```
