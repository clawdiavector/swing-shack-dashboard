# insight_analyst

Turn raw data into decisions — anomalies, wins, leaks, opportunities.

## Role
Second layer. Takes harvested data and extracts signal: which hooks are working, what's trending, where are the leaks, what opportunities were missed. Feeds decision data to taskmaster.

## Scripts owned
- `analyse_hooks.js` — hook performance analysis
- `extract_youtube_signals.js` — YouTube trend extraction
- `generate_anomaly_alerts.js` — anomaly detection
- `detect_missed_opportunities.js` — missed opportunity detection
- `generate_funnel_leaks.js` — funnel leak analysis
- `generate_conversion_attribution.js` — conversion attribution
- `generate_retargeting_recommendations.js` — retargeting strategy
- `generate_recommendation_scores.js` — score recommendations
- `generate_recommendation_outcomes.js` — track recommendation outcomes

## Inputs consumed
- `data/ig-analytics.json` — IG posts and engagement
- `data/ga4-report.json` — web traffic data
- `data/seo-rankings.json` — SEO rankings
- `data/hook-bank.json` — hook performance history
- `data/recommendation-scores.json` — prior recommendation scores

## Outputs produced
- `data/hook-bank.json` — updated hook bank with scores
- `data/anomaly-alerts.json`
- `data/missed-opportunities.json`
- `data/funnel-leaks.json`
- `data/conversion-attribution.json`
- `data/retargeting-recommendations.json`
- `data/recommendation-scores.json`
- `data/recommendation-outcomes.json`

## How to run
```bash
node agents/insight_analyst/run.js
node scripts/run_agent.js insight_analyst
```

## Run history
Tracked in `data/agent-runs.json` under `agents.insight_analyst`.