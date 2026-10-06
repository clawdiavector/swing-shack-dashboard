# Campaign OS — Mac build / preview / emergency deploy

Prod still auto-deploys from GitHub. The root `Dockerfile` runs `npm ci &&
npm run build` in `web/`, then copies `dist` into the Flask image. Merge to
the Railway branch as usual.

Use this module for **local preview** and **emergency** `railway` commands on
`fives-mac-mini`. Do not treat Mac as the only ship path.

## Local preview (Mac)

Repo: `${CLAUDE_PROJECT_DIR}` (or the feat worktree).

```bash
cd web
npm ci
npm run build          # writes web/dist
npm run dev            # Vite on :5173, proxies /api to Flask :8080
```

Flask serves built files at `/app` when `web/dist` exists. Friendly aliases:
`/daily`, `/review`, `/create`, `/calendar`, `/publish`, `/results`, `/other`.
Classic `/` stays `campaign-os.html`.

## Emergency Railway (Mac only)

Linux desk has no Railway CLI. Dispatch via mac-bridge:

```bash
python3 bin/mac-bridge-client.py dispatch --wait --prompt '
cd "${CLAUDE_PROJECT_DIR:-.}"
# confirm branch, then:
railway redeploy --yes
# or same-day upload of a local tree:
# railway up
'
```

Prefer GitHub merge → Railway Docker build. Redeploy only if auto-deploy
stalled or you changed service variables.

## Do not

- Commit `web/dist/` or `web/node_modules/`
- Push `main` without Kyle naming that branch
- Use ClubLab `Invoke-ClubLabMacDeploy.sh` (wrong product)
- Delete leftover HTML pages (they live under Other until Kyle reviews)
