"""Pull Google Search Console query/page stats → search-console.json."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from ._io import atomic_write, io_for_job, utc_now_iso, _fallback_brand
from ..brand_lanes import _brand_safe

JOB_NAME = "gsc_report"
from . import ga4_report

OUTPUT = "search-console.json"
SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
API_BASE = "https://www.googleapis.com/webmasters/v3"

# GSC returns 403 both for "this principal has no grant on this property"
# (an ACL state, not a run failure) and for revoked/missing scopes. Only the
# first is a skip, and only for a non-default brand lane — a 403 on the
# default brand's property is a real regression and must stay FAILED/LATE.
_ACL_DENIED_MARKERS = (
    "does not have sufficient permission",
    "insufficient permission",
    "user does not have access",
    "permission_denied",
)


def _is_acl_denied(message: str) -> bool:
    if "GSC HTTP 403" not in message:
        return False
    low = message.lower()
    return any(m in low for m in _ACL_DENIED_MARKERS)


def _resolve_site_url(brand: str | None) -> tuple[str, str | None]:
    """Return (site_url, error). Non-default brands require GSC_SITE_URL_<BRAND>.

    Order of resolution (and a SC safety net):
      1) GSC_SITE_URL_<BRAND> env var (explicit override) — but if that
         points at `sc-domain:…` AND the OAuth token can see a URL-prefix
         property, prefer the URL-prefix form. The env var for Stick was
         historically set to sc-domain (legacy); a URL-prefix property the
         account actually owns is always a better primary.
      2) Cache file at DATA_DIR/gsc-site-url-<brand>.json written by a
         previous successful gsc_report run (auto-learned).
      3) For non-default brands: probe the brand's stored OAuth token via
         webmasters.sites.list() and pick the first URL-prefix property
         with `siteOwner` or `siteFullUser` permissionLevel.
      4) Default brand fall-through: GSC_SITE_URL / SEARCH_CONSOLE_SITE_URL /
         hard-coded `https://swingshack.co.za/`.
    """
    bid = brand or _fallback_brand()
    safe = _brand_safe(bid)

    # 1) Explicit override (with the SC safety net below).
    explicit = os.environ.get(f"GSC_SITE_URL_{safe}", "").strip()
    if explicit:
        # SC safety net: if explicit points at sc-domain and the OAuth token
        # actually owns a URL-prefix property, prefer the URL-prefix form.
        if explicit.startswith("sc-domain:"):
            better_url, _better_err = _probe_site_via_oauth(bid)
            if better_url and not better_url.startswith("sc-domain:"):
                # We have a URL-prefix form the account owns. Use it.
                return better_url, None
        return explicit, None

    # 2) Auto-learned cache (sticky across restarts on DATA_DIR).
    try:
        cache_path = Path(os.environ.get("DATA_DIR", "/data")) / f"gsc-site-url-{bid}.json"
        if cache_path.is_file():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            cached_url = cached.get("site_url")
            cached_at = cached.get("resolved_at", "")
            if cached_url:
                try:
                    age = (datetime.now(timezone.utc) - datetime.fromisoformat(cached_at.replace("Z", "+00:00"))).days
                except Exception:
                    age = 999
                if age < 7:
                    return cached_url, None
    except Exception:
        pass

    default_bid = _fallback_brand()
    if bid != default_bid:
        # 3) Probe via OAuth for a URL-prefix siteOwner property.
        probe_url, probe_err = _probe_site_via_oauth(bid)
        if probe_url:
            try:
                cache_path = Path(os.environ.get("DATA_DIR", "/data")) / f"gsc-site-url-{bid}.json"
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps({
                        "site_url": probe_url,
                        "resolved_at": datetime.now(timezone.utc).isoformat(),
                        "via": "oauth_sites_list_probed",
                    }, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass
            return probe_url, None
        return None, probe_err or f"GSC_SITE_URL_{safe} not set and OAuth sites.list probe did not find a usable property"

    # 4) Default brand fall-through.
    site = (
        os.environ.get("GSC_SITE_URL", "").strip()
        or os.environ.get("SEARCH_CONSOLE_SITE_URL", "").strip()
        or "https://swingshack.co.za/"
    )
    return site, None


def _probe_site_via_oauth(brand: str) -> tuple[str | None, str | None]:
    """Use the brand's stored OAuth refresh token to call
    webmasters.v3.sites.list() and pick the best URL-prefix property
    the account has siteOwner / siteFullUser permission on.

    Selection priority (descending):
      0. URL-prefix + siteOwner + matches the brand's domain (e.g.
         https://stickgolf.co.za/ for brand=stick). This is the strong
         preference — same domain, same brand.
      1. URL-prefix + siteOwner + matches the brand's domain (e.g.
         https://swingshack.co.za/ for brand=swing-shack).
      2. URL-prefix + siteOwner on any other domain.
      3. URL-prefix + siteFullUser on the brand's domain.
      4. URL-prefix + siteUnverifiedUser on the brand's domain.
      5. URL-prefix + anything else.
      6. Domain-property + siteOwner.
    """
    try:
        from _lib import gsc_oauth as _gsc_oauth
    except Exception as exc:
        return None, f"gsc_oauth import failed: {exc}"
    try:
        access_token = _gsc_oauth.get_access_token(brand=brand)
    except Exception as exc:
        return None, f"get_access_token failed: {exc}"
    if not access_token:
        return None, "no access_token (refresh_token missing or expired)"
    try:
        req = urllib.request.Request(
            "https://www.googleapis.com/webmasters/v3/sites",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return None, f"sites.list http {exc.code}: {exc.read().decode('utf-8', errors='replace')[:300]}"
    except Exception as exc:
        return None, f"sites.list failed: {exc}"

    # Resolve expected brand domain. The single source of truth is the
    # operating brands registry (`data/brands.json`); we read that to
    # pick the correct GSC property for the brand.
    brand_domain = ""
    try:
        from _lib import brand_directory as _bd
        # brand_directory.load_brand returns a dict; check for 'domain' / 'website'
        bd_data = _bd.load_brand(brand)
        brand_domain = (
            bd_data.get("domain")
            or bd_data.get("website")
            or bd_data.get("site_url")
            or ""
        )
    except Exception:
        pass
    # Allow ENV override (BRAND_DOMAIN_<BRAND> or BRAND_DOMAIN)
    if not brand_domain:
        brand_domain = (
            os.environ.get(f"BRAND_DOMAIN_{brand.upper().replace('-', '_')}", "")
            or os.environ.get("BRAND_DOMAIN", "")
        )

    entries = payload.get("siteEntry") or []
    by_pref = []
    for e in entries:
        url = e.get("siteUrl") or ""
        perm = e.get("permissionLevel") or ""
        is_prefix = url.startswith("http")
        is_domain = url.startswith("sc-domain:")
        url_host = url.split("//", 1)[-1].rstrip("/") if is_prefix else url.replace("sc-domain:", "")

        # Strong match: same domain as the brand, URL-prefix, siteOwner
        if is_prefix and perm == "siteOwner" and brand_domain and brand_domain in url_host:
            by_pref.append((0, url, perm))
        # Same domain, URL-prefix, any owner
        elif is_prefix and brand_domain and brand_domain in url_host:
            by_pref.append((2, url, perm))
        # URL-prefix, siteOwner on any domain
        elif is_prefix and perm == "siteOwner":
            by_pref.append((3, url, perm))
        # URL-prefix, siteFullUser on any domain
        elif is_prefix and perm == "siteFullUser":
            by_pref.append((4, url, perm))
        # URL-prefix, siteUnverifiedUser on any domain
        elif is_prefix and perm == "siteUnverifiedUser":
            by_pref.append((5, url, perm))
        # URL-prefix, anything else
        elif is_prefix:
            by_pref.append((6, url, perm))
        # Domain-property, siteOwner
        elif is_domain and perm == "siteOwner":
            by_pref.append((7, url, perm))
        # Domain-property, anything else
        else:
            by_pref.append((8, url, perm))
    by_pref.sort(key=lambda t: t[0])
    if not by_pref:
        return None, "sites.list returned no siteEntry items"
    chosen = by_pref[0][1]
    return chosen, None


def _get_search_console_bearer(*, brand: str | None = None) -> str:
    try:
        from _lib import gsc_oauth as _gsc_oauth  # noqa: PLC0415

        oauth_token = _gsc_oauth.get_access_token(brand=brand)
        if oauth_token:
            return oauth_token
    except Exception:
        pass

    _, sa_path = ga4_report._resolve_ga4_creds(brand)
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


def run(*, brand: str | None = None) -> dict:
    """Fetch Search Console stats and write search-console.json."""
    io = io_for_job(JOB_NAME, brand)
    site, site_err = _resolve_site_url(brand)
    if site_err:
        return {"ok": False, "error": site_err}

    try:
        from _lib import gsc_oauth as _gsc_oauth  # noqa: PLC0415

        has_oauth = _gsc_oauth.gsc_oauth_credentials_present() and _gsc_oauth.load_token(brand=brand)
    except Exception:
        has_oauth = False
    if not has_oauth:
        missing = ga4_report._missing_env_error(brand)
        if missing:
            return {"ok": False, "error": missing}

    end = date.today() - timedelta(days=3)  # GSC data lag
    start = end - timedelta(days=27)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=27)

    try:
        bearer = _get_search_console_bearer(brand=brand)
        queries = _search_analytics(site, bearer, start.isoformat(), end.isoformat(), ["query"], 50)
        pages = _search_analytics(site, bearer, start.isoformat(), end.isoformat(), ["page"], 25)
        prev_queries = _search_analytics(
            site, bearer, prev_start.isoformat(), prev_end.isoformat(), ["query"], 50
        )
    except RuntimeError as exc:
        msg = str(exc)[:400]
        if brand and brand != _fallback_brand() and _is_acl_denied(msg):
            return {
                "ok": True,
                "skipped": True,
                "reason": f"GSC property {site} not shared with this brand's credential",
                "detail": msg,
            }
        return {"ok": False, "error": msg}

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
    io.write(OUTPUT, payload)
    return {"ok": True, "rows": len(queries)}
