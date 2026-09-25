# Registered jobs

Layer 1 (and related) batch work is **`JobSpec`** entries under `campaign-os/_lib/jobs/`, plus a small set registered from `app.py` bootstrap.

## Live job count — never freeze a number in prose

```bash
cd campaign-os
python3 -c "import sys;sys.path.insert(0,'.');from _lib.jobs.registry import JOBS;print(len(JOBS))"
grep -nA1 '_register_job(_JobSpec(' app.py | grep name=
```

Also: **`GET /api/jobs/status`** (bearer or session) for verdicts.

Integrate registry length and `app.py` registrations differ from `origin/main` when branches diverge — re-run at write time ([`state-of-play.md`](state-of-play.md)).

## JobSpec anatomy

- Definition: `campaign-os/_lib/jobs/spec.py`
- Registry: `campaign-os/_lib/jobs/registry.py`
- Runner / verdicts: `campaign-os/_lib/jobs/runner.py`, ledger in `$DATA_DIR/job-runs.jsonl`
- Diagnostics: `$DATA_DIR/diagnostics/<job>/<run_id>.json` on non-OK runs

`app.py` additionally registers (among others) **`gbp_tick`**, **`freshness_scan`**, **`publish_dispatch`** via `_register_job(_JobSpec(...))`.

## Verdicts

Rules and phone runbook: [`RAILWAY.md`](../../RAILWAY.md) §6.2 — `OK`, `LATE`, `FAILED`, `STUCK`, `NEVER`.

## Brand lanes

Multi-brand jobs use **`JobSpec.brands`** — see brand-lanes program doc in agent-control.

## Schedulers (GitHub Actions)

Workflows under `.github/workflows/` include (verify with `ls .github/workflows/`):

- `layer1-daily-cron.yml`
- `layer2-7-daily-cron.yml`
- `gbp-daily-cron.yml`
- `meta-live-fetch.yml`
- `ci.yml`, `lint-brand-copy.yml`

Crons POST to prod with bearer token — token must match Railway + GitHub secret + Mac `~/.hermes/.env`.

## Layer 5 Create chain (daily cron)

Order in `.github/workflows/layer2-7-daily-cron.yml`:

1. `retry_failed_images` — operator auto-enqueue; reset bad rows (not pollable `waiting`)
2. `draft_assets` — cook pending caption/image rows
3. `krea_poll_draft_images` — poll Krea `waiting` rows; write PNG; record spend after bytes
4. `asset_qc` — deterministic QC on draft sidecars

Env:

| Variable | Default | Role |
|---|---|---|
| `CAMPAIGN_OS_MAX_IMAGES_PER_DAY` | `2` | Per-brand image **submit** cap (enqueue + `draft_assets` cook) |
| `KREA_POLL_BATCH_SIZE` | `10` | Max waiting rows per poll job pass |
| `CAMPAIGN_OS_DAILY_LLM_CAP_USD` | `5` | Daily modelled spend cap (`llm_spend`) |

Read-only recovery (no submit): `scripts/cos_krea_recover_probe.py` — lists `provider_job_id` from `draft-assets/images/**/*.meta.json` and Krea status.

## Adding a job

Recipe: [`how-to.md`](how-to.md). Salvage reference for Layer 1 shapes: `docs/layer1-salvage-20260911.yaml`.
