# Architecture — hosts, data, auth

## Application shape

- **Flask monolith** — `campaign-os/app.py` serves APIs, session auth, job runner, and static/HTML bundles.
- **Classic UI** — `campaign-os/campaign-os.html` at `/` (large single-page cockpit).
- **Campaign Heroes** — Vite + React in `web/`, built in Docker, served at **`/app`** on integrate (see [`state-of-play.md`](state-of-play.md)).
- **Ops console** — `/ops` and `/ops/jobs` (session login).

Do not delete leftover classic HTML when extending Heroes — both surfaces coexist until cutover tickets land.

## Runtime data

| Location | Role |
|---|---|
| `$DATA_DIR` | Production runtime (Railway default `/data/campaign-os`) — job outputs, ledger, queue, editorial JSON |
| Repo `data/` | **Seed only** — never written by automation |
| Git | Bootstrap + docs; not live editorial truth |

Deploy-overlay work may add bootstrap paths — treat [`state-of-play.md`](state-of-play.md) for in-flight caveats.

## Hosts

| Host | Runs |
|---|---|
| **Railway** | Prod Flask, job execution when triggered, `$DATA_DIR` volume |
| **GitHub Actions** | Layer 1 / GBP / meta fetch crons (bearer to prod) |
| **Mac (`fives-mac-mini`)** | Hermes `cos-*` agents, watch/digest shims, Railway CLI emergencies |
| **Linux desk** | Foreman, agent-control, writer jobs — **not** `cos-*` execution |

Authoritative host map: `agent-control/context/campaign-os-hosts.md`.

### Cron host ruling (2026-09-22)

**Hermes crons for Campaign OS watch/digest and the L3 daily Mac chain run on the Mac (`fives-mac-mini`), not on the Linux foreman box.**

Evidence at ruling time: `agent-control/context/campaign-os-l3-daily-chain.md` (2026-09-22), `campaign-os-hosts.md`, and `origin/main` HEAD message aligning L3 seeds with **Mac** crons. Kyle may overturn — update this dated paragraph if so.

**Do not change live crons in a docs-only ticket.** Verify runtime with `hermes cron list` on the Mac.

`AGENTS.md` §7 and `RAILWAY.md` §6.5 should agree with this ruling.

## Auth

| Caller | Mechanism |
|---|---|
| Humans in browser | Session (`CAMPAIGN_OS_PASSWORD` in prod) |
| Jobs, Mac agents, scripts | `Authorization: Bearer $COS_JOB_TOKEN` |
| `/api/jobs/*` | Bearer **or** session |
| `/api/ops/runbook`, HTML `/ops/jobs` | **Session only** — bearer alone returns 401 on runbook |

Never embed `COS_JOB_TOKEN` in client-side JS. Presence checks only: `[ -n "$COS_JOB_TOKEN" ]`.

## Deploy

Full runbook: [`RAILWAY.md`](../../RAILWAY.md) — Dockerfile multi-stage (Node `web/` + Python), `railway.json`, volume mount, env vars. Do not duplicate that file here.

Integration branch for Railway source: **`integrate/campaign-os-brand-lanes-v1`** (see [`conventions.md`](conventions.md)).
