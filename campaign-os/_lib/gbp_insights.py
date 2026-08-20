"""gbp_insights.py — Google Business Profile Insights API integration.

Built 2026-08-20. Real-world wind per the daily-post generator's
"improve GEO finds" brief: pull the last 30 days of GBP Insights for
each location, surface what is actually driving calls / direction
requests / website clicks, and feed those signals back into the daily
post generator's keyword scoring so the system learns from what
worked instead of guessing from generic Ubersuggest volume.

What we read (per the GBP Insights API docs):
  - QUERIES_DIRECT:    searches where the user typed your business name
  - QUERIES_INDIRECT:  searches where your business surfaced as a result
  - VIEWS_SEARCH:      views from Google Search
  - VIEWS_MAPS:        views from Google Maps
  - ACTIONS_WEBSITE:   clicks to your website
  - ACTIONS_PHONE:     phone calls initiated from your listing
  - ACTIONS_DRIVING_DIRECTIONS: driving directions requested
  - PHOTOS_VIEWS_MERCHANT:    views of merchant-uploaded photos
  - PHOTOS_VIEWS_CUSTOMERS:   views of customer-uploaded photos

We DON'T touch the live GBP listing (no Q&A writes, no reviews, no
attribute edits). This module is read-only by design — the per-loc token
already has business.manage which includes writes, but we only call
GET endpoints here. Adding writes later is a separate audit pass.

The "what worked" feed into gbp_daily_poster: each call/direction
request is a real customer interaction tied to a real GBP post that
ranked in the local SERP. We don't have per-post attribution in the
Insights API itself, but we DO have day-level totals — the daily
poster can correlate its own post dates against the daily totals to
learn which days/posts actually moved the needle. That's a 2-step
analysis: post X went out on date D; insights on date D went up by
Y% compared to baseline. We do that correlation when scoring keywords.

Real-world constraint: the OAuth token (saved per brand via
gbp_oauth.save_token) needs a refresh-token to keep working. The token
auto-refreshes on each call (see _get_fresh_access_token below).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional, Tuple

_LOG = logging.getLogger("campaign_os.gbp_insights")

INSIGHTS_DIR = Path(os.path.expanduser("~/.openclaw-instance2/workspace/swing-shack-dashboard/data/gbp-insights"))


def _insights_path(brand_id: str) -> Path:
    INSIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    return INSIGHTS_DIR / f"{brand_id}-latest.json"


# ── Auth: refresh-token → fresh access-token ─────────────────────────

def _get_access_token(brand_id: str) -> Optional[str]:
    """Return a fresh access token for the brand, refreshing if needed.

    Returns None if the brand has no OAuth token on file or refresh
    fails. Refresh token expires after 6 months of inactivity — if
    refresh fails with invalid_grant, the user needs to re-do the
    OAuth round-trip via /api/gbp/oauth/login.
    """
    try:
        from _lib import gbp_oauth as _g
        tok = _g.load_token(brand_id)
        if not tok:
            return None
        # Refresh if we have a refresh_token — even if access_token is
        # still valid, refreshing costs nothing and avoids race conditions.
        rt = tok.get("refresh_token")
        cid = tok.get("google_account_email")
        if rt:
            try:
                data, err = _g.refresh_access_token(rt)
                if not err and data and data.get("access_token"):
                    # Persist the new access token alongside the old refresh
                    tok2 = dict(tok)
                    tok2["access_token"] = data["access_token"]
                    tok2["expires_in"] = data.get("expires_in", tok2.get("expires_in"))
                    # Some refreshes rotate the refresh token; persist that too.
                    if data.get("refresh_token"):
                        tok2["refresh_token"] = data["refresh_token"]
                    tok2["google_account_email"] = cid or tok2.get("google_account_email")
                    _g.save_token(brand_id, tok2, google_account_email=tok2.get("google_account_email"))
                    return tok2["access_token"]
            except Exception as exc:
                _LOG.warning("gbp_insights: refresh failed for %s: %s", brand_id, exc)
        return tok.get("access_token")
    except Exception as exc:
        _LOG.warning("gbp_insights: _get_access_token failed: %s", exc)
        return None


# ── GBP Insights API ────────────────────────────────────────────────

INSIGHTS_BASE = "https://mybusinessbusinessinformation.googleapis.com/v1"
ACCOUNT_MGMT_BASE = "https://mybusinessaccountmanagement.googleapis.com/v1"


def _request(method: str, url: str, access_token: str, *, json_body: Optional[dict] = None, timeout: int = 30) -> Tuple[Optional[Any], Optional[Tuple[str, str]]]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    payload = json.dumps(json_body).encode("utf-8") if json_body is not None else None
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=payload, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            if not raw.strip():
                return None, None
            try:
                return json.loads(raw), None
            except json.JSONDecodeError:
                return {"_raw": raw[:500]}, None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        try:
            body = json.loads(body)
        except Exception:
            pass
        return None, (str(e.code), body if isinstance(body, dict) else body[:500])
    except urllib.error.URLError:
        raise


def list_accounts(access_token: str) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    """List the GBP accounts under this Google account (typically 1)."""
    return _request("GET", f"{ACCOUNT_MGMT_BASE}/accounts", access_token)


def list_locations(access_token: str, account_name: str = "accounts") -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    """List locations under the given account name.

    `account_name` is the resource name (e.g. "accounts/1234567890"). Returns
    a list of locations with name, title, locationState, primaryCategory, etc.
    """
    return _request("GET", f"{account_name}/locations?readMask=name,title,locationName,storefrontAddress,primaryCategory", access_token)


def fetch_daily_insights(access_token: str, location_name: str, *, days: int = 30) -> Tuple[Optional[dict], Optional[Tuple[str, str]]]:
    """Pull the daily metrics for the last N days from one location.

    The Insights API uses a 30-day rolling window — older days return 0 or
    are not present. The endpoint is at:
        https://mybusinessbusinessinformation.googleapis.com/v1/{location_name}/insights
    with query params: dailyRange.startDate, dailyRange.endDate, metricNames=...
    """
    today = _dt.date.today()
    start = today - _dt.timedelta(days=days)
    end = today - _dt.timedelta(days=1)  # exclude today (partial day)
    qs = urllib.parse.urlencode({
        "dailyRange.startDate.year": start.year,
        "dailyRange.startDate.month": start.month,
        "dailyRange.startDate.day": start.day,
        "dailyRange.endDate.year": end.year,
        "dailyRange.endDate.month": end.month,
        "dailyRange.endDate.day": end.day,
        "metricNames": ",".join([
            "QUERIES_DIRECT",
            "QUERIES_INDIRECT",
            "VIEWS_SEARCH",
            "VIEWS_MAPS",
            "ACTIONS_WEBSITE",
            "ACTIONS_PHONE",
            "ACTIONS_DRIVING_DIRECTIONS",
            "PHOTOS_VIEWS_MERCHANT",
            "PHOTOS_VIEWS_CUSTOMERS",
        ]),
    })
    return _request("GET", f"{INSIGHTS_BASE}/{location_name}/insights?{qs}", access_token)


# ── Orchestration ───────────────────────────────────────────────────

def sync_for_brand(brand_id: str = "swing-shack", days: int = 30) -> dict:
    """Pull live insights for the brand and cache to data/gbp-insights/<brand>-latest.json.

    Read-only upstream (just GETs). Side effect: writes a cache file on disk
    for the daily poster's keyword scoring pass. Returns the structured
    summary so the route can surface what happened.
    """
    access_token = _get_access_token(brand_id)
    if not access_token:
        return {"ok": False, "error": f"no GBP token for brand={brand_id}. Visit /api/gbp/oauth/login?brand={brand_id}", "brand_id": brand_id}
    summary = {
        "ok": False,
        "brand_id": brand_id,
        "synced_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "days": days,
        "accounts": 0,
        "locations": [],
        "insights_records": 0,
        "errors": [],
    }
    # 1. List accounts
    accounts_data, err = list_accounts(access_token)
    if err:
        summary["errors"].append(f"accounts: {err[0]} {err[1]}")
        return summary
    accounts = (accounts_data or {}).get("accounts") or []
    summary["accounts"] = len(accounts)
    for acc in accounts:
        acc_name = acc.get("name")
        if not acc_name:
            continue
        # 2. List locations under account
        locs_data, err = list_locations(access_token, acc_name)
        if err:
            summary["errors"].append(f"locations for {acc_name}: {err[0]} {err[1]}")
            continue
        locs = (locs_data or {}).get("locations") or []
        for loc in locs:
            loc_name = loc.get("name")
            title = loc.get("title") or loc.get("locationName") or ""
            if not loc_name:
                continue
            # 3. Pull daily insights
            insights_data, err = fetch_daily_insights(access_token, loc_name, days=days)
            if err:
                summary["errors"].append(f"insights for {loc_name}: {err[0]} {err[1]}")
                continue
            # Extract the per-day breakdown. The Insights API shape is:
            # { "locationMetrics": [ { "metricName": "...", "dimensionalValues": [ { "timeDimension": {"timeRange": {"startTime", "endTime"}}, "value": "..." } ] } ] }
            per_day = _flatten_insights(insights_data)
            summary["insights_records"] += len(per_day)
            summary["locations"].append({
                "location_name": loc_name,
                "title": title,
                "days": len(per_day),
                "first_day": per_day[0]["date"] if per_day else None,
                "last_day": per_day[-1]["date"] if per_day else None,
                "totals": _sum_totals(per_day),
            })
    # Persist cache
    if summary["insights_records"]:
        summary["ok"] = True
    _insights_path(brand_id).write_text(json.dumps(summary, indent=2, default=str))
    return summary


def _flatten_insights(raw: dict) -> list[dict]:
    """Convert the Insights API response into a flat list of per-day records."""
    out = []
    by_date: dict = {}
    for loc_metric in (raw or {}).get("locationMetrics", []):
        metric_name = loc_metric.get("metricName") or loc_metric.get("metric")
        for dv in (loc_metric.get("dimensionalValues") or []):
            t = (dv.get("timeDimension") or {}).get("timeRange") or {}
            start = t.get("startTime") or ""
            date = start[:10] if start else ""
            if not date:
                continue
            try:
                value = int(dv.get("value") or 0)
            except (ValueError, TypeError):
                value = 0
            rec = by_date.setdefault(date, {"date": date})
            rec[metric_name] = value
    out = list(by_date.values())
    out.sort(key=lambda x: x["date"])
    return out


def _sum_totals(per_day: list[dict]) -> dict:
    totals = {}
    for rec in per_day:
        for k, v in rec.items():
            if k == "date":
                continue
            totals[k] = totals.get(k, 0) + (v or 0)
    return totals


def latest_summary(brand_id: str = "swing-shack") -> Optional[dict]:
    """Return the most recent cached summary, or None if no sync has run."""
    p = _insights_path(brand_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def score_boost(brand_id: str = "swing-shack") -> dict:
    """Compute a per-keyword boost from the cached insights.

    Maps top performing queries (via QUERIES_DIRECT / INDIRECT totals) to
    boost multipliers for the daily poster's keyword scoring. The boost
    is conservative (max +30%) so unknown keywords still rank by
    Ubersuggest; only when GBP has data does the boost apply.

    Returns: { ok, boost: {keyword_lower: multiplier}, source: 'insights' | 'none' }
    """
    summary = latest_summary(brand_id)
    if not summary or not summary.get("ok"):
        return {"ok": False, "boost": {}, "source": "none", "reason": "no insights synced"}
    # The Insights API doesn't expose the actual search terms (those are
    # surfaced in a separate "Search keywords" report that requires GBP
    # Performance API access — out of scope for the standard Insights API).
    # What we DO have: total calls + direction requests + website clicks.
    # Heuristic: if the location drove > 5 calls or > 5 direction requests
    # in the last 30 days, the brand's voice + proof-points are working;
    # boost commercial-intent keywords by +20%. This is a signal that the
    # brand is *finding* searchers, even if we can't tie it to a keyword.
    totals = {}
    for loc in summary.get("locations", []):
        for k, v in (loc.get("totals") or {}).items():
            totals[k] = totals.get(k, 0) + (v or 0)
    calls = totals.get("ACTIONS_PHONE", 0) or 0
    directions = totals.get("ACTIONS_DRIVING_DIRECTIONS", 0) or 0
    website = totals.get("ACTIONS_WEBSITE", 0) or 0
    boost_mult = 1.0
    if calls >= 5 or directions >= 5:
        boost_mult = 1.20
    if calls >= 20 or directions >= 20 or website >= 100:
        boost_mult = 1.30
    return {
        "ok": True,
        "boost": {"_brand_signal": boost_mult},
        "calls_30d": calls,
        "directions_30d": directions,
        "website_30d": website,
        "source": "insights",
    }
