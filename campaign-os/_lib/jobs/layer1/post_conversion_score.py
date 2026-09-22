"""Score IG posts by GA4 /bookings/ attribution → post-conversion-score.json."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from ._io import as_dict, as_list, io_for_job, parse_float, utc_now_iso

JOB_NAME = "post_conversion_score"
from . import ga4_report

OUTPUT = "post-conversion-score.json"

HOOK_THEMES = {
    "club_fitting": ["fitting", "fitted", "club", "driver", "iron", "sub 70", "avoda", "miura", "takomo"],
    "wrong_ball": ["wrong ball", "ball fitting"],
    "golf_lessons": ["lesson", "coach", "cat", "dave", "coaching", "putting", "short game"],
    "golf_humor": ["spirit", "lovely", "same old setup", "off-the-rack", "golf is", "golf's"],
    "trackman_stats": ["trackman", "data", "stat", "yard", "metric"],
    "booking_cta": ["book your", "book today", "book a", "dm us"],
}

WINNING_THEME_COMBOS = [
    {"club_fitting", "booking_cta"},
    {"club_fitting", "wrong_ball", "booking_cta"},
    {"golf_lessons", "booking_cta"},
]


def _classify_themes(caption: str) -> list[str]:
    cap = (caption or "").lower()
    return [theme for theme, kws in HOOK_THEMES.items() if any(kw in cap for kw in kws)]


def _is_winning_combo(themes: list[str]) -> bool:
    themes_set = set(themes)
    return any(combo.issubset(themes_set) for combo in WINNING_THEME_COMBOS)


def _caption_of(post: dict) -> str:
    return (
        post.get("captionPreview")
        or post.get("caption_preview")
        or post.get("caption")
        or ""
    )


def _caption_to_hook_id(caption: str) -> str:
    """Mirror layer7/post_outcomes._caption_to_hook_id — first line, slugified, 50 chars."""
    first_line = (caption or "").split("\n")[0]
    return re.sub(r"[^a-z0-9]+", "-", first_line.lower()).strip("-")[:50]


def _merge_sources(ig_analytics: dict, ig_business: dict) -> list[dict]:
    """Analytics posts as the base roster, enriched from business media by id."""
    analytics = [p for p in as_list(ig_analytics.get("posts")) if isinstance(p, dict)]
    business = [m for m in as_list(ig_business.get("media")) if isinstance(m, dict)]
    if not analytics:
        return business

    biz_by_id = {str(m.get("id")): m for m in business if m.get("id")}
    merged: list[dict] = []
    seen: set[str] = set()
    for post in analytics:
        pid = str(post.get("id") or "")
        biz = biz_by_id.get(pid) or {}
        row = {**post, **{k: v for k, v in biz.items() if v not in (None, "", {}, [])}}
        merged.append(row)
        if pid:
            seen.add(pid)
    merged.extend(m for m in business if str(m.get("id") or "") not in seen)
    return merged


def _run_ga4_report(property_id: str, bearer: str, body: dict) -> dict:
    return ga4_report._run_ga4_report(property_id, bearer, body)


def _fetch_ga4_attribution(property_id: str, bearer: str, start: str, end: str) -> list[dict]:
    out: list[dict] = []
    for page in ("/bookings/", "/club-fitting/", "/membership/", "/customer-portal/"):
        body = {
            "dateRanges": [{"startDate": start, "endDate": end}],
            "dimensions": [{"name": "sessionManualAdContent"}, {"name": "pagePath"}],
            "metrics": [{"name": "sessions"}],
            "limit": 50,
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
            "dimensionFilter": {
                "andGroup": {
                    "expressions": [
                        {
                            "filter": {
                                "fieldName": "sessionSource",
                                "stringFilter": {"value": "instagram", "matchType": "EXACT"},
                            }
                        },
                        {
                            "filter": {
                                "fieldName": "pagePath",
                                "stringFilter": {"value": page, "matchType": "CONTAINS"},
                            }
                        },
                    ]
                }
            },
        }
        report = _run_ga4_report(property_id, bearer, body)
        for row in report.get("rows") or []:
            dims = row.get("dimensionValues") or []
            metrics = row.get("metricValues") or []
            utm = dims[0].get("value") if len(dims) > 0 else ""
            path = dims[1].get("value") if len(dims) > 1 else ""
            sess = int((metrics[0].get("value") if metrics else 0) or 0)
            if sess > 0:
                out.append({"hook_id": utm, "page_path": path, "sessions": sess})
    return out


def _fetch_daily_ig_bookings(property_id: str, bearer: str, start: str, end: str) -> dict[str, int]:
    body = {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": "date"}, {"name": "sessionSource"}],
        "metrics": [{"name": "sessions"}],
        "limit": 500,
        "dimensionFilter": {
            "filter": {
                "fieldName": "landingPagePlusQueryString",
                "stringFilter": {"value": "/bookings/", "matchType": "CONTAINS"},
            }
        },
    }
    report = _run_ga4_report(property_id, bearer, body)
    by_date: dict[str, int] = {}
    for row in report.get("rows") or []:
        dims = row.get("dimensionValues") or []
        metrics = row.get("metricValues") or []
        d_raw = dims[0].get("value") if len(dims) > 0 else ""
        src = dims[1].get("value") if len(dims) > 1 else ""
        sess = int((metrics[0].get("value") if metrics else 0) or 0)
        if src != "instagram" or not d_raw:
            continue
        d_norm = f"{d_raw[:4]}-{d_raw[4:6]}-{d_raw[6:]}" if "-" not in d_raw else d_raw[:10]
        by_date[d_norm] = by_date.get(d_norm, 0) + sess
    return by_date


def _score_posts(
    source: dict | list,
    ga_by_hook: dict[str, int],
    ig_daily: dict[str, int],
    median_ig_bookings: float,
) -> list[dict]:
    posts = source if isinstance(source, list) else as_list(as_dict(source).get("media"))
    scored: list[dict] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        post_date_raw = post.get("timestamp") or ""
        if not post_date_raw:
            continue
        post_date = post_date_raw[:10]
        caption = _caption_of(post)

        engagement_rate = parse_float(
            post.get("engagement_rate_pct")
            if post.get("engagement_rate_pct") is not None
            else post.get("engagementRate"),
            0.0,
        )

        format_type_raw = str(post.get("format_type") or "").lower()
        media_type = post.get("media_type") or {
            "reel": "VIDEO",
            "carousel": "CAROUSEL_ALBUM",
        }.get(format_type_raw, "IMAGE")
        is_reel = format_type_raw == "reel" or str(media_type).upper() in ("VIDEO", "REEL")

        metrics = post.get("metrics") if isinstance(post.get("metrics"), dict) else {}
        reach = int(metrics.get("reach") or post.get("reach") or 0)

        def _engagement(metric_key: str, *post_keys: str) -> int:
            val = metrics.get(metric_key)
            if val is None:
                for pk in post_keys:
                    val = post.get(pk)
                    if val is not None:
                        break
            return int(val or 0)

        likes = _engagement("likes", "likes")
        comments = _engagement("comments", "comments")
        saves = _engagement("saved", "saves", "saved")
        shares = _engagement("shares", "shares")
        permalink = post.get("permalink") or post.get("permalink_url") or ""

        hook_id = str(post.get("hook_id") or "")
        if not hook_id or hook_id.isdigit() or hook_id == str(post.get("id") or ""):
            hook_id = _caption_to_hook_id(caption)

        direct_sessions = ga_by_hook.get(hook_id, 0)
        if direct_sessions == 0 and hook_id:
            for k, v in ga_by_hook.items():
                if k.startswith(hook_id[:25]) or hook_id.startswith(k[:25]):
                    direct_sessions = max(direct_sessions, v)

        window_total = 0
        window_breakdown: dict[str, int] = {}
        for offset in range(3):
            d_off = (datetime.strptime(post_date, "%Y-%m-%d") + timedelta(days=offset)).strftime("%Y-%m-%d")
            day_sessions = ig_daily.get(d_off, 0)
            window_total += day_sessions
            window_breakdown[d_off] = day_sessions

        themes = _classify_themes(caption)
        theme_mult = 1.5 if _is_winning_combo(themes) else 1.0
        raw_score = (direct_sessions * 10 + (window_total / 3.0) * 3 + reach * 0.001) * theme_mult
        baseline_expected = median_ig_bookings * 3
        lift_pct = (
            ((window_total - baseline_expected) / baseline_expected * 100)
            if baseline_expected > 0
            else 0.0
        )

        scored.append({
            "post_id": post.get("id"),
            "post_date": post_date,
            "hook_id": hook_id,
            "media_type": media_type,
            "format_type": "reel" if is_reel else "image",
            "caption_preview": caption[:100],
            "permalink": permalink,
            "reach": reach,
            "engagement_rate_pct": engagement_rate,
            "likes": likes,
            "comments": comments,
            "saves": saves,
            "shares": shares,
            "themes": themes,
            "is_winning_theme_combo": _is_winning_combo(themes),
            "direct_attributed_sessions": direct_sessions,
            "time_window_sessions": window_total,
            "time_window_breakdown": window_breakdown,
            "lift_vs_baseline_pct": round(lift_pct, 1),
            "raw_score": round(raw_score, 2),
            "sessions_per_1k_reach": round((direct_sessions / reach * 1000), 3) if reach > 0 else 0,
        })

    if scored:
        max_raw = max(p["raw_score"] for p in scored) or 1
        for p in scored:
            p["normalized_score"] = round((p["raw_score"] / max_raw) * 100, 1)
        scored.sort(key=lambda p: p["normalized_score"], reverse=True)
    return scored


def run(*, brand: str | None = None) -> dict:
    """Build post-conversion-score.json from GA4 + ig-analytics / ig-business sources."""
    io = io_for_job(JOB_NAME, brand)
    missing = ga4_report._missing_env_error(brand)
    if missing:
        return {"ok": False, "error": missing}

    ig_analytics = as_dict(io.read("ig-analytics.json"))
    ig_business = as_dict(io.read("ig-business-analytics.json"))
    posts = _merge_sources(ig_analytics, ig_business)
    if not posts:
        return {
            "ok": False,
            "error": (
                "ig-analytics.json and ig-business-analytics.json missing or empty "
                "— run meta_refresh first"
            ),
        }

    end = date.today()
    start = end - timedelta(days=30)
    start_str = start.isoformat()
    end_str = end.isoformat()

    try:
        property_id, _ = ga4_report._resolve_ga4_creds(brand)
        bearer = ga4_report._get_ga4_bearer(brand)
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}

    ga_attribution = _fetch_ga4_attribution(property_id, bearer, start_str, end_str)
    ga_by_hook: dict[str, int] = defaultdict(int)
    for row in ga_attribution:
        ga_by_hook[row["hook_id"]] += row["sessions"]

    ig_daily = _fetch_daily_ig_bookings(property_id, bearer, start_str, end_str)
    baseline_vals = sorted(ig_daily.values())
    median_ig_bookings = baseline_vals[len(baseline_vals) // 2] if baseline_vals else 0

    scored_posts = _score_posts(posts, ga_by_hook, ig_daily, float(median_ig_bookings))
    top_posts = scored_posts[:5]
    reels = [p for p in scored_posts if p.get("format_type") == "reel"]
    images = [p for p in scored_posts if p.get("format_type") == "image"]

    theme_counts: dict[str, int] = defaultdict(int)
    for p in top_posts:
        for t in p.get("themes") or []:
            theme_counts[t] += 1
    recommended_themes = sorted(theme_counts.keys(), key=lambda t: theme_counts[t], reverse=True)

    top_10 = scored_posts[:10]
    reel_avg = (
        sum(p["normalized_score"] for p in top_10 if p.get("format_type") == "reel")
        / max(1, sum(1 for p in top_10 if p.get("format_type") == "reel"))
    )
    image_avg = (
        sum(p["normalized_score"] for p in top_10 if p.get("format_type") == "image")
        / max(1, sum(1 for p in top_10 if p.get("format_type") == "image"))
    )
    winning_format = "reel" if reel_avg > image_avg and reels else "image"

    payload = {
        "schema": "https://clawdia.io/agents/post-conversion-score/v1",
        "updated": utc_now_iso(),
        "generated_by": "layer1/post_conversion_score.py",
        "window": {"start": start_str, "end": end_str},
        "sources": {
            "ig_analytics_posts": len(as_list(ig_analytics.get("posts"))),
            "ig_business_media": len(as_list(ig_business.get("media"))),
            "merged_posts": len(posts),
        },
        "scoring_formula": (
            "raw_score = (direct_attributed * 10 + (window_total/3) * 3 + reach * 0.001) * theme_mult"
            " | normalized_score = raw / max(raw) * 100"
        ),
        "winning_theme_combos": [list(c) for c in WINNING_THEME_COMBOS],
        "summary": {
            "posts_scored": len(scored_posts),
            "baseline_median_ig_bookings_per_day": median_ig_bookings,
            "winning_themes": recommended_themes,
            "winning_format": winning_format,
            "top_score": scored_posts[0]["normalized_score"] if scored_posts else 0,
            "median_score": scored_posts[len(scored_posts) // 2]["normalized_score"] if scored_posts else 0,
            "reel_count": len(reels),
            "image_count": len(images),
        },
        "posts_ranked": scored_posts,
        "recommendation": {
            "next_post_themes": recommended_themes[:3],
            "next_post_format": winning_format,
            "winning_pattern_caption_examples": [
                p["caption_preview"][:80] for p in top_posts[:3] if p.get("caption_preview")
            ],
            "reel_themes": recommended_themes[:3],
            "image_themes": recommended_themes[:3],
            "rationale": (
                f"Top posts share themes: {', '.join(recommended_themes[:3]) or 'n/a'}. "
                f"Preferred format: {winning_format}."
            ),
        },
    }
    io.write(OUTPUT, payload)
    return {"ok": True, "rows": len(scored_posts)}
