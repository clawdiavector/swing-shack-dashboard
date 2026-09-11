# data_harvester

Pull all external data sources on schedule.

## Role
First-mover layer. Fetches all external data (IG analytics, GA4, SEO, Reddit, Golf News, YouTube, website insights) before any other agent runs. If this agent fails, downstream agents have stale data.

## Scripts owned
- `sync_ig_analytics.js` — Instagram post data and engagement
- `fetch_golf_news.js` — Golf news headlines
- `fetch_reddit_trends.js` — Reddit golf trends
- `fetch_seo_rankings.js` — SEO keyword rankings
- `fetch_ga4.js` — Google Analytics 4 web data
- `fetch_youtube_trends.js` — YouTube search trends for golf
- `fetch_website_insights.js` — website performance data
- `run_seo_audit.js` — SEO technical audit
- `run_geo_audit.js` — geographic/geo SEO audit

## Inputs consumed
- `credentials/instagram-api-token.json` — Instagram API token
- `credentials/gcp-service-account.json` — GA4/GSC service account

## Outputs produced
- `data/ig-analytics.json`
- `data/ga4-report.json`
- `data/seo-rankings.json`
- `data/reddit-trends.json`
- `data/golf-news.json`
- `data/youtube-trends.json`
- `data/website-insights.json`
- `data/seo-audit.json`
- `data/geo-audit.json`

## GA4 auth risk
GA4 is a known failure point. When it fails, `ga4_risk_visible: true` is logged and system-health shows the risk. Other agents still run with stale data.

## How to run
```bash
node agents/data_harvester/run.js
node scripts/run_agent.js data_harvester
```

## Run history
Tracked in `data/agent-runs.json` under `agents.data_harvester`.