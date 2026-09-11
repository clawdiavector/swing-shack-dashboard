# pulse_keeper

System health, pipeline reliability, dashboard uptime.

## Role
Monitor pipeline health. Generate system-health.json and agent-scorecards.json each run. Store daily learnings. The "pulse" of the whole system.

## Scripts owned
- `generate_pulse_keeper.js` — produces system-health.json
- `generate_agent_scorecards.js` — produces agent-scorecards.json  
- `store_daily_learnings.js` — produces memory/daily/YYYY-MM-DD.json

## Inputs consumed
- `logs/daily-run.log` — pipeline execution log
- `data/build-meta.json` — build metadata
- `data/dashboard-summary.json` — dashboard summary
- `data/system-health.json` — prior health state (for trend)

## Outputs produced
- `data/system-health.json` — current system health
- `data/agent-scorecards.json` — per-agent scores (freshness, reliability, usefulness)
- `memory/daily/YYYY-MM-DD.json` — daily learning log

## How to run
```bash
node agents/pulse_keeper/run.js
# or via universal runner:
node scripts/run_agent.js pulse_keeper
```

## Run history
Tracked in `data/agent-runs.json` under `agents.pulse_keeper`.