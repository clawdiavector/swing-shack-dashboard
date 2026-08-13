"""Ad correlation engine — joins GA4 traffic with IG post timestamps + ad data.

Truth-before-cleverness: every verdict cites the actual timestamp + data source.
If we don't have ad-platform data, we say so — never fabricate "the ad worked".

Three correlation layers:
  1. CONTENT-TRAFFIC: when did a post go live vs when did traffic spike on
     the matching landing page? Match within ±24h. Verdict: "Post X went
     live Mon 9am; sessions on /page/ spiked Mon +212%. Likely content
     drove the spike."
  2. AD-TRAFFIC: when did a paid campaign go live vs when did traffic spike
     on the matching landing page? Only runs if Google Ads / Meta Ads
     data is present. Otherwise returns "Ad data not configured".
  3. ORGANIC-ONLY: GA4 source/medium breakdown shows "what % of traffic
     was organic vs referral vs paid". Always runs.

Why this matters: Christelle asked "if ad went live Monday and traffic
spiked Monday, show it could be the ad". This module answers exactly that
question with explicit timestamping instead of vibes.

Layered data model:
  - GA4 (daily sessions)     → from data/ga4-metrics.json
  - IG posts (timestamps)    → from data/instagram.json + Graph API
  - Content publishes        → from data/published-items.json (if exists)
  - Google Ads               → from data/google-ads.json (if exists)
  - Meta Ads                 → from data/meta-ads.json (if exists)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _data_dir() -> Path:
    """Resolve DATA_DIR at call time so tests can change it without re-import.

    On Railway, DATA_DIR defaults to /data (an empty volume) — the real
    data lives in the bundled repo copy at REPO_ROOT/data. We probe both
    and pick whichever has the most JSON data, so a fresh deploy with an
    empty volume still reads the bundled repo.
    """
    runtime = Path(os.environ.get("DATA_DIR", "/data"))
    # BUNDLED_DATA_DIR = REPO_ROOT/data — set by app.py before this is imported.
    bundled = Path(os.environ.get("BUNDLED_DATA_DIR", str(runtime)))
    if runtime == bundled:
        return runtime
    # Score each root by JSON count so the populated one wins.
    def _score(root: Path) -> int:
        if not root.is_dir():
            return 0
        total = 0
        for _dir, _dirs, files in os.walk(root):
            total += sum(1 for f in files if f.endswith(".json"))
        return total
    r_score = _score(runtime)
    b_score = _score(bundled)
    return runtime if r_score >= b_score else bundled


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _load_ig_posts() -> tuple[list[dict[str, Any]], str | None]:
    """Load Instagram posts from whichever file is present on disk.

    The platform has had three different IG data stores over time:
      - data/instagram.json                  (canonical, written by ingestion)
      - data/analytics/instagram-analytics.json (largest historical archive)
      - data/ig-analytics.json               (lightweight daily tracker)

    We try them in priority order and normalise the post shape so callers
    can treat them uniformly. Returns (posts, source_label).
    """
    base = _data_dir()
    candidates = [
        base / "instagram.json",
        base / "analytics" / "instagram-analytics.json",
        base / "ig-analytics.json",
    ]
    for path in candidates:
        data = _read_json(path)
        if not data or not isinstance(data, dict):
            continue
        posts = data.get("posts")
        if not isinstance(posts, list) or not posts:
            continue
        # Normalise each post into the shape insights v2 expects.
        normalised: list[dict[str, Any]] = []
        for p in posts:
            if not isinstance(p, dict):
                continue
            # Field aliases across stores.
            er = p.get("engagementRate")
            if er is None:
                er = p.get("engagement_rate", 0)
            try:
                er_val = float(er or 0)
            except (TypeError, ValueError):
                er_val = 0.0
            normalised.append({
                "id": p.get("id") or p.get("postId"),
                "timestamp": p.get("timestamp"),
                "engagementRate": er_val,
                "permalink": p.get("permalink") or p.get("postUrl") or "",
                "thumbnail_url": p.get("thumbnail_url") or p.get("thumbnailUrl")
                    or p.get("media_url") or p.get("mediaUrl") or "",
                "media_type": p.get("media_type") or p.get("mediaType") or "IMAGE",
                "caption_excerpt": (
                    p.get("caption_excerpt") or p.get("captionPreview")
                    or p.get("hook_text") or p.get("caption") or ""
                )[:140],
                # camelCase aliases: instagram-analytics.json (the largest IG
                # archive) uses Meta's Graph API field names — likeCount /
                # commentsCount — not the snake_case the snake_case-first
                # alias list expected. Without these the Insights Top Posts
                # card silently shows "0 likes" and "(no caption)" for posts
                # that actually have 16 likes and a real caption.
                "like_count": int(p.get("like_count") or p.get("likeCount")
                                   or p.get("likes") or 0),
                "comments_count": int(p.get("comments_count") or p.get("commentsCount")
                                      or p.get("comments") or 0),
                "reach": int(p.get("reach") or p.get("views") or 0),
                "saves": int(p.get("saves") or p.get("saved") or 0),
                "shares": int(p.get("shares") or 0),
            })
        if normalised:
            label = str(path.relative_to(base)) if path.is_relative_to(base) else str(path)
            return normalised, label
    return [], None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # ISO 8601 with optional Z
        v = value.replace("Z", "+00:00") if value.endswith("Z") else value
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _to_iso(dt: datetime) -> str:
    return dt.isoformat()


def _spike_pct(value: float, baseline: float) -> float:
    if baseline <= 0:
        return 0.0
    return round(((value - baseline) / baseline) * 100, 1)


def get_content_traffic_correlations(days: int = 30) -> dict[str, Any]:
    """JOIN: when did IG posts go live vs when did GA4 see a traffic spike?

    Returns:
      {
        ok: True,
        matches: [{
          date, post_id, post_caption_excerpt, post_permalink,
          post_engagement, ga4_sessions_on_day, ga4_sessions_baseline,
          lift_pct, verdict: "likely content drove spike" | "spike not
          explained by content", confidence: "high"|"medium"|"low"
        }],
        unmatched_spikes: [...],   # days where traffic spiked but we have
                                   # no matching content
        _meta: { posts_scanned, days_covered, ga4_window }
      }
    """
    ga4 = _read_json(_data_dir() / "ga4-metrics.json") or {}
    if not isinstance(ga4, dict):
        ga4 = {}
    posts, ig_source = _load_ig_posts()
    # Page-level sessions from GA4 (pages[] has path + sessions + engRate)
    pages = ga4.get("pages", []) if isinstance(ga4, dict) else []
    # No daily sessions time series in the current shape — we work with
    # the 7-day totals from `data_window` and surface what we can.

    matches: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []

    if not posts:
        return {
            "ok": True,
            "matches": [],
            "unmatched_spikes": [],
            "_meta": {
                "posts_scanned": 0,
                "days_covered": days,
                "ga4_window": ga4.get("data_window"),
                "reason": "No IG posts found in instagram.json / analytics/instagram-analytics.json / ig-analytics.json",
            },
        }

    # No daily time-series GA4 data → use the 7-day totals as proxy.
    # Tell the user clearly in _meta that the verdict is "directional" only.
    return {
        "ok": True,
        "matches": [],
        "unmatched_spikes": [],
        "_meta": {
            "posts_scanned": len(posts),
            "days_covered": days,
            "ga4_window": ga4.get("data_window"),
            "ga4_total_sessions": ga4.get("total_sessions"),
            "top_pages": [{"path": p.get("path"), "sessions": p.get("sessions"),
                            "engagement": p.get("engRate")} for p in pages[:10]],
            "reason": (
                "GA4 daily time-series not yet wired; verdict below uses 7-day "
                "aggregate. Add daily breakdown to ga4-metrics.json for per-day "
                "correlation. Top IG posts and top GA4 pages returned for "
                "manual cross-reference."
            ),
            "top_instagram_posts": [
                {
                    "id": p.get("id"),
                    "timestamp": p.get("timestamp"),
                    "engagementRate": p.get("engagementRate"),
                    "permalink": p.get("permalink"),
                    "thumbnail": p.get("thumbnail_url") or p.get("media_url"),
                    "caption_excerpt": (p.get("caption") or "")[:80],
                }
                for p in sorted(
                    [p for p in posts if isinstance(p, dict)],
                    key=lambda x: float(x.get("engagementRate") or 0),
                    reverse=True,
                )[:8]
            ],
        },
    }


def get_ad_correlation_verdicts(days: int = 30) -> dict[str, Any]:
    """JOIN: when did a paid campaign go live vs when did traffic spike?

    Returns structured verdicts when ad data is available, OR a clean
    "not configured" payload when not. Never fabricates.

    Returns:
      {
        ok: True,
        configured: bool,  # at least one ad platform has data
        google_ads: { configured, campaigns: [...], verdicts: [...] },
        meta_ads:   { configured, campaigns: [...], verdicts: [...] },
        combined_summary: "..."  # 1-line layman explanation
      }
    """
    gads_data = _read_json(_data_dir() / "google-ads.json") or {}
    if not isinstance(gads_data, dict):
        gads_data = {}
    mads_data = _read_json(_data_dir() / "meta-ads.json") or {}
    if not isinstance(mads_data, dict):
        mads_data = {}
    ga4 = _read_json(_data_dir() / "ga4-metrics.json") or {}
    if not isinstance(ga4, dict):
        ga4 = {}

    gads_configured = bool(gads_data.get("campaigns"))
    mads_configured = bool(mads_data.get("campaigns"))

    # Build per-platform verdicts
    def _verdicts_for(platform_data: dict, platform_name: str) -> dict:
        if not platform_data.get("campaigns"):
            return {
                "configured": False,
                "reason": (
                    f"{platform_name} data not present. To wire: add "
                    f"data/{platform_name.lower().replace(' ','-')}.json "
                    "with shape {campaigns: [{id,name,start_date,end_date,"
                    "spend,clicks,impressions,landing_page}]} or set "
                    f"{platform_name.upper().replace(' ','_')}_TOKEN env var"
                ),
                "campaigns": [],
                "verdicts": [],
            }
        # Compute simple verdict: campaign went live + landing page sessions.
        # GA4 may emit MULTIPLE rows for the same path (one per date window), so
        # we SUM matching sessions across all rows to give an honest total instead
        # of silently picking the first match and reporting the same number for
        # every campaign. We also compute clicks:sessions ratio and cost:session
        # so the verdict says something actionable instead of a static number.
        campaigns = platform_data.get("campaigns", [])
        pages = (ga4.get("pages", []) if isinstance(ga4, dict) else [])
        verdicts = []
        for c in campaigns:
            lp = c.get("landing_page", "")
            matching_pages = [p for p in pages if p.get("path") == lp]
            total_sessions = sum(
                (p.get("sessions") or 0) for p in matching_pages
            )
            eng_rates = []
            for p in matching_pages:
                er = p.get("engRate")
                if er is None:
                    continue
                if isinstance(er, (int, float)):
                    eng_rates.append(float(er))
                elif isinstance(er, str):
                    stripped = er.replace("%", "").strip()
                    try:
                        eng_rates.append(float(stripped))
                    except ValueError:
                        continue
            avg_eng = (sum(eng_rates) / len(eng_rates)) if eng_rates else None
            clicks = c.get("clicks")
            spend = c.get("spend")
            try:
                cps = round(float(spend) / float(total_sessions), 2) if (spend not in (None, "", 0) and total_sessions) else None
            except (TypeError, ValueError):
                cps = None
            try:
                ctr_pct = round((float(clicks) / float(total_sessions)) * 100, 1) if (clicks not in (None, "") and total_sessions) else None
            except (TypeError, ValueError, ZeroDivisionError):
                ctr_pct = None
            # Verdict string: prefer the enriched one (clicks→sessions ratio +
            # cost-per-session) when we have both numbers. Falls back to the
            # plain "X clicks, Y sessions" line when one side is missing.
            if matching_pages and total_sessions:
                base = (
                    f"Campaign '{c.get('name')}' spent {spend or '—'} "
                    f"and drove {clicks or '—'} clicks to {lp}. "
                    f"GA4 shows {total_sessions} sessions on that page"
                )
                if ctr_pct is not None:
                    base += f" (clicks were {ctr_pct}% of sessions)"
                if cps is not None:
                    base += f" - R{cps} per session"
                base += "."
                verdict = base
            elif matching_pages:
                verdict = (
                    f"Campaign '{c.get('name')}' spent {spend or '—'} and drove "
                    f"{clicks or '—'} clicks to {lp}. GA4 has the page in its "
                    f"index but no session count yet for that path."
                )
            else:
                verdict = (
                    f"Campaign '{c.get('name')}' spent {spend or '—'} and drove "
                    f"{clicks or '—'} clicks to {lp}. GA4 has no data for that "
                    f"page yet — could be a tracking gap or a low-traffic URL."
                )
            verdicts.append({
                "campaign_id": c.get("id"),
                "campaign_name": c.get("name"),
                "start_date": c.get("start_date"),
                "end_date": c.get("end_date"),
                "spend": spend,
                "clicks": clicks,
                "impressions": c.get("impressions"),
                "landing_page": lp,
                "matching_page_sessions": total_sessions,
                "matching_page_engagement": avg_eng,
                "cost_per_session": cps,
                "clicks_to_sessions_pct": ctr_pct,
                "verdict": verdict,
            })
        return {"configured": True, "campaigns": campaigns, "verdicts": verdicts}

    gads_block = _verdicts_for(gads_data, "Google Ads")
    mads_block = _verdicts_for(mads_data, "Meta Ads")

    if not gads_configured and not mads_configured:
        summary = (
            "Ad data not configured yet. To see 'did the ad drive this spike' "
            "answers: add data/google-ads.json and/or data/meta-ads.json (see "
            "each block below for the exact shape), or wire live API tokens."
        )
    elif gads_configured and not mads_configured:
        summary = f"Google Ads wired ({len(gads_block['campaigns'])} campaigns); Meta Ads not yet."
    elif mads_configured and not gads_configured:
        summary = f"Meta Ads wired ({len(mads_block['campaigns'])} campaigns); Google Ads not yet."
    else:
        summary = (
            f"Both platforms wired — Google Ads: {len(gads_block['campaigns'])}, "
            f"Meta Ads: {len(mads_block['campaigns'])} campaigns."
        )

    return {
        "ok": True,
        "configured": gads_configured or mads_configured,
        "google_ads": gads_block,
        "meta_ads": mads_block,
        "combined_summary": summary,
    }


def get_top_instagram_posts(limit: int = 8) -> dict[str, Any]:
    """Surface top IG posts with thumbnails + engagement + plain-English verdict.

    Used by Insights v2 'Top Instagram Posts' card. Always runs (just reads
    instagram.json). When the file is missing, returns empty + reason.

    Returns:
      {
        ok: True,
        posts: [{
          id, timestamp, engagementRate, permalink, thumbnail_url,
          media_type, caption_excerpt, like_count, comments_count,
          verdict: "Above average" | "Top performer" | "Below average",
          plain_english: "This post got 3.2x more engagement than your average..."
        }],
        _meta: { total_scanned, average_engagement, source }
      }
    """
    ig_data = _read_json(_data_dir() / "instagram.json") or {}
    if not isinstance(ig_data, dict):
        ig_data = {}
    # Prefer the larger/more-complete IG store if it exists on disk.
    _fallback_posts, ig_source = _load_ig_posts()
    if _fallback_posts and (not ig_data.get("posts") or len(_fallback_posts) > len(ig_data.get("posts", []))):
        ig_data = {"posts": _fallback_posts}
    posts = ig_data.get("posts", []) if isinstance(ig_data, dict) else []
    # Track the actual source so the response is honest about where data came from.
    actual_source = ig_source or "instagram.json"
    if not posts:
        return {
            "ok": True,
            "posts": [],
            "_meta": {
                "total_scanned": 0,
                "average_engagement": None,
                "source": actual_source,
                "reason": "No posts in any IG store yet. Once IG data syncs, top posts appear here.",
            },
        }
    scored = []
    total_er = 0.0
    for p in posts:
        if not isinstance(p, dict):
            continue
        try:
            er = float(p.get("engagementRate") or 0)
        except (TypeError, ValueError):
            er = 0.0
        total_er += er
        scored.append({**p, "_er": er})
    if not scored:
        return {"ok": True, "posts": [], "_meta": {"total_scanned": 0, "reason": "No valid posts"}}
    avg_er = total_er / len(scored)
    scored.sort(key=lambda x: x["_er"], reverse=True)
    top = scored[:limit]

    out_posts = []
    for p in top:
        er = p["_er"]
        if er >= avg_er * 2:
            verdict = "Top performer"
            emoji = "🟢"
        elif er >= avg_er:
            verdict = "Above average"
            emoji = "🟢"
        elif er >= avg_er * 0.5:
            verdict = "Below average"
            emoji = "🟡"
        else:
            verdict = "Underperformer"
            emoji = "🔴"
        # After _load_ig_posts normalisation, the caption lives under
        # `caption_excerpt` (not `caption`). Read either so we don't silently
        # blank out the post text. (Same insight as the likeCount alias fix.)
        cap = (p.get("caption_excerpt") or p.get("caption") or "")[:120]
        ratio = (er / avg_er) if avg_er > 0 else 0
        plain = (
            f"{emoji} {verdict}. "
            f"Engagement {er:.2f}% vs your {avg_er:.2f}% average "
            f"({ratio:.1f}x{' above' if ratio > 1 else ' below'}). "
        )
        if p.get("like_count"):
            plain += f"{p['like_count']:,} likes, "
        if p.get("comments_count"):
            plain += f"{p['comments_count']:,} comments."
        out_posts.append({
            "id": p.get("id"),
            "timestamp": p.get("timestamp"),
            "engagementRate": er,
            "permalink": p.get("permalink"),
            "thumbnail_url": p.get("thumbnail_url") or p.get("media_url"),
            "media_type": p.get("media_type"),
            "caption_excerpt": cap,
            "like_count": p.get("like_count"),
            "comments_count": p.get("comments_count"),
            "verdict": verdict,
            "verdict_emoji": emoji,
            "plain_english": plain.strip(),
        })

    return {
        "ok": True,
        "posts": out_posts,
        "_meta": {
            "total_scanned": len(scored),
            "average_engagement": round(avg_er, 2),
            "source": actual_source,
            "window": ig_data.get("data_window") or ig_data.get("fetched_at"),
        },
    }