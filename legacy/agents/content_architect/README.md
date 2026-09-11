# content_architect

Bridge from idea to usable build brief — turn hook + CTA + goal + channel into content blueprints.

## Role
Fourth creative worker agent. Takes output from hook_smith and idea_generator and translates it into platform-specific content blueprints (reel concept, carousel plan, static post, short script, blog outline).

This is the bridge between "what to say" and "how to build it."

## Scripts owned
- `generate_content_blueprints.js` — builds blueprints from hooks and plan

## Inputs consumed
- `data/hook-bank.json` — proven and trending hooks
- `data/post-plan.json` — post plan entries
- `data/cta-performance.json` — CTA data
- `data/content-ideas.json` — content ideas

## Outputs produced
- `data/content-blueprints.json` — platform-specific blueprints

## Blueprint types
| Type | Content |
|---|---|
| `static` | Image overlay text + caption + hashtags |
| `carousel` | 10-slide structure: hook → proof → CTA |
| `reel` | Hook + 25s script + trending audio note |
| `blog` | Title + intro + sections + CTA |
| `short_script` | Timestamp breakdown for 20-30s video |

## Blueprint schema
```json
{
  "blueprint_id": "bp-2026-04-22-001",
  "source_hook_id": "...",
  "format_type": "reel",
  "hook_overlay_text": "...",
  "caption": "...",
  "hashtags": ["..."],
  "service": "Coaching",
  "cta_text": "...",
  "creative_notes": "...",
  "status": "ready|test_next|scheduled",
  "confidence": 75
}
```

## How to run
```bash
node agents/content_architect/run.js
node scripts/run_agent.js content_architect
```