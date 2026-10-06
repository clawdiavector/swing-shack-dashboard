# Campaign OS — Jobs module

Layer 1 data jobs on Railway. GitHub Actions fires crons; Flask runs job code; JSON lands in `$DATA_DIR`.

## Registered jobs (live count)

Do **not** quote a fixed job count. From the product repo:

```bash
cd campaign-os && python3 -c "import sys;sys.path.insert(0,'.');from _lib.jobs.registry import JOBS;print(len(JOBS))"
grep -nA1 '_register_job(_JobSpec(' app.py | grep name=
```

| Shape | Schedule (SAST) | Scheduler |
|---|---|---|
| `gbp_tick` | 06:00 | GH `gbp-daily-cron.yml` |
| `meta_refresh` | 06:30, 18:30 | GH `meta-live-fetch.yml` |
| Layer 1 batch | 07:00 | GH `layer1-daily-cron.yml` |
| Layers 2–7 daily | varies | GH `layer2-7-daily-cron.yml` |
| `freshness_scan`, `publish_dispatch`, … | see `/api/jobs/status` | registry + `app.py` bootstrap |

Full anatomy: product [`docs/dev/jobs.md`](docs/dev/jobs.md).

Wave order in layer1 batch: golf → reddit → seo → ga4 → site_audit → freshness → youtube → insights_hooks → insights_reco.

## UI — `/ops/jobs`

- **Schedule at a glance** — default tab; verdict colors; hover tooltips
- **Job cards** — Run now, history, last output
- **View JSON** — on each output file; opens pretty-printed JSON drawer
- **View outputs** — per job; lists all declared write paths

Deep link: `/ops/jobs?job=seo_rankings` (opens job cards).

## CLI (foreman — Linux or Mac)

From agent-control (uses `~/.hermes/.env` for `COS_JOB_TOKEN`; watch/digest **Mac only**):

Needs the `agent-control` foreman repo — **Kyle’s desk only**. On any other
machine use the bearer `curl` recipes in [api.md](api.md) instead.

```bash
AC=~/finder-workspace/repos/work/agent-control

python3 "$AC/bin/campaign_os_jobs.py" status
python3 "$AC/bin/campaign_os_jobs.py" run seo_rankings
python3 "$AC/bin/campaign_os_jobs.py" outcome ga4_report
python3 "$AC/bin/campaign_os_jobs.py" outputs seo_rankings
python3 "$AC/bin/campaign_os_jobs.py" output seo_rankings ga4-metrics.json
```

Hermes watch/digest — **Mac only** (see `context/campaign-os-watch.md`):

```bash
# Mac ~/.hermes/scripts shims, not Linux
python3 ~/.hermes/scripts/watch_campaign_os.py
python3 ~/.hermes/scripts/campaign_os_digest.py
```

## API (bearer or session)

| Endpoint | Purpose |
|---|---|
| `GET /api/jobs/status` | Verdict table |
| `POST /api/jobs/run/<name>` | Manual run |
| `GET /api/jobs/outcome?job=` | Human summary + file highlights |
| `GET /api/jobs/outputs?job=` | Declared output paths |
| `GET /api/jobs/output?job=&path=` | Raw output JSON (allowlisted paths only) |
| `GET /api/jobs/digest` | Stable bytes for watch script |

## Verdicts

| Verdict | Meaning |
|---|---|
| OK | Last run succeeded within cadence |
| LATE | best_effort job missed cadence or soft failure |
| FAILED | Hard job failed |
| STUCK | Running too long / ambiguous |
| NEVER | No run logged yet |

## Check workflow

1. `status` or open `/ops/jobs`
2. For non-OK: `outcome <job>` or Failure detail in UI
3. Verify data: `output <job> <path.json>` or **View JSON** in UI
4. Fix creds on Railway if error class is auth; re-run manually

## Do not

- Confuse **LLM spend pill** ($0/$5) with jobs — that tracks image-gen routes only
- Push to `main` without Kyle approval
- Run watch/digest on Linux (Mac only). Never on both hosts.
