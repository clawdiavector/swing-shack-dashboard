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
      4. Fall back to user token (_read_meta_access_token)
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
    # Fallback: user token. May not work for page endpoints (Meta requires
    # page-scoped token post-2024 for /{page_id}/posts).
    return _read_meta_access_token()


# ── Low-level Graph API caller ────────────────────────────────────────────────

def _graph_get(path: str, params: Optional[dict] = None, timeout: int = 15,
                  use_page_token: bool = False,
                  token_override: Optional[str] = None) -> dict:
    """Make a GET request to the Meta Graph API. Returns parsed JSON.

    Args:
      path: Graph API path (e.g. "/me/accounts", "/{page_id}/posts")
      params: query string parameters
      timeout: request timeout in seconds
      use_page_token: if True, use the page-scoped token (META_PAGE_ACCESS_TOKEN[_FILE])
        instead of the user token. Required for endpoints like /{page_id}/posts
        and /{post_id}/comments which reject user tokens post-2024.
      token_override: explicit token to use. Takes priority over
        env-based resolution. Used by per-brand functions that
        resolve credentials via resolve_credentials_for_brand().

    Resolution order for the bearer token:
      1. token_override (explicit per-call)
      2. use_page_token ? META_PAGE_ACCESS_TOKEN : META_ACCESS_TOKEN
      3. System User token (META_SYSTEM_USER_TOKEN — EAAB)
      4. Page token fallback if use_page_token=True

    Raises:
      MetaAuthError: token missing or 401/403 from upstream
      MetaUpstreamError: other 4xx/5xx from upstream
      MetaNetworkError: connection/timeout failure
    """
    if token_override:
        token = token_override
    elif use_page_token:
        token = _read_meta_page_token()
    else:
        token = _read_meta_access_token()
        if not token:
            # Fallback to system user token (EAAB, never expires)
            sys_tok = _read_system_user_token()
            if sys_tok:
                token = sys_tok
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
        values = entry.get("values", [])
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
    """
    if not os.environ.get("META_APP_ID"):
        return False
    if not _read_meta_access_token():
        return False
    if not os.environ.get("META_PAGE_ID"):
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
    page_id = os.environ.get("META_PAGE_ID", "").strip()
    if not page_id.isdigit():
        raise ValueError(f"META_PAGE_ID must be numeric, got: {page_id!r}")
    default_fields = [
        "id",
        "message",
        "created_time",
        "permalink_url",
        "full_picture",
        "reactions.limit(0).summary(true)",
        "comments.limit(0).summary(true)",
        "shares",
        "status_type",
        "is_published",
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


# ─── PER-BRAND CREDENTIAL RESOLUTION (Phase 1.4 IG ingestion) ──────────────
#
# Per heidi.txt 2026-09-08 architecture rule:
#   Each configured OPERATING brand needs an explicit connection record
#   resolving brand_id → facebook_page_id → instagram_business_account_id
#   → server-side credential. The same shared token may be reused where
#   technically appropriate, but the resolved Page + IG account
#   relationship MUST be explicit per brand.
#
# Operating brands: swing-shack, stick, bag-drop.
# Takomo is NOT an operating brand — it is a product_brand inside stick.

OPERATING_BRANDS = ("swing-shack", "stick", "bag-drop")

INTEGRATIONS_INDEX_PATH = Path(
    os.environ.get("CAMPAIGN_OS_REPO", str(Path(__file__).resolve().parents[2]))
    + "/data/integrations/index.json"
)


def _integrations_root() -> Path:
    """Path to data/integrations/ — per-brand config dir.

    On Railway the writable persistent volume is mounted at DATA_DIR
    (set by the Railway container). The repo copy (REPO_ROOT/data)
    is baked into the image and is read-only. We prefer DATA_DIR
    if it exists so writes survive deploys.
    """
    data_dir = os.environ.get("DATA_DIR", "")
    if data_dir:
        # Check if DATA_DIR exists and is writable
        try:
            p = Path(data_dir) / "integrations"
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            pass
    # Fallback to repo copy
    repo = Path(os.environ.get("CAMPAIGN_OS_REPO",
                                 str(Path(__file__).resolve().parents[2])))
    return repo / "data" / "integrations"


def _read_system_user_token() -> Optional[str]:
    """Read Meta System User token (EAAB) from env. Never expires when used as designed."""
    raw = os.environ.get("META_SYSTEM_USER_TOKEN", "").strip()
    if raw:
        return raw
    # File fallback
    path = os.environ.get("META_SYSTEM_USER_TOKEN_FILE", "").strip()
    if path:
        try:
            data = json.loads(Path(path).read_text())
            tok = data.get("access_token") or data.get("token")
            if tok:
                return str(tok).strip()
        except Exception as e:
            _LOG.warning("could not read META_SYSTEM_USER_TOKEN_FILE=%s: %s", path, e)
    return None


def load_brand_integration(brand_id: str, platform: str = "instagram") -> dict[str, Any]:
    """Load per-brand integration config from data/integrations/<brand>/<platform>.json.

    Returns the raw config dict. The brand may not be configured — caller is
    responsible for checking `configured` flag and missing fields.
    """
    if brand_id not in OPERATING_BRANDS:
        raise ValueError(
            f"brand_id {brand_id!r} is not an operating brand. "
            f"Operating brands: {OPERATING_BRANDS}. "
            "Takomo is a product_brand, not an operating brand."
        )
    cfg_path = _integrations_root() / brand_id / f"{platform}.json"
    if not cfg_path.exists():
        return {"brand_id": brand_id, "platform": platform, "configured": False,
                "notes": "No config file at " + str(cfg_path)}
    try:
        return json.loads(cfg_path.read_text())
    except Exception as e:
        return {"brand_id": brand_id, "platform": platform, "configured": False,
                "notes": f"Config unreadable: {e}"}


def resolve_credentials_for_brand(
    brand_id: str,
    cfg: Optional[dict] = None,
) -> dict[str, Any]:
    """Resolve Meta credentials for a specific operating brand.

    Resolution order:
      1. cfg["credential_env"] env var (per-brand override) — preferred
      2. cfg["credential_env_file"] file — per-brand file override
      3. META_SYSTEM_USER_TOKEN env var — system user fallback
      4. META_ACCESS_TOKEN env var — legacy user token fallback

    Returns dict with:
      - token (str | None) — never logged
      - mode ("system_user_token" | "user_token" | "page_token" | None)
      - source (str | None) — which path the token came from (for diagnostics)
      - errors (list[str]) — non-fatal warnings about partial config
    """
    out: dict[str, Any] = {
        "token": None,
        "mode": None,
        "source": None,
        "errors": [],
    }
    if cfg is None:
        cfg = load_brand_integration(brand_id)
    env_name = cfg.get("credential_env")
    env_file = cfg.get("credential_env_file")

    # 1. Per-brand env
    if env_name:
        tok = os.environ.get(env_name, "").strip()
        if tok:
            out["token"] = tok
            out["mode"] = cfg.get("credential_mode", "system_user_token")
            out["source"] = f"env:{env_name}"
            return out
        out["errors"].append(f"{env_name} not set in env")

    # 2. Per-brand file
    if env_file:
        path = Path(env_file)
        if not path.is_absolute():
            # Relative to repo root
            repo = Path(os.environ.get("CAMPAIGN_OS_REPO", str(Path(__file__).resolve().parents[2])))
            path = repo / env_file
        try:
            data = json.loads(path.read_text())
            tok = data.get("access_token") or data.get("token")
            if tok:
                out["token"] = str(tok).strip()
                out["mode"] = cfg.get("credential_mode", "system_user_token")
                out["source"] = f"file:{path}"
                return out
            out["errors"].append(f"{path} missing access_token")
        except Exception as e:
            out["errors"].append(f"could not read {path}: {e}")

    # 3. System user fallback
    sys_tok = _read_system_user_token()
    if sys_tok:
        out["token"] = sys_tok
        out["mode"] = "system_user_token"
        out["source"] = "env:META_SYSTEM_USER_TOKEN"
        return out

    # 4. Legacy user-token fallback
    user_tok = _read_meta_access_token()
    if user_tok:
        out["token"] = user_tok
        out["mode"] = "user_token"
        out["source"] = "env:META_ACCESS_TOKEN"
        out["errors"].append("Using legacy META_ACCESS_TOKEN — System User token preferred")
        return out

    return out


# ─── PER-BRAND OVERRIDES for the existing domain methods ─────────────────────
# The existing functions (list_recent_posts, get_post_comments, get_post_insights)
# use global env. We add per-brand variants below that the IG ingestion script
# uses. The original functions remain for backwards compatibility.

def list_recent_posts_for_brand(
    brand_id: str,
    limit: int = 25,
    fields: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Per-brand IG media listing. Resolves account_id + token from
    data/integrations/<brand>/instagram.json.

    Returns:
      {
        "data": [...],
        "paging": {...},
        "_meta": {
          brand_id, ig_account_id, credential_mode,
          credential_source, fetched, endpoint,
        }
      }
    """
    if brand_id not in OPERATING_BRANDS:
        raise ValueError(f"{brand_id} is not an operating brand")
    cfg = load_brand_integration(brand_id)
    ig_account_id = cfg.get("ig_business_account_id")
    creds = resolve_credentials_for_brand(brand_id, cfg)
    if not creds["token"]:
        raise MetaAuthError(
            f"No Meta credentials resolved for {brand_id}. "
            f"Errors: {creds['errors']}"
        )
    if not ig_account_id:
        raise MetaAuthError(
            f"No ig_business_account_id configured for {brand_id}. "
            "Add it to data/integrations/<brand>/instagram.json or run a "
            "discovery pass via /me/accounts → /{page_id}?fields=instagram_business_account."
        )
    default_fields = [
        "id", "caption", "media_type", "media_url", "permalink",
        "thumbnail_url", "timestamp", "username", "is_comment_enabled",
    ]
    fields = fields or default_fields
    params = {
        "fields": ",".join(fields),
        "limit": min(int(limit), 100),
    }
    out = _graph_get(f"/{ig_account_id}/media", params,
                      use_page_token=False, token_override=creds["token"])
    out["_meta"] = {
        "brand_id": brand_id,
        "ig_account_id": ig_account_id,
        "credential_mode": creds["mode"],
        "credential_source": creds["source"],
        "fetched": len(out.get("data", [])),
        "endpoint": f"/{ig_account_id}/media",
    }
    return out


def _metrics_for_media_type(media_type: str) -> list[str]:
    """Pick the metrics set Meta accepts for this media product type.

    Per Meta Graph API (2026) — different media types support
    different metric sets. Requesting an unsupported metric fails
    the whole call with error 100.
    """
    mt = (media_type or "").upper()
    if mt in ("IMAGE", "CAROUSEL_ALBUM"):
        # Full set including impressions, follows, profile_*
        return ["impressions", "reach", "saved", "likes", "comments",
                "shares", "total_interactions", "follows",
                "profile_visits", "profile_activity"]
    if mt in ("VIDEO", "REEL", "IG_REEL", "CLIPS"):
        # VIDEO doesn't support impressions/follows/profile_visits/profile_activity
        # via /{media_id}/insights — those are only on /insights/video
        return ["reach", "saved", "likes", "comments", "shares",
                "total_interactions"]
    # Default = safest minimal set
    return ["impressions", "reach", "saved", "likes", "comments",
            "shares", "total_interactions"]


def get_post_insights_for_brand(
    brand_id: str, media_id: str, media_type: str | None = None,
) -> dict[str, Any]:
    """Per-brand IG media insights, media-type-aware.

    For VIDEO/REEL media, impressions / follows / profile_visits /
    profile_activity are NOT supported via /{media_id}/insights —
    they live on /{media_id}/insights?metric=video_views (a
    separate endpoint). We pick the metric set that works for the
    given media_type.
    """
    if brand_id not in OPERATING_BRANDS:
        raise ValueError(f"{brand_id} is not an operating brand")
    if not media_id or not str(media_id).isdigit():
        raise ValueError(f"IG media_id must be numeric, got: {media_id!r}")
    cfg = load_brand_integration(brand_id)
    creds = resolve_credentials_for_brand(brand_id, cfg)
    if not creds["token"]:
        raise MetaAuthError(f"No Meta credentials for {brand_id}")
    metrics = _metrics_for_media_type(media_type or "")
    params = {"metric": ",".join(metrics), "period": "lifetime"}
    out = _graph_get(f"/{media_id}/insights", params,
                      use_page_token=False, token_override=creds["token"])
    flat: dict[str, Any] = {}
    for entry in out.get("data", []):
        name = entry.get("name", "?")
        values = entry.get("values", [])
        if values and isinstance(values, list) and values:
            v = values[0].get("value")
            flat[name] = v
    er = None
    try:
        reach = flat.get("reach") or 0
        if reach and reach > 0:
            interactions = sum(filter(None, [
                flat.get("likes"), flat.get("comments"),
                flat.get("shares"), flat.get("saved"),
            ]))
            er = round((interactions / reach) * 100, 3)
    except Exception:
        er = None
    flat["engagement_rate"] = er
    out["_flat"] = flat
    out["_meta"] = {
        "brand_id": brand_id,
        "media_id": media_id,
        "media_type": media_type,
        "credential_mode": creds["mode"],
        "credential_source": creds["source"],
        "metrics_requested": metrics,
        "fetched": len(out.get("data", [])),
        "endpoint": f"/{media_id}/insights",
    }
    return out


def health_check_for_brand(brand_id: str) -> dict[str, Any]:
    """Run a live API check against the per-brand resolved connection.

    Validates:
      - token works (lightweight /me call)
      - facebook page is reachable
      - IG business account is reachable
      - media endpoint reachable
      - (insights endpoint spot-checked at first media, see caller)

    Returns health dict. NEVER raises — always returns a structured
    status so the Connection Centre can render it without exceptions.
    """
    out: dict[str, Any] = {
        "brand_id": brand_id,
        "platform": "instagram",
        "checks": {},
        "healthy": False,
        "issues": [],
    }
    if brand_id not in OPERATING_BRANDS:
        out["issues"].append(f"{brand_id} is not an operating brand")
        return out
    cfg = load_brand_integration(brand_id)
    out["configured"] = cfg.get("configured", False)
    creds = resolve_credentials_for_brand(brand_id, cfg)
    out["credential_mode"] = creds["mode"]
    out["credential_source"] = creds["source"]
    out["credential_errors"] = creds["errors"]
    if not cfg.get("configured", False):
        out["issues"].append("brand_marked_not_configured")
        return out
    if not creds["token"]:
        out["issues"].append("no_credentials_resolved")
        return out
    # Token liveness — /me endpoint (passing per-brand token)
    try:
        me = _graph_get("/me", {"fields": "id,name"}, token_override=creds["token"])
        out["checks"]["token"] = {"ok": True, "name": me.get("name")}
    except MetaAuthError as e:
        out["checks"]["token"] = {"ok": False, "error": str(e)}
        out["issues"].append("token_invalid_or_missing_scope")
        return out
    except Exception as e:
        out["checks"]["token"] = {"ok": False, "error": str(e)}
        out["issues"].append("token_endpoint_unreachable")
        return out
    # Page reachability
    page_id = cfg.get("facebook_page_id")
    if page_id:
        try:
            _graph_get(f"/{page_id}", {"fields": "id,name"}, token_override=creds["token"])
            out["checks"]["page"] = {"ok": True, "page_id": page_id}
        except Exception as e:
            out["checks"]["page"] = {"ok": False, "page_id": page_id, "error": str(e)}
            out["issues"].append("page_unreachable")
    # IG account reachability
    ig_account_id = cfg.get("ig_business_account_id")
    if ig_account_id:
        try:
            _graph_get(f"/{ig_account_id}", {"fields": "id,username"}, token_override=creds["token"])
            out["checks"]["ig_account"] = {"ok": True, "ig_account_id": ig_account_id}
        except Exception as e:
            out["checks"]["ig_account"] = {"ok": False, "ig_account_id": ig_account_id, "error": str(e)}
            out["issues"].append("ig_account_unreachable")
            return out
        # Media endpoint
        try:
            media = _graph_get(f"/{ig_account_id}/media", {"limit": 1, "fields": "id"}, token_override=creds["token"])
            out["checks"]["media_endpoint"] = {"ok": True, "sample_media_count": len(media.get("data", []))}
        except Exception as e:
            out["checks"]["media_endpoint"] = {"ok": False, "error": str(e)}
            out["issues"].append("media_endpoint_unreachable")
            return out
    else:
        out["issues"].append("ig_business_account_id_not_configured")
        return out
    out["healthy"] = len(out["issues"]) == 0
    return out


def discover_pages_and_ig_account(brand_id: str) -> dict[str, Any]:
    """Discover Facebook Pages + linked IG business accounts available
    to the resolved credential.

    Returns:
      {
        "pages": [
          {"page_id": "...", "page_name": "...", "ig_account_id": "...", "ig_username": "..."},
          ...
        ],
        "credential_mode": "system_user_token" | ...,
        "credential_source": "...",
      }

    This is used ONCE per brand to populate the config. Once
    facebook_page_id + ig_business_account_id are known, the
    ingestion script uses them directly.

    System User tokens can list ALL pages + IG accounts the token has
    access to. This is the canonical way to discover what brands +
    IG accounts a single token can reach.
    """
    if brand_id not in OPERATING_BRANDS:
        raise ValueError(f"{brand_id} is not an operating brand")
    cfg = load_brand_integration(brand_id)
    creds = resolve_credentials_for_brand(brand_id, cfg)
    if not creds["token"]:
        raise MetaAuthError(f"No credentials for {brand_id}")
    # /me/accounts returns all pages the token can act on
    try:
        out = _graph_get("/me/accounts",
                          {"fields": "id,name,instagram_business_account"},
                          use_page_token=False,
                          token_override=creds["token"])
    except Exception as e:
        raise MetaUpstreamError(f"/me/accounts failed: {e}") from e
    pages = []
    for p in out.get("data", []):
        page_id = p.get("id")
        page_name = p.get("name")
        ig = p.get("instagram_business_account") or {}
        ig_id = ig.get("id") if isinstance(ig, dict) else None
        # Get username if we have an IG account
        ig_username = None
        if ig_id:
            try:
                ig_info = _graph_get(f"/{ig_id}", {"fields": "id,username"},
                                      use_page_token=False,
                                      token_override=creds["token"])
                ig_username = ig_info.get("username")
            except Exception:
                pass
        pages.append({
            "page_id": page_id,
            "page_name": page_name,
            "ig_account_id": ig_id,
            "ig_username": ig_username,
        })
    return {
        "pages": pages,
        "credential_mode": creds["mode"],
        "credential_source": creds["source"],
        "fetched": len(pages),
    }
