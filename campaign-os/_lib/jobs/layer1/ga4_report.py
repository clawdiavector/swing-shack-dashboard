"""Pull GA4 pagePath × sessionSource report and write ga4-metrics.json."""

from __future__ import annotations

import base64
import json
import os
from datetime import date, timedelta
from typing import Any, Optional

from ._io import as_dict, atomic_write, read_json, utc_now_iso, io_for_job

JOB_NAME = "ga4_report"

OUTPUT = "ga4-metrics.json"
REPORT_TIMEOUT = 20
_BRAND_SAFE = "SWING_SHACK"


def _resolve_ga4_creds() -> tuple[str, str]:
    """Resolve property id + service-account JSON path for the nightly job.

    Order matches app._ga4_credentials('swing-shack'):
      1. GA4_PROPERTY_ID + GA4_SERVICE_ACCOUNT_JSON_PATH (explicit job vars)
      2. GA4_PROPERTY_SWING_SHACK + GA4_CREDENTIALS_JSON_SWING_SHACK (Railway b64)
      3. GA4_PROPERTY_SWING_SHACK + GA4_CREDENTIALS_SWING_SHACK / GOOGLE_APPLICATION_CREDENTIALS
    """
    prop = os.environ.get("GA4_PROPERTY_ID", "").strip()
    path = os.environ.get("GA4_SERVICE_ACCOUNT_JSON_PATH", "").strip()
    if prop and path and os.path.isfile(path):
        return prop, path

    prop = (
        os.environ.get(f"GA4_PROPERTY_{_BRAND_SAFE}", "").strip()
        or prop
    )
    inline_env = os.environ.get(f"GA4_CREDENTIALS_JSON_{_BRAND_SAFE}", "").strip()
    if inline_env:
        try:
            decoded = base64.b64decode(inline_env).decode("utf-8")
            parsed = json.loads(decoded)
            if not parsed.get("type") or not parsed.get("client_email"):
                raise ValueError("missing required service-account fields")
            marker = f"/tmp/campaign-os-ga4-{_BRAND_SAFE}.json"
            with open(marker, "w", encoding="utf-8") as fh:
                fh.write(decoded)
            os.chmod(marker, 0o600)
            if prop:
                return prop, marker
        except Exception as exc:
            raise RuntimeError(f"GA4_CREDENTIALS_JSON_{_BRAND_SAFE} invalid: {exc}") from exc

    path = (
        os.environ.get(f"GA4_CREDENTIALS_{_BRAND_SAFE}", "").strip()
        or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        or path
    )
    if prop and path and os.path.isfile(path):
        return prop, path

    if not prop:
        raise RuntimeError("missing GA4_PROPERTY_ID")
    raise RuntimeError("missing GA4 service account credentials")


def _missing_env_error() -> Optional[str]:
    try:
        _resolve_ga4_creds()
        return None
    except RuntimeError as exc:
        return str(exc)


def _get_ga4_bearer() -> str:
    """Obtain GA4 bearer token from service account; patch in tests."""
    _, sa_path = _resolve_ga4_creds()
    try:
        from google.oauth2 import service_account as _sa
        from google.auth.transport.requests import Request as _GRequest
    except ImportError as exc:
        raise RuntimeError(f"google-auth not installed: {exc}") from exc

    with open(sa_path, encoding="utf-8") as fh:
        sa_info = json.load(fh)
    scopes = ["https://www.googleapis.com/auth/analytics.readonly"]
    creds = _sa.Credentials.from_service_account_info(sa_info, scopes=scopes)
    creds.refresh(_GRequest())
    token = creds.token
    if not token:
        raise RuntimeError("GA4 bearer token could not be obtained")
    return token


def _run_ga4_report(property_id: str, bearer: str, body: dict) -> dict:
    """POST runReport; patch in tests."""
    import urllib.error
    import urllib.request

    url = f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=REPORT_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_rows(report: dict) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in report.get("rows") or []:
        dims = row.get("dimensionValues") or []
        metrics = row.get("metricValues") or []
        rows.append(
            {
                "pagePath": (dims[0].get("value") if len(dims) > 0 else "") or "",
                "source": (dims[1].get("value") if len(dims) > 1 else "") or "",
                "sessions": int((metrics[0].get("value") if len(metrics) > 0 else 0) or 0),
                "engagementRate": float((metrics[1].get("value") if len(metrics) > 1 else 0) or 0),
                "avgSessionDuration": float((metrics[2].get("value") if len(metrics) > 2 else 0) or 0),
            }
        )
    return rows


def _aggregate_pages(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_path: dict[str, dict[str, float]] = {}
    for row in rows:
        path = row["pagePath"]
        bucket = by_path.setdefault(path, {"sessions": 0.0, "weightedErSum": 0.0})
        sessions = row["sessions"]
        bucket["sessions"] += sessions
        bucket["weightedErSum"] += row["engagementRate"] * sessions

    aggregated = [
        {
            "pagePath": path,
            "sessions": int(vals["sessions"]),
            "engagementRate": vals["weightedErSum"] / vals["sessions"] if vals["sessions"] else 0.0,
        }
        for path, vals in by_path.items()
    ]
    aggregated.sort(key=lambda r: r["sessions"], reverse=True)
    return aggregated


def _build_payload(rows: list[dict[str, Any]], property_id: str, start: str, end: str) -> dict[str, Any]:
    aggregated = _aggregate_pages(rows)
    top_pages = [
        {
            "path": r["pagePath"],
            "sessions": r["sessions"],
            "engRate": f"{r['engagementRate'] * 100:.1f}%",
        }
        for r in aggregated[:10]
    ]

    sources: dict[str, int] = {}
    for row in rows:
        src = row.get("source") or "direct"
        sources[src] = sources.get(src, 0) + row["sessions"]
    top_sources = [
        {"source": src, "sessions": count}
        for src, count in sorted(sources.items(), key=lambda kv: kv[1], reverse=True)[:5]
    ]

    weak_pages = [p for p in top_pages if float(p["engRate"].rstrip("%")) < 50]
    recommendations: list[dict[str, Any]] = []
    if weak_pages:
        recommendations.append(
            {
                "type": "weak_cta",
                "priority": "high",
                "message": (
                    f"{len(weak_pages)} pages with high traffic but <50% engagement. "
                    "Review CTA placement."
                ),
                "pages": [p["path"] for p in weak_pages],
            }
        )
    organic = [s for s in top_sources if "google" in s["source"] or "organic" in s["source"]]
    if organic:
        organic_sessions = sum(s["sessions"] for s in organic)
        recommendations.append(
            {
                "type": "organic_opportunity",
                "priority": "medium",
                "message": (
                    f"{organic_sessions} organic sessions. "
                    "Ensure these pages have clear booking CTAs."
                ),
            }
        )

    return {
        "updated": utc_now_iso(),
        "fetched_at": utc_now_iso(),
        "property_id": property_id,
        "data_window": f"{start} to {end}",
        "total_sessions": sum(r["sessions"] for r in rows),
        "pages": top_pages,
        "sources": top_sources,
        "insights": {"recommendations": recommendations},
        "top_pages_count": len(top_pages),
        "insights_count": len(recommendations),
        "_stale": False,
        "_auth_worked": True,
    }


def _apply_stale_fallback(existing: dict, reason: str) -> dict:
    existing = dict(existing)
    existing["updated"] = utc_now_iso()
    existing["_stale"] = True
    existing["_stale_reason"] = reason[:500]
    existing["_fallback_used"] = True
    return existing


def run(*, brand: str | None = None) -> dict:
    """Fetch GA4 metrics and write ga4-metrics.json."""
    io = io_for_job(JOB_NAME, brand)
    missing = _missing_env_error()
    if missing:
        return {"ok": False, "error": missing}

    property_id, _ = _resolve_ga4_creds()
    end = date.today()
    start = end - timedelta(days=7)
    start_str = start.isoformat()
    end_str = end.isoformat()

    existing = as_dict(io.read(OUTPUT))
    had_fallback = bool(existing.get("total_sessions"))

    body = {
        "dateRanges": [{"startDate": start_str, "endDate": end_str}],
        "dimensions": [{"name": "pagePath"}, {"name": "sessionSource"}],
        "metrics": [
            {"name": "sessions"},
            {"name": "engagementRate"},
            {"name": "averageSessionDuration"},
        ],
        "limit": 200,
    }

    try:
        bearer = _get_ga4_bearer()
        report = _run_ga4_report(property_id, bearer, body)
        if report.get("error"):
            raise RuntimeError(json.dumps(report["error"])[:200])
        rows = _parse_rows(report)
        payload = _build_payload(rows, property_id, start_str, end_str)
        io.write(OUTPUT, payload)
        return {"ok": True, "rows": payload["total_sessions"]}
    except Exception as exc:
        err_msg = str(exc)[:500]
        if had_fallback:
            payload = _apply_stale_fallback(existing, err_msg)
            io.write(OUTPUT, payload)
            return {"ok": True, "rows": payload.get("total_sessions", 0), "stale": True}
        empty = {
            "updated": utc_now_iso(),
            "error": err_msg,
            "total_sessions": 0,
            "pages": [],
            "sources": [],
            "insights": {"recommendations": []},
            "_stale": True,
            "_fallback_used": False,
            "_no_previous_data": True,
        }
        io.write(OUTPUT, empty)
        return {"ok": False, "error": err_msg}
