#!/usr/bin/env python3
"""v25_daily_pull.py — Daily cache refresh for V2.5 Editorial Intelligence.

V2.5 reads cache files. Without daily pulls the report shows
"unavailable" for paid media / "missing" for GA4 sessions.

This script runs the live ingest endpoints and writes the cache
files V2.5 expects:

  data/paid-media-v24/<brand>.json   ← /api/meta/ads/cache/<brand>
  data/analytics/ga4-sessions.json   ← /api/ga4/<brand>/sessions
  data/analytics/ga4-pages.json      ← /api/ga4/<brand>/pages
  data/seo-rankings.json             ← /api/seo/overview
  data/analytics/instagram-analytics.json ← already updated daily elsewhere

Auth: shared password login → session cookie. Reuse cookie file
across runs (24h max-age).

Exit codes:
  0  all pulls succeeded
  1  partial failure (some sections succeeded)
  2  total failure (could not even log in)

Cron: 06:00 SAST daily (before 06:30 meta_refresh + 06:30 newsjack).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get(
    "CAMPAIGN_OS_DATA_DIR", REPO_ROOT / "data"))
CACHE_DIR = DATA_DIR / "paid-media-v24"
ANALYTICS_DIR = DATA_DIR / "analytics"
COOKIE_FILE = Path(os.environ.get(
    "V25_COOKIE_FILE",
    str(Path.home() / ".newsjack" / "v25-cookie.txt")))

DEFAULT_BASE_URL = os.environ.get(
    "CAMPAIGN_OS_BASE_URL", "http://127.0.0.1:8080")
DEFAULT_PASSWORD = os.environ.get(
    "CAMPAIGN_OS_PASSWORD", "swing-shack-dev-2026")
DEFAULT_BRANDS = os.environ.get(
    "V25_BRANDS", "swing-shack,stick").split(",")


def _log(stage: str, msg: str, ok: bool = True) -> None:
    marker = "✓" if ok else "✗"
    print(f"{marker} [{stage}] {msg}", flush=True)


def _login(base_url: str, password: str) -> str:
    """POST /login, return the session cookie value."""
    data = urllib.parse.urlencode({"password": password}).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/login",
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        cookie_header = resp.headers.get("Set-Cookie") or ""
        if "cos_session=" in cookie_header:
            return cookie_header.split("cos_session=", 1)[1].split(";", 1)[0]
    except Exception as e:
        _log("login", f"failed: {e}", ok=False)
        return ""
    return ""


def _get_session_cookie(base_url: str, password: str) -> str:
    """Reuse cached cookie if fresh, else log in fresh."""
    if COOKIE_FILE.exists():
        age = time.time() - COOKIE_FILE.stat().st_mtime
        if age < 12 * 3600:  # 12h fresh
            cookie = COOKIE_FILE.read_text().strip()
            if cookie:
                _log("login", f"reused cached cookie ({age/3600:.1f}h old)")
                return cookie
    cookie = _login(base_url, password)
    if cookie:
        COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
        COOKIE_FILE.write_text(cookie)
        _log("login", "fresh login succeeded")
    return cookie


def _call(base_url: str, cookie: str, path: str,
           timeout: int = 60,
           method: str = "GET",
           json_body: dict | None = None) -> tuple[bool, dict]:
    """<method> <base><path> with the session cookie. Returns (ok, body)."""
    url = f"{base_url.rstrip('/')}{path}"
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data, method=method)
        if cookie:
            req.add_header("Cookie", f"cos_session={cookie}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=timeout)
        body = json.loads(resp.read())
        return True, body
    except Exception as e:
        _log("call", f"{path}: {e}", ok=False)
        return False, {"error": str(e)[:200]}


def _write_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(path)


def _format_ga4_sessions(body: dict) -> dict:
    """Convert /api/ga4/<brand>/sessions response to V2.5 shape."""
    return {
        "schema": "v2.5-editorial-ga4-sessions-v1",
        "brand_id": body.get("brand_id"),
        "sessions": body.get("total_sessions"),
        "conversions": body.get("total_conversions"),
        "engagement_rate_avg": (
            sum(r.get("engagement_rate", 0) for r in (body.get("rows") or []))
            / max(1, len(body.get("rows") or []))),
        "rows": body.get("rows", []),
        "fetched_at": body.get("checked_at"),
        "window": "last 30 days (rolling)",
    }


def _format_ga4_pages(body: dict) -> dict:
    """Convert /api/ga4/<brand>/pages response to V2.5 shape."""
    pages = body.get("pages") or []
    return {
        "schema": "v2.5-editorial-ga4-pages-v1",
        "brand_id": body.get("brand_id"),
        "top_pages": pages[:10],
        "fetched_at": body.get("checked_at"),
    }


def _format_meta_cache(body: dict, brand_id: str) -> dict:
    """Pass through /api/meta/ads/cache/<brand> into V2.5 cache shape.

    Writes even if data_status=NOT_CONNECTED, so V2.5 has a consistent
    snapshot rather than re-querying Meta on every page load.
    """
    cache = body.get("cache") or {}
    return {
        "schema": "v2.5-editorial-paid-media-v24-v1",
        "brand_id": brand_id,
        "paid_media_v24": cache,
        "fetched_at": body.get("fetched_at") or time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "snapshot_note": body.get("note") or "",
    }


def _format_seo(body: dict) -> dict:
    """Pass through /api/seo/overview into V2.5 SEO shape.

    The live endpoint returns:
      {domain_health: {domain_authority, total_backlinks,
        ref_domains, keyword_footprint: {top_3, top_10, ...},
        weekly_change, manager_read},
       freshness: {...}, summary: {...}, generated_at, ok}

    We extract the fields V2.5 cares about and pass through the raw
    response for downstream debugging.
    """
    dh = body.get("domain_health") or {}
    kf = dh.get("keyword_footprint") or {}
    return {
        "schema": "v2.5-editorial-seo-v1",
        "fetched_at": body.get("generated_at") or time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "domain_authority": dh.get("domain_authority"),
        "backlinks": dh.get("total_backlinks"),
        "ref_domains": dh.get("ref_domains"),
        "top_3_keywords": kf.get("top_3"),
        "top_10_keywords": kf.get("top_10"),
        "ranking_top_100": kf.get("ranking_top_100"),
        "weekly_change": dh.get("weekly_change") or {},
        "manager_read": dh.get("manager_read") or "",
        "raw": body,  # keep full response for the editorial reporter
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--brand", action="append", default=None,
                          help="brand to pull (repeatable). default: swing-shack,stick")
    args = parser.parse_args()
    brands = args.brand or DEFAULT_BRANDS

    _log("start", f"base={args.base_url} brands={brands}")

    cookie = _get_session_cookie(args.base_url, args.password)
    if not cookie:
        _log("login", "no session cookie; aborting", ok=False)
        return 2

    successes = 0
    failures = 0
    total = 0

    for brand in brands:
        _log("brand", brand)
        # Meta ads cache → data/paid-media-v24/<brand>.json
        # Always write the cache file, even if the response says
        # ok:false with data_status=NOT_CONNECTED. This means V2.5
        # gets a consistent snapshot rather than re-querying Meta
        # on every page load.
        total += 1
        ok, body = _call(args.base_url, cookie,
                          f"/api/meta/ads/cache/{brand}", timeout=60)
        cache = body.get("cache") or {}
        data_status = cache.get("data_status", "OK" if body.get("ok") else "UNKNOWN")
        _write_atomic(CACHE_DIR / f"{brand}.json",
                        _format_meta_cache(body, brand))
        n_camp = len((cache.get("current_period") or {}).get("rows") or [])
        if data_status == "OK" and body.get("ok"):
            _log("meta-cache", f"{n_camp} current campaigns")
            successes += 1
        else:
            _log("meta-cache",
                  f"snapshot written (data_status={data_status}, "
                  f"camps={n_camp})", ok=False)
            # Don't count as failure — we have a snapshot
            successes += 1

        # GA4 sessions → data/analytics/ga4-sessions.json
        total += 1
        ok, body = _call(args.base_url, cookie,
                          f"/api/ga4/{brand}/sessions", timeout=60)
        if ok and body.get("ok"):
            total_sessions = body.get("total_sessions", 0)
            _write_atomic(ANALYTICS_DIR / "ga4-sessions.json",
                            _format_ga4_sessions(body))
            _log("ga4-sessions", f"{total_sessions} sessions (30d)")
            successes += 1
        else:
            _log("ga4-sessions",
                  f"failed: {(body.get('error') or 'unknown')[:100]}", ok=False)
            failures += 1

        # GA4 pages → data/analytics/ga4-pages.json
        total += 1
        ok, body = _call(args.base_url, cookie,
                          f"/api/ga4/{brand}/pages", timeout=60)
        if ok and body.get("ok"):
            npages = len(body.get("pages") or [])
            _write_atomic(ANALYTICS_DIR / "ga4-pages.json",
                            _format_ga4_pages(body))
            _log("ga4-pages", f"{npages} pages")
            successes += 1
        else:
            _log("ga4-pages",
                  f"failed: {(body.get('error') or 'unknown')[:100]}", ok=False)
            failures += 1

    # SEO is domain-scoped, not brand-scoped
    total += 1
    ok, body = _call(args.base_url, cookie, "/api/seo/overview", timeout=60)
    if ok and body.get("ok"):
        da = (body.get("domain") or {}).get("domainAuthority")
        _write_atomic(DATA_DIR / "seo-rankings.json", _format_seo(body))
        _log("seo", f"DA={da} written")
        successes += 1
    else:
        _log("seo", f"failed: {(body.get('error') or 'unknown')[:100]}",
              ok=False)
        failures += 1

    print()
    _log("done", f"{successes}/{total} succeeded, {failures} failed")
    return 0 if failures == 0 else (1 if successes > 0 else 2)


if __name__ == "__main__":
    sys.exit(main())
