# blog_beast

SEO blog drafts, GEO pages, FAQ clusters, landing page outlines, authority articles.

## Role
Third Phase 2C agent. Reads SEO audit, rankings, website insights, and content ideas to produce SEO-optimised blog briefs and drafts. **Write for search + AI answerability + real conversion intent. Not fluff.**

## Schema
`https://clawdia.io/agents/blog-beast/v1`

## Scripts owned
- `generate_blog_drafts.js` — produces blog-briefs.json, blog-drafts.json, faq-opportunities.json

## Inputs consumed
- `data/seo-audit.json` — audit findings (16 recommendations)
- `data/seo-rankings.json` — keywords, rising/falling, quick wins
- `data/website-insights.json` — top pages, traffic data
- `data/content-ideas.json` — content ideas
- `memory/daily/` — recent learnings and wins

## Outputs produced
| File | Contents |
|---|---|
| `data/blog-briefs.json` | Blog briefs with SEO targets, word count, structure |
| `data/blog-drafts.json` | Full article drafts with sections + FAQ |
| `data/faq-opportunities.json` | FAQ clusters from SEO gaps |

## Topic clusters owned
1. TrackMan Golf Technology
2. Indoor Golf Johannesburg
3. Golf Coaching & Lessons
4. Golf Club Fitting
5. Practice & Warm-up

## Rule
Write for real search intent. Include TrackMan data angles. Target 1,200-1,800 words. FA must be actual answers, not brand filler.

## QA rule
All outputs are `draft: true` until QA. Not for publication until reviewed.

## How to run
```bash
node agents/blog_beast/run.js
node scripts/run_agent.js blog_beast
```