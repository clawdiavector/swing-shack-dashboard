# Railway deployment for Campaign OS

## 1 — What builds this

`Dockerfile` at the repo root is the build. `railway.json` selects `builder: DOCKERFILE`, sets `startCommand` to `python app.py` (relative to the image `WORKDIR` `/app/campaign-os`), and health-checks `/api/health`. **There is no other build config.**

`Procfile`, `runtime.txt`, and `campaign-os/railway.json` were removed on 2026-09-09 and must not come back. They disagreed with the Dockerfile (Nixpacks vs Docker, Python 3.11 vs 3.12, different start commands) and that ambiguity cost a day of builder ping-pong.

Python is **3.12**, declared once, in `Dockerfile` line 1 (`python:3.12-slim-bookworm`).

## 2 — Which branch the service points at

Set the Railway service's deploy branch to **`fix/asset-state-engine-deploy`** while this work is in flight, and move it back to `feat/asset-state-engine` (or `main`) once the fix branch merges.

Dashboard path: *Service → Settings → Source → Branch*.

The fix branch is **local-only until someone with push rights pushes it**.

## 3 — Environment variables

These live on the **Railway service**, not in `railway.json`. `railway.json` cannot set environment variables or volumes; the old `deploy.env` / `deploy.volumes` blocks were silently ignored.

| Variable | Value | Required | Set where |
|---|---|---|---|
| `PORT` | injected by Railway | auto | Railway sets it; app reads it at `app.py` boot, default `8000` |
| `DATA_DIR` | `/data/campaign-os` | **yes** | **Railway service variables — NOT `railway.json`** |

If `DATA_DIR` is not set in the service variables, the app falls back to `/data` on ephemeral storage and editorial state is lost on every redeploy.

No secrets are required to boot. Postiz / GA4 credentials are only needed for optional integrations.

## 4 — Volume

A volume must be attached at mount path `/data/campaign-os` via *Service → Settings → Volumes*.

**Action: verify this exists on the live service.** If it does not, `scheduled-items.json` and review state have been evaporating on each deploy. Check that before concluding data was "lost".

## 5 — Verifying a deploy

```bash
# Full local proof — build, boot, probe, report module gap
bash tests/smoke_boot.sh

# Against the live service
SMOKE_URL=https://<service>.up.railway.app bash tests/smoke_boot.sh

# Just the module gap, no Docker
python3 scripts/check_lib_modules.py
python3 scripts/check_lib_modules.py --json | python3 -m json.tool

# After Track A lands (36 modules pushed): must exit 0
STRICT=1 bash tests/smoke_boot.sh
```

**A 200 from `/api/health` does not mean the app works.** `app.py` wraps most `_lib` imports in `try/except`, so the process boots and health passes while hundreds of routes 500 on first request. The real readiness signal is `lib_modules_missing` in `/api/ready`.

Expected-good payload (after Track A):

```
"lib_modules_missing": [], "lib_modules_present": 44, "strategy_page_present": true
```

`/api/ready` may return 503 when a *data/volume* check fails (empty first mount). That is not a boot failure. Module-gap fields are siblings of `checks` and never flip the status code.

## 6 — Developer checklist: push the 36 `_lib` modules

**These files exist only on the developer's machine.** They are not in git — on any branch, in any of ~1,400 commits — and they are **not** gitignored (`git check-ignore` finds no match; they were simply never `git add`ed). No one else can recreate them: they are ~40% of the application. Nothing in this repo, and no agent, will stub or fake them.

From the machine that has them:

```bash
cd <repo>
git checkout feat/asset-state-engine     # or the current fix branch
git status --short campaign-os/_lib/     # expect ~36 untracked .py files
python3 scripts/check_lib_modules.py     # expect: 0 missing, exit 0
git add campaign-os/_lib/*.py campaign-os/_lib/strategy_page.html
git commit -m "feat(_lib): commit the 36 modules app.py imports"
git push origin feat/asset-state-engine
```

Required files (36 `.py` + `strategy_page.html`):

```
audit brand_bible brand_brief_intel brand_dna brand_overlay campaign_brief
connection_status creative_director decision gbp_daily_poster gbp_insights
gbp_oauth governance image_gen_router insights_correlator integrity krea_mcp
marketing_lanes meme_templates meta_live_fetch portfolio postiz_client
product_service_library reference_dna report_html seo_insights social_history
spend stock_importer strategy_evidence strategy_store ubersuggest_mcp
weekly_brief weighted_sort windsor_client windsor_fetcher
```

plus `campaign-os/_lib/strategy_page.html`.

**Before pushing, check for secrets.** These modules include OAuth and API clients (`gbp_oauth`, `postiz_client`, `windsor_client`, `krea_mcp`, `ubersuggest_mcp`). Grep for hardcoded tokens/keys first — this is a public repo.

**After pushing:** `git pull && STRICT=1 bash tests/smoke_boot.sh` → must exit 0. Then drop `--warn-only` from the Dockerfile check layer so the gap can never silently return.

## 7 — Fly.io

`fly.toml` is a maintained backup target sharing the same `Dockerfile`. It is not what's live. Fly's HTTP check probes `/api/health` (not `/`, which 302s to `/login`). `PORT=8080` matches `internal_port` — do not change it.

Railway CLI is not required for this deploy path. GitHub integration + the Dockerfile is enough.
