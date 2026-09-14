"""Layer 1 jobs — network scrapers and deterministic insight ports.

bootstrap_layer1() registers eight JobSpecs. Called from registry.py next to
_bootstrap_meta() so app.py stays untouched (check_lib_modules package blindness).
"""

from __future__ import annotations

from typing import Callable

from ..spec import JobSpec
from . import (
    ga4_report,
    golf_news,
    insights_hooks,
    insights_reco,
    reddit_trends,
    seo_rankings,
    site_audit,
    youtube_trends,
)

LAYER1_JOB_NAMES: tuple[str, ...] = (
    "golf_news",
    "reddit_trends",
    "youtube_trends",
    "seo_rankings",
    "ga4_report",
    "site_audit",
    "insights_hooks",
    "insights_reco",
)


def layer1_specs() -> list[JobSpec]:
    """Return the eight Layer 1 JobSpecs (t29 table / t30 port)."""
    return [
        JobSpec(
            name="golf_news",
            fn=golf_news.run,
            every_seconds=86400,
            timeout_seconds=60,
            best_effort=True,
            criticality="LOW",
            retries=2,
            writes=("golf-news.json",),
        ),
        JobSpec(
            name="reddit_trends",
            fn=reddit_trends.run,
            every_seconds=86400,
            timeout_seconds=60,
            best_effort=True,
            criticality="LOW",
            retries=2,
            writes=("reddit-trends.json",),
        ),
        JobSpec(
            name="youtube_trends",
            fn=youtube_trends.run,
            every_seconds=86400,
            timeout_seconds=90,
            best_effort=True,
            criticality="LOW",
            retries=2,
            credentials=("YOUTUBE_API_KEY",),
            writes=("youtube-trends.json",),
            reads=("golf-news.json", "reddit-trends.json"),
            upstream=("golf_news", "reddit_trends"),
        ),
        JobSpec(
            name="seo_rankings",
            fn=seo_rankings.run,
            every_seconds=86400,
            timeout_seconds=120,
            best_effort=True,
            criticality="MEDIUM",
            retries=1,
            credentials=("UBERSUGGEST_TOKEN_FILE", "SWING_SHACK_DOMAIN"),
            writes=(
                "seo-rankings.json",
                "ubersuggest-domain.json",
                "ubersuggest-competitors.json",
                "ubersuggest-backlinks.json",
            ),
        ),
        JobSpec(
            name="ga4_report",
            fn=ga4_report.run,
            every_seconds=86400,
            timeout_seconds=90,
            best_effort=False,
            criticality="MEDIUM",
            retries=1,
            credentials=("GA4_PROPERTY_ID", "GA4_SERVICE_ACCOUNT_JSON_PATH"),
            writes=("ga4-metrics.json",),
        ),
        JobSpec(
            name="site_audit",
            fn=site_audit.run,
            every_seconds=86400,
            timeout_seconds=90,
            best_effort=True,
            criticality="MEDIUM",
            retries=2,
            writes=("seo-audit.json", "geo-audit.json"),
        ),
        JobSpec(
            name="insights_hooks",
            fn=insights_hooks.run,
            every_seconds=86400,
            timeout_seconds=120,
            best_effort=False,
            criticality="HIGH",
            retries=0,
            writes=("hook-bank.json", "youtube-hook-signals.json"),
            reads=(
                "ig-analytics.json",
                "youtube-trends.json",
                "golf-news.json",
                "reddit-trends.json",
                "hook-bank.json",
            ),
            upstream=("meta_refresh", "youtube_trends"),
        ),
        JobSpec(
            name="insights_reco",
            fn=insights_reco.run,
            every_seconds=86400,
            timeout_seconds=180,
            best_effort=False,
            criticality="MEDIUM",
            retries=0,
            writes=(
                "anomaly-alerts.json",
                "missed-opportunities.json",
                "funnel-leaks.json",
                "conversion-attribution.json",
                "retargeting-recommendations.json",
                "recommendation-scores.json",
                "recommendation-outcomes.json",
                "website-insights.json",
            ),
            reads=(
                "ga4-metrics.json",
                "seo-rankings.json",
                "ig-analytics.json",
                "hook-bank.json",
                "geo-audit.json",
                "recommendation-scores.json",
            ),
            upstream=("insights_hooks", "ga4_report", "seo_rankings", "site_audit"),
        ),
    ]


def bootstrap_layer1(register: Callable[[JobSpec], None] | None = None) -> None:
    """Register all Layer 1 JobSpecs. Pass register to avoid circular imports."""
    if register is None:
        from ..registry import register as register  # noqa: PLC0415

    for spec in layer1_specs():
        register(spec)
