# Swing Shack Agent System

## Architecture

Layer 1 agents execute in sequence as part of the master pipeline. Each agent is a wrapper around related scripts that:
1. Declares inputs and outputs
2. Executes its owned scripts
3. Validates outputs
4. Logs run result to `agent-runs.json`

## Agents

| Agent | Layer | Role | Criticality |
|---|---|---|---|
| `data_harvester` | 1 | Pull all external data sources | HIGH |
| `insight_analyst` | 1 | Turn raw data into decisions | HIGH |
| `taskmaster` | 1 | Turn insights into task cards | HIGH |
| `memory_keeper` | 1 | Permanent memory (wins/losses/bugs) | HIGH |
| `pulse_keeper` | 1 | System health and pipeline reliability | HIGH |

## Running agents

### Universal runner
```bash
node scripts/run_agent.js <agent_id>   # run one agent
node scripts/run_agent.js --all        # run all layer-1 agents
node scripts/run_agent.js --list        # list all agents
```

### Direct
```bash
node agents/<agent_id>/run.js
```

## Agent outputs tracked
Each run is logged to `data/agent-runs.json` with:
- `status` (PASS / PARTIAL / FAIL)
- `duration_ms`
- Per-script results
- Output files validated

## Dashboard
AGENT RUNS TODAY section shows live status of today's runs pulled from `agent-runs.json`.

## Phase status
- Phase 1A (Agent HQ): COMPLETE ✅
- Phase 1B (Memory Castle): COMPLETE ✅
- Phase 2A (Real Agentisation): COMPLETE ✅