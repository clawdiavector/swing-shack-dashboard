# postback_logger

Log what actually got posted, mark used items immediately, update attribution.

## Role
Phase 3B. Closes the real-time used-items gap. Hook and idea are marked used at the moment publishing confirms — not on next daily reconciliation.

## Schema
`https://clawdia.io/agents/postback-logger/v1`

## Inputs consumed
- `data/published-items.json` — what was published
- `data/scheduled-items.json` — what was scheduled
- `data/publish-failures.json` — what failed
- `data/used-items.json` — current suppress list
- `data/recommendation-outcomes.json` — attribution

## Outputs produced
| File | Contents |
|---|---|
| `data/postback-log.json` | All postback events with timestamps |
| `data/used-items.json` | Updated suppress list (hooks + ideas) |
| `data/published-posts.json` | Published history (last 200) |

## What it closes
- **Real-time used-items**: Hook/idea marked used at moment of publish
- **Attribution loop**: `recommendation_id → published → outcome tracked`
- **Publish history**: `published-posts.json` grows with each run

## How to run
```bash
node agents/postback_logger/run.js
node scripts/run_agent.js postback_logger
```