# reddit_ghost

Reddit answer drafts, thread opportunities, soft-brand mentions, backlink bait.

## Role
Fourth Phase 2C agent (medium criticality). Reads Reddit trends and produces native-feeling answer drafts and thread participation opportunities. **No spam. Soft-brand only. Native tone.**

## Schema
`https://clawdia.io/agents/reddit-ghost/v1`

## Scripts owned
- `generate_reddit_ghost.js` — produces reddit-replies.json, reddit-opportunities.json, forum-opportunities.json

## Inputs consumed
- `data/reddit-trends.json` — hot pain points and trends
- `data/content-ideas.json` — content angles
- `data/website-insights.json` — backlink bait opportunities
- `memory/daily/` — recent learnings

## Outputs produced
| File | Contents |
|---|---|
| `data/reddit-replies.json` | Draft replies to Reddit threads |
| `data/reddit-opportunities.json` | Thread participation opportunities |
| `data/forum-opportunities.json` | Forum backlink opportunities |

## Per-reply schema
```json
{
  "reply_id": "rr-abc123",
  "question_context": "...",
  "reply_draft": "...",
  "soft_brand_mention": "TrackMan data — numbers that help.",
  "subreddit": "r/golf",
  "safety_check": {
    "no_direct_link": true,
    "no_salesy_language": true,
    "adds_value_first": true,
    "native_tone": true
  },
  "status": "draft",
  "ready_for_qa": true
}
```

## Hard rules
- No direct links (links require QA)
- No salesy language — value first, mention second
- Only post if upvote signal is positive
- Soft-brand mentions only (e.g. "TrackMan data", not "Swing Shack is the best")
- Post within 24-48h of trend surfacing

## QA rule
All outputs require QA review before posting. Manual posting only.

## How to run
```bash
node agents/reddit_ghost/run.js
node scripts/run_agent.js reddit_ghost
```