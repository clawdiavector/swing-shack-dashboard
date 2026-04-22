# nudge_bot

Nudge generation, suppression logic, delivery prep, auto-messages, fallback routing.

## Role
Fifth creative worker agent (medium criticality). Manages the nudge system — who needs to be reminded of what, when to suppress nudges to avoid spam, and how to route tasks when primary paths are blocked.

## Scripts owned
- `generate_nudge_queue.js` — generates nudges per owner/task
- `generate_suppression_rules.js` — smart suppression to avoid nudge fatigue
- `generate_fallback_queue.js` — fallback tasks when primary blocked
- `generate_auto_messages.js` — auto-message templates
- `send_discord_nudges.js` — sends nudges to Discord
- `log_discord_deliveries.js` — logs delivery results

## Inputs consumed
- `data/daily-task-cards.json` — task cards requiring owner action
- `data/approval-queue.json` — content awaiting approval
- `data/blockers.json` — blockers for nudge context
- `data/deadline-risk.json` — deadline risk for urgency nudges
- `data/suppression-rules.json` — suppression rules

## Outputs produced
- `data/nudge-queue.json` — nudge tasks per owner
- `data/auto-messages.json` — auto-message templates
- `data/suppression-rules.json` — updated suppression rules
- `data/fallback-queue.json` — fallback tasks
- `logs/discord-deliveries.json` — Discord delivery log

## Suppression rules
- Don't nudge if task already completed
- Don't nudge if same task nudged within 24h
- Escalate to different channel if 3 nudges failed

## How to run
```bash
node agents/nudge_bot/run.js
node scripts/run_agent.js nudge_bot
```