#!/usr/bin/env python3
"""
fetch_facebook_page.py — live Facebook Page posts + per-post insights for Swing Shack.

Why this exists
---------------
The IG Business fetcher pulls reach + engagement from instagram_business_manage_insights.
Same story for FB Page: get the page's recent posts + per-post reactions + clicks.

Page-level metrics (page_impressions etc.) are NOT available on small pages
(verified 2026-08-26: fan_count=450, page-level /insights returns
"The value must be a valid insights metric"). But PER-POST metrics work:
  - post_clicks
  - post_reactions_by_type_total
  - post_reactions_like_total
  - post_reactions_love_total
  - post_reactions_wow_total
  - post_reactions_haha_total
  - post_reactions_sorry_total
  - post_reactions_anger_total

These together give a real picture of how FB content performs.

Outputs
-------
  data/fb-page-analytics.json   -- page info + per-post metrics

Environment
-----------
  META_SYSTEM_USER_TOKEN    (preferred; Server-to-Server System User token)
  DATA_DIR                  (where the output file goes)

Exit codes
----------
  0 -- success
  1 -- generic failure
  2 -- no token configured
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ── Setup ────────────────────────────────────────────────────────────
_LOG = logging.getLogger("fetch_facebook_page")
if not _LOG.handlers:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("[%(asctime)s SAST] %(message)s",
                                    datefmt="%Y-%m-%d %H:%M:%S"))
    _LOG.addHandler(h)
    _LOG.setLevel(logging.INFO)

DEFAULT_GRAPH_VERSION = "v21.0"
DEFAULT_WINDOW_DAYS = 30
DEFAULT_MEDIA_LIMIT = 25
HTTP_TIMEOUT = 30

# ── Paths ─────────────────────────────────────────────────────────────
_env_data = (
    os.environ.get("DATA_DIR")
    or os.environ.get("SWING_SHACK_DATA_DIR")
)
if _env_data:
    DATA_DIR = Path(_env_data)
else:
    DATA_DIR = Path(__file__).resolve().parent.parent / "data"

DEFAULT_PAGE_ID = "198859063301219"  # Swing Shack (Driving range)
DEFAULT_BRAND = "swing-shack"

# Per-post metrics that work for small pages (verified 2026-08-26).
# Page-level totals require fan_count > some threshold; per-post reactions always work.
POST_METRICS = (
    "post_clicks",
    "post_reactions_by_type_total",
    "post_reactions_like_total",
    "post_reactions_love_total",
    "post_reactions_wow_total",
    "post_reactions_haha_total",
    "post_reactions_sorry_total",
    "post_reactions_anger_total",
)


# ── Token ────────────────────────────────────────────────────────────
def _resolve_token() -> str | None:
    """Get the System User token. Exits with code 2 if missing."""
    tok = os.environ.get("META_SYSTEM_USER_TOKEN", "").strip()
    if tok:
        return tok
    tok = os.environ.get("META_ACCESS_TOKEN", "").strip()
    if tok:
        return tok
    return None


def _gv() -> str:
    return os.environ.get("GRAPH_API_VERSION", DEFAULT_GRAPH_VERSION)


# ── HTTP ─────────────────────────────────────────────────────────────
def _http_get_json(url: str, params: dict | None = None, retries: int = 3) -> dict:
    """GET with retries + exponential backoff."""
    full = f"{url}?{urlencode(params or {})}"
    last_err = None
    for attempt in range(retries):
        try:
            req = Request(full, headers={"Accept": "application/json"})
            with urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(body)
            except Exception:
                pass
            if e.code == 400 or e.code == 401:
                # Permission/format error — don't retry
                return {"error": body, "_status": e.code}
            last_err = body
            time.sleep(2 ** attempt)
        except (URLError, TimeoutError) as e:
            last_err = str(e)
            time.sleep(2 ** attempt)
    return {"error": last_err or "max retries", "_status": None}


# ── Page helpers ─────────────────────────────────────────────────────
def _get_page_token(user_token: str, page_id: str) -> str | None:
    """Mint a page-scoped token from the System User token."""
    # If the token is already System User, it can access pages directly.
    # But page-level endpoints need a page-scoped token, so we still mint one.
    url = f"https://graph.facebook.com/{_gv()}/me/accounts"
    resp = _http_get_json(url, {"fields": "id,access_token", "access_token": user_token})
    if isinstance(resp, dict):
        for entry in resp.get("data", []) or []:
            if str(entry.get("id")) == str(page_id):
                return entry.get("access_token")
        # Fallback: first page
        data = resp.get("data", [])
        if data:
            return data[0].get("access_token")
    return None


def _get_page_info(page_token: str, page_id: str) -> dict:
    """GET /{page_id}?fields=id,name,fan_count,category,about"""
    url = f"https://graph.facebook.com/{_gv()}/{page_id}"
    return _http_get_json(url, {
        "fields": "id,name,fan_count,category,about,link,picture",
        "access_token": page_token,
    })


def _list_page_posts(page_token: str, page_id: str, limit: int) -> list[dict]:
    """GET /{page_id}/posts?fields=id,message,created_time,permalink_url..."""
    url = f"https://graph.facebook.com/{_gv()}/{page_id}/posts"
    resp = _http_get_json(url, {
        "fields": "id,message,created_time,permalink_url,full_picture,shares,status_type",
        "limit": str(limit),
        "access_token": page_token,
    })
    if isinstance(resp, dict):
        return resp.get("data", []) or []
    return []


def _get_post_insights(page_token: str, post_id: str, metrics: tuple[str, ...] = POST_METRICS) -> dict:
    """GET /{post_id}/insights?metric=post_clicks,post_reactions..."""
    url = f"https://graph.facebook.com/{_gv()}/{post_id}/insights"
    resp = _http_get_json(url, {
        "metric": ",".join(metrics),
        "access_token": page_token,
    })
    if not isinstance(resp, dict) or "error" in resp:
        return {"data": [], "_error": resp.get("error") if isinstance(resp, dict) else str(resp)}
    return resp


# ── Atomic write ─────────────────────────────────────────────────────
def _atomic_write(path: Path, data: dict) -> bool:
    """Write to a tmp file, then rename. Returns True if changed."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(data, indent=2, sort_keys=True, default=str)
        if path.exists() and path.read_text() == serialized:
            return False
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(serialized)
        tmp.replace(path)
        return True
    except Exception as e:
        _LOG.warning(f"write failed: {e}")
        return False


# ── Main ─────────────────────────────────────────────────────────────
def fetch_and_persist(brand_id: str = DEFAULT_BRAND) -> int:
    user_token = _resolve_token()
    if not user_token:
        _LOG.warning("no token configured (set META_SYSTEM_USER_TOKEN)")
        return 2

    page_id = os.environ.get("SWING_SHACK_FB_PAGE_ID", DEFAULT_PAGE_ID)
    media_limit = int(os.environ.get("SWING_SHACK_FB_MEDIA_LIMIT", DEFAULT_MEDIA_LIMIT))

    # Mint page token
    page_token = _get_page_token(user_token, page_id)
    if not page_token:
        _LOG.warning(f"could not mint page token for page_id={page_id}")
        return 1
    _LOG.info(f"got page token (EAAjT6eUgv8U...{page_token[-6:]})")

    # Page info
    page_info = _get_page_info(page_token, page_id)
    if "error" in page_info:
        _LOG.warning(f"page info failed: {page_info['error']}")
    else:
        _LOG.info(f"@{page_info.get('name')} · fans={page_info.get('fan_count')} "
                  f"category={page_info.get('category')}")

    # Page posts
    posts = _list_page_posts(page_token, page_id, media_limit)
    _LOG.info(f"page posts: {len(posts)} returned")

    # Per-post insights — parallel
    media_out = []
    if posts:
        _LOG.info(f"fetching insights for {len(posts)} posts (parallel)...")
        with ThreadPoolExecutor(max_workers=4) as ex:
            future_to_post = {
                ex.submit(_get_post_insights, page_token, p["id"]): p
                for p in posts if p.get("id")
            }
            for fut in as_completed(future_to_post):
                post = future_to_post[fut]
                insight = fut.result()
                metrics = {}
                for m in insight.get("data", []) or []:
                    values = m.get("values", [])
                    if values:
                        metrics[m["name"]] = values[0].get("value")
                # Build the record
                msg = (post.get("message") or "")[:200]
                media_out.append({
                    "id": post.get("id"),
                    "permalink": post.get("permalink_url"),
                    "timestamp": post.get("created_time"),
                    "status_type": post.get("status_type"),
                    "message_preview": msg,
                    "reactions_total": sum(
                        v for k, v in metrics.items()
                        if k.startswith("post_reactions_") and k != "post_reactions_by_type_total"
                        and isinstance(v, (int, float))
                    ),
                    "reactions_breakdown": metrics.get("post_reactions_by_type_total", {}),
                    "clicks": metrics.get("post_clicks"),
                    "shares": post.get("shares", {}).get("count") if isinstance(post.get("shares"), dict) else post.get("shares"),
                    "metrics": metrics,
                })

    # Sort by timestamp desc
    media_out.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    # Build output
    out = {
        "brand": brand_id,
        "page": {
            "id": page_info.get("id"),
            "name": page_info.get("name"),
            "fan_count": page_info.get("fan_count"),
            "category": page_info.get("category"),
            "link": page_info.get("link"),
        },
        "media": media_out,
        "metadata": {
            "brand": brand_id,
            "page_id": page_id,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            "media_limit": media_limit,
            "posts_with_metrics": len([m for m in media_out if m.get("metrics")]),
            "metrics_requested": list(POST_METRICS),
        },
    }

    out_path = DATA_DIR / "fb-page-analytics.json"
    wrote = _atomic_write(out_path, out)
    _LOG.info(f"{'wrote' if wrote else 'updated'} {out_path.name} "
              f"({len(json.dumps(out, default=str))} bytes)")
    return 0


# ── Caption / hashtag / URL extractors (NEW 2026-08-31) ──────────────
def _extract_hashtags(text: str) -> list:
    """Extract #hashtags from caption / message."""
    if not text:
        return []
    import re as _re
    return _re.findall(r"#([\w\u00C0-\u017F]+)", text)


def _extract_first_url(text: str) -> str | None:
    """Find the first http(s) URL in the caption / message."""
    if not text:
        return None
    import re as _re
    m = _re.search(r"https?://[^\s]+", text)
    return m.group(0) if m else None


if __name__ == "__main__":
    sys.exit(fetch_and_persist())
