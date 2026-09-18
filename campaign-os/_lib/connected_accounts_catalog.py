"""Connected Accounts catalog — UI-ready integration snapshots with live probes."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_KNOWN_PROVIDERS = frozenset(
    {
        "gmb",
        "gbp",
        "instagram",
        "facebook",
        "tiktok",
        "twitter",
        "x",
        "linkedin",
        "youtube",
        "pinterest",
        "threads",
        "reddit",
    }
)

_JOB_BY_INTEGRATION: dict[str, tuple[str, ...]] = {
    "ga4": ("ga4_report",),
    "gsc": ("gsc_report",),
    "youtube": ("youtube_trends",),
    "reddit": ("reddit_trends",),
    "golf_news": ("golf_news",),
    "gbp": ("gbp_tick",),
    "ubersuggest": ("seo_rankings",),
    "meta": ("meta_refresh",),
}

_DATA_FILE_BY_INTEGRATION: dict[str, str] = {
    "ga4": "ga4-metrics.json",
    "gsc": "search-console.json",
    "meta": "ig-business-analytics.json",
    "youtube": "youtube-trends.json",
    "reddit": "reddit-trends.json",
    "golf_news": "golf-news.json",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _age_label(iso_ts: Optional[str]) -> Optional[str]:
    if not iso_ts:
        return None
    try:
        raw = iso_ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        secs = (_utc_now() - dt.astimezone(timezone.utc)).total_seconds()
        if secs < 0:
            return "just now"
        if secs < 3600:
            return f"{max(1, int(secs // 60))}m ago"
        if secs < 86400:
            return f"{int(secs // 3600)}h ago"
        return f"{int(secs // 86400)}d ago"
    except Exception:
        return None


def _data_roots() -> list[Path]:
    roots: list[Path] = []
    for key in ("DATA_DIR", "BUNDLED_DATA_DIR"):
        val = os.environ.get(key)
        if val:
            p = Path(val)
            if p not in roots:
                roots.append(p)
    if not roots:
        roots.append(Path("/data"))
    return roots


def _data_file_mtime(rel: str) -> Optional[str]:
    for base in _data_roots():
        path = base / rel
        if path.is_file():
            return _iso(datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc))
    return None


def _job_activity(job_names: tuple[str, ...]) -> dict[str, Any]:
    try:
        from _lib.jobs import ledger
        from _lib.jobs.runner import _last_success, verdict_for
    except Exception:
        return {}
    now = _utc_now()
    last_at: Optional[str] = None
    verdict: Optional[str] = None
    for name in job_names:
        rows = ledger.read_rows(name)
        if not rows:
            continue
        v = verdict_for(name, rows, now=now)
        success = _last_success(rows)
        finished = (success or {}).get("finished") or (success or {}).get("started")
        if finished and (last_at is None or finished > last_at):
            last_at = finished
            verdict = v
    return {"last_success_at": last_at, "job_verdict": verdict, "last_used_label": _age_label(last_at)}


def _env_any(*names: str) -> bool:
    for n in names:
        if (os.environ.get(n) or "").strip():
            return True
    return False


def _env_prefix(*names: str) -> Optional[str]:
    for n in names:
        val = (os.environ.get(n) or "").strip()
        if val:
            return val[:8] + "…"
    return None


def infer_postiz_provider(item: dict[str, Any]) -> str:
    """Best-effort platform label for a Postiz integration row."""
    for key in ("providerIdentifier", "provider", "type", "identifier", "internalId"):
        raw = (item.get(key) or "").strip().lower()
        if raw in _KNOWN_PROVIDERS:
            return "gmb" if raw == "gbp" else raw
        if raw and raw not in {"unknown", "integration"}:
            return raw
    name = (item.get("name") or "").strip().lower()
    if name in _KNOWN_PROVIDERS:
        return "gmb" if name == "gbp" else name
    return "channel"


def _state_from_flags(
    *,
    live_ok: Optional[bool] = None,
    creds_ok: bool = False,
    partial: bool = False,
) -> str:
    if live_ok is True:
        return "connected"
    if live_ok is False and creds_ok:
        return "degraded"
    if creds_ok and not partial:
        return "connected"
    if creds_ok or partial:
        return "partial"
    return "missing"


def build_catalog_extras() -> dict[str, Any]:
    """Integrations beyond postiz/gbp/meta handled in app route."""
    items: list[dict[str, Any]] = []

    # GA4
    ga4_creds = _env_any(
        "GA4_PROPERTY_ID",
        "GA4_PROPERTY_SWING_SHACK",
        "GA4_CREDENTIALS_JSON_SWING_SHACK",
        "GA4_SERVICE_ACCOUNT_JSON_PATH",
    )
    ga4_activity = _job_activity(_JOB_BY_INTEGRATION["ga4"])
    ga4_file_at = _data_file_mtime(_DATA_FILE_BY_INTEGRATION["ga4"])
    ga4_last = ga4_activity.get("last_success_at") or ga4_file_at
    items.append(
        {
            "id": "ga4",
            "icon": "📈",
            "name": "Google Analytics 4",
            "category": "analytics",
            "category_label": "Analytics & data",
            "purpose": "Site traffic, top pages, session sources for Insights and weekly reports.",
            "state": _state_from_flags(
                live_ok=True if ga4_activity.get("job_verdict") == "OK" else None,
                creds_ok=ga4_creds,
                partial=ga4_creds and ga4_activity.get("job_verdict") not in (None, "OK"),
            ),
            "last_used_at": ga4_last,
            "last_used_label": _age_label(ga4_last),
            "job_verdict": ga4_activity.get("job_verdict"),
            "credentials": {
                "configured": ga4_creds,
                "env_vars": [
                    "GA4_PROPERTY_SWING_SHACK",
                    "GA4_CREDENTIALS_JSON_SWING_SHACK",
                    "GA4_SERVICE_ACCOUNT_JSON_PATH",
                ],
                "key_prefix": _env_prefix("GA4_PROPERTY_SWING_SHACK"),
            },
            "connect": {"type": "portal", "url": "/meta-portal", "label": "GA4 setup portal"},
            "setup": {
                "auth_type": "Service account JSON",
                "steps": [
                    "Google Cloud → IAM → service account with Analytics Data API access.",
                    "Add JSON to Railway as GA4_CREDENTIALS_JSON_SWING_SHACK (base64) or mount path via GA4_SERVICE_ACCOUNT_JSON_PATH.",
                    "Set GA4_PROPERTY_SWING_SHACK to the numeric property ID.",
                    "Optional: use setup portal at /meta-portal (Ask Heidi) for Mac credential drop.",
                ],
            },
        }
    )

    # GSC
    try:
        from _lib import gsc_oauth as _gsc_oauth

        gsc_oauth_client = _gsc_oauth.gsc_oauth_credentials_present()
        gsc_oauth_token = bool(_gsc_oauth.load_token())
    except Exception:
        gsc_oauth_client = False
        gsc_oauth_token = False
    gsc_creds = (gsc_oauth_client and gsc_oauth_token) or (
        _env_any("GSC_SITE_URL", "SEARCH_CONSOLE_SITE_URL") and ga4_creds
    )
    gsc_activity = _job_activity(_JOB_BY_INTEGRATION["gsc"])
    gsc_file_at = _data_file_mtime(_DATA_FILE_BY_INTEGRATION["gsc"])
    gsc_last = gsc_activity.get("last_success_at") or gsc_file_at
    gsc_connect = (
        {"type": "oauth", "url": "/api/gsc/oauth/login", "label": "Connect Search Console"}
        if gsc_oauth_client and not gsc_oauth_token
        else {"type": "manual", "url": "https://search.google.com/search-console", "label": "Open Search Console"}
    )
    items.append(
        {
            "id": "gsc",
            "icon": "🔎",
            "name": "Google Search Console",
            "category": "analytics",
            "category_label": "Analytics & data",
            "purpose": "Search queries, impressions, clicks — SEO Assistant and rank views.",
            "state": _state_from_flags(
                live_ok=True if gsc_activity.get("job_verdict") == "OK" else None,
                creds_ok=bool(gsc_creds),
                partial=bool(gsc_creds) and gsc_activity.get("job_verdict") not in (None, "OK"),
            ),
            "last_used_at": gsc_last,
            "last_used_label": _age_label(gsc_last),
            "job_verdict": gsc_activity.get("job_verdict"),
            "credentials": {
                "configured": bool(gsc_creds),
                "oauth_client": gsc_oauth_client,
                "oauth_token": gsc_oauth_token,
                "env_vars": ["GSC_SITE_URL", "google-search-console-oauth.json"],
            },
            "connect": gsc_connect,
            "setup": {
                "auth_type": "OAuth (webmasters.readonly) or GA4 service account fallback",
                "steps": [
                    "GCP → enable Search Console API → Web OAuth client.",
                    "Sync client JSON via /secrets-sync (google-search-console-oauth).",
                    "Add redirect: https://<prod-host>/api/gsc/oauth/callback",
                    "Click Connect Search Console on Connected Accounts (signed in).",
                    "Set GSC_SITE_URL=https://swingshack.co.za/ if needed (default).",
                ],
            },
        }
    )

    # YouTube trends
    yt_creds = _env_any("YOUTUBE_API_KEY")
    yt_activity = _job_activity(_JOB_BY_INTEGRATION["youtube"])
    yt_file_at = _data_file_mtime(_DATA_FILE_BY_INTEGRATION["youtube"])
    yt_last = yt_activity.get("last_success_at") or yt_file_at
    items.append(
        {
            "id": "youtube",
            "icon": "▶️",
            "name": "YouTube Data API (trends scout)",
            "category": "optional",
            "category_label": "Optional scouts",
            "purpose": "Public golf trend videos for Signal radar — not your own channel.",
            "state": _state_from_flags(creds_ok=yt_creds, partial=not yt_creds),
            "last_used_at": yt_last,
            "last_used_label": _age_label(yt_last),
            "job_verdict": yt_activity.get("job_verdict"),
            "credentials": {
                "configured": yt_creds,
                "env_vars": ["YOUTUBE_API_KEY"],
                "key_prefix": _env_prefix("YOUTUBE_API_KEY"),
            },
            "connect": {"type": "portal", "url": "/secrets-sync", "label": "Secrets sync"},
            "setup": {
                "auth_type": "API key",
                "steps": [
                    "GCP → enable YouTube Data API v3 → create API key.",
                    "Paste via /secrets-sync (service: youtube-api, shape: {\"api_key\": \"...\"}).",
                    "Or set YOUTUBE_API_KEY on Railway.",
                ],
            },
        }
    )

    # Ubersuggest
    uber_creds = _env_any("UBERSUGGEST_ACCESS", "UBERSUGGEST_TOKEN_FILE", "UBERSUGGEST_REFRESH_TOKEN")
    uber_activity = _job_activity(_JOB_BY_INTEGRATION["ubersuggest"])
    uber_last = uber_activity.get("last_success_at") or _data_file_mtime("seo-rankings.json")
    items.append(
        {
            "id": "ubersuggest",
            "icon": "📊",
            "name": "Ubersuggest (SEO rankings)",
            "category": "analytics",
            "category_label": "Analytics & data",
            "purpose": "Domain keyword rankings and SEO snapshots.",
            "state": _state_from_flags(
                live_ok=True if uber_activity.get("job_verdict") == "OK" else None,
                creds_ok=uber_creds,
            ),
            "last_used_at": uber_last,
            "last_used_label": _age_label(uber_last),
            "job_verdict": uber_activity.get("job_verdict"),
            "credentials": {
                "configured": uber_creds,
                "env_vars": ["UBERSUGGEST_ACCESS", "UBERSUGGEST_REFRESH_TOKEN", "UBERSUGGEST_TOKEN_FILE"],
            },
            "connect": {"type": "none", "label": "Configured on Railway"},
            "setup": {
                "auth_type": "OAuth tokens on Railway",
                "steps": ["Tokens already set if seo_rankings job is OK.", "Refresh via Ubersuggest account if job goes LATE."],
            },
        }
    )

    # Krea
    krea = _env_any("KREA_API_KEY", "Krea_API")
    items.append(
        {
            "id": "krea",
            "icon": "🎨",
            "name": "Krea (image gen)",
            "category": "optional",
            "category_label": "Optional scouts",
            "purpose": "AI image generation API for Image Lab / visual pipeline.",
            "state": "connected" if krea else "missing",
            "credentials": {"configured": krea, "env_vars": ["KREA_API_KEY"], "key_prefix": _env_prefix("KREA_API_KEY")},
            "connect": {"type": "manual", "url": "https://krea.ai", "label": "Krea account"},
            "setup": {"auth_type": "API key", "steps": ["Set KREA_API_KEY on Railway."]},
        }
    )

    # Publish sandbox mode
    try:
        from _lib.publish_mode import get_publish_mode

        pub_mode = get_publish_mode()
    except Exception:
        pub_mode = "unknown"
    items.append(
        {
            "id": "publish_mode",
            "icon": "🧪",
            "name": "Publish mode",
            "category": "publish",
            "category_label": "Publish",
            "purpose": "sandbox = receipts only, no Postiz/GBP HTTP. live = real publish (Kyle gate).",
            "state": "connected" if pub_mode == "sandbox" else ("partial" if pub_mode == "live" else "missing"),
            "summary": pub_mode,
            "credentials": {"env_vars": ["PUBLISH_MODE"], "configured": True},
            "connect": {"type": "none", "label": f"Current: {pub_mode}"},
            "setup": {
                "auth_type": "Env flag",
                "steps": [
                    "Default PUBLISH_MODE=sandbox on Railway.",
                    "Only set PUBLISH_MODE=live after Postiz + channels verified.",
                ],
            },
        }
    )

    # Group by category
    order = ("publish", "analytics", "optional")
    labels = {
        "publish": "Publish",
        "analytics": "Analytics & data",
        "optional": "Optional / scouts",
    }
    by_cat: dict[str, list[dict[str, Any]]] = {k: [] for k in order}
    for it in items:
        by_cat.setdefault(it.get("category", "optional"), []).append(it)
    categories = [{"id": cid, "label": labels.get(cid, cid), "items": by_cat.get(cid, [])} for cid in order if by_cat.get(cid)]

    summary = {"connected": 0, "partial": 0, "degraded": 0, "missing": 0}
    for it in items:
        st = it.get("state", "missing")
        if st in summary:
            summary[st] += 1
        elif st == "connected":
            summary["connected"] += 1

    return {"categories": categories, "integrations": items, "summary": summary}
