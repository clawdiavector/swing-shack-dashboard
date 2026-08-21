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
      1. META_SYSTEM_USER_TOKEN — server-side CAPI / Admin System User token
         (never expires, full CRUD on page/ad-account/catalogue).
      2. META_ACCESS_TOKEN_FILE — JSON file with {"access_token": "..."}
      3. data/meta-tokens.json — bundled credentials fallback (same shape)
      4. META_ACCESS_TOKEN — raw env value
    Returns None if not configured.
    """
    # META_SYSTEM_USER_TOKEN is the preferred source — it never expires and
    # has full CAPI/admin scope (the secret-drop slot for the system user).
    sys_user = os.environ.get("META_SYSTEM_USER_TOKEN")
    if sys_user and sys_user.strip():
        return sys_user.strip()
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
    # META_SYSTEM_USER_TOKEN wins — system user tokens have admin scope
    # on the page, work for /{page_id}/insights + /posts + per-post endpoints.
    sys_user = os.environ.get("META_SYSTEM_USER_TOKEN")
    if sys_user and sys_user.strip():
        return sys_user.strip()
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


# Default IDs for swing-shack fallback when neither env nor bundle is set.
# Mirrors meta_live_fetch.py's META_PAGE_ID / META_INSTAGRAM_BUSINESS_ACCOUNT_ID defaults.
_META_DEFAULT_IDS = {
    "META_PAGE_ID": "198859063301219",
    "META_INSTAGRAM_BUSINESS_ACCOUNT_ID": "17841456713897671",
    "META_APP_ID": "1187824310088903",
}


def _read_meta_id(env_key: str, bundled_key: str) -> Optional[str]:
    """Resolve a Meta ID (page_id, ig_account_id, app_id) from:
      1. env vars (preferred)
      2. data/meta-tokens.json (bundled credentials)
      3. hardcoded fallback for swing-shack (matches meta_live_fetch.py)
    Returns None if not set.
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
    # Ultimate fallback for swing-shack brand
    default = _META_DEFAULT_IDS.get(env_key)
    if default:
        return default
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
        # Use the cached page-scoped token (exchanged from user/system)
        # when the request path mentions a numeric page id.
        # path like "/198859063301219/insights" → "198859063301219"
        import re as _re_page
        m = _re_page.match(r"^/(\d+)/", path)
        if m:
            requested_page = m.group(1)
            token = _PAGE_TOKEN_CACHE.get(requested_page) or _read_meta_page_token()
        else:
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
    """True if a Page-scoped workflow has the bits it needs.

    Returns True if EITHER:
      - META_APP_ID + token + META_PAGE_ID are all set (legacy user token)
      - META_SYSTEM_USER_TOKEN + META_PAGE_ID are set (server-side CAPI
        system user — no META_APP_ID needed because the token is bound
        to a specific app at generation time)

    Env vars take priority; data/meta-tokens.json is the bundled fallback.
    """
    tok = _read_meta_access_token()
    if not tok:
        return False
    if not _read_meta_id("META_PAGE_ID", "page_id"):
        return False
    # CAPI System User tokens don't need META_APP_ID — just the token + page id.
    if os.environ.get("META_SYSTEM_USER_TOKEN"):
        return True
    # Legacy user-token path still requires META_APP_ID.
    if not _read_meta_id("META_APP_ID", "app_id"):
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
    # Pre-mint a page-scoped token if we don't have one yet. Meta's
    # /{page_id}/insights endpoint requires a Page Access Token (admin
    # scope alone — even CAPI — returns #190). The exchange:
    #   GET /{page_id}?fields=access_token → returns a page-scoped token.
    if page_id not in _PAGE_TOKEN_CACHE:
        try:
            user_tok = _read_meta_access_token()
            exchange_url = (f"{GRAPH_API_BASE}/{page_id}"
                            f"?fields=access_token&access_token={user_tok}")
            req = Request(exchange_url)
            with urlopen(req, timeout=10) as r:
                ex_body = json.loads(r.read().decode())
            page_tok = ex_body.get("access_token")
            if page_tok:
                _PAGE_TOKEN_CACHE[page_id] = page_tok
                _LOG.info("minted page-scoped token for page_id=%s (len=%d)", page_id, len(page_tok))
        except Exception as e:
            _LOG.warning("could not exchange to page token (will try direct): %s", e)
    # Exchange code is now ONLY at the top of get_page_insights (line 460+)
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
        # The weekly report collector reads these names directly:
        #   page_views_total → fb_views
        #   page_post_engagements → fb_post_engagements
        #   page_impressions_unique → fb_reach
        #   page_impressions → fb_impressions
        #   page_engaged_users → fb_engaged_users
        # Some are rejected by Meta (#100 invalid metric) for specific
        # pages even with full scope — get_page_insights() already
        # handles per-metric failures, so we just attempt all.
        "page_views_total",
        "page_post_engagements",
        "page_impressions_unique",
        "page_impressions",
        "page_engaged_users",
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



# ── Stories fetchers (IG + FB page) ─────────────────────────────────────────
#
# Why these exist: the weekly report had `ig_stories` and `fb_stories` rendering
# rows but no fetcher populated them, so they always read "0 (flat)" - silent
# zeros. Christelle called this out on 2026-08-14: "Report says swing shack
# stories 0 is a lie there are currently 2 stories. Stories go up every day."
#
# Both endpoints work with the page-scoped token we already have. IG stories
# returns reach/follows via the inline insights field; FB page stories is a
# separate endpoint that returns an empty list for Swing Shack (they don't
# post to the FB Page story surface), but we still query it so the report
# can honestly report "0" instead of fabricating.


def get_ig_stories(limit: int = 50, with_insights: bool = True) -> dict:
    """GET /{ig_account_id}/stories - list recent Instagram stories.

    Requires scope: instagram_basic, instagram_manage_insights (the latter for
    per-story reach/follows via the inline `insights.metric(...)` field).

    Returns:
      {
        "data": [{ id, media_type, timestamp, permalink, reach?, follows?,
                   total_interactions? }],
        "paging": {...},
        "_meta": { ig_account_id, fetched, endpoint, source, has_insights }
      }

    Stories older than 24h disappear from this endpoint automatically (Meta
    expires them). For a 28d window we may want a separate archival strategy,
    but for the weekly report this is fine.
    """
    if not meta_credentials_present():
        raise MetaAuthError(
            "Meta credentials not configured - set META_APP_ID, "
            "META_INSTAGRAM_BUSINESS_ACCOUNT_ID, META_ACCESS_TOKEN[_FILE]"
        )
    ig_account_id = _read_meta_id("META_INSTAGRAM_BUSINESS_ACCOUNT_ID", "instagram_account_id") or ""
    if not ig_account_id.isdigit():
        raise ValueError(f"META_INSTAGRAM_BUSINESS_ACCOUNT_ID must be numeric, got: {ig_account_id!r}")
    fields = ["id", "media_type", "timestamp", "permalink"]
    if with_insights:
        # `reach` works without extra App Review; the other metrics were
        # validated separately on 2026-08-14 (replies, shares, follows,
        # total_interactions, saved). We request reach + follows + total_interactions
        # because those three tell us whether the story actually drove action.
        fields.append("insights.metric(reach,follows,total_interactions)")
    params = {
        "fields": ",".join(fields),
        "limit": min(int(limit), 100),
    }
    out = _graph_get(f"/{ig_account_id}/stories", params)
    # Flatten insights into the story object so downstream code is uniform.
    for story in out.get("data", []):
        ins_obj = story.pop("insights", None)
        ins = ins_obj.get("data", []) if isinstance(ins_obj, dict) else []
        for m in ins:
            vals = m.get("values", [])
            if vals:
                story[m["name"]] = vals[0].get("value", 0)
    out["_meta"] = {
        "ig_account_id": ig_account_id,
        "fetched": len(out.get("data", [])),
        "endpoint": f"/{ig_account_id}/stories",
        "source": "instagram_stories",
        "has_insights": with_insights,
    }
    return out


def get_page_stories(limit: int = 25) -> dict:
    """GET /{page_id}/stories - list recent Facebook Page stories.

    Swing Shack does not currently post stories on their FB Page surface,
    but we still query it so the weekly report can honestly render "0" instead
    of silent fabricated zeros. The endpoint works with the page-scoped token
    and only requires pages_show_list.

    Returns:
      {
        "data": [{ id, created_time }],
        "_meta": { page_id, fetched, endpoint, source }
      }
    """
    if not _page_credentials_present():
        raise MetaAuthError(
            "FB-page credentials not configured - set META_APP_ID, META_PAGE_ID, "
            "META_ACCESS_TOKEN[_FILE]"
        )
    page_id = _read_meta_id("META_PAGE_ID", "page_id") or ""
    if not page_id.isdigit():
        raise ValueError(f"META_PAGE_ID must be numeric, got: {page_id!r}")
    params = {"limit": min(int(limit), 100)}
    try:
        out = _graph_get(f"/{page_id}/stories", params, use_page_token=True)
    except (MetaUpstreamError, MetaNetworkError) as e:
        # Some pages do not expose the /stories endpoint at all. Return empty
        # so the report still renders rather than crashing the whole render.
        return {
            "data": [],
            "_meta": {
                "page_id": page_id,
                "fetched": 0,
                "endpoint": f"/{page_id}/stories",
                "source": "facebook_page_stories",
                "error": str(e)[:200],
            },
        }
    out["_meta"] = {
        "page_id": page_id,
        "fetched": len(out.get("data", [])),
        "endpoint": f"/{page_id}/stories",
        "source": "facebook_page_stories",
    }
    # Normalise FB page story fields. The /{page_id}/stories endpoint returns
    # a different shape than IG /stories: fields are post_id, status,
    # creation_time (Unix epoch seconds), media_type, url, media_id. Rename
    # them so the downstream summary code is uniform.
    import datetime as _dt
    for s in out.get("data", []):
        if s.get("post_id") and not s.get("id"):
            s["id"] = s["post_id"]
        if s.get("creation_time") is not None and not s.get("created_time"):
            try:
                s["created_time"] = (
                    _dt.datetime.fromtimestamp(int(s["creation_time"]), _dt.timezone.utc)
                    .isoformat()
                )
            except Exception:
                s["created_time"] = None
    return out


def summarize_stories() -> dict:
    """Combined IG + FB page stories summary for the weekly report.

    Cross-references both data streams so we do not double-count if the same
    story shows up in both surfaces (rare in practice - IG and FB stories are
    separate objects - but worth checking).

    Returns a dict with IG and FB summaries, a combined count, and reach totals.
    """
    import datetime as _dt  # used for normalising FB page creation_time (Unix epoch)
    out: dict = {
        "ig_stories": {
            "count": 0, "reach_total": 0, "follows_total": 0,
            "total_interactions_total": 0, "oldest": None, "newest": None,
            "items": [],
        },
        "fb_page_stories": {
            "count": 0, "oldest": None, "newest": None, "items": [],
        },
        "combined_count": 0,
        "combined_reach": 0,
        "data_sources": [],
        "window_label": "active (last 24h - Meta expires stories automatically)",
        "truth_note": (
            "Stories are only queryable while live (≤24h after posting). "
            "This summary reflects only currently-live stories. For an archival "
            "view we would need a separate daily snapshot fetch."
        ),
    }

    # IG stories
    try:
        ig = get_ig_stories(limit=50, with_insights=True)
        stories = ig.get("data", [])
        out["data_sources"].append("instagram_stories")
        items = []
        reach_total = 0
        follows_total = 0
        interactions_total = 0
        timestamps = []
        for s in stories:
            ts = s.get("timestamp")
            timestamps.append(ts)
            reach = s.get("reach", 0) or 0
            follows = s.get("follows", 0) or 0
            interactions = s.get("total_interactions", 0) or 0
            reach_total += int(reach)
            follows_total += int(follows)
            interactions_total += int(interactions)
            items.append({
                "id": s.get("id"),
                "media_type": s.get("media_type"),
                "timestamp": ts,
                "permalink": s.get("permalink"),
                "reach": int(reach),
                "follows": int(follows),
                "total_interactions": int(interactions),
            })
        out["ig_stories"] = {
            "count": len(stories),
            "reach_total": reach_total,
            "follows_total": follows_total,
            "total_interactions_total": interactions_total,
            "oldest": min(timestamps) if timestamps else None,
            "newest": max(timestamps) if timestamps else None,
            "items": items,
        }
    except Exception as e:
        out["ig_stories"]["error"] = str(e)[:200]

    # FB page stories
    try:
        fb = get_page_stories(limit=25)
        stories = fb.get("data", [])
        out["data_sources"].append("facebook_page_stories")
        timestamps = []
        normalised_items = []
        for s in stories:
            # Defensive normalisation - in case the upstream payload bypassed
            # get_page_stories() (e.g. tests, or future code that calls the
            # Graph API directly). Without this, the de-dup in combined_count
            # misses cross-posted stories because `id` stays None while the
            # IG side has the same numeric id.
            if not s.get("id") and s.get("post_id"):
                s["id"] = s["post_id"]
            if s.get("created_time") is None and s.get("creation_time") is not None:
                try:
                    s["created_time"] = (
                        _dt.datetime.fromtimestamp(int(s["creation_time"]), _dt.timezone.utc)
                        .isoformat()
                    )
                except Exception:
                    s["created_time"] = None
            if s.get("created_time"):
                timestamps.append(s["created_time"])
            normalised_items.append({
                "id": s.get("id"),
                "created_time": s.get("created_time"),
            })
        out["fb_page_stories"] = {
            "count": len(stories),
            "oldest": min(timestamps) if timestamps else None,
            "newest": max(timestamps) if timestamps else None,
            "items": normalised_items,
        }
    except Exception as e:
        out["fb_page_stories"]["error"] = str(e)[:200]

    # Combined (de-duped by id)
    ig_ids = {s["id"] for s in out["ig_stories"]["items"]}
    fb_ids = {s["id"] for s in out["fb_page_stories"]["items"]}
    overlap = ig_ids & fb_ids
    out["combined_count"] = len(ig_ids | fb_ids)
    out["combined_reach"] = out["ig_stories"]["reach_total"]
    out["overlap_ids"] = sorted(overlap)
    return out
