# caption_closer

Convert blueprints into platform-ready captions with CTA variants for every channel.

## Role
Highest priority Phase 2C agent. Reads content-blueprints.json and produces polished captions for every platform format — IG feed, Story, Reel, YouTube Shorts.

## Schema
`https://clawdia.io/agents/caption-closer/v1`

## Scripts owned
- `generate_captions.js` — produces captions.json + caption-variants.json

## Inputs consumed (primary)
- `data/content-blueprints.json` — primary briefing layer (never bypass)
- `data/hook-bank.json` — original hook text
- `data/cta-performance.json` — CTA rankings
- `data/post-plan.json` — planned items

## Outputs produced
| File | Contents |
|---|---|
| `data/captions.json` | Short + medium captions per blueprint |
| `data/caption-variants.json` | CTA variants, channel adaptations |

## Per-caption schema
```json
{
  "caption_id": "cap-2026-04-22-abc123",
  "linked_blueprint_id": "bp-2026-04-22-001",
  "short_caption": "...",
  "medium_caption": "...",
  "strong_cta": "...",
  "soft_cta": "...",
  "channels": { "ig_post": "...", "story": "...", "reel": "...", "youtube_shorts": "..." },
  "status": "draft",
  "ready_for_qa": true,
  "confidence": 75
}
```

## QA rule
All outputs are `draft: true` until QA inspector exists. Do not post without QA review.

## How to run
```bash
node agents/caption_closer/run.js
node scripts/run_agent.js caption_closer
```