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
    "windsor": ("windsor_refresh",),
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
    "windsor": "meta-ads.json",
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
) -> tuple[str, str]:
    """Return (state, health) — degraded collapses into partial per P1a contract."""
    if live_ok is True:
        return "connected", "ok"
    if live_ok is False and creds_ok:
        return "partial", "degraded"
    if creds_ok and not partial:
        return "connected", "ok"
    if creds_ok or partial:
        return "partial", "ok"
    return "missing", "ok"


def _job_activity_for_brand(job_names: tuple[str, ...], brand_id: str) -> dict[str, Any]:
    try:
        from _lib.jobs import ledger
        from _lib.jobs.runner import _last_success, verdict_for
    except Exception:
        return {}
    now = _utc_now()
    last_at: Optional[str] = None
    verdict: Optional[str] = None
    for name in job_names:
        rows = ledger.read_rows(name, brand=brand_id)
        if not rows:
            continue
        v = verdict_for(name, rows, now=now, brand=brand_id)
        success = _last_success(rows)
        finished = (success or {}).get("finished") or (success or {}).get("started")
        if finished and (last_at is None or finished > last_at):
            last_at = finished
            verdict = v
    return {"last_success_at": last_at, "job_verdict": verdict, "last_used_label": _age_label(last_at)}


def _integration_row(
    brand_id: str,
    integration_id: str,
    *,
    label: str,
    icon: str,
    category: str,
    purpose: str,
    connect: dict[str, Any],
    setup: dict[str, Any],
) -> dict[str, Any]:
    from _lib.jobs.brand_lanes import integration_applies, integration_state, load_brands_registry

    reg = load_brands_registry()
    scope = ((reg.get("brands") or {}).get(brand_id) or {}).get("integration_scope") or {}
    scope_entry = scope.get(integration_id) or {}
    applies = integration_applies(brand_id, integration_id)
    state = integration_state(brand_id, integration_id)
    health = "ok"

    job_names = _JOB_BY_INTEGRATION.get(integration_id, ())
    activity = _job_activity_for_brand(job_names, brand_id) if job_names else {}
    data_rel = _DATA_FILE_BY_INTEGRATION.get(integration_id)
    file_at = _data_file_mtime(data_rel) if data_rel else None
    last_used = activity.get("last_success_at") or file_at

    if state == "connected" and activity.get("job_verdict") not in (None, "OK", "SKIPPED"):
        state = "partial"
        if activity.get("job_verdict") in ("LATE", "FAILED"):
            health = "degraded"

    env_vars = list(scope_entry.get("env") or [])
    creds_ok = state in ("connected", "partial")

    return {
        "id": integration_id,
        "brand": brand_id,
        "icon": icon,
        "name": label,
        "category": category,
        "purpose": purpose,
        "state": state,
        "health": health,
        "visible": True,
        "applies": applies,
        "na_reason": scope_entry.get("na_reason") if not applies else None,
        "last_used_at": last_used,
        "last_used_label": _age_label(last_used),
        "job_verdict": activity.get("job_verdict"),
        "credentials": {
            "configured": creds_ok,
            "env_vars": env_vars,
            "key_prefix": _env_prefix(env_vars[0]) if env_vars else None,
        },
        "connect": connect,
        "setup": setup,
    }


def build_brand_integrations(brand_id: str) -> dict[str, Any]:
    """Brand-aware integration rows — every catalog key, all visible."""
    from _lib.jobs.brand_lanes import load_brands_registry

    reg = load_brands_registry()
    catalog = reg.get("integrations") or {}
    meta = catalog.get("meta") or {}
    items: list[dict[str, Any]] = []

    items.append(
        _integration_row(
            brand_id,
            "postiz",
            label="Postiz (publish hub)",
            icon="📮",
            category="publish",
            purpose="Cross-post to Instagram, Facebook, TikTok, X, GBP, YouTube, LinkedIn.",
            connect={"type": "oauth", "url": f"/api/postiz/oauth/login?brand={brand_id}", "label": "Connect Postiz"},
            setup={
                "auth_type": "API key + OAuth client",
                "steps": [
                    f"Set POSTIZ_API_KEY_{brand_id.upper().replace('-', '_')} or shared POSTIZ_API_KEY on Railway.",
                    "Connect button runs Postiz OAuth; channels list refreshes on this page.",
                ],
            },
        )
    )
    items.append(
        _integration_row(
            brand_id,
            "meta",
            label=meta.get("label") or "Meta (IG + FB)",
            icon="📊",
            category="publish",
            purpose="IG + Facebook analytics and insights.",
            connect={"type": "portal", "url": "/meta-portal", "label": "Meta setup portal"},
            setup={
                "auth_type": "System user token",
                "steps": [
                    "Set brand-scoped Meta env vars from integration_scope in brands.json.",
                    "Use Refresh from Meta on Connected Accounts after credentials are set.",
                ],
            },
        )
    )
    items.append(
        _integration_row(
            brand_id,
            "gbp",
            label="Google Business Profile",
            icon="📍",
            category="publish",
            purpose="GBP daily plans, location insights, local SEO posts.",
            connect={"type": "oauth", "url": f"/api/gbp/oauth/login?brand={brand_id}", "label": "Connect GBP"},
            setup={
                "auth_type": "Google OAuth (business.manage scope)",
                "steps": [
                    "Click Connect → sign in as GBP owner → token stored on DATA_DIR volume.",
                ],
            },
        )
    )

    for iid, icon, purpose, connect in (
        ("ga4", "📈", "Site traffic and conversion analytics.", {"type": "portal", "url": "/meta-portal", "label": "GA4 setup portal"}),
        ("gsc", "🔎", "Search queries, impressions, clicks.", {"type": "manual", "url": "https://search.google.com/search-console", "label": "Open Search Console"}),
        ("windsor", "💰", "Paid media spend and campaign metrics.", {"type": "manual", "url": "https://windsor.ai", "label": "Windsor dashboard"}),
        ("ubersuggest", "📊", "Domain keyword rankings and SEO snapshots.", {"type": "none", "label": "Configured on Railway"}),
        ("youtube", "▶️", "Public golf trend videos for Signal radar.", {"type": "manual", "url": "https://console.cloud.google.com/apis/library/youtube.googleapis.com", "label": "Enable YouTube API"}),
        ("krea", "🎨", "AI image generation for Image Lab.", {"type": "manual", "url": "https://krea.ai", "label": "Krea account"}),
        ("google_drive", "📁", "Ingest brand folders from Drive.", {"type": "portal", "url": "/secrets-sync", "label": "Secrets sync"}),
    ):
        entry = catalog.get(iid) or {}
        items.append(
            _integration_row(
                brand_id,
                iid,
                label=entry.get("label") or iid,
                icon=icon,
                category="analytics" if iid not in ("youtube", "krea", "google_drive") else "optional",
                purpose=purpose,
                connect=connect,
                setup={"auth_type": "See brands.json integration_scope", "steps": [f"Configure env vars for {brand_id}."]},
            )
        )

    summary = {"connected": 0, "partial": 0, "missing": 0, "na": 0}
    for it in items:
        st = it.get("state", "missing")
        if st in summary:
            summary[st] += 1

    return {"brand": brand_id, "integrations": items, "summary": summary}


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
            )[0],
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
    gsc_creds = _env_any("GSC_SITE_URL", "SEARCH_CONSOLE_SITE_URL") and ga4_creds
    gsc_activity = _job_activity(_JOB_BY_INTEGRATION["gsc"])
    gsc_file_at = _data_file_mtime(_DATA_FILE_BY_INTEGRATION["gsc"])
    gsc_last = gsc_activity.get("last_success_at") or gsc_file_at
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
            )[0],
            "last_used_at": gsc_last,
            "last_used_label": _age_label(gsc_last),
            "job_verdict": gsc_activity.get("job_verdict"),
            "credentials": {
                "configured": bool(gsc_creds),
                "env_vars": ["GSC_SITE_URL", "GA4 service account (shared)"],
            },
            "connect": {"type": "manual", "url": "https://search.google.com/search-console", "label": "Open Search Console"},
            "setup": {
                "auth_type": "Service account (same as GA4) + Search Console user",
                "steps": [
                    "Enable Search Console API in the same GCP project as GA4.",
                    "In Search Console → Settings → Users → add the GA4 service account email as a user.",
                    "Set GSC_SITE_URL=https://swingshack.co.za/ on Railway (default if unset).",
                    "gsc_report job writes search-console.json on success.",
                ],
            },
        }
    )

    # Windsor
    windsor_creds = _env_any("WINDSOR_API_KEY", "WINDSOR_API_KEY_FILE")
    windsor_activity = _job_activity(_JOB_BY_INTEGRATION["windsor"])
    windsor_file_at = _data_file_mtime(_DATA_FILE_BY_INTEGRATION["windsor"])
    windsor_last = windsor_activity.get("last_success_at") or windsor_file_at
    items.append(
        {
            "id": "windsor",
            "icon": "💰",
            "name": "Windsor.ai (Meta + Google Ads)",
            "category": "analytics",
            "category_label": "Analytics & data",
            "purpose": "Live paid media spend and campaign metrics (meta-ads.json, google-ads.json).",
            "state": _state_from_flags(
                creds_ok=windsor_creds,
                partial=windsor_creds and windsor_activity.get("job_verdict") == "LATE",
            )[0],
            "last_used_at": windsor_last,
            "last_used_label": _age_label(windsor_last),
            "job_verdict": windsor_activity.get("job_verdict"),
            "credentials": {
                "configured": windsor_creds,
                "env_vars": ["WINDSOR_API_KEY", "WINDSOR_API_KEY_FILE"],
                "key_prefix": _env_prefix("WINDSOR_API_KEY"),
            },
            "connect": {"type": "manual", "url": "https://windsor.ai", "label": "Windsor dashboard"},
            "setup": {
                "auth_type": "API key",
                "steps": [
                    "Copy API key from Windsor.ai account settings.",
                    "Railway → WINDSOR_API_KEY=<key>.",
                    "windsor_refresh job pulls live Meta/Google ads on schedule.",
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
            "state": _state_from_flags(creds_ok=yt_creds, partial=not yt_creds)[0],
            "last_used_at": yt_last,
            "last_used_label": _age_label(yt_last),
            "job_verdict": yt_activity.get("job_verdict"),
            "credentials": {
                "configured": yt_creds,
                "env_vars": ["YOUTUBE_API_KEY"],
                "key_prefix": _env_prefix("YOUTUBE_API_KEY"),
            },
            "connect": {"type": "manual", "url": "https://console.cloud.google.com/apis/library/youtube.googleapis.com", "label": "Enable YouTube API"},
            "setup": {
                "auth_type": "API key",
                "steps": [
                    "GCP → enable YouTube Data API v3 → create API key.",
                    "Railway → YOUTUBE_API_KEY=<key>.",
                    "Optional — skip if you do not want YouTube in Trend Catcher.",
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
            )[0],
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

    # Google Drive
    try:
        from _lib import google_drive as _gd

        drive = _gd.status()
    except Exception as exc:
        drive = {"connected": False, "has_oauth_client": False, "has_token": False, "auth_error": str(exc)}
    items.append(
        {
            "id": "google_drive",
            "icon": "📁",
            "name": "Google Drive (brand assets)",
            "category": "optional",
            "category_label": "Optional scouts",
            "purpose": "Ingest brand folders from Drive into brand-directory (images/docs).",
            "state": "connected" if drive.get("connected") else ("partial" if drive.get("has_token") or drive.get("has_oauth_client") else "missing"),
            "last_used_at": None,
            "last_used_label": None,
            "credentials": {
                "oauth_client": bool(drive.get("has_oauth_client")),
                "token_present": bool(drive.get("has_token")),
                "env_vars": ["GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_DRIVE_TOKEN"],
            },
            "connect": {"type": "portal", "url": "/secrets-sync", "label": "Secrets sync"},
            "setup": {
                "auth_type": "OAuth (Drive readonly)",
                "steps": [
                    "GCP → enable Drive API → Desktop OAuth client JSON.",
                    "Upload client JSON via /secrets-sync or set GOOGLE_OAUTH_CLIENT_SECRET path.",
                    "Run one-time OAuth dance (Mac: google_drive.setup_interactive).",
                    "Token stored at google-drive-token.json on credentials volume.",
                ],
            },
            "error": drive.get("auth_error"),
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

    summary = {"connected": 0, "partial": 0, "missing": 0, "na": 0}
    for it in items:
        st = it.get("state", "missing")
        if st in summary:
            summary[st] += 1
        elif st == "connected":
            summary["connected"] += 1

    return {"categories": categories, "integrations": items, "summary": summary}
