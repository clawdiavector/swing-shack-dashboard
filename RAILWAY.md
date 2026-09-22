# Railway deployment for Campaign OS

## 1 — What builds this

`Dockerfile` at the repo root is the build. It is **multi-stage**: a Node 20
stage runs `npm ci && npm run build` in `web/` (Vite + Tailwind), then the
Python 3.12 image copies `web/dist` to `/app/web/dist`. Flask serves that
bundle at **`/app`** (`/daily` redirects there). Classic `/` is still
`campaign-os.html` until Kyle cuts over.

`railway.json` selects `builder: DOCKERFILE`, sets `startCommand` to
`python app.py` (relative to the image `WORKDIR` `/app/campaign-os`), and
health-checks `/api/health`. **There is no other build config.** GitHub
merge to the Railway branch still auto-deploys — do not treat Mac as the
only ship path. Mac preview commands: skill `campaign-os` module
`mac-build-deploy.md`.

`Procfile`, `runtime.txt`, and `campaign-os/railway.json` were removed on 2026-09-09 and must not come back. They disagreed with the Dockerfile (Nixpacks vs Docker, Python 3.11 vs 3.12, different start commands) and that ambiguity cost a day of builder ping-pong.

Python is **3.12**, declared once, in `Dockerfile` line 1 (`python:3.12-slim-bookworm`).

## 2 — Which branch the service points at

Set the Railway service deploy branch to **`integrate/campaign-os-brand-lanes-v1`** while program work is in flight (confirm in Railway: *Service → Settings → Source → Branch*). Do **not** point at retired branches (`integrate/campaign-os-option-c`, `feat/asset-state-engine`, `fix/asset-state-engine-deploy`).

## 3 — Environment variables

These live on the **Railway service**, not in `railway.json`.

| Variable | Value | Required | Set where |
|---|---|---|---|
| `PORT` | injected by Railway | auto | Railway sets it; app reads it at boot, default `8000` |
| `DATA_DIR` | `/data/campaign-os` | **yes** | Railway service variables |
| `COS_JOB_TOKEN` | long random string | **yes** for jobs / Hermes | Railway service variables — never print the value |
| `CAMPAIGN_OS_DAILY_LLM_CAP_USD` | e.g. `5` (default) | no | Hard daily cap for image generate routes |
| `COS_LLM_DAILY_CAP_USD` | alias for the above | no | Accepted if the longer name unset |
| `CAMPAIGN_OS_PASSWORD` | shared login | yes in prod | Railway service variables |

If `DATA_DIR` is not set, the app falls back to ephemeral storage and editorial state is lost on every redeploy.

## 4 — Volume

Attach a volume at mount path `/data/campaign-os` (*Service → Settings → Volumes*).

## 5 — Verifying a deploy

```bash
bash tests/smoke_boot.sh
SMOKE_URL=https://<service>.up.railway.app bash tests/smoke_boot.sh
python3 scripts/check_lib_modules.py
```

A 200 from `/api/health` does not mean the app works. Prefer `/api/ready` module-gap fields.

---

## 6 — Monitoring runbook (phone-first)

You got paged at 07:00 or Telegram shouted. Act from this page alone — no laptop required.

### 6.0 Ops API cheat-sheet

| Endpoint | Auth | Use on phone |
|---|---|---|
| `GET /api/jobs/status` | bearer **or** session | Full verdict table (timestamps) |
| `GET /api/jobs/failures` | bearer **or** session | Open incidents — **excludes `best_effort`** |
| `GET /api/jobs/diagnostics/<run_id>` | bearer **or** session | Redacted bundle (30d / 200 per job retention) |
| `GET /api/ops/runbook` | **session only** | Snapshot: checks, errors, `llm_spend`, jobs snippet. Bearer alone → **401** here (auth asymmetry vs `/api/jobs/*`) |
| `GET /api/ops/errors` / `…/stats` | session | In-memory ring (~200). **Per process** — empties on every deploy / replica |
| `GET /api/ops/llm-spend` | session | Today’s generate spend vs hard cap |
| `GET /ops/jobs` | **session only** (bearer does **not** open HTML) | Human dashboard — verdicts, drawer, Run now |

### 6.0b Registered jobs (live count — do not freeze)

Job names, cadence, and criticality change. Use **`GET /api/jobs/status`** on phone or:

```bash
cd campaign-os && python3 -c "import sys;sys.path.insert(0,'.');from _lib.jobs.registry import JOBS;print(len(JOBS))"
```

Shape reference (not exhaustive): Layer 1 daily batch via `layer1-daily-cron.yml`, `gbp_tick`, `meta_refresh`, `freshness_scan`, **`publish_dispatch`**, plus layer 2–7 jobs — see [`docs/dev/jobs.md`](docs/dev/jobs.md).

`meta_refresh` goes LATE at **18h** when `every_s=43200`; 24h jobs go LATE at **36h**. STUCK uses `timeout_seconds × 2` per job (see §6.2).

### 6.1 What the alerts mean

| Signal | Meaning | First action on phone |
|---|---|---|
| Silence from `campaign-os-watch` (15m) | Healthy — every job verdict is `OK` | Nothing |
| One or more Telegram lines from the watch | At least one job is not `OK` | Open `/ops/jobs` (login), tap the red/amber row |
| **Missing** 07:00 `campaign-os-digest` | Watchdog host / cron is down — **not** "all clear" | Check Hermes cron host; then curl status below |
| `🟢 … recovered` | Prior bad set cleared | Optional glance at `/ops/jobs` |

### 6.2 Verdicts (stand-in SLOs)

From `GET /api/jobs/status` / the Jobs page chips. Numbers from `runner.verdict_for`:

| Verdict | Rule |
|---|---|
| `OK` | Last finished status is `OK` **and** age since last success `< every_seconds × 1.5` |
| `LATE` | Success is older than `every_seconds × 1.5`, **or** a `best_effort` job's last finish was not OK |
| `FAILED` | Last finished status ≠ OK on a non–`best_effort` job |
| `STUCK` | A `started` row with no matching `finished`, older than `timeout_seconds × 2` |
| `NEVER` | No ledger rows (fresh volume / never scheduled) |

Severity sort for phone reading: `FAILED` → `STUCK` → `NEVER` → `LATE`.

### 6.3 Phone checklist (copy/paste)

1. Open **`https://<service>.up.railway.app/ops/jobs`** (session login — this page is **not** public).
2. Read the verdict chips. Tap **Failure detail** on `FAILED` / `STUCK`.
3. Work the **Suggested checks** checklist in the drawer (technical traceback stays collapsed).
4. If the check says credentials / env — open Railway variables (presence only; do not paste secrets into Telegram).
5. Optional: **Run now** (rate-limited, `triggered_by=manual`).
6. Confirm recovery: watch goes silent, or next digest shows `OK`.

Deep link from alerts: `/ops/jobs?job=<name>` (and `&run=<run_id>` when present).

### 6.4 API endpoints (curl from phone Termux / Shortcuts)

Never print token values — only whether the header is set.

```bash
# Verdict table (timestamps) — what the digest uses
curl -sS -H "Authorization: Bearer $COS_JOB_TOKEN" \
  "https://<service>.up.railway.app/api/jobs/status" | python3 -m json.tool

# Open incidents + bundle refs (excludes best_effort)
curl -sS -H "Authorization: Bearer $COS_JOB_TOKEN" \
  "https://<service>.up.railway.app/api/jobs/failures"

# One redacted diagnostic bundle
curl -sS -H "Authorization: Bearer $COS_JOB_TOKEN" \
  "https://<service>.up.railway.app/api/jobs/diagnostics/<run_id>"

# Ops snapshot (session cookie OR use browser on /ops)
# /api/ops/runbook  — health + readiness + llm_spend + jobs snippet
# /api/ops/errors   — recent error ring buffer
# /api/ops/llm-spend — today's generate spend vs hard cap
```

If Hermes is down and you only have Railway: *Service → Deployments → View Logs*, then the curls above from any machine that has `COS_JOB_TOKEN` in the environment.

### 6.5 Telegram routing

| Cron | Cadence | Mode | Behaviour |
|---|---|---|---|
| `campaign-os-watch` | 15m | `--no-agent` | Prints **nothing** when all OK; change-detect + 4h re-assert on bad sets |
| `campaign-os-digest` | 07:00 daily | `--no-agent` | **Always** prints the full table (dead-man switch) |

Both belong on **exactly one** cron host — **Mac `fives-mac-mini`** (2026-09-22 ruling). Do not schedule them on the Linux foreman box. See [`docs/dev/architecture.md`](docs/dev/architecture.md).

**Status at plan time:** scripts live in agent-control; Hermes cron registration may still be blocked on `COS_JOB_TOKEN` in the cron host env. **Do not assume silence means healthy until `hermes cron list` shows both jobs active.** A missing 07:00 digest is the dead-man signal either way.

### 6.6 LLM spend (t50)

Generate routes (`/api/image/generate`, `/edit`, `/from-asset`, `/from-reference`,
`/from-product`, `/api/build-post/draft`, `/api/visual-library/<brand>/generate`)
refuse with `402` when today's spend would exceed
`CAMPAIGN_OS_DAILY_LLM_CAP_USD` (default **$5**; alias `COS_LLM_DAILY_CAP_USD`).
They also require `human_approved=true` (writes a receipt under `$DATA_DIR/receipts/`).
Counter: `$DATA_DIR/llm-spend/<YYYY-MM-DD>.json`, visible on `/ops/jobs` and
`/api/ops/runbook` → `llm_spend`. OpenAI path uses a **modelled** per-size price (upstream reports $0).

**Blueprint scope:** no HTTP blueprint route in the live app.
`scripts/generate-blueprint.py` is a standalone MiniMax CLI — out of scope for
the in-app counter until a route exists (plan §8.4: document, don't invent).

---

## 7 — Fly.io

`fly.toml` is a maintained backup target sharing the same `Dockerfile`. It is not what's live. Fly's HTTP check probes `/api/health` (not `/`, which 302s to `/login`).
