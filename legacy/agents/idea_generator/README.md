# idea_generator

Generate content ideas, post plan ideas, follow-up queue, retargeting angles.

## Role
Third creative worker agent. Takes data from insight_analyst and generates actionable content ideas with freshness scoring, novelty checking, and used-items suppression.

## Scripts owned
- `generate_content_ideas.js` — core content ideas from hooks and trends
- `generate_follow_up_queue.js` — follow-up content angles
- `generate_retargeting_recommendations.js` — retargeting angles for cold audiences

## Inputs consumed
- `data/ig-analytics.json` — IG performance for direction
- `data/golf-news.json` — timely ideas from news
- `data/reddit-trends.json` — Reddit pain points
- `data/hook-bank.json` — hook formulas for idea generation
- `data/content-ideas.json` — prior ideas for novelty check
- `data/used-items.json` — used ideas to suppress

## Outputs produced
- `data/content-ideas.json` — ideas with freshness, hooks, CTAs, formats
- `data/follow-up-queue.json` — follow-up angles
- `data/retargeting-recommendations.json` — retargeting angles

## How to run
```bash
node agents/idea_generator/run.js
node scripts/run_agent.js idea_generator
```