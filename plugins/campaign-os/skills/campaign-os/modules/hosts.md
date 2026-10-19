# Campaign OS — Hosts module

```text
Railway (prod)          GitHub Actions
  Flask + $DATA_DIR       POST /api/jobs/run/*  (COS_JOB_TOKEN)
        ▲                          │
        └──────────────────────────┘

Linux desk (omarchy)     Mac (fives-mac-mini)
  foreman / agent-control   Hermes cos-* agents
  tickets / manifests       watch (15m) + digest (07:00)
                            Railway CLI redeploy
                            mac-bridge dispatch
```

| Task | Host |
|---|---|
| Product UI + jobs | Railway (Docker runs `npm run build` for `/app`) |
| Cron fires | GitHub Actions |
| Watch + digest | **Mac only** |
| Calendar scout / cos-* | Mac Hermes |
| Railway redeploy | Mac via mac-bridge |
| Tickets / manifests | Linux agent-control (foreman only) |
| Suggest Date / named window | Foreman skill `campaign-os-campaign` → `suggest_campaign.py` POSTs a candidate (Waiting for you). Not Main Calendar until a human adds it. |
| Lodge one dated post | Foreman (Telegram or Mac `cos-foreman`) via `operator-post.md` → calendar + Create queue; Review only when complete |

Full doc *(Kyle’s desk only)*: `~/finder-workspace/repos/work/agent-control/context/campaign-os-hosts.md`  
Watch install: `context/campaign-os-watch.md`

Mac dispatch: skill `agent-control-mac-bridge`.
