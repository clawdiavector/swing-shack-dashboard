"""
meta_api.py — Instagram + Facebook Graph API wrapper for Campaign OS.

Three capabilities:
  - list_recent_posts(): paginated IG media for the connected business account
  - get_post_comments(media_id): read comment text + usernames for a post
  - get_post_insights(media_id): impressions, reach, saved, shares for a post

Server-side reads only. No publishing, no replying, no DMs.
Credentials resolved from env (META_ACCESS_TOKEN_FILE / META_ACCESS_TOKEN) same
as truth_collector.py.

Truth-before-cleverness: when credentials are missing or the Graph call fails,
this module raises explicit exceptions with the upstream error verbatim. It
never fabricates metric values.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

_LOG = logging.getLogger("campaign_os.meta_api")

GRAPH_API_VERSION = "v18.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


# ── Credential resolution (mirrors truth_collector._read_meta_access_token) ──

def meta_credentials_present() -> bool:
    """True if all of: META_APP_ID, an access token, and an IG business account id are set."""
    if not os.environ.get("META_APP_ID"):
        return False
    if not (_read_meta_access_token()):
        return False
    if not os.environ.get("META_INSTAGRAM_BUSINESS_ACCOUNT_ID"):
        return False
    return True


def _read_meta_access_token() -> Optional[str]:
    """Read Meta access token from (in order):
      1. META_ACCESS_TOKEN_FILE — JSON file with {"access_token": "..."}
      2. META_ACCESS_TOKEN — raw env value
    Returns None if not configured.
    """
    from_file = os.environ.get("META_ACCESS_TOKEN_FILE")
    if from_file:
        try:
            with open(from_file) as f:
                data = json.load(f)
            tok = data.get("access_token") or data.get("token")
            if tok:
                return str(tok).strip()
        except Exception as e:
            _LOG.warning("could not read META_ACCESS_TOKEN_FILE=%s: %s", from_file, e)
    raw = os.environ.get("META_ACCESS_TOKEN")
    if raw and raw.strip():
        return raw.strip()
    return None


# ── Low-level Graph API caller ────────────────────────────────────────────────

def _graph_get(path: str, params: Optional[dict] = None, timeout: int = 15) -> dict:
    """Make a GET request to the Meta Graph API. Returns parsed JSON.

    Raises:
      MetaAuthError: token missing or 401/403 from upstream
      MetaUpstreamError: other 4xx/5xx from upstream
      MetaNetworkError: connection/timeout failure
    """
    token = _read_meta_access_token()
    if not token:
        raise MetaAuthError("META_ACCESS_TOKEN (or META_ACCESS_TOKEN_FILE) not configured")
    merged = dict(params or {})
    merged["access_token"] = token
    url = f"{GRAPH_API_BASE}{path}?{urlencode(merged)}"
    req = Request(url, headers={"User-Agent": "campaign-os/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return json.loads(body.decode("utf-8"))
    except HTTPError as e:
        # Body usually contains a structured error
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = {"error": {"message": str(e), "code": e.code}}
        upstream_err = err_body.get("error", {})
        code = upstream_err.get("code")
        msg = upstream_err.get("message", "")
        if code in (401, 403) or "access token" in msg.lower() or "permission" in msg.lower():
            raise MetaAuthError(f"Graph API auth failed ({code}): {msg}", upstream=err_body) from e
        raise MetaUpstreamError(f"Graph API error ({code}): {msg}", upstream=err_body, code=code) from e
    except URLError as e:
        raise MetaNetworkError(f"network error reaching Graph API: {e}") from e
    except (TimeoutError, json.JSONDecodeError) as e:
        raise MetaNetworkError(f"timeout/parse error: {e}") from e


# ── Domain methods ───────────────────────────────────────────────────────────

def list_recent_posts(limit: int = 25, fields: Optional[list[str]] = None) -> dict:
    """GET /me/media for the IG business account.

    Returns:
      {
        "data": [{ id, caption, media_type, permalink, timestamp, thumbnail_url, ... }],
        "paging": { cursors, next },
        "_meta": { ig_account_id, fetched, total_returned }
      }
    """
    if not meta_credentials_present():
        raise MetaAuthError("Meta credentials not configured — set META_APP_ID, META_ACCESS_TOKEN[_FILE], META_INSTAGRAM_BUSINESS_ACCOUNT_ID")
    ig_account_id = os.environ.get("META_INSTAGRAM_BUSINESS_ACCOUNT_ID", "").strip()
    default_fields = [
        "id",
        "caption",
        "media_type",
        "media_url",
        "permalink",
        "thumbnail_url",
        "timestamp",
        "username",
        "is_comment_enabled",
    ]
    fields = fields or default_fields
    params = {
        "fields": ",".join(fields),
        "limit": min(int(limit), 100),
    }
    out = _graph_get(f"/{ig_account_id}/media", params)
    out["_meta"] = {
        "ig_account_id": ig_account_id,
        "fetched": len(out.get("data", [])),
        "endpoint": f"/{ig_account_id}/media",
    }
    return out


def get_post_comments(media_id: str, limit: int = 50) -> dict:
    """GET /{media_id}/comments — read comments on a single IG post.

    Returns:
      {
        "data": [{ id, text, username, timestamp, like_count, replies? }],
        "paging": { ... },
        "_meta": { media_id, fetched }
      }
    """
    if not meta_credentials_present():
        raise MetaAuthError("Meta credentials not configured")
    if not media_id or not str(media_id).isdigit():
        raise ValueError(f"IG media_id must be numeric, got: {media_id!r}")
    params = {
        "fields": "id,text,username,timestamp,like_count",
        "limit": min(int(limit), 100),
    }
    out = _graph_get(f"/{media_id}/comments", params)
    out["_meta"] = {
        "media_id": media_id,
        "fetched": len(out.get("data", [])),
        "endpoint": f"/{media_id}/comments",
    }
    return out


def get_post_insights(media_id: str) -> dict:
    """GET /{media_id}/insights?metric=... — read engagement metrics for one post.

    Returns:
      {
        "data": [{ name, period, values: [{ value, end_time }] }],
        "_meta": { media_id, metrics, fetched }
      }

    Default metrics (per Stage 4 §3): impressions, reach, saved, likes, comments, shares.
    """
    if not meta_credentials_present():
        raise MetaAuthError("Meta credentials not configured")
    if not media_id or not str(media_id).isdigit():
        raise ValueError(f"IG media_id must be numeric, got: {media_id!r}")
    metrics = ["impressions", "reach", "saved", "likes", "comments", "shares"]
    params = {"metric": ",".join(metrics), "period": "lifetime"}
    out = _graph_get(f"/{media_id}/insights", params)
    # Flatten into a dict {metric_name: value} for easy SPA consumption
    flat: dict[str, Any] = {}
    for entry in out.get("data", []):
        name = entry.get("name", "?")
        values = entry.get("data", [])
        if values and isinstance(values, list) and values:
            v = values[0].get("value")
            flat[name] = v
    # Engagement rate = (likes + comments + shares + saved) / reach
    er = None
    try:
        reach = flat.get("reach")
        if reach and reach > 0:
            interactions = sum(filter(None, [
                flat.get("likes"), flat.get("comments"), flat.get("shares"), flat.get("saved"),
            ]))
            er = round((interactions / reach) * 100, 3)
    except Exception:
        er = None
    flat["engagement_rate"] = er
    out["_flat"] = flat
    out["_meta"] = {
        "media_id": media_id,
        "metrics_requested": metrics,
        "fetched": len(out.get("data", [])),
        "endpoint": f"/{media_id}/insights",
    }
    return out


# ── Custom exceptions (surfaced to SPA with explicit status codes) ───────────

class MetaAuthError(Exception):
    """Token missing, expired, or lacks required scopes."""
    def __init__(self, message: str, upstream: Optional[dict] = None):
        super().__init__(message)
        self.upstream = upstream or {}


class MetaUpstreamError(Exception):
    """Other 4xx/5xx from the Graph API."""
    def __init__(self, message: str, upstream: Optional[dict] = None, code: Optional[int] = None):
        super().__init__(message)
        self.upstream = upstream or {}
        self.code = code


class MetaNetworkError(Exception):
    """Connection/timeout/parse failure."""
    pass
