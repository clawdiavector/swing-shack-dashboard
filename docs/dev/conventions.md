# Conventions — branch, secrets, tests, land

## Branches

| Rule | Detail |
|---|---|
| Canonical release | `main` — Kyle merges; **never push `main`/`master`/`develop` without explicit approval** |
| Active integration | **`integrate/campaign-os-brand-lanes-v1`** — feature branches merge here first |
| Feature work | `feat/*`, `fix/*`, `integrate/*` as ticket specifies |
| Dead history | `feat/asset-state-engine`, `integrate/campaign-os-option-c` — superseded; do not target |

Protected-branch doc: `agent-control/context/protected-branch-push.md`.

## Secrets

| Secret | Where set |
|---|---|
| `COS_JOB_TOKEN` | Railway service, GitHub Actions secret, Mac `~/.hermes/.env` — **same value** |
| `CAMPAIGN_OS_PASSWORD` | Railway — session login |
| `DATA_DIR` | `/data/campaign-os` on Railway volume |

Presence only in docs and logs: `[ -n "$COS_JOB_TOKEN" ]`. Never print values.

## Tests

```bash
cd campaign-os && python3 -m pytest --collect-only -q
```

Count tests at run time; do not quote stale totals. No CI merge gate on all tests yet (see `AGENTS.md` §12).

## Data and safety

- No automation commits to repo **`data/`**.
- No direct writes to **`campaign-data.json`** from agents.
- No agent **Postiz publish**.
- **`visibility_guard`** is frozen — do not modify.

## Local port

Use **`runtime.ports.web`** from the agent job file — never hardcode 8765 or 8080.

## Tickets and handoffs

Program order lives in **agent-control** manifests — not in this repo ([`state-of-play.md`](state-of-play.md)).

Standing agent rules: [`AGENTS.md`](../../AGENTS.md) §8.

## Land flow

`feat/*` → PR / merge to **`integrate/campaign-os-brand-lanes-v1`** → Kyle → `main` → Railway deploy from configured branch.

Deploy details: [`RAILWAY.md`](../../RAILWAY.md).
