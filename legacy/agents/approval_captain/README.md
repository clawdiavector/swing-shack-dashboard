# approval_captain

Approval queue, signoff order, what needs review, approved and ready.

## Role
Phase 3A layer. Takes QA output and routes items to the right approval path. Manages the approval queue state.

## Schema
`https://clawdia.io/agents/approval-captain/v1`

## Inputs consumed
- `data/ready-for-approval.json` — QA-passed items
- `data/qa-failures.json` — QA-failed items (blocked)
- `data/post-plan.json` — for schedule check
- `data/content-blueprints.json`, `data/captions.json` — context

## Outputs produced
| File | Contents |
|---|---|
| `data/approval-queue.json` | Full queue categorised by approval type |
| `data/approval-summary.json` | Summary with message to owner |

## Queue categories
- `waiting_copy_approval` — captions, blog drafts, reddit replies
- `waiting_creative_approval` — visual briefs, image prompts
- `waiting_pricing` — items with pricing/offer confirmation needed
- `approved_ready` — passed all checks, ready to schedule
- `blocked_qa_fail` — failed QA, fix required first

## Priority
- `high` = QA reject (critical issue)
- `normal` = QA fix (medium/low issue)

## How to run
```bash
node agents/approval_captain/run.js
node scripts/run_agent.js approval_captain
```