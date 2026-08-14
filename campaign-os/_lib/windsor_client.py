"""
windsor_client.py - minimal read-only Windsor.ai connector for the Swing
Shack dashboard.

Windsor.ai aggregates Meta Ads, Google Ads, GA4, LinkedIn, TikTok and ~40
other ad platforms into one JSON API. For Swing Shack we only use the
``facebook`` (Meta Ads) and ``google_ads`` connectors, both read-only.

Endpoint (from https://windsor.ai/api-documentation/):
    https://connectors.windsor.ai/{connector}?api_key=KEY&fields=...&date_from=YYYY-MM-DD&date_to=YYYY-MM-DD

Returns a JSON array of rows. Auth errors return ``{"error": "..."}``.

This module deliberately has zero write-side affordances. No mutation, no
publish, no spend edits. Read-only per project constraint.

Usage:
    from _lib.windsor_client import fetch_connector, read_api_key

    key = read_api_key()
    if not key:
        return None  # caller handles "not configured"

    rows, meta = fetch_connector("facebook", api_key=key,
                                 fields=["date", "campaign", "spend",
                                         "impressions", "clicks", "reach"],
                                 date_from="2026-07-15",
                                 date_to="2026-08-13")
    # rows is a list[dict] | []  ;  meta is {error: "..."} on failure
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Iterable

WINDSOR_BASE = "https://connectors.windsor.ai"
DEFAULT_TIMEOUT = 30  # seconds


# ----- API key resolution -----------------------------------------------------

def _strip_quotes(v: str) -> str:
    v = (v or "").strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1].strip()
    return v


def read_api_key() -> str:
    """Resolve Windsor.ai API key from env vars first, then on-disk creds.

    Env var: ``WINDSOR_API_KEY``
    File: ``credentials/windsor-api.json`` with key ``api_key``

    Returns empty string when not configured. Never raises.
    """
    # 1. In-process env (Railway Variables + secrets-sync sets this)
    env = _strip_quotes(os.environ.get("WINDSOR_API_KEY", ""))
    if env:
        return env

    # 2. On-disk bundled fallback (Railway /data/ persistent volume OR local repo)
    candidates = []
    env_path = os.environ.get("WINDSOR_API_KEY_FILE", "").strip()
    if env_path:
        candidates.append(env_path)
    repo_root = os.environ.get("SWING_SHACK_REPO_ROOT", "").strip()
    if repo_root:
        candidates.append(os.path.join(repo_root, "credentials", "windsor-api.json"))
        candidates.append(os.path.join(repo_root, "data", "windsor-api.json"))
    # Common defaults
    candidates.append("/data/credentials/windsor-api.json")
    candidates.append("/data/windsor-api.json")
    candidates.append("/data/campaign-os/credentials/windsor-api.json")
    candidates.append("/data/campaign-os/windsor-api.json")
    candidates.append(os.path.expanduser("~/.openclaw-instance2/workspace/swing-shack-dashboard/credentials/windsor-api.json"))

    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                k = _strip_quotes(str(data.get("api_key") or ""))
                if k:
                    return k
        except (FileNotFoundError, IsADirectoryError, PermissionError, json.JSONDecodeError):
            continue
        except Exception:
            continue
    return ""


# ----- HTTP call --------------------------------------------------------------

def _http_get_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """GET url, parse JSON. Returns dict with 'data' on success or 'error' on failure.

    Never raises. Network and parse errors become ``{"error": "<message>"}``.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "swing-shack-dashboard/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return {"error": f"invalid JSON: {e}", "raw": raw[:500]}
        return data
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return {"error": f"HTTP {e.code}: {e.reason}", "body": body[:500]}
    except Exception as e:
        return {"error": f"network error: {type(e).__name__}: {e}"}


def fetch_connector(
    connector: str,
    api_key: str,
    fields: Iterable[str],
    date_from: str | None = None,
    date_to: str | None = None,
    extra_filters: list | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[list[dict], dict]:
    """Call a Windsor connector. Returns (rows, meta).

    rows is always a list (possibly empty). meta is ``{"error": "..."}`` on
    failure or ``{"ok": True, "fetched_at": ...}`` on success.
    """
    if not api_key:
        return [], {"error": "no_api_key"}
    if not connector or not isinstance(connector, str):
        return [], {"error": "missing_connector"}

    params = {
        "api_key": api_key,
        "fields": ",".join(f for f in fields if f),
    }
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to
    if extra_filters:
        params["filter"] = json.dumps(extra_filters)

    url = f"{WINDSOR_BASE}/{urllib.parse.quote(connector)}?{urllib.parse.urlencode(params)}"
    result = _http_get_json(url, timeout=timeout)

    if isinstance(result, dict) and "error" in result and "data" not in result:
        return [], result

    # Windsor returns either {"data": [...]} or a bare list. Be tolerant.
    if isinstance(result, list):
        rows = result
    elif isinstance(result, dict):
        rows = result.get("data", [])
        if not isinstance(rows, list):
            rows = []
    else:
        rows = []

    return rows, {
        "ok": True,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "url_host": WINDSOR_BASE,
        "connector": connector,
        "row_count": len(rows),
    }


# ----- Date helpers -----------------------------------------------------------

def iso_window(days_back: int, end_offset_days: int = 0) -> tuple[str, str]:
    """Return (date_from, date_to) as YYYY-MM-DD strings.

    ``days_back`` is how many days of history to pull. ``end_offset_days``
    lets the caller shift the window forward (e.g. for "the future" - not
    used here, kept for symmetry with other fetchers).
    """
    today = datetime.now(timezone.utc).date() + timedelta(days=end_offset_days)
    start = today - timedelta(days=days_back)
    return start.isoformat(), today.isoformat()


def week_window(days_back: int = 7) -> tuple[str, str]:
    """7-day rolling window ending today. Matches the weekly report cadence."""
    return iso_window(days_back=days_back)


def month_window(days_back: int = 30) -> tuple[str, str]:
    """30-day rolling window. Matches the IG 28d + small buffer."""
    return iso_window(days_back=days_back)


# ----- Field sets -------------------------------------------------------------

# Conservative field set per connector. Windsor returns these straight from the
# underlying ad API. Adding fields is cheap; missing fields just come back null.
# IMPORTANT: Windsor validates field names against the upstream ad API
# (Facebook Marketing API, Google Ads API) and rejects the whole request with
# HTTP 400 if ANY field name is unknown. So we keep this list tight to the
# fields Windsor docs explicitly list as supported.
FACEBOOK_FIELDS = [
    "date",
    "campaign",
    "campaign_id",
    "spend",
    "impressions",
    "clicks",
    "reach",
    "frequency",
    "currency",
]

GOOGLE_ADS_FIELDS = [
    "date",
    "campaign",
    "campaign_id",
    "spend",
    "impressions",
    "clicks",
    "currency",
]