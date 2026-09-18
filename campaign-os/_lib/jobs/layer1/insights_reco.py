"""Layer 1 recommendation insights job.

Pipeline order (must match legacy daily_pipeline):

1. generate_anomaly_alerts.js       → anomaly-alerts.json
2. detect_missed_opportunities.js   → missed-opportunities.json
3. generate_funnel_leaks.js         → funnel-leaks.json
4. generate_conversion_attribution.js → conversion-attribution.json
5. generate_retargeting_recommendations.js → retargeting-recommendations.json
6. generate_recommendation_scores.js → recommendation-scores.json  (before outcomes)
7. generate_recommendation_outcomes.js → recommendation-outcomes.json
8. fetch_website_insights.js        → website-insights.json
"""

from __future__ import annotations

from ._io import io_for_job

JOB_NAME = "insights_reco"
from ._reco_steps import (
    count_reco_rows,
    empty_anomaly_alerts,
    empty_conversion_attribution,
    empty_funnel_leaks,
    empty_missed_opportunities,
    empty_recommendation_outcomes,
    empty_recommendation_scores,
    empty_retargeting_recommendations,
    empty_website_insights,
    step_anomaly_alerts,
    step_conversion_attribution,
    step_funnel_leaks,
    step_missed_opportunities,
    step_recommendation_outcomes,
    step_recommendation_scores,
    step_retargeting_recommendations,
    step_website_insights,
)

OUTPUT_FILES = (
    "anomaly-alerts.json",
    "missed-opportunities.json",
    "funnel-leaks.json",
    "conversion-attribution.json",
    "retargeting-recommendations.json",
    "recommendation-scores.json",
    "recommendation-outcomes.json",
    "website-insights.json",
)

_STEP_FNS = (
    step_anomaly_alerts,
    step_missed_opportunities,
    step_funnel_leaks,
    step_conversion_attribution,
    step_retargeting_recommendations,
    step_recommendation_scores,
    step_recommendation_outcomes,
    step_website_insights,
)

_EMPTY_FNS = (
    empty_anomaly_alerts,
    empty_missed_opportunities,
    empty_funnel_leaks,
    empty_conversion_attribution,
    empty_retargeting_recommendations,
    empty_recommendation_scores,
    empty_recommendation_outcomes,
    empty_website_insights,
)


def run(*, brand: str | None = None) -> dict:
    """Run all eight reco scripts in pipeline order."""
    io = io_for_job(JOB_NAME, brand)
    outputs: dict[str, dict] = {}
    try:
        for name, step_fn in zip(OUTPUT_FILES, _STEP_FNS):
            payload = step_fn(io)
            outputs[name] = payload
            io.write(name, payload)

        return {"ok": True, "rows": count_reco_rows(outputs)}
    except Exception:
        for name, empty_fn in zip(OUTPUT_FILES, _EMPTY_FNS):
            io.write(name, empty_fn())
        return {"ok": False, "rows": 0}
