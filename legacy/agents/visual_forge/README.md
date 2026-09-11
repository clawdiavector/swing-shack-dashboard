# visual_forge

Generate visual briefs, image prompts, carousel panel briefs, thumbnail briefs from blueprints.

## Role
Second Phase 2C agent. Reads content-blueprints.json and produces execution-ready visual briefs for image AI tools or human designers. **Prompts only — not finished images.**

## Schema
`https://clawdia.io/agents/visual-forge/v1`

## Scripts owned
- `generate_visual_briefs.js` — produces visual-briefs.json, image-prompts.json, thumbnail-briefs.json

## Inputs consumed (primary)
- `data/content-blueprints.json` — primary briefing layer
- `data/hook-bank.json` — hook overlay text
- `data/post-plan.json` — planned items

## Outputs produced
| File | Contents |
|---|---|
| `data/visual-briefs.json` | Full visual brief per blueprint |
| `data/image-prompts.json` | AI image generation prompts |
| `data/thumbnail-briefs.json` | YouTube/Shorts thumbnail briefs |

## Per-prompt schema
```json
{
  "prompt_id": "ip-abc123",
  "linked_blueprint_id": "bp-2026-04-22-001",
  "format_type": "static",
  "prompt_text": "Golf social media post, dark background...",
  "aspect_ratio": "1:1",
  "status": "draft",
  "ready_for_qa": true,
  "confidence": 75,
  "next_action": "Run prompt through image AI, QA result"
}
```

## Rule
Prompts only. Do not generate finished images. Execute via image AI or human designer, then QA.

## How to run
```bash
node agents/visual_forge/run.js
node scripts/run_agent.js visual_forge
```