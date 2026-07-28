# Railway deployment for Campaign OS

Campaign OS is configured to deploy to Railway. The `railway.json`, `Dockerfile`,
`Procfile`, and `runtime.txt` at the repo root cover Railway's auto-detection.

## Two ways to deploy

### Option A — GitHub integration (recommended, no CLI required)

1. Go to https://railway.app/new
2. Click **"Deploy from GitHub repo"**
3. Select `clawdiavector/swing-shack-dashboard`
4. Pick the `feat/asset-state-engine` branch (or `main` once merged)
5. Railway auto-detects `railway.json` and starts the build
6. After deploy, click **Settings → Networking → Generate Domain**
   to get `https://campaign-os-production.up.railway.app`
7. Every push to the branch triggers a redeploy automatically

### Option B — CLI from local

```bash
brew install railway
railway login                # browser opens, sign in
railway init                 # pick repo + branch
railway up                   # deploy
railway domain               # generate public URL
```

## What Railway needs

| Variable | Default | Notes |
|---|---|---|
| `PORT` | `8000` | App reads `os.environ.get('PORT')` |
| `DATA_DIR` | `/data/campaign-os` | Persistent volume for scheduled-items, review state |

No secrets are required to run. Postiz / GA4 credentials only needed if you
wire the optional integrations.

## Verifying the deploy

```
curl https://<your-railway-url>/api/health
# → {"git_synced":false,"status":"ok","ts":"..."}
```

Open the URL in a browser — should see the Campaign OS SPA.

## Persistent data

The `scheduled-items.json` and `review state` files live in the persistent
volume at `/data/campaign-os`. If you want to keep editorial state across
redeploys, do NOT redeploy with `--no-volume`. The default railway.json
already requests a volume mount.

## What's NOT Railway's problem

- `GITHUB_TOKEN` — only needed if you want bidirectional GitHub sync
  (the app can run entirely without it)
- Postiz publishing — disabled per "no publish/schedule/Postiz-draft" rules
- Image generation — no API credentials wired yet