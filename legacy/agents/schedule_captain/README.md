# schedule_captain

Posting calendar — slot assignment, owner load balancing, same-day reshuffles, fallback substitution.

## Role
Phase 3B. Builds the daily publishing schedule — fills 3 time slots (9am/12pm/6pm) with approved content, balances across service buckets and formats, substitutes fallbacks when approved items are missing.

## Schema
`https://clawdia.io/agents/schedule-captain/v1`

## Inputs consumed
- `data/post-plan.json` — planned items
- `data/ready-for-approval.json` — approved items
- `data/daily-task-cards.json` — task cards
- `data/fallback-queue.json` — fallback when approved missing
- `data/capacity-shift.json` — capacity for load balancing

## Outputs produced
| File | Contents |
|---|---|
| `data/schedule-board.json` | Today's schedule with slots filled |
| `data/tomorrow-slots.json` | Tomorrow's open slots with fallback pool |
| `data/reschedule-log.json` | Fallback/reschedule events |

## Schedule model
3 slots per day: Morning (09:00), Lunch (12:00), Evening (18:00)
Each slot filled with: caption → approved item → fallback

## How to run
```bash
node agents/schedule_captain/run.js
node scripts/run_agent.js schedule_captain
```