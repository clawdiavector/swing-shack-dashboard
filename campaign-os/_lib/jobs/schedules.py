"""External scheduler metadata for /ops/jobs (cron times are SAST)."""

from __future__ import annotations

from typing import Any

# GitHub Actions crons are documented in UTC in workflow YAML; SAST = UTC+2.
_LAYER1_DAILY = {
    "scheduler": "GitHub Actions (layer1-daily-cron.yml)",
    "cron_sast": ["07:00"],
    "cadence": "daily",
}
_LAYER2_7_DAILY = {
    "scheduler": "GitHub Actions (layer2-7-daily-cron.yml)",
    "cron_sast": ["07:15"],
    "cadence": "daily",
}

JOB_SCHEDULES: dict[str, dict[str, Any]] = {
    "meta_refresh": {
        "scheduler": "GitHub Actions (meta-live-fetch.yml)",
        "cron_sast": ["06:30", "18:30"],
        "cadence": "every 12h",
    },
    "gbp_tick": {
        "scheduler": "GitHub Actions (gbp-daily-cron.yml)",
        "cron_sast": ["06:00"],
        "cadence": "daily",
    },
    "freshness_scan": _LAYER1_DAILY,
    "golf_news": _LAYER1_DAILY,
    "youtube_trends": _LAYER1_DAILY,
    "seo_rankings": _LAYER1_DAILY,
    "ga4_report": _LAYER1_DAILY,
    "site_audit": _LAYER1_DAILY,
    "insights_hooks": _LAYER1_DAILY,
    "insights_reco": _LAYER1_DAILY,
    "slot_planner": _LAYER2_7_DAILY,
    "agent_queue_writer": _LAYER2_7_DAILY,
    "review_sla": _LAYER2_7_DAILY,
    "holiday_inject": _LAYER2_7_DAILY,
    "data_archive": _LAYER2_7_DAILY,
    "draft_assets": _LAYER2_7_DAILY,
    "asset_qc": _LAYER2_7_DAILY,
    "publish_dispatch": _LAYER2_7_DAILY,
    "post_outcomes": _LAYER2_7_DAILY,
    "winner_promotion": _LAYER2_7_DAILY,
    "proposal_outcome": _LAYER2_7_DAILY,
    "human_edit_signal": _LAYER2_7_DAILY,
}


def schedule_for(job_name: str) -> dict[str, Any]:
    """Return schedule metadata for a registered job (empty dict if unknown)."""
    return dict(JOB_SCHEDULES.get(job_name) or {})
