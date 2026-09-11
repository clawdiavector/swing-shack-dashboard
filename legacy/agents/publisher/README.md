# publisher

Final send to Postiz — assembles platform-safe payloads, publishes or schedules approved content.

## Role
Phase 3B controlled publishing. Takes QA-passed, brand-passed, approval-passed content and sends it to Postiz. Nothing publishes without all three gates.

## Schema
`https://clawdia.io/agents/publisher/v1`

## Inputs consumed
- `data/ready-for-approval.json` — cleared items
- `data/approval-queue.json` — approval status
- `data/captions.json` — caption data with CTA
- `data/content-blueprints.json` — blueprints
- `data/post-plan.json` — for scheduled items

## Outputs produced
| File | Contents |
|---|---|
| `data/publish-queue.json` | Items queued for publish today |
| `data/published-items.json` | Items actually published |
| `data/scheduled-items.json` | Items scheduled via Postiz |
| `data/publish-failures.json` | Failed attempts with reason |

## Hard rules
- Only items with QA PASS + Brand PASS + Approval PASS publish
- Requires: caption, platform, owner, hook_id
- Must write back: post_id, scheduled_id, publish_timestamp

## Mode: DRY RUN
Currently runs in DRY RUN — logs what would publish without actually posting to Postiz.
Set `DRY_RUN = false` in `scripts/run_publisher.js` to enable live publishing.

## Postiz integrations
- Instagram: `cmnfoum2703e6ql0yiajgcg21`
- TikTok: `cmmdgfz3b00s1o20ykrwau2o2`
- GMB: `cmmdgju7f00tppk0y6bne9zrk`

## How to run
```bash
node agents/publisher/run.js
node scripts/run_agent.js publisher
```