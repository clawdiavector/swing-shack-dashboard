# cta_analyst

CTA ranking, testing logic, replacement strategy, booking vs awareness selection.

## Role
Second creative worker agent. Analyses which CTAs perform best per format, hook type, and audience segment. Generates CTA recommendations and performance tracking.

## Scripts owned
- `generate_cta_performance.js` — CTA performance scoring

## Inputs consumed
- `data/ig-analytics.json` — IG posts for CTA analysis
- `data/conversion-attribution.json` — conversion data
- `data/hook-bank.json` — hooks paired with CTAs
- `data/recommendation-scores.json` — prior recommendations

## Outputs produced
- `data/cta-performance.json` — top CTAs ranked by performance
- `data/cta-recommendations.json` — improvement recommendations

## CTA types
- **booking** — "Book your session", "Link in bio", "DM to get started"
- **awareness** — "Swipe to see", "Tag someone who needs this"
- **engagement** — "Drop a 🫂", "Comment below"

## How to run
```bash
node agents/cta_analyst/run.js
node scripts/run_agent.js cta_analyst
```