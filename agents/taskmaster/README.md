# taskmaster

Turn insights into executable task cards with clear owners.

## Role
Third layer. Takes analysis output and produces actionable task cards, post plans, approval queues, experiment queues, and workload assignments. The bridge between insight and action.

## Scripts owned
- `generate_post_plan.js` — weekly post plan
- `generate_sales_priority.js` — sales priority ranking
- `generate_daily_task_cards.js` — daily task cards
- `generate_approval_queue.js` — content awaiting approval
- `generate_deadline_risk.js` — deadline risk assessment
- `generate_blockers.js` — current blockers
- `generate_capacity_shift.js` — capacity analysis
- `generate_follow_up_queue.js` — follow-up tasks
- `generate_experiment_queue.js` — A/B tests to run
- `generate_scaling_recommendations.js` — scaling strategy
- `generate_kill_list.js` — content to retire
- `generate_asset_needs.js` — creative assets needed
- `generate_owner_workload.js` — workload per owner

## Inputs consumed
- `data/post-plan.json` — post plan
- `data/missed-opportunities.json` — opportunities
- `data/retargeting-recommendations.json` — retargeting recs
- `data/experiment-queue.json` — experiments
- `data/hook-bank.json` — hook bank

## Outputs produced
- `data/post-plan.json`
- `data/sales-priority.json`
- `data/daily-task-cards.json`
- `data/approval-queue.json`
- `data/deadline-risk.json`
- `data/blockers.json`
- `data/capacity-shift.json`
- `data/asset-needs.json`
- `data/owner-workload.json`
- `data/experiment-queue.json`
- `data/scaling-recommendations.json`
- `data/kill-list.json`

## How to run
```bash
node agents/taskmaster/run.js
node scripts/run_agent.js taskmaster
```

## Run history
Tracked in `data/agent-runs.json` under `agents.taskmaster`.