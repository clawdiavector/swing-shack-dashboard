#!/usr/bin/env python3
"""
ig_insights_pull.py — Brand-scoped Instagram performance ingestion.

Pipeline per heidi.txt 2026-09-08 P0 Phase 1.4:

  per operating brand (swing-shack | stick | bag-drop):
    1. load data/integrations/<brand>/instagram.json
    2. resolve per-brand credentials (env → file → system_user fallback)
    3. validate connection (health_check_for_brand — token, page, ig_account, media endpoint)
    4. list recent media for the IG business account (paginated)
    5. pull per-media insights (media-type-aware metrics)
    6. map IG media → Campaign OS asset via:
         (a) data/meta-post-index.json by_media_id
         (b) data/publishing-references.json (Postiz back-map)
         (c) deterministic fallback by permalink/timestamp (skip if unsafe)
         unmatched → log + skip (NEVER fuzzy attribute)
    7. POST normalised records to /api/image/feedback/import-ig
       with brand_id and platform_post_id (the IG media ID)
    8. update data/integrations/<brand>/instagram.json sync timestamps

Failure semantics:
  - one bad media item never aborts the whole job
  - one broken operating brand never stops sync for the others
  - exit non-zero only on genuine job-level failure (e.g. all
    configured brands failed)
  - report partial success accurately per brand

Idempotency:
  - The server-side /api/image/feedback/import-ig uses brand +
    platform_post_id (IG media ID) as the dedup key in feedback
    storage. Re-running this script does NOT create duplicates.

NOT in scope (per heidi.txt):
  - Takomo. Takomo is NOT an operating brand.
  - Recreating Takomo as an operating brand.
  - Giving Takomo an Instagram connection.
  - Fuzzy matching that could attribute performance to wrong creative.

Usage:
  .venv/bin/python scripts/ig_insights_pull.py                    # all brands
  .venv/bin/python scripts/ig_insights_pull.py --brand swing-shack  # one brand
  .venv/bin/python scripts/ig_insights_pull.py --since-days 30   # time window
  .venv/bin/python scripts/ig_insights_pull.py --limit 50         # per-page cap
  .venv/bin/python scripts/ig_insights_pull.py --dry-run          # report, no writes
  .venv/bin/python scripts/ig_insights_pull.py --api-base URL     # override API base
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "campaign-os"))

# Default API base — Railway production. Override with --api-base.
DEFAULT_API_BASE = os.environ.get(
    "CAMPAIGN_OS_API_BASE",
    "https://swing-shack-dashboard-production.up.railway.app",
)

# Per heidi.txt: operating brands only.
OPERATING_BRANDS = ("swing-shack", "stick", "bag-drop")

# Media-type-aware metrics (Meta exposes different metrics per type).
IMAGE_METRICS = {"impressions", "reach", "likes", "comments", "shares", "saved"}
VIDEO_METRICS = IMAGE_METRICS | {"video_views", "ig_reels_avg_watch_time",
                                   "ig_reels_video_view_total_time"}

# Auth — for /api/image/feedback/import-ig. Local dev password;
# production uses CAMPAIGN_OS_AUTH env or session cookie.
DEFAULT_PASSWORD = os.environ.get("CAMPAIGN_OS_PASSWORD", "swing-shack-dev-2026")


def log(msg: str) -> None:
    """Single-line structured log line per heidi.txt spec."""
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}",
          flush=True)


def api_login(api_base: str, password: str) -> str:
    """Authenticate and return a session cookie value."""
    url = api_base.rstrip("/") + "/login"
    data = urllib.parse.urlencode({"password": password}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            cookie = r.headers.get("Set-Cookie", "")
            if "cos_session=" not in cookie:
                raise RuntimeError("login failed: no cos_session cookie")
            return cookie.split(";")[0]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"login failed: HTTP {e.code}") from e


def api_post(path: str, body: dict, cookie: str, api_base: str) -> dict:
    """POST JSON to the API."""
    url = api_base.rstrip("/") + path
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={
            "Content-Type": "application/json",
            "Cookie": cookie,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="ignore")[:500]
        raise RuntimeError(f"POST {path} → HTTP {e.code}: {body_text}") from e


# ─── MAPPING ─────────────────────────────────────────────────────────────────

def load_meta_post_index() -> dict:
    """Load data/meta-post-index.json. Returns dict with by_media_id + by_asset_id."""
    p = REPO / "data" / "meta-post-index.json"
    if not p.exists():
        return {"by_media_id": {}, "by_asset_id": {}, "unresolved": []}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {"by_media_id": {}, "by_asset_id": {}, "unresolved": []}


def load_publishing_references() -> dict:
    """Load data/publishing-references.json. Returns { postiz_id → ig_media_id }."""
    p = REPO / "data" / "publishing-references.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text())
        refs = d.get("references", []) or []
        out = {}
        for r in refs:
            postiz = r.get("postiz_post_id") or r.get("publishing_id") or r.get("postiz_id")
            media = r.get("platform_media_id") or r.get("ig_media_id")
            if postiz and media:
                out[str(postiz)] = str(media)
            asset = r.get("asset_id")
            if asset and media:
                # Reverse: asset_id → media_id
                out[f"asset:{asset}"] = str(media)
        return out
    except Exception:
        return {}


def build_mapper():
    """Build the IG media → Campaign OS asset mapper.

    Returns a function (ig_media_id: str) → dict | None.
    Resolution order:
      1. meta-post-index.json by_media_id
      2. publishing-references.json Postiz → IG back-map
      3. asset_id reverse lookup from publishing-references
      (no deterministic fallback — per heidi.txt: never fuzzy attribute)
    """
    index = load_meta_post_index()
    pub_refs = load_publishing_references()

    def mapper(ig_media_id: str) -> dict | None:
        # 1. by_media_id from meta-post-index
        rec = (index.get("by_media_id") or {}).get(str(ig_media_id))
        if rec:
            return {
                "asset_id": rec.get("asset_id"),
                "campaign_id": rec.get("campaign_id"),
                "postiz_post_id": rec.get("postiz_post_id"),
                "platform_media_id": str(ig_media_id),
                "publisher": "postiz",
                "source": "meta-post-index",
            }
        # 2/3. publishing-references lookup
        for k, v in pub_refs.items():
            if k.startswith("asset:"):
                continue
            if str(v) == str(ig_media_id):
                return {
                    "asset_id": None,
                    "campaign_id": None,
                    "postiz_post_id": k,
                    "platform_media_id": str(ig_media_id),
                    "publisher": "postiz",
                    "source": "publishing-references",
                }
        return None

    return mapper


# ─── INGESTION ───────────────────────────────────────────────────────────────

def normalise_insights_for_media(insights: dict, media_type: str) -> dict:
    """Map Meta's flat insight dict → Campaign OS feedback shape.

    Only includes metrics that Meta actually returned (non-None).
    Per heidi: do NOT fabricate zeros for unavailable metrics.
    """
    flat = insights.get("_flat") or {}
    out: dict[str, Any] = {}
    # Required shape per POST /api/image/feedback/import-ig
    metric_keys = ["impressions", "reach", "likes", "comments", "saves",
                    "shares", "link_clicks"]
    for k in metric_keys:
        v = flat.get(k if k != "saves" else "saved")
        if isinstance(v, (int, float)):
            out[k] = int(v)
    # Reels/Video extras (only for video/reels media types)
    if media_type in ("VIDEO", "REEL", "IG_REEL"):
        for k in ("video_views", "ig_reels_avg_watch_time",
                   "ig_reels_video_view_total_time"):
            v = flat.get(k)
            if isinstance(v, (int, float)):
                # Save video_views under a Campaign OS-friendly name
                if k == "video_views":
                    out["video_views"] = int(v)
                else:
                    out[k] = float(v)
    # Engagement rate if available
    er = flat.get("engagement_rate")
    if isinstance(er, (int, float)):
        out["engagement_rate"] = round(float(er), 3)
    return out


def sync_brand(brand_id: str, mapper, cookie: str, api_base: str,
                limit: int, since_days: int, dry_run: bool) -> dict:
    """Run the full ingestion for one operating brand. Returns result dict."""
    result = {
        "brand_id": brand_id,
        "status": None,  # success | partial_success | not_configured | error
        "media_discovered": 0,
        "insights_fetched": 0,
        "mapped": 0,
        "unmatched": 0,
        "feedback_imported": 0,
        "duplicates_skipped": 0,
        "errors": [],
        "duration_seconds": 0,
    }
    started = time.monotonic()
    # Import here so the rest of the script's CLI/parsing works even if
    # meta_api.py has a syntax error.
    from _lib.meta_api import (
        load_brand_integration,
        resolve_credentials_for_brand,
        list_recent_posts_for_brand,
        get_post_insights_for_brand,
        health_check_for_brand,
        MetaAuthError,
        MetaUpstreamError,
        MetaNetworkError,
    )
    cfg = load_brand_integration(brand_id)
    if not cfg.get("configured", False):
        result["status"] = "not_configured"
        result["duration_seconds"] = round(time.monotonic() - started, 2)
        log(f"  Brand: {brand_id}")
        log(f"  Status: not_configured")
        log(f"  Notes: {cfg.get('notes', '')}")
        return result

    creds = resolve_credentials_for_brand(brand_id, cfg)
    if not creds["token"]:
        result["status"] = "error"
        result["errors"].append("no_credentials_resolved")
        for e in creds["errors"]:
            result["errors"].append(e)
        result["duration_seconds"] = round(time.monotonic() - started, 2)
        log(f"  Brand: {brand_id}")
        log(f"  Status: error (no credentials)")
        log(f"  Errors: {result['errors']}")
        return result

    # Health check (token + page + ig_account + media_endpoint)
    health = health_check_for_brand(brand_id)
    if not health.get("healthy"):
        result["status"] = "error"
        for issue in health.get("issues", []):
            result["errors"].append(f"health:{issue}")
        result["duration_seconds"] = round(time.monotonic() - started, 2)
        log(f"  Brand: {brand_id}")
        log(f"  Status: error (unhealthy connection)")
        for chk_name, chk in health.get("checks", {}).items():
            log(f"    check {chk_name}: {chk.get('ok')} {chk.get('error', '')}")
        return result
    log(f"  Brand: {brand_id}")
    log(f"  Connection: healthy (mode={creds['mode']})")

    # Pull recent media (paginated — follow Meta's next cursor up to limit pages)
    all_media: list[dict] = []
    cursor: str | None = None
    pages = 0
    max_pages = 10  # safety cap
    while pages < max_pages:
        try:
            page_kwargs = {}
            # list_recent_posts_for_brand doesn't accept cursor — call _graph_get directly
            # via the imported module.
            from _lib import meta_api as _ma
            params = {"fields": "id,caption,media_type,media_url,permalink,"
                                  "thumbnail_url,timestamp,username",
                       "limit": min(int(limit), 100)}
            if cursor:
                params["after"] = cursor
            out = _ma._graph_get(
                f"/{cfg['ig_business_account_id']}/media", params,
                use_page_token=False,
            )
        except (MetaAuthError, MetaUpstreamError, MetaNetworkError) as e:
            result["status"] = "partial_success" if all_media else "error"
            result["errors"].append(f"media_pull:{type(e).__name__}:{e}")
            break
        media = out.get("data", [])
        all_media.extend(media)
        pages += 1
        cursor = (out.get("paging") or {}).get("cursors", {}).get("after")
        if not cursor:
            break
    result["media_discovered"] = len(all_media)
    log(f"  Media discovered: {len(all_media)} ({pages} page(s))")

    # Time-window filter (--since-days)
    cutoff = datetime.now(timezone.utc) - timedelta(days=int(since_days))
    filtered = []
    for m in all_media:
        ts = m.get("timestamp")
        if not ts:
            filtered.append(m)
            continue
        try:
            media_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if media_dt >= cutoff:
                filtered.append(m)
        except Exception:
            filtered.append(m)
    if len(filtered) != len(all_media):
        log(f"  Filtered to last {since_days} days: {len(filtered)} media items")
        all_media = filtered

    # Pull insights + map + import
    records_to_import: list[dict] = []
    unmatched_log: list[dict] = []
    for m in all_media:
        media_id = m.get("id")
        media_type = m.get("media_type", "IMAGE")
        if not media_id:
            continue
        # Skip non-numeric IDs (defensive)
        if not str(media_id).isdigit():
            result["unmatched"] += 1
            unmatched_log.append({"media_id": media_id, "reason": "non_numeric_id"})
            continue
        # Pull insights
        try:
            ins = get_post_insights_for_brand(brand_id, media_id,
                                                media_type=media_type)
            result["insights_fetched"] += 1
        except (MetaAuthError, MetaUpstreamError, MetaNetworkError) as e:
            result["errors"].append(f"insights:{media_id}:{type(e).__name__}:{e}")
            result["unmatched"] += 1
            unmatched_log.append({"media_id": media_id, "reason": f"insights_failed:{e}"})
            continue
        # Normalise
        sig = normalise_insights_for_media(ins, media_type)
        # Map to Campaign OS asset
        mapping = mapper(media_id)
        if not mapping:
            result["unmatched"] += 1
            unmatched_log.append({"media_id": media_id,
                                   "reason": "no_asset_mapping",
                                   "caption_preview": (m.get("caption") or "")[:80]})
            continue
        result["mapped"] += 1
        # Build the feedback record
        asset_id = mapping.get("asset_id") or f"unmapped-{brand_id}-{media_id}"
        records_to_import.append({
            "image_id": asset_id,
            "post_id": media_id,
            "platform": "instagram",
            "captured_at": time.time(),
            "ig_media_id": media_id,
            "permalink": m.get("permalink"),
            "media_type": media_type,
            "ig_timestamp": m.get("timestamp"),
            "captured_signal": sig,
            "mapping_source": mapping.get("source"),
            "postiz_post_id": mapping.get("postiz_post_id"),
            "campaign_id": mapping.get("campaign_id"),
        })

    # Send to feedback endpoint
    if not dry_run and records_to_import:
        try:
            resp = api_post(
                "/api/image/feedback/import-ig",
                {"brand": brand_id, "records": records_to_import},
                cookie=cookie, api_base=api_base,
            )
            result["feedback_imported"] = resp.get("imported", 0)
            if resp.get("errors"):
                for e in resp["errors"]:
                    result["errors"].append(f"feedback:{e}")
            # Compute duplicates skipped = mapped - imported (idempotency rejections)
            result["duplicates_skipped"] = max(
                0, result["mapped"] - result["feedback_imported"]
            )
        except Exception as e:
            result["errors"].append(f"feedback_post:{e}")
    elif dry_run:
        result["feedback_imported"] = 0
        result["duplicates_skipped"] = 0

    # Update config sync timestamps
    if not dry_run:
        cfg["last_media_sync"] = datetime.now(timezone.utc).isoformat()
        cfg["last_insights_sync"] = datetime.now(timezone.utc).isoformat()
        cfg_path = REPO / "data" / "integrations" / brand_id / "instagram.json"
        try:
            cfg_path.write_text(json.dumps(cfg, indent=2))
        except Exception as e:
            result["errors"].append(f"config_write:{e}")

    # Final status
    if result["errors"] and result["feedback_imported"] > 0:
        result["status"] = "partial_success"
    elif result["errors"]:
        result["status"] = "error"
    else:
        result["status"] = "success"
    result["duration_seconds"] = round(time.monotonic() - started, 2)

    log(f"  Insights fetched: {result['insights_fetched']}")
    log(f"  Mapped: {result['mapped']}")
    log(f"  Unmatched: {result['unmatched']}")
    log(f"  Feedback imported: {result['feedback_imported']}")
    log(f"  Duplicates skipped: {result['duplicates_skipped']}")
    log(f"  Errors: {len(result['errors'])}")
    log(f"  Duration: {result['duration_seconds']}s")
    if unmatched_log:
        log(f"  Unmatched sample (first 5):")
        for u in unmatched_log[:5]:
            log(f"    {u}")
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--brand", choices=OPERATING_BRANDS + ("all",),
                    default="all")
    p.add_argument("--limit", type=int, default=50,
                    help="Meta media limit per page (max 100)")
    p.add_argument("--since-days", type=int, default=30,
                    help="Time window in days (Meta returns all if filter fails)")
    p.add_argument("--dry-run", action="store_true",
                    help="Discover + map but do not POST feedback")
    p.add_argument("--api-base", default=DEFAULT_API_BASE,
                    help="Campaign OS API base URL")
    p.add_argument("--password", default=DEFAULT_PASSWORD,
                    help="Campaign OS login password (or env CAMPAIGN_OS_PASSWORD)")
    args = p.parse_args()

    brands = OPERATING_BRANDS if args.brand == "all" else (args.brand,)
    log(f"ig_insights_pull starting — brands={list(brands)} "
        f"limit={args.limit} since_days={args.since_days} dry_run={args.dry_run}")

    mapper = build_mapper()
    cookie = api_login(args.api_base, args.password)

    results: list[dict] = []
    any_real_failure = False
    for brand_id in brands:
        try:
            r = sync_brand(brand_id, mapper, cookie, args.api_base,
                            args.limit, args.since_days, args.dry_run)
        except Exception as e:
            log(f"  Brand: {brand_id}")
            log(f"  Status: error (job-level exception)")
            log(f"  Exception: {type(e).__name__}: {e}")
            r = {"brand_id": brand_id, "status": "error",
                  "errors": [f"job_exception:{type(e).__name__}:{e}"],
                  "media_discovered": 0, "insights_fetched": 0,
                  "mapped": 0, "unmatched": 0, "feedback_imported": 0,
                  "duplicates_skipped": 0, "duration_seconds": 0}
        results.append(r)
        if r["status"] == "error":
            any_real_failure = True

    log("\n=== SUMMARY ===")
    for r in results:
        log(f"  {r['brand_id']}: {r['status']} | "
            f"media={r['media_discovered']} insights={r['insights_fetched']} "
            f"mapped={r['mapped']} unmatched={r['unmatched']} "
            f"imported={r['feedback_imported']} dup={r['duplicates_skipped']} "
            f"err={len(r.get('errors', []))} dur={r['duration_seconds']}s")

    # Exit non-zero only on genuine job-level failure
    if any_real_failure and all(r["status"] == "error" for r in results):
        log("\nJob-level failure — exiting 1")
        return 1
    log("\nDone — exiting 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
