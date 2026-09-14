"""Human-authored suggested_checks keyed by (error_class, job_id) — t37."""

from __future__ import annotations

from typing import Optional

# Resolve: specific pair → job default → class default.
# Strings name consoles/screens, never env values, never print instructions.

_CLASS_DEFAULTS: dict[str, list[str]] = {
    "auth": [
        "Open the provider console for this job's credentials and confirm the key or "
        "service account is still active and not revoked."
    ],
    "rate_limit": [
        "Open the provider quota / API usage page for this job and confirm the daily or "
        "minute budget has not been exhausted."
    ],
    "http_5xx": [
        "Check the upstream provider status page, then re-run once the service reports healthy."
    ],
    "http_4xx": [
        "Open the provider API console and confirm the request path, project, and permissions "
        "still match what Campaign OS expects."
    ],
    "timeout": [
        "Confirm the upstream endpoint is reachable from Railway, then re-run; do not stack "
        "manual retries while a timed-out worker may still be writing outputs."
    ],
    "parse": [
        "Open the last written output under $DATA_DIR for this job and confirm the upstream "
        "payload shape has not changed."
    ],
    "empty_result": [
        "Open the job's input files under $DATA_DIR and confirm the upstream feed returned "
        "rows for the current window."
    ],
    "missing_input": [
        "Open the Campaign OS jobs status page, confirm the upstream job that writes this "
        "input last finished OK, then re-run that upstream job first."
    ],
    "disk": [
        "Open the Railway volume metrics for /data/campaign-os and free space or fix "
        "permissions before re-running."
    ],
    "unknown": [
        "Open GET /api/jobs/diagnostics/<run_id> for this failure, read suggested_checks and "
        "the redacted exception, then re-run once."
    ],
}

_JOB_DEFAULTS: dict[str, list[str]] = {
    "meta_refresh": [
        "Open Meta Business Suite → System Users and confirm the system user token still "
        "has pages_read_engagement on the linked assets."
    ],
    "gbp_tick": [
        "Open Google Cloud Console → APIs & Services → Credentials and confirm the OAuth "
        "client used for Google Business Profile is still enabled."
    ],
    "ga4_report": [
        "Open Google Cloud Console → APIs & Services → Credentials and confirm the GA4 "
        "service account still has Viewer on the property."
    ],
    "youtube_trends": [
        "Open Google Cloud Console → APIs & Services → Credentials and confirm the YouTube "
        "Data API key is enabled for this project."
    ],
    "seo_rankings": [
        "Open the Ubersuggest account → API usage screen and confirm the token file path "
        "still points at a valid key."
    ],
}

_PAIR: dict[tuple[str, str], list[str]] = {
    ("auth", "meta_refresh"): [
        "Open Meta Business Suite → System Users and rotate or re-authorize the system user "
        "token used by meta_refresh."
    ],
    ("auth", "ga4_report"): [
        "GA4 service account may have lost property access — check Google Cloud Console → "
        "APIs & Services → Credentials."
    ],
    ("auth", "gbp_tick"): [
        "Open Google Cloud Console → APIs & Services → Credentials and re-consent the Google "
        "Business Profile OAuth client."
    ],
    ("auth", "youtube_trends"): [
        "Open Google Cloud Console → APIs & Services → Credentials and confirm the YouTube "
        "API key has not been restricted or deleted."
    ],
    ("auth", "seo_rankings"): [
        "Open Ubersuggest account → API usage and confirm the token file still contains a "
        "live key."
    ],
    ("rate_limit", "meta_refresh"): [
        "Open Meta Business Suite → System Users / app dashboard rate-limit charts and wait "
        "for the Meta Graph quota window to reset before re-running."
    ],
    ("rate_limit", "youtube_trends"): [
        "Open Google Cloud Console → APIs & Services → YouTube Data API quotas and confirm "
        "the daily units have not been exhausted."
    ],
    ("rate_limit", "seo_rankings"): [
        "Open Ubersuggest account → API usage and confirm the daily request budget remains."
    ],
    ("rate_limit", "gbp_tick"): [
        "Open the Google Business Profile API quota page and confirm the project still has "
        "available QPM."
    ],
    ("http_5xx", "meta_refresh"): [
        "Check Meta's status page and Meta Business Suite → System Users, then re-run "
        "meta_refresh after Graph reports healthy."
    ],
    ("http_5xx", "ga4_report"): [
        "Check Google Cloud Status for Analytics and Google Cloud Console → APIs & Services, "
        "then re-run ga4_report once green."
    ],
    ("missing_input", "insights_hooks"): [
        "Open Campaign OS jobs status, confirm meta_refresh / youtube_trends last finished "
        "OK, then re-run those upstream jobs before insights_hooks."
    ],
    ("missing_input", "insights_reco"): [
        "Open Campaign OS jobs status, confirm insights_hooks last finished OK and wrote its "
        "outputs, then re-run insights_reco."
    ],
}


def checks_for(error_class: str, job_id: str) -> list[str]:
    pair = _PAIR.get((error_class, job_id))
    if pair:
        return list(pair)
    job_default = _JOB_DEFAULTS.get(job_id)
    if job_default and error_class in ("auth", "rate_limit", "http_4xx", "http_5xx"):
        return list(job_default)
    class_default = _CLASS_DEFAULTS.get(error_class)
    if class_default:
        return list(class_default)
    return [
        "Open GET /api/jobs/diagnostics/<run_id> for this failure and follow the redacted "
        "bundle's next steps."
    ]


def all_known_jobs() -> Optional[list[str]]:
    """Helper for tests — prefer importing app registry instead."""
    return None
