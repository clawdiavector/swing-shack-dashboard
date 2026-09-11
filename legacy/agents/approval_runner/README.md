# approval_runner

Approval expiry, stale detection, promoting approved items to publish-ready.

## Role
Phase 3B. Moves approved items into queue, detects stale approvals (72h TTL), resets approvals when copy changes after sign-off, promotes approved-and-valid items to ready-to-publish.

## Schema
`https://clawdia.io/agents/approval-runner/v1`

## Inputs consumed
- `data/approval-queue.json` — full approval queue
- `data/ready-for-approval.json` — QA-cleared items
- `data/captions.json` — for copy-change detection

## Outputs produced
| File | Contents |
|---|---|
| `data/approval-actions.json` | Actions taken (reset/promote) |
| `data/approval-expiry.json` | Expired approvals |

## Hard rules
- **72h TTL**: Approvals older than 72 hours are flagged for re-approval
- **Copy-change reset**: If caption text changes after approval, approval resets to `waiting_copy_approval`
- **Promote valid**: If item is `approved_ready` and not expired → `ready_to_publish`

## Why it matters
Stops stale approved copy going live after it's been edited, or expired approvals sneaking through.

## How to run
```bash
node agents/approval_runner/run.js
node scripts/run_agent.js approval_runner
```