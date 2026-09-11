# memory_keeper

Permanent memory — all campaigns, wins, losses, bugs, patterns.

## Role
Long-term memory layer. Aggregates daily learnings, wins, losses, bugs into memory files. Maintains the memory index. Feeds back learned patterns to influence future decisions.

## Scripts owned
- `store_daily_learnings.js` — stores daily learning log, updates index

## Inputs consumed
- `data/system-health.json` — system health
- `data/agent-scorecards.json` — agent scores
- `data/recommendation-scores.json` — rec scores
- `data/recommendation-outcomes.json` — rec outcomes
- `memory/index.json` — prior memory index

## Outputs produced
- `memory/daily/YYYY-MM-DD.json` — daily learning log
- `memory/index.json` — updated memory index
- `memory/wins/YYYY-MM-DD.json` — win records
- `memory/losses/YYYY-MM-DD.json` — loss records
- `memory/bugs/YYYY-MM-DD.json` — bug records

## Memory folders
- `memory/daily/` — daily logs
- `memory/wins/` — positive outcomes
- `memory/losses/` — negative outcomes  
- `memory/bugs/` — system failures
- `memory/campaigns/` — campaign data
- `memory/hooks/` — hook performance history
- `memory/tasks/` — task history
- `memory/learnings/` — aggregated learnings

## How to run
```bash
node agents/memory_keeper/run.js
node scripts/run_agent.js memory_keeper
```

## Run history
Tracked in `data/agent-runs.json` under `agents.memory_keeper`.