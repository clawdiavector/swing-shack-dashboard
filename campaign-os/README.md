# Campaign OS — Swing Shack

Operational marketing application for Swing Shack's indoor golf content pipeline.

**Start here:** [`docs/dev/INDEX.md`](../docs/dev/INDEX.md) — developer library for jobs, agents, UI, and land rules.

Then read root [`AGENTS.md`](../AGENTS.md) — branches, `$DATA_DIR`, standing rules.

## Architecture

**Flask backend + SPAs.** Not client-only.

- `app.py` — Flask app (session auth for humans; bearer `COS_JOB_TOKEN` for job endpoints). Serves UIs and `/api/*`.
- `campaign-os.html` — Classic product UI. Nav inventory: [`WORKSPACE_MAP.md`](../WORKSPACE_MAP.md).
- `web/` — Campaign Heroes desk SPA at `/app` (on integrate — see [`docs/dev/state-of-play.md`](../docs/dev/state-of-play.md)).
- `$DATA_DIR` — Runtime state (Railway: `/data/campaign-os`). Editorial and job outputs live here. **Not** `localStorage`.
- `data/` (repo) — Seed data only. Human-committed. Automation never writes it.
- `campaign-data.json` — Seed campaign document; runtime copy is under `$DATA_DIR`.
- `_lib/jobs/` — Registered jobs — count at runtime ([`docs/dev/jobs.md`](../docs/dev/jobs.md)).

## Deployment

Deploys to **Railway** via the **repo-root** `Dockerfile` + `railway.json` (`python app.py`, healthcheck `/api/health`). Details: [`RAILWAY.md`](../RAILWAY.md).

GitHub Pages lane retired in t51 (2026-09-14): media-only mirror remains; Railway is the only product surface. See root `AGENTS.md` §11.

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
