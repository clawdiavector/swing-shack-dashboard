# hook_smith

Own the hook bank — generate, refine, retire, and promote hooks based on performance data.

## Role
First creative worker agent. Feeds directly from data_harvester and insight_analyst. Populates and maintains the hook bank from IG analytics, trend signals, and A/B test results. Every downstream creative agent depends on a healthy hook bank.

**Priority:** Fix the empty hook bank immediately. Every post in IG analytics has a `hook_text` field — hook_smith must extract and score all of them.

## Scripts owned
- `analyse_hooks.js` — reads IG analytics, scores hooks, builds output buckets

## Inputs consumed
- `data/ig-analytics.json` — raw IG posts with `hook_text`, reach, likes, engagement
- `data/hook-bank.json` — existing hook bank state
- `data/youtube-trends.json` — YouTube trend signals
- `data/reddit-trends.json` — Reddit pain points
- `data/ab-test-input.json` — A/B test results

## Outputs produced
- `data/hook-bank.json` — updated with hooks in output_buckets (proven_and_trending, proven_only, trending_to_test, retire)
- `data/hook-variants.json` — hook variant candidates for A/B testing
- `data/hook-recommendations.json` — hook improvement recommendations

## Hook bank structure
```json
{
  "output_buckets": {
    "proven_and_trending": [...],  // IG proof + YouTube alignment
    "proven_only": [...],           // IG proof, no YouTube signal
    "trending_to_test": [...],      // YouTube signal, no IG proof yet
    "retire": [...]                 // Low engagement, replacing
  }
}
```

## How to run
```bash
node agents/hook_smith/run.js
node scripts/run_agent.js hook_smith
```

## Run history
Tracked in `data/agent-runs.json` under `agents.hook_smith`.