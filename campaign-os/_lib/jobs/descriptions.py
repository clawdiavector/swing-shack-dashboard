"""Human-readable job descriptions for /ops/jobs tooltips."""

from __future__ import annotations

from typing import Any

JOB_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "meta_refresh": {
        "title": "Meta analytics refresh",
        "summary": "Pulls latest IG + Facebook post metrics from the Graph API.",
        "detail": (
            "Fetches Instagram and Facebook analytics via Meta system user tokens and "
            "writes ig-analytics.json, ig-business-analytics.json, and facebook-*.json "
            "to $DATA_DIR. Powers intel views and downstream insights_hooks."
        ),
    },
    "gbp_tick": {
        "title": "Google Business Profile daily tick",
        "summary": "Generates today's GBP posting plan files.",
        "detail": (
            "Runs the GBP daily cron logic and writes plan files under gbp-daily-plans/. "
            "Uses Google OAuth credentials. Feeds the calendar / GBP workflow."
        ),
    },
    "freshness_scan": {
        "title": "Data freshness scan",
        "summary": "Walks $DATA_DIR and marks files fresh / stale / rotten.",
        "detail": (
            "Scans all JSON data files on the Railway volume and writes freshness.json. "
            "The OS freshness card and /api/freshness read this — no live walk on every page load."
        ),
    },
    "golf_news": {
        "title": "Golf news RSS harvest",
        "summary": "Fetches golf headlines from RSS feeds into golf-news.json.",
        "detail": (
            "Best-effort scraper across configured RSS sources. Failures show as LATE, not FAILED. "
            "Feeds youtube_trends keyword context and hook insights."
        ),
    },
    "reddit_trends": {
        "title": "Reddit trend harvest",
        "summary": "Pulls hot posts from golf subreddits into reddit-trends.json.",
        "detail": (
            "Best-effort Reddit JSON API fetch. Rate limits or blocks → LATE. "
            "Upstream for youtube_trends and insights_hooks."
        ),
    },
    "youtube_trends": {
        "title": "YouTube trend search",
        "summary": "Searches YouTube for golf keywords; writes youtube-trends.json.",
        "detail": (
            "Uses YOUTUBE_API_KEY. Reads golf-news + reddit-trends for query seeds. "
            "Runs after those jobs in the daily batch."
        ),
    },
    "seo_rankings": {
        "title": "SEO / Ubersuggest rankings",
        "summary": "Runs Ubersuggest CLI for domain SEO snapshots.",
        "detail": (
            "Needs UBERSUGGEST_TOKEN_FILE and SWING_SHACK_DOMAIN. Writes seo-rankings.json "
            "and ubersuggest-*.json. Best-effort — partial files still useful."
        ),
    },
    "ga4_report": {
        "title": "GA4 metrics report",
        "summary": "Pulls Google Analytics 4 metrics into ga4-metrics.json.",
        "detail": (
            "Requires GA4_PROPERTY_ID and GA4_SERVICE_ACCOUNT_JSON_PATH on Railway. "
            "Non-best-effort — missing creds → FAILED. Feeds insights_reco."
        ),
    },
    "site_audit": {
        "title": "Site SEO + geo audit",
        "summary": "Runs on-site SEO and geo audits; writes seo-audit + geo-audit JSON.",
        "detail": (
            "Deterministic audit against swingshack.co.za content. Best-effort. "
            "Outputs feed recommendation engine inputs."
        ),
    },
    "insights_hooks": {
        "title": "Hook bank generator",
        "summary": "Builds hook-bank.json from Meta + trend inputs.",
        "detail": (
            "HIGH criticality. Combines IG analytics, YouTube trends, golf/reddit news "
            "into hook-bank.json and youtube-hook-signals.json for content planning."
        ),
    },
    "insights_reco": {
        "title": "Recommendation engine",
        "summary": "Writes 8 recommendation JSON files (anomalies, funnel, retargeting, …).",
        "detail": (
            "Downstream aggregator: GA4, SEO, hooks, site audit → anomaly-alerts, "
            "missed-opportunities, funnel-leaks, website-insights, etc. Last step in daily batch."
        ),
    },
    "competitor_tracker": {
        "title": "Competitor social tracker",
        "summary": "Refreshes competitor IG cadence + diffs into competitor-tracker.json.",
        "detail": (
            "Uses Meta Graph business_discovery for configured competitor handles. "
            "Writes posting frequency, last_post, recent_posts, and summary.changes for Trend Catcher."
        ),
    },
    "windsor_refresh": {
        "title": "Paid ads refresh (Windsor)",
        "summary": "Pulls Meta + Google Ads via Windsor.ai into meta-ads.json / google-ads.json.",
        "detail": (
            "Needs WINDSOR_API_KEY. Powers Insights ad-correlation and paid performance cards."
        ),
    },
    "post_conversion_score": {
        "title": "Post → booking score",
        "summary": "Scores IG posts by GA4 /bookings/ attribution.",
        "detail": (
            "Joins ig-business-analytics.json with GA4 hook_id + time-window attribution. "
            "Writes post-conversion-score.json for winning-theme recommendations."
        ),
    },
    "gsc_report": {
        "title": "Google Search Console report",
        "summary": "Pulls query/page stats into search-console.json.",
        "detail": (
            "Uses the GA4 service account + webmasters.readonly scope against GSC_SITE_URL. "
            "Surfaces rising/falling queries and quick wins for SEO Assistant."
        ),
    },
    "booking_truth": {
        "title": "Booking + lead truth refresh",
        "summary": "Probes GA4 for funnel events; refreshes leads from Reddit trends.",
        "detail": (
            "Updates booking-events.json measurability flags, writes leads.json + lead-quality.json. "
            "Closes the commercial attribution inventory gap until site webhooks land."
        ),
    },
    "content_ideas_refresh": {
        "title": "Content ideas refresh",
        "summary": "Mines hooks, missed opps, Reddit, competitor moves into content-ideas.json.",
        "detail": (
            "Daily auto-populate for the Ideas board. Preserves used ideas and billboards."
        ),
    },
}


def description_for(job_name: str) -> dict[str, Any]:
    """Return title/summary/detail for a job (empty strings if unknown)."""
    raw = JOB_DESCRIPTIONS.get(job_name) or {}
    return {
        "title": raw.get("title", job_name.replace("_", " ").title()),
        "summary": raw.get("summary", ""),
        "detail": raw.get("detail", ""),
    }
