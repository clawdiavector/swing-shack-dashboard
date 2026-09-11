# Campaign OS — Swing Shack

Operational marketing application for Swing Shack's indoor golf content pipeline.

**Read root [`AGENTS.md`](../AGENTS.md) first** — branches, `$DATA_DIR`, registered jobs, standing rules.

## Architecture

**Flask backend + one SPA.** Not client-only.

- `app.py` — Flask app (session auth for humans; bearer `COS_JOB_TOKEN` for job endpoints). Serves the SPA and the `/api/*` surface.
- `campaign-os.html` — The product UI (**44 sections / 45 nav keys**). See `../WORKSPACE_MAP.md`.
- `$DATA_DIR` — Runtime state (Railway: `/data/campaign-os`). Editorial and job outputs live here. **Not** `localStorage`.
- `data/` (repo) — Seed data only. Human-committed. Automation never writes it.
- `campaign-data.json` — Seed campaign document; runtime copy is under `$DATA_DIR`.
- `_lib/jobs/` — Registered jobs: `meta_refresh`, `gbp_tick`, `freshness_scan` (see `AGENTS.md` §6).

## Deployment

Deploys to **Railway** via the **repo-root** `Dockerfile` + `railway.json` (`python app.py`, healthcheck `/api/health`). Details: `../RAILWAY.md`.

GitHub Pages (if still wired) is legacy static output — Railway is the product.

## Development

Port comes from your agent-job file (`runtime.ports.web`). Never hardcode 8765/8080.

```bash
export DATA_DIR=/tmp/campaign-os-scratch
export COS_JOB_TOKEN=dev-token   # any non-empty string
cd campaign-os && python3 app.py
# open http://localhost:<port>/
```

Job smoke:

```bash
curl -H "Authorization: Bearer $COS_JOB_TOKEN" http://localhost:<port>/api/jobs/status
```
