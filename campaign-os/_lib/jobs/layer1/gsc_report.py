"""Pull Google Search Console query/page stats → search-console.json."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any, Optional

from ._io import atomic_write, utc_now_iso
from . import ga4_report

OUTPUT = "search-console.json"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
API_BASE = "https://www.googleapis.com/webmasters/v3"


def _site_url() -> str:
    return (
        os.environ.get("GSC_SITE_URL", "").strip()
        or os.environ.get("SEARCH_CONSOLE_SITE_URL", "").strip()
        or "https://swingshack.co.za/"
    )


def _get_search_console_bearer() -> str:
    _, sa_path = ga4_report._resolve_ga4_creds()
    try:
        from google.oauth2 import service_account as _sa  # noqa: PLC0415
        from google.auth.transport.requests import Request as _GRequest  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(f"google-auth not installed: {exc}") from exc

    with open(sa_path, encoding="utf-8") as fh:
        sa_info = json.load(fh)
    creds = _sa.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    creds.refresh(_GRequest())
    token = creds.token
    if not token:
        raise RuntimeError("Search Console bearer token could not be obtained")
    return token


def _search_analytics(
    site: str,
    bearer: str,
    start: str,
    end: str,
    dimensions: list[str],
    row_limit: int = 25,
) -> list[dict[str, Any]]:
    encoded_site = urllib.parse.quote(site, safe="")
    url = f"{API_BASE}/sites/{encoded_site}/searchAnalytics/query"
    body = {
        "startDate": start,
        "endDate": end,
        "dimensions": dimensions,
        "rowLimit": row_limit,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"GSC HTTP {exc.code}: {err_body}") from exc

    rows: list[dict[str, Any]] = []
    for row in payload.get("rows") or []:
        keys = row.get("keys") or []
        rows.append({
            "key": keys[0] if keys else "",
            "clicks": int(row.get("clicks") or 0),
            "impressions": int(row.get("impressions") or 0),
            "ctr": round(float(row.get("ctr") or 0) * 100, 2),
            "position": round(float(row.get("position") or 0), 1),
        })
    return rows


def _delta(current: list[dict], previous: list[dict]) -> dict[str, dict]:
    prev_map = {r["key"]: r for r in previous if r.get("key")}
    out: dict[str, dict] = {}
    for row in current:
        key = row.get("key")
        if not key:
            continue
        old = prev_map.get(key) or {}
        out[key] = {
            "clicks_delta": row.get("clicks", 0) - int(old.get("clicks") or 0),
            "impressions_delta": row.get("impressions", 0) - int(old.get("impressions") or 0),
            "position_delta": round(float(row.get("position") or 0) - float(old.get("position") or 0), 1),
        }
    return out


def run() -> dict:
    """Fetch Search Console stats and write search-console.json."""
    missing = ga4_report._missing_env_error()
    if missing:
        return {"ok": False, "error": missing}

    site = _site_url()
    end = date.today() - timedelta(days=3)  # GSC data lag
    start = end - timedelta(days=27)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=27)

    try:
        bearer = _get_search_console_bearer()
        queries = _search_analytics(site, bearer, start.isoformat(), end.isoformat(), ["query"], 50)
        pages = _search_analytics(site, bearer, start.isoformat(), end.isoformat(), ["page"], 25)
        prev_queries = _search_analytics(
            site, bearer, prev_start.isoformat(), prev_end.isoformat(), ["query"], 50
        )
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)[:400]}

    deltas = _delta(queries, prev_queries)
    rising = sorted(
        [q for q in queries if deltas.get(q["key"], {}).get("position_delta", 0) < -0.5],
        key=lambda q: deltas[q["key"]]["position_delta"],
    )[:10]
    falling = sorted(
        [q for q in queries if deltas.get(q["key"], {}).get("position_delta", 0) > 0.5],
        key=lambda q: deltas[q["key"]]["position_delta"],
        reverse=True,
    )[:10]
    quick_wins = sorted(
        [q for q in queries if q.get("impressions", 0) >= 20 and q.get("ctr", 0) < 3],
        key=lambda q: q.get("impressions", 0),
        reverse=True,
    )[:10]

    payload = {
        "updated": utc_now_iso(),
        "fetched_at": utc_now_iso(),
        "site_url": site,
        "data_window": {"start": start.isoformat(), "end": end.isoformat()},
        "source": "google_search_console_api",
        "queries": queries,
        "pages": pages,
        "rising": [{"query": q["key"], **q, **deltas.get(q["key"], {})} for q in rising],
        "falling": [{"query": q["key"], **q, **deltas.get(q["key"], {})} for q in falling],
        "quick_wins": [{"query": q["key"], **q} for q in quick_wins],
        "summary": {
            "queries_tracked": len(queries),
            "pages_tracked": len(pages),
            "rising_count": len(rising),
            "falling_count": len(falling),
            "quick_wins_count": len(quick_wins),
        },
        "_live": True,
    }
    atomic_write(OUTPUT, payload)
    return {"ok": True, "rows": len(queries)}
