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
    """True if all of: META_APP_ID, an access token, and an IG business account id are set.

    Env vars take priority; data/meta-tokens.json is the bundled fallback so the
    app works even when Railway env vars are missing and the file was synced via
    data-sync-to-railway.py.
    """
    if not _read_meta_id("META_APP_ID", "app_id"):
        return False
    if not (_read_meta_access_token()):
        return False
    if not _read_meta_id("META_INSTAGRAM_BUSINESS_ACCOUNT_ID", "instagram_account_id"):
        return False
    return True


def _read_meta_access_token() -> Optional[str]:
    """Read Meta access token from (in order):
      1. META_ACCESS_TOKEN_FILE — JSON file with {"access_token": "..."}
      2. data/meta-tokens.json — bundled credentials fallback (same shape)
      3. META_ACCESS_TOKEN — raw env value
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
    # Bundled fallback: data/meta-tokens.json — same shape as the *_FILE pattern.
    # Production should still set META_ACCESS_TOKEN (or *_FILE pointing at the
    # same file) but this lets local-dev + Railway-without-env-vars work when
    # the file is force-added to the repo or synced via data-sync-to-railway.py.
    for bundled in ("data/meta-tokens.json",
                    os.path.join(os.environ.get("DATA_DIR", ""), "meta-tokens.json")):
        if not bundled:
            continue
        try:
            with open(bundled) as f:
                data = json.load(f)
            tok = data.get("access_token") or data.get("token")
            if tok:
                return str(tok).strip()
        except FileNotFoundError:
            continue
        except Exception as e:
            _LOG.warning("could not read bundled %s: %s", bundled, e)
    raw = os.environ.get("META_ACCESS_TOKEN")
    if raw and raw.strip():
        return raw.strip()
    return None


def _read_meta_page_token() -> Optional[str]:
    """Read Meta Page-scoped access token (preferred for FB-page endpoints).

    The page-scoped token inherits Page-level scopes (pages_show_list,
    pages_read_engagement, pages_read_user_content, read_insights) and works
    with /{page_id}/posts, /{post_id}/comments, /{post_id}/insights, etc.

    Falls back to the user token if a page-scoped one isn't saved. Note that
    the user token may NOT be accepted by page endpoints (returns
    "Page access token required" error code 190 subcode 2069032), so this
    fallback is best-effort.

    Sources checked in order:
      1. META_PAGE_ACCESS_TOKEN_FILE — JSON file with {"access_token": "..."}
      2. META_PAGE_ACCESS_TOKEN — raw env value
      3. META_PAGE_TOKEN_FILE — alias
      4. data/meta-tokens.json — bundled fallback (same shape; falls back to
         bundled user token if no page_token field)
      5. Fall back to user token (_read_meta_access_token)
    """
    for env_key in ("META_PAGE_ACCESS_TOKEN_FILE", "META_PAGE_TOKEN_FILE"):
        path = os.environ.get(env_key)
        if path:
            try:
                with open(path) as f:
                    data = json.load(f)
                tok = data.get("access_token") or data.get("token")
                if tok:
                    return str(tok).strip()
            except Exception as e:
                _LOG.warning("could not read %s=%s: %s", env_key, path, e)
    for env_key in ("META_PAGE_ACCESS_TOKEN", "META_PAGE_TOKEN"):
        raw = os.environ.get(env_key)
        if raw and raw.strip():
            return raw.strip()
    # Bundled fallback — same pattern as user token. If the bundled file has
    # an explicit page_token field use that; otherwise fall through to user token.
    for bundled in ("data/meta-tokens.json",
                    os.path.join(os.environ.get("DATA_DIR", ""), "meta-tokens.json")):
        if not bundled:
            continue
        try:
            with open(bundled) as f:
                data = json.load(f)
            tok = data.get("page_access_token") or data.get("page_token")
            if tok:
                return str(tok).strip()
        except FileNotFoundError:
            continue
        except Exception as e:
            _LOG.warning("could not read bundled %s: %s", bundled, e)
    # Fallback: user token. May not work for page endpoints (Meta requires
    # page-scoped token post-2024 for /{page_id}/posts).
    return _read_meta_access_token()


def _read_meta_id(env_key: str, bundled_key: str) -> Optional[str]:
    """Resolve a Meta ID (page_id, ig_account_id, app_id) from env + bundled fallback.

    Env wins. Falls back to data/meta-tokens.json[bundled_key]. Returns None if not set.
    """
    raw = os.environ.get(env_key)
    if raw and raw.strip():
        return raw.strip()
    for bundled in ("data/meta-tokens.json",
                    os.path.join(os.environ.get("DATA_DIR", ""), "meta-tokens.json")):
        if not bundled:
            continue
        try:
            with open(bundled) as f:
                data = json.load(f)
            val = data.get(bundled_key)
            if val:
                return str(val).strip()
        except FileNotFoundError:
            continue
        except Exception as e:
            _LOG.warning("could not read bundled %s: %s", bundled, e)
    return None


# ── Low-level Graph API caller ────────────────────────────────────────────────

def _graph_get(path: str, params: Optional[dict] = None, timeout: int = 15, use_page_token: bool = False) -> dict:
    """Make a GET request to the Meta Graph API. Returns parsed JSON.

    Args:
      path: Graph API path (e.g. "/me/accounts", "/{page_id}/posts")
      params: query string parameters
      timeout: request timeout in seconds
      use_page_token: if True, use the page-scoped token (META_PAGE_ACCESS_TOKEN[_FILE])
        instead of the user token. Required for endpoints like /{page_id}/posts
        and /{post_id}/comments which reject user tokens post-2024.

    Raises:
      MetaAuthError: token missing or 401/403 from upstream
      MetaUpstreamError: other 4xx/5xx from upstream
      MetaNetworkError: connection/timeout failure
    """
    if use_page_token:
        token = _read_meta_page_token()
    else:
        token = _read_meta_access_token()
    if not token:
        if use_page_token:
            raise MetaAuthError("META_PAGE_ACCESS_TOKEN (or _FILE) not configured — and user token fallback also missing")
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
        raise MetaAuthError("Meta credentials not configured - set META_APP_ID, META_ACCESS_TOKEN[_FILE], META_INSTAGRAM_BUSINESS_ACCOUNT_ID")
    ig_account_id = _read_meta_id("META_INSTAGRAM_BUSINESS_ACCOUNT_ID", "instagram_account_id") or ""
    if not ig_account_id.isdigit():
        raise ValueError(f"META_INSTAGRAM_BUSINESS_ACCOUNT_ID must be numeric, got: {ig_account_id!r}")
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


# ── Facebook Page-side equivalents (work with the 5 currently-approved scopes) ──
#
# Why these exist separately: the IG-side functions above need `instagram_basic`,
# `instagram_manage_insights`, and `pages_read_user_content` (App Review pending).
# The FB-page functions below only need `pages_show_list`, `pages_read_engagement`,
# `pages_read_user_content`, `read_insights`, `business_management` — all already
# granted. They expose Swing Shack's Facebook Page posts, post insights, and
# post comments so the dashboard has live data while App Review is pending.
#
# Once IG scopes are approved, both function families coexist — the SPA can
# render IG and FB data side-by-side from a single dashboard view.

def _page_credentials_present() -> bool:
    """True if META_APP_ID + token + META_PAGE_ID are set.

    Unlike meta_credentials_present(), this does NOT require an IG business
    account id — the FB-page endpoints work with just the page id.

    Env vars take priority; data/meta-tokens.json is the bundled fallback.
    """
    if not _read_meta_id("META_APP_ID", "app_id"):
        return False
    if not _read_meta_access_token():
        return False
    if not _read_meta_id("META_PAGE_ID", "page_id"):
        return False
    return True


def list_page_posts(limit: int = 25, fields: Optional[list[str]] = None) -> dict:
    """GET /{page_id}/posts — list recent Facebook Page posts.

    Requires scope: pages_read_engagement, pages_show_list.

    Returns:
      {
        "data": [{ id, message, created_time, permalink_url,
                   reactions.summary, comments.summary, shares, ... }],
        "paging": { cursors, next },
        "_meta": { page_id, fetched, endpoint }
      }
    """
    if not _page_credentials_present():
        raise MetaAuthError(
            "FB-page credentials not configured — set META_APP_ID, META_PAGE_ID, "
            "META_ACCESS_TOKEN[_FILE]"
        )
    page_id = _read_meta_id("META_PAGE_ID", "page_id") or ""
    if not page_id.isdigit():
        raise ValueError(f"META_PAGE_ID must be numeric, got: {page_id!r}")
    default_fields = [
        "id",
        "message",
        "created_time",
        "permalink_url",
        "shares",  # safe - no extra scope needed
    ]
    fields = fields or default_fields
    params = {
        "fields": ",".join(fields),
        "limit": min(int(limit), 100),
    }
    out = _graph_get(f"/{page_id}/posts", params, use_page_token=True)
    out["_meta"] = {
        "page_id": page_id,
        "fetched": len(out.get("data", [])),
        "endpoint": f"/{page_id}/posts",
        "source": "facebook_page",
    }
    return out


def get_page_post_insights(post_id: str) -> dict:
    """GET /{post_id}/insights?metric=... — engagement metrics for one FB post.

    Requires scope: read_insights, pages_read_engagement.

    Returns:
      {
        "_flat": { impressions, reach, engaged_users, reactions_by_type_total,
                   post_clicks, ... },
        "data": [ raw upstream per-metric blocks ],
        "_meta": { post_id, metrics_requested, fetched, endpoint, source }
      }
    """
    if not _page_credentials_present():
        raise MetaAuthError("FB-page credentials not configured")
    if not post_id or not str(post_id).isdigit():
        raise ValueError(f"FB post_id must be numeric, got: {post_id!r}")
    # Standard post-level insight metrics available to pages with read_insights.
    # Note: not all metrics are valid for every post type (e.g. video has video_views).
    metrics = [
        "post_impressions",
        "post_impressions_unique",   # = reach
        "post_engaged_users",
        "post_reactions_by_type_total",
    ]
    params = {"metric": ",".join(metrics)}
    try:
        out = _graph_get(f"/{post_id}/insights", params, use_page_token=True)
    except MetaUpstreamError as e:
        # Some posts (e.g. shared posts, events) don't support insights — fall
        # back to a minimal metric set so the dashboard still has something.
        if e.code in (100, 400):
            fallback_metrics = ["post_impressions", "post_impressions_unique", "post_engaged_users"]
            params = {"metric": ",".join(fallback_metrics)}
            out = _graph_get(f"/{post_id}/insights", params, use_page_token=True)
            out["_meta"] = {
                "post_id": post_id,
                "metrics_requested": fallback_metrics,
                "fetched": len(out.get("data", [])),
                "endpoint": f"/{post_id}/insights",
                "source": "facebook_page",
                "fallback_used": True,
                "fallback_reason": str(e),
            }
            return _flatten_page_insights(out)
        raise
    # Flatten into a dict for easy SPA consumption
    out = _flatten_page_insights(out)
    out["_meta"] = {
        "post_id": post_id,
        "metrics_requested": metrics,
        "fetched": len(out.get("data", [])),
        "endpoint": f"/{post_id}/insights",
        "source": "facebook_page",
    }
    return out


def _flatten_page_insights(out: dict) -> dict:
    """Flatten /{post_id}/insights response into _flat + computed engagement_rate."""
    flat: dict[str, Any] = {}
    for entry in out.get("data", []):
        name = entry.get("name", "?")
        values = entry.get("values", [])
        if values and isinstance(values, list) and values:
            v = values[0].get("value")
            flat[name] = v
    # Compute engagement rate = engaged_users / reach
    er = None
    try:
        reach = flat.get("post_impressions_unique") or flat.get("reach")
        engaged = flat.get("post_engaged_users")
        if reach and engaged is not None and reach > 0:
            er = round((engaged / reach) * 100, 3)
    except Exception:
        er = None
    flat["engagement_rate"] = er
    # Friendly aliases so SPA code is uniform across IG + FB
    flat["impressions"] = flat.get("post_impressions")
    flat["reach"] = flat.get("post_impressions_unique")
    flat["engaged_users"] = flat.get("post_engaged_users")
    out["_flat"] = flat
    return out


def get_page_post_comments(post_id: str, limit: int = 50) -> dict:
    """GET /{post_id}/comments — comments on a single Facebook Page post.

    Requires scope: pages_read_user_content.

    Returns:
      {
        "data": [{ id, message, from{id,name}, created_time, like_count, ... }],
        "paging": { cursors, next },
        "_meta": { post_id, fetched, endpoint, source }
      }
    """
    if not _page_credentials_present():
        raise MetaAuthError("FB-page credentials not configured")
    if not post_id or not str(post_id).isdigit():
        raise ValueError(f"FB post_id must be numeric, got: {post_id!r}")
    params = {
        "fields": "id,message,from{id,name},created_time,like_count,comment_count,permalink_url",
        "limit": min(int(limit), 100),
    }
    out = _graph_get(f"/{post_id}/comments", params, use_page_token=True)
    out["_meta"] = {
        "post_id": post_id,
        "fetched": len(out.get("data", [])),
        "endpoint": f"/{post_id}/comments",
        "source": "facebook_page",
    }
    return out


def get_page_info(fields: Optional[list[str]] = None) -> dict:
    """GET /{page_id} — read the Page's own metadata.

    Requires scope: pages_show_list, pages_read_engagement.

    Returns flat dict with: id, name, fan_count, followers_count, link, picture, etc.
    Useful for the weekly report's "Facebook page fans / followers" headline numbers.
    """
    if not _page_credentials_present():
        raise MetaAuthError(
            "FB-page credentials not configured - set META_APP_ID, META_PAGE_ID, META_ACCESS_TOKEN[_FILE]"
        )
    page_id = _read_meta_id("META_PAGE_ID", "page_id") or ""
    if not page_id.isdigit():
        raise ValueError(f"META_PAGE_ID must be numeric, got: {page_id!r}")
    default_fields = [
        "id",
        "name",
        "username",
        "fan_count",          # people who liked the page
        "followers_count",    # people who follow (different metric since 2024)
        "link",
        "picture.type(large)",
        "about",
        "category",
        "verification_status",
        "website",
    ]
    params = {
        "fields": ",".join(fields or default_fields),
    }
    out = _graph_get(f"/{page_id}", params, use_page_token=True)
    out["_meta"] = {
        "page_id": page_id,
        "fetched": len([k for k in out.keys() if not k.startswith("_")]),
        "endpoint": f"/{page_id}",
        "source": "facebook_page",
    }
    return out


def get_page_insights(metrics: Optional[list[str]] = None, period: str = "days_28") -> dict:
    """GET /{page_id}/insights?metric=...&period=days_28 - read page-level metrics.

    Requires scope: read_insights, pages_read_engagement.

    Default metrics (the standard 28-day view):
      - page_views_total: total page views
      - page_impressions: number of times the page was shown (unique + repeat)
      - page_impressions_unique: unique people who saw the page (= reach)
      - page_engaged_users: unique people who engaged (any action)
      - page_post_engagements: total post engagements

    Other useful metrics (valid for days_28 / week / day):
      - page_fan_adds_unique, page_fan_removes_unique
      - page_fans_gender_age
      - page_tab_views_login, page_tab_views_logout
      - page_actions_post_reactions_total

    Returns:
      {
        "_flat": {metric_name: value},
        "data": [raw upstream per-metric blocks],
        "_meta": {page_id, metrics, period, source}
      }
    """
    if not _page_credentials_present():
        raise MetaAuthError(
            "FB-page credentials not configured - set META_APP_ID, META_PAGE_ID, META_ACCESS_TOKEN[_FILE]"
        )
    page_id = _read_meta_id("META_PAGE_ID", "page_id") or ""
    if not page_id.isdigit():
        raise ValueError(f"META_PAGE_ID must be numeric, got: {page_id!r}")
    default_metrics = [
        # Only request metrics we know this page+app can read. If a metric is
        # not in the page's whitelist, Meta returns 400 and the WHOLE call
        # fails - so we call each metric individually below and skip failures.
        "page_views_total",
        "page_post_engagements",
        "page_actions_post_reactions_total",
        "page_actions_post_reactions_like_total",
        "page_fan_adds",
        "page_fan_removes",
    ]
    metrics_to_try = metrics or default_metrics
    flat: dict[str, Any] = {}
    per_metric_errors: dict[str, str] = {}
    for metric in metrics_to_try:
        params = {"metric": metric, "period": period}
        try:
            single = _graph_get(f"/{page_id}/insights", params, use_page_token=True)
            for entry in single.get("data", []):
                name = entry.get("name", "?")
                values = entry.get("values", [])
                if values and isinstance(values, list) and values:
                    v = values[0].get("value")
                    if not isinstance(v, (dict, list)):
                        flat[name] = v
        except MetaAuthError:
            raise  # propagate auth errors - token issues are not recoverable per-metric
        except (MetaUpstreamError, MetaNetworkError) as e:
            # Skip this metric - likely "value must be a valid insights metric"
            # (Meta app review not approved for this metric on this page)
            per_metric_errors[metric] = str(e)[:100]
    out = {"data": [{"name": k, "values": [{"value": v}]} for k, v in flat.items()]}
    out["_flat"] = flat
    out["_meta"] = {
        "page_id": page_id,
        "metrics": metrics_to_try,
        "metrics_returned": list(flat.keys()),
        "metrics_blocked": per_metric_errors,
        "period": period,
        "fetched": len(flat),
        "source": "facebook_page",
    }
    return out
