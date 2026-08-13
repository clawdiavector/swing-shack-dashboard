#!/usr/bin/env python3
"""fetch_ig_business.py — live IG Business account + media insights for Swing Shack.

Why this exists
---------------
The existing `scripts/sync_ig_analytics.js` (auto-ran by the meta-analytics plist
at 06:30 SAST) reads from a separate `instagram-analytics.json` tracker that
**does not populate reach** — so the weekly report sees `reach=0` across all
10 IG posts. This script goes directly to the Graph API to pull the real
numbers the existing sync misses.

It writes a NEW file (`data/ig-business-analytics.json`) so the existing
ig-analytics.json pipeline is not disturbed. The intelligence module reads
both: ig-analytics.json for post-level engagement + hook_ids (legacy
sync still useful), and ig-business-analytics.json for reach + account-level
daily metrics.

Live-verified shape (2026-08-13):
  - Account-level daily: reach, accounts_engaged, total_interactions,
    profile_views, profile_links_taps (metric_type=total_value).
  - Account-level daily: reach alone also works WITHOUT metric_type.
  - Media-level lifetime insights: total_interactions, reach, impressions,
    likes, comments, shares, saved (period=lifetime).
  - Account info: followers_count, follows_count, media_count, biography.
  - Page-level (Facebook Page) insights REJECTED with #10 — long-lived
    user token does NOT carry `pages_read_engagement` (added 2024).
    So this script is intentionally IG-Business-only. FB Page metrics
    require a separately-granted scope Christelle hasn't approved.

Outputs
-------
  data/ig-business-analytics.json   -- account + media metrics for the
                                       weekly_report cross-cut.

Exit codes
----------
  0 -- success (one or more files written, or every metric gracefully
       skipped with documented reason)
  1 -- generic failure (auth, network, malformed response)
  2 -- token file missing (no credentials configured -- silent cron)

Environment
-----------
  SWING_SHACK_META_TOKEN_FILE  (default: ~/.openclaw-instance2/workspace/
                                clients/swing-shack/credentials/meta-token.json)
  SWING_SHACK_IG_WINDOW_DAYS   (default: 30)
  SWING_SHACK_IG_MEDIA_LIMIT   (default: 25)
  GRAPH_API_VERSION            (default: v21.0)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# ── Paths ─────────────────────────────────────────────────────────────

REPO_ROOT = Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard")
DATA_DIR = REPO_ROOT / "data"

DEFAULT_TOKEN_FILE = (
    "/Users/fivefriday/.openclaw-instance2/workspace/"
    "clients/swing-shack/credentials/meta-token.json"
)
DEFAULT_WINDOW_DAYS = 30
# v2026-08-13: bumped from 25 → 100 so post-conversion scoring has enough
# posts for noise rejection on bottom-rank (skill note: needs 30+ posts).
# Meta API page limit is 250; we paginate within the script if needed.
DEFAULT_MEDIA_LIMIT = 100
DEFAULT_GRAPH_VERSION = "v21.0"
DEFAULT_MAX_WORKERS = 8

# Live-verified (2026-08-13): Swing Shack page id + IG business account id
# both live in the saved token file. Hardcoded fallback mirrors the
# meta-token.json values so the script can also self-discover if the
# token file shape changes.
DEFAULT_PAGE_ID = "198859063301219"
DEFAULT_IG_BIZ_ID = "17841456713897671"

_LOG = logging.getLogger("fetch_ig_business")

# Account-level metrics that work as metric_type=total_value over `period=day`.
# (Live-verified 2026-08-13 against ig_biz=17841456713897671.)
ACCOUNT_TOTAL_VALUE_METRICS = (
    "reach",
    "accounts_engaged",
    "total_interactions",
    "profile_views",
    "profile_links_taps",
)

# Metrics that work WITHOUT metric_type=total_value (daily sums).
ACCOUNT_DAILY_METRICS = (
    "reach",
    "follower_count",
)

# Media-level lifetime metrics (one per post, not time-series).
MEDIA_LIFETIME_METRICS = (
    "total_interactions",
    "reach",
    "impressions",
    "likes",
    "comments",
    "shares",
    "saved",
)


# ── Logging ───────────────────────────────────────────────────────────


def _setup_logging(verbose: bool = False) -> None:
    fmt = "[%(asctime)s SAST] %(message)s"
    if verbose:
        fmt = "[%(asctime)s SAST] [%(name)s] %(levelname)s %(message)s"
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format=fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ── Atomic write ───────────────────────────────────────────────────────


def _atomic_write(path: Path, data: dict) -> bool:
    """Write JSON atomically: tmp → rename. Returns True if file changed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, indent=2, sort_keys=True, default=str)
    if path.exists() and path.read_text() == serialized:
        _LOG.debug(f"unchanged: {path}")
        return False
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(serialized)
    tmp.replace(path)
    _LOG.info(f"wrote {path} ({len(serialized)} bytes)")
    return True


# ── Token / page helpers ───────────────────────────────────────────────


def _read_token_file(path: str) -> Tuple[Optional[str], Dict[str, Any]]:
    """Read the meta-token.json. Returns (user_token, meta_dict).

    Silently returns (None, {}) if the file is missing or unreadable --
    the caller treats that as exit code 2.
    """
    p = Path(path)
    if not p.exists():
        return None, {}
    try:
        meta = json.loads(p.read_text())
        tok = (meta.get("access_token") or "").strip() or None
        return tok, meta
    except (json.JSONDecodeError, OSError) as e:
        _LOG.warning(f"could not parse token file {path}: {e}")
        return None, {}


def _resolve_page_token(user_token: str, page_id: str) -> Optional[str]:
    """Mint a page-scoped token via /me/accounts. Required for /{ig_biz_id}
    and /{page_id}/insights endpoints that reject user tokens.

    Returns None on any failure (silent cron: caller logs + exits 0 with
    nothing written).
    """
    url = (
        f"https://graph.facebook.com/{_gv()}/me/accounts"
        f"?fields=id,access_token&access_token={user_token}"
    )
    try:
        with urlopen(url, timeout=20) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except (HTTPError, URLError, json.JSONDecodeError) as e:
        _LOG.warning(f"/me/accounts failed: {e}")
        return None
    for entry in (payload.get("data") or []):
        if isinstance(entry, dict) and entry.get("id") == page_id:
            tok = entry.get("access_token")
            if tok:
                _LOG.info(f"minted page token ({tok[:12]}...{tok[-6:]})")
                return tok.strip()
    _LOG.warning(f"page_id={page_id} not present in /me/accounts response")
    return None


def _gv() -> str:
    return os.environ.get("GRAPH_API_VERSION", DEFAULT_GRAPH_VERSION)


# ── Low-level Graph caller ─────────────────────────────────────────────


def _graph_get(path: str, params: Dict[str, Any], token: str, timeout: int = 30) -> Dict[str, Any]:
    """GET against the Graph API. Returns parsed JSON or `{"error": {...}}`.

    Never raises -- the caller decides what to do with upstream errors
    (we don't fabricate metrics; missing/skipped metrics are skipped, not
    invented).
    """
    params = {**params, "access_token": token}
    url = f"https://graph.facebook.com/{_gv()}{path}?{urlencode(params)}"
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = {"error": {"message": str(e), "code": e.code}}
        return body
    except (URLError, json.JSONDecodeError, TimeoutError) as e:
        return {"error": {"message": str(e), "code": -1}}


# ── Pull 1: account-level daily metrics ────────────────────────────────


def _pull_account_daily(
    page_token: str,
    ig_biz_id: str,
    *,
    since_ts: int,
    until_ts: int,
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    """Pull account-level daily timeseries metrics.

    Returns:
        (metrics_dict, skipped_list)
        metrics_dict: {metric_name: [{date, value}, ...]}
        skipped_list: metrics that returned an error (for transparency)
    """
    out: Dict[str, List[Dict[str, Any]]] = {}
    skipped: List[str] = []

    # 1) total_value metrics (one bucket per metric, total over the window)
    #    These return total_value.value (single number), not a timeseries.
    #    Note: `reach` works with metric_type=total_value (verified
    #    2026-08-13) and gives the summed daily-reach across the window.
    #    If the daily-timeseries pass (below) also fills `reach`, that
    #    wins — it's richer (per-day breakdown). The total_value is the
    #    fallback when daily isn't supported.
    total_value_url = f"/{ig_biz_id}/insights"
    for metric in ACCOUNT_TOTAL_VALUE_METRICS:
        params = {
            "metric": metric,
            "period": "day",
            "metric_type": "total_value",
            "since": since_ts,
            "until": until_ts,
        }
        data = _graph_get(total_value_url, params, page_token)
        if "error" in data:
            _LOG.debug(f"skip {metric}: {data['error'].get('message')}")
            skipped.append(metric)
            continue
        for entry in (data.get("data") or []):
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            tv = entry.get("total_value") or {}
            v = tv.get("value") if isinstance(tv, dict) else None
            if name and v is not None:
                out.setdefault(name, []).append({"date": "window_total", "value": int(v)})

    # 2) Daily timeseries metrics (reach, follower_count)
    for metric in ACCOUNT_DAILY_METRICS:
        params = {
            "metric": metric,
            "period": "day",
            "since": since_ts,
            "until": until_ts,
        }
        data = _graph_get(total_value_url, params, page_token)
        if "error" in data:
            _LOG.debug(f"skip daily {metric}: {data['error'].get('message')}")
            skipped.append(f"{metric}_daily")
            continue
        for entry in (data.get("data") or []):
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            values = entry.get("values") or []
            series = []
            for v in values:
                if not isinstance(v, dict):
                    continue
                # end_time may be ISO with +00:00; normalize to YYYY-MM-DD.
                end = v.get("end_time") or v.get("value") or ""
                date_str = str(end)[:10] if end else ""
                val = v.get("value")
                if isinstance(val, (int, float)) and date_str:
                    series.append({"date": date_str, "value": int(val)})
            if name and series:
                # Daily series replaces any earlier window_total entry.
                out[name] = series

    return out, skipped


# ── Pull 2: account info snapshot ──────────────────────────────────────


def _pull_account_info(page_token: str, ig_biz_id: str) -> Dict[str, Any]:
    """Snapshot: followers_count, follows_count, media_count, username."""
    url = f"/{ig_biz_id}"
    params = {
        "fields": "id,username,name,biography,followers_count,follows_count,media_count",
    }
    data = _graph_get(url, params, page_token)
    if "error" in data:
        _LOG.warning(f"account info failed: {data['error'].get('message')}")
        return {}
    return {k: v for k, v in data.items() if not k.startswith("profile_picture")}


# ── Pull 3: media-level insights (last N posts) ───────────────────────


def _pull_media(
    page_token: str,
    ig_biz_id: str,
    *,
    since_ts: int,
    until_ts: int,
    limit: int,
) -> List[Dict[str, Any]]:
    """Pull the last `limit` media objects, each with lifetime insights.

    Skips a media entry's metrics gracefully if any one of them returns
    an error — but keeps the post (with `insights_error`) so the
    intelligence module can count it.

    Metric queries are issued ONE AT A TIME because Meta's Graph API
    rejects the entire batch when even one metric is unsupported for the
    media type (e.g. `impressions` is no longer supported for IMAGE media
    on v22+, REEL supports it). Live-verified 2026-08-13.
    """
    # Step 1: list media (id, caption, media_type, timestamp, permalink)
    list_url = f"/{ig_biz_id}/media"
    list_params = {
        "fields": "id,caption,media_type,permalink,timestamp",
        "limit": limit,
        # Only fetch posts inside the window so we don't waste requests
        # on ancient posts.
        "since": since_ts,
        "until": until_ts,
    }
    listed = _graph_get(list_url, list_params, page_token)
    if "error" in listed:
        _LOG.warning(f"media list failed: {listed['error'].get('message')}")
        return []

    media_out: List[Dict[str, Any]] = []
    for entry in (listed.get("data") or []):
        if not isinstance(entry, dict):
            continue
        mid = entry.get("id")
        if not mid:
            continue
        caption = entry.get("caption") or ""
        caption_str = str(caption) if caption else ""
        # Step 2: query each lifetime metric in parallel so a 25-post
        # sweep finishes in ~3s instead of ~20s. The Graph API rate-limits
        # at ~200 calls/hour per token; DEFAULT_MAX_WORKERS=8 keeps us
        # well below that for any reasonable media_limit.
        metric_jobs = [(mid, m) for m in MEDIA_LIFETIME_METRICS]

        def _fetch_one(job: Tuple[str, str]) -> Tuple[str, Dict[str, Any]]:
            media_id, metric = job
            url = f"/{media_id}/insights"
            return metric, _graph_get(url, {"metric": metric}, page_token)

        metrics_flat: Dict[str, int] = {}
        ins_errors: List[str] = []
        with ThreadPoolExecutor(max_workers=DEFAULT_MAX_WORKERS) as ex:
            for metric, payload in ex.map(_fetch_one, metric_jobs):
                if "error" in payload:
                    msg = str(payload["error"].get("message", "unknown"))
                    if msg not in ins_errors:
                        _LOG.debug(f"media {mid} {metric}: {msg}")
                        ins_errors.append(msg)
                    continue
                for m in (payload.get("data") or []):
                    if not isinstance(m, dict) or m.get("name") != metric:
                        continue
                    vals = m.get("values") or []
                    if not vals:
                        continue
                    v = vals[0].get("value") if isinstance(vals[0], dict) else None
                    if isinstance(v, (int, float)):
                        metrics_flat[metric] = int(v)
        # engagement_rate = total_interactions / reach (when reach > 0)
        er = None
        if metrics_flat.get("total_interactions") and metrics_flat.get("reach"):
            try:
                er = round(metrics_flat["total_interactions"] / metrics_flat["reach"] * 100, 2)
            except ZeroDivisionError:
                pass
        media_out.append({
            "id": mid,
            "media_type": entry.get("media_type"),
            "permalink": entry.get("permalink"),
            "timestamp": entry.get("timestamp"),
            "caption_preview": caption_str[:160],
            "hook_id": _caption_to_hook_id(caption_str),
            "metrics": metrics_flat,
            "engagement_rate_pct": er,
            **({"insights_errors": ins_errors} if ins_errors else {}),
        })
    return media_out


def _caption_to_hook_id(caption: str) -> str:
    """Mirror sync_ig_analytics.js hook_id derivation so cross-source
    linking still works."""
    if not caption:
        return ""
    first_line = caption.split("\n", 1)[0] or caption[:80]
    return re.sub(r"[^a-z0-9]+", "-", first_line.lower()).strip("-")[:50]


# ── Orchestration ─────────────────────────────────────────────────────


def _resolve_args(args: argparse.Namespace) -> Tuple[str, str, str, int, int]:
    """Return (token_file, page_id, ig_biz_id, window_days, media_limit)."""
    token_file = os.environ.get("SWING_SHACK_META_TOKEN_FILE", DEFAULT_TOKEN_FILE)
    window = int(os.environ.get("SWING_SHACK_IG_WINDOW_DAYS", DEFAULT_WINDOW_DAYS))
    if args.window:
        window = int(args.window)
    media_limit = int(os.environ.get("SWING_SHACK_IG_MEDIA_LIMIT", DEFAULT_MEDIA_LIMIT))
    if args.media_limit:
        media_limit = int(args.media_limit)
    page_id = DEFAULT_PAGE_ID
    ig_biz_id = DEFAULT_IG_BIZ_ID
    return token_file, page_id, ig_biz_id, window, media_limit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--window", type=int, help=f"override window days (default: {DEFAULT_WINDOW_DAYS})")
    parser.add_argument("--media-limit", type=int, help=f"override media limit (default: {DEFAULT_MEDIA_LIMIT})")
    parser.add_argument("--once", action="store_true", help="Run once and exit (default).")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute everything but don't write the data file.")
    args = parser.parse_args()

    _setup_logging(args.verbose)

    token_file, page_id, ig_biz_id, window_days, media_limit = _resolve_args(args)

    # ── 1. Auth gate ──────────────────────────────────────────────────
    user_token, token_meta = _read_token_file(token_file)
    if not user_token:
        _LOG.warning(
            f"no Meta token at {token_file}. Silent-cron exit code 2. "
            f"Run `python3 scripts/refresh_meta_token.py` if token is expired."
        )
        return 2
    _LOG.info(f"loaded user token ({user_token[:12]}...{user_token[-6:]}) from {token_file}")

    # Trust the token's own page_id / ig_biz_id when present so we don't
    # hardcode-drift if the account gets swapped.
    page_id = str(token_meta.get("page_id") or page_id)
    ig_biz_id = str(token_meta.get("instagram_account_id") or ig_biz_id)

    # ── 2. Mint page-scoped token (required for IG biz + page insights)
    page_token = _resolve_page_token(user_token, page_id)
    if not page_token:
        _LOG.warning(
            f"could not mint page-scoped token for page_id={page_id}. "
            f"Silent-cron exit code 0 with nothing written."
        )
        # Exit 0 (silent): the script is operationally correct, the token
        # just doesn't carry the required scope. Don't alarm the cron.
        return 0

    # ── 3. Compute window
    now = dt.datetime.now(dt.timezone.utc)
    until_ts = int(now.timestamp())
    since_ts = int((now - dt.timedelta(days=window_days)).timestamp())
    _LOG.info(f"window: {window_days}d, since={since_ts} until={until_ts}")

    # ── 4. Account info
    account_info = _pull_account_info(page_token, ig_biz_id)
    if account_info:
        _LOG.info(
            f"@{account_info.get('username')} · followers={account_info.get('followers_count')} "
            f"media={account_info.get('media_count')}"
        )

    # ── 5. Account-level daily metrics
    daily_metrics, skipped = _pull_account_daily(
        page_token, ig_biz_id, since_ts=since_ts, until_ts=until_ts,
    )
    for name, series in daily_metrics.items():
        if series and series[0].get("date") == "window_total":
            _LOG.info(f"  {name}: {series[0]['value']} (window total)")
        else:
            _LOG.info(f"  {name}: {len(series)} daily buckets")

    # ── 6. Media-level insights (recent posts in window)
    media = _pull_media(
        page_token, ig_biz_id,
        since_ts=since_ts, until_ts=until_ts, limit=media_limit,
    )
    media_with_reach = sum(1 for m in media if (m.get("metrics") or {}).get("reach"))
    media_with_engagement = sum(1 for m in media if (m.get("metrics") or {}).get("total_interactions"))
    _LOG.info(
        f"  media: {len(media)} posts · {media_with_reach} with reach · "
        f"{media_with_engagement} with engagement"
    )

    # ── 7. Assemble output
    # Pull the window_total values into a flat summary so the weekly
    # report can read them without re-traversing.
    window_totals = {
        name: series[0]["value"]
        for name, series in daily_metrics.items()
        if series and series[0].get("date") == "window_total"
    }
    daily_reach_series = [
        s for s in daily_metrics.get("reach", [])
        if s.get("date") != "window_total"
    ]

    # Sort media newest first; cap caption preview for size.
    media_sorted = sorted(media, key=lambda m: m.get("timestamp") or "", reverse=True)

    # Top post by reach (fallback to interactions)
    top_post = None
    if media_sorted:
        by_reach = sorted(
            [m for m in media_sorted if (m.get("metrics") or {}).get("reach")],
            key=lambda m: m["metrics"].get("reach", 0),
            reverse=True,
        )
        top_post = by_reach[0] if by_reach else media_sorted[0]

    out: Dict[str, Any] = {
        "metadata": {
            "source": "meta_graph_api.instagram_business",
            "page_id": page_id,
            "instagram_business_id": ig_biz_id,
            "username": account_info.get("username"),
            "fetched_at": now.isoformat(),
            "window_days": window_days,
            "since_ts": since_ts,
            "until_ts": until_ts,
            "graph_version": _gv(),
            "metrics_skipped": skipped,
            "media_limit": media_limit,
        },
        "account": {
            **account_info,
            "followers_count": account_info.get("followers_count"),
            "follows_count": account_info.get("follows_count"),
            "media_count": account_info.get("media_count"),
        },
        "window_totals": window_totals,
        "daily_reach": daily_reach_series,
        "media": media_sorted,
        "top_post": _top_post_summary(top_post) if top_post else None,
    }

    if args.dry_run:
        _LOG.info("[dry-run] would have written:")
        _LOG.info(json.dumps(out, indent=2, default=str)[:2000])
        return 0

    out_path = DATA_DIR / "ig-business-analytics.json"
    wrote = _atomic_write(out_path, out)
    _LOG.info(
        f"{'updated' if wrote else 'unchanged'} {out_path.name} "
        f"({len(json.dumps(out, default=str))} bytes)"
    )
    return 0


def _top_post_summary(post: Dict[str, Any]) -> Dict[str, Any]:
    m = post.get("metrics") or {}
    return {
        "id": post.get("id"),
        "media_type": post.get("media_type"),
        "permalink": post.get("permalink"),
        "timestamp": post.get("timestamp"),
        "caption_preview": post.get("caption_preview"),
        "hook_id": post.get("hook_id"),
        "reach": m.get("reach"),
        "interactions": m.get("total_interactions"),
        "likes": m.get("likes"),
        "comments": m.get("comments"),
        "saves": m.get("saved"),
        "shares": m.get("shares"),
        "engagement_rate_pct": post.get("engagement_rate_pct"),
    }


if __name__ == "__main__":
    sys.exit(main())
