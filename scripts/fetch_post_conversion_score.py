"""
fetch_post_conversion_score.py — Score every IG post by its actual /bookings/
contribution per unit of reach.

This is the CMO brain's "what to publish more of" answer. It uses TWO
attribution signals:

  1. Direct hook_id match (when available) - GA4 sessionManualAdContent
     tagged with the same hook_id as an IG post.

  2. Time-windowed attribution - for each IG post on date D, sum the
     IG-sourced /bookings/ sessions on D, D+1, and D+2 (people don't
     always click-through immediately). Compare to the IG account's
     baseline 3-day avg session rate to score the lift.

Output: data/post-conversion-score.json — per-post scoring + a "next post
recommendation" based on the winning pattern.

The score formula:
  conversion_score = (
      direct_bookings_attributed * 10     # if hook_id matches
    + time_window_bookings * 3             # indirect via time-window
    + post_reach * 0.001                   # raw reach contribution
  ) * hook_theme_multiplier                # 1.5x if winning theme combo

  normalized_score = conversion_score / max_score_across_all_posts * 100
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
import requests as r
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GARequest

REPO_ROOT = "/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard"
CREDS_FILE = os.path.join(REPO_ROOT, "credentials", "google-service-account.json")
PROPERTY_ID = "427380680"
OUTPUT_FILE = os.path.join(REPO_ROOT, "data", "post-conversion-score.json")

# Hook theme taxonomy — same as in generate_conversion_attribution.js
HOOK_THEMES = {
    "club_fitting": ["fitting", "fitted", "club", "driver", "iron", "sub 70", "avoda", "miura", "takomo"],
    "wrong_ball": ["wrong ball", "ball fitting", "ball fitting"],
    "golf_lessons": ["lesson", "coach", "cat", "dave", "coaching", "putting", "short game"],
    "golf_humor": ["spirit", "lovely", "same old setup", "off-the-rack", "golf is", "golf's"],
    "trackman_stats": ["trackman", "data", "stat", "yard", "metric"],
    "booking_cta": ["book your", "book today", "book a", "dm us"],
}

# The winning combo from GA4 attribution data — club_fitting + booking_cta
WINNING_THEME_COMBOS = [
    {"club_fitting", "booking_cta"},
    {"club_fitting", "wrong_ball", "booking_cta"},
    {"golf_lessons", "booking_cta"},
]


def _get_token() -> str:
    creds = service_account.Credentials.from_service_account_file(
        CREDS_FILE, scopes=["https://www.googleapis.com/auth/analytics.readonly"]
    )
    creds.refresh(GARequest())
    return creds.token


def _run_ga4(token: str, body: dict) -> dict:
    resp = r.post(
        f"https://analyticsdata.googleapis.com/v1beta/properties/{PROPERTY_ID}:runReport",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        json=body,
        timeout=30,
    )
    return resp.json()


def _fetch_ga4_attribution(token: str, start: str, end: str) -> dict:
    """Pull IG-sourced /bookings/ + /club-fitting/ + /membership/ by (UTM content, pagePath)."""
    out = []
    for page in ("/bookings/", "/club-fitting/", "/membership/", "/customer-portal/"):
        body = {
            "dateRanges": [{"startDate": start, "endDate": end}],
            "dimensions": [
                {"name": "sessionManualAdContent"},
                {"name": "pagePath"},
            ],
            "metrics": [{"name": "sessions"}],
            "limit": 50,
            "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
            "dimensionFilter": {
                "andGroup": {"expressions": [
                    {"filter": {"fieldName": "sessionSource",
                                "stringFilter": {"value": "instagram", "matchType": "EXACT"}}},
                    {"filter": {"fieldName": "pagePath",
                                "stringFilter": {"value": page, "matchType": "CONTAINS"}}},
                ]}
            },
        }
        r_ = _run_ga4(token, body)
        if "rows" in r_:
            for row in r_["rows"]:
                utm = row["dimensionValues"][0]["value"]
                path = row["dimensionValues"][1]["value"]
                sess = int(row["metricValues"][0]["value"])
                if sess > 0:
                    out.append({"hook_id": utm, "page_path": path, "sessions": sess})
    return out


def _fetch_daily_ig_bookings(token: str, start: str, end: str) -> dict:
    """Daily /bookings/ sessions from Instagram source — for time-window attribution."""
    body = {
        "dateRanges": [{"startDate": start, "endDate": end}],
        "dimensions": [{"name": "date"}, {"name": "sessionSource"}],
        "metrics": [{"name": "sessions"}],
        "limit": 500,
        "orderBys": [{"dimension": {"dimensionName": "date"}, "desc": False}],
        "dimensionFilter": {
            "filter": {"fieldName": "landingPagePlusQueryString",
                       "stringFilter": {"value": "/bookings/", "matchType": "CONTAINS"}}
        },
    }
    r_ = _run_ga4(token, body)
    by_date = {}
    if "rows" in r_:
        for row in r_["rows"]:
            d = row["dimensionValues"][0]["value"]
            src = row["dimensionValues"][1]["value"]
            sess = int(row["metricValues"][0]["value"])
            if d not in by_date:
                by_date[d] = {}
            by_date[d][src] = by_date[d].get(src, 0) + sess
    return by_date


def _classify_themes(caption: str) -> list:
    """Return list of hook themes matched in this caption."""
    cap = (caption or "").lower()
    matched = []
    for theme, kws in HOOK_THEMES.items():
        if any(kw in cap for kw in kws):
            matched.append(theme)
    return matched


def _is_winning_combo(themes: list) -> bool:
    """Check if this post's theme combo matches a historically winning pattern."""
    themes_set = set(themes)
    return any(combo.issubset(themes_set) for combo in WINNING_THEME_COMBOS)


def main():
    print("=== fetch_post_conversion_score.py ===")
    end_date = datetime(2026, 8, 13)
    start_date = end_date - timedelta(days=30)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    print(f"Window: {start_str} to {end_str}")

    token = _get_token()

    # 1. Pull GA4 data
    print("\n[1/4] Pulling IG-attributed /bookings/ sessions from GA4...")
    ga_attribution = _fetch_ga4_attribution(token, start_str, end_str)
    print(f"  {len(ga_attribution)} attribution rows")
    ga_by_hook = defaultdict(int)
    for row in ga_attribution:
        ga_by_hook[row["hook_id"]] += row["sessions"]

    print("[2/4] Pulling daily /bookings/ sessions for time-window attribution...")
    daily_bookings = _fetch_daily_ig_bookings(token, start_str, end_str)
    ig_daily = {}
    for d, srcs in daily_bookings.items():
        # GA4 dates are YYYYMMDD - convert to YYYY-MM-DD
        if "-" not in d:
            d_norm = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        else:
            d_norm = d
        ig_daily[d_norm] = srcs.get("instagram", 0)
    print(f"  {len(ig_daily)} days with IG /bookings/ data")

    # Baseline = median daily IG /bookings/ sessions (a non-spike day)
    baseline_ig = sorted(ig_daily.values())
    if baseline_ig:
        median_idx = len(baseline_ig) // 2
        median_ig_bookings = baseline_ig[median_idx]
    else:
        median_ig_bookings = 0
    print(f"  Median IG /bookings/ sessions per day: {median_ig_bookings}")

    # 2. Load IG posts
    print("\n[3/4] Loading IG posts + scoring each...")
    ig_business_path = os.path.join(REPO_ROOT, "data", "ig-business-analytics.json")
    with open(ig_business_path) as f:
        ig_business = json.load(f)

    scored_posts = []
    for post in ig_business.get("media", []):
        post_date_raw = post.get("timestamp", "")
        if not post_date_raw:
            continue
        # Normalise to YYYY-MM-DD
        post_date = post_date_raw[:10]
        hook_id = post.get("hook_id") or ""
        reach = int((post.get("metrics") or {}).get("reach", 0))
        engagement_rate = float(post.get("engagement_rate_pct") or 0)
        caption = post.get("caption_preview", "")

        # 1. Direct hook_id attribution
        direct_sessions = ga_by_hook.get(hook_id, 0)
        # Loose match
        if direct_sessions == 0 and hook_id:
            for k, v in ga_by_hook.items():
                if k.startswith(hook_id[:25]) or hook_id.startswith(k[:25]):
                    direct_sessions = max(direct_sessions, v)

        # 2. Time-window attribution: D, D+1, D+2
        window_total = 0
        window_breakdown = {}
        for offset in range(0, 3):
            d_off = (datetime.strptime(post_date, "%Y-%m-%d") + timedelta(days=offset)).strftime("%Y-%m-%d")
            d_off_ga = d_off.replace("-", "")
            day_sessions = ig_daily.get(d_off, 0)
            window_total += day_sessions
            window_breakdown[d_off] = day_sessions

        # 3. Theme classification
        themes = _classify_themes(caption)
        is_winning = _is_winning_combo(themes)

        # 4. Composite score
        #    Direct hook match = strong signal (10x weight)
        #    Time-window = weaker signal (3x weight, divided by 3 days for daily avg)
        #    Reach = baseline contribution
        #    Winning theme combo = 1.5x multiplier
        theme_mult = 1.5 if is_winning else 1.0
        raw_score = (
            direct_sessions * 10
            + (window_total / 3.0) * 3
            + reach * 0.001
        ) * theme_mult

        # 5. Lift over baseline
        #    How much above the median daily IG /bookings/ traffic did this post drive?
        baseline_expected = median_ig_bookings * 3  # 3-day window
        lift_pct = ((window_total - baseline_expected) / baseline_expected * 100) if baseline_expected > 0 else 0

        scored_posts.append({
            "post_id": post.get("id"),
            "post_date": post_date,
            "hook_id": hook_id,
            "caption_preview": caption[:100],
            "permalink": post.get("permalink", ""),
            "reach": reach,
            "engagement_rate_pct": engagement_rate,
            "themes": themes,
            "is_winning_theme_combo": is_winning,
            "direct_attributed_sessions": direct_sessions,
            "time_window_sessions": window_total,
            "time_window_breakdown": window_breakdown,
            "lift_vs_baseline_pct": round(lift_pct, 1),
            "raw_score": round(raw_score, 2),
            "sessions_per_1k_reach": round((direct_sessions / reach * 1000), 3) if reach > 0 else 0,
        })

    # Normalise to 0-100
    if scored_posts:
        max_raw = max(p["raw_score"] for p in scored_posts) or 1
        for p in scored_posts:
            p["normalized_score"] = round((p["raw_score"] / max_raw) * 100, 1)
        scored_posts.sort(key=lambda p: p["normalized_score"], reverse=True)

    # 3. Build recommendation
    print("\n[4/4] Building next-post recommendation...")
    top_posts = scored_posts[:5]
    winning_themes_count = defaultdict(int)
    for p in top_posts:
        for t in p["themes"]:
            winning_themes_count[t] += 1
    recommended_themes = sorted(winning_themes_count.keys(),
                                 key=lambda t: winning_themes_count[t],
                                 reverse=True)
    top_caption_examples = [p["caption_preview"][:80] for p in top_posts[:3] if p["caption_preview"]]

    # 4. Write output
    out = {
        "schema": "https://clawdia.io/agents/post-conversion-score/v1",
        "updated": datetime.utcnow().isoformat() + "Z",
        "generated_by": "fetch_post_conversion_score.py",
        "window": {"start": start_str, "end": end_str},
        "scoring_formula": (
            "raw_score = (direct_attributed * 10 + (window_total/3) * 3 + reach * 0.001) * theme_mult"
            " | normalized_score = raw / max(raw) * 100"
        ),
        "winning_theme_combos": [list(c) for c in WINNING_THEME_COMBOS],
        "summary": {
            "posts_scored": len(scored_posts),
            "baseline_median_ig_bookings_per_day": median_ig_bookings,
            "winning_themes": recommended_themes,
            "top_score": scored_posts[0]["normalized_score"] if scored_posts else 0,
            "median_score": scored_posts[len(scored_posts) // 2]["normalized_score"] if scored_posts else 0,
        },
        "posts_ranked": scored_posts,
        "recommendation": {
            "next_post_themes": recommended_themes[:3],
            "winning_pattern_caption_examples": top_caption_examples,
            "rationale": (
                "Top 5 scoring posts share these themes: "
                + ", ".join(recommended_themes[:3])
                + ". The content engine should weight next-post idea generation "
                  "toward these themes. Booking-CTA posts with club_fitting or "
                  "wrong_ball hooks historically drive 0.5-1% of IG reach to /bookings/."
            ),
        },
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nWrote: {OUTPUT_FILE}")

    print("\n=== Top 10 scored posts ===")
    print(f"{'rank':>4s} {'date':12s} {'reach':>6s} {'ER%':>5s} {'themes':40s} {'direct':>7s} {'window':>7s} {'lift%':>7s} {'score':>6s}")
    for i, p in enumerate(scored_posts[:10], 1):
        themes_str = ", ".join(p["themes"][:3])[:38]
        print(f"{i:>4d} {p['post_date']:12s} {p['reach']:>6d} {p['engagement_rate_pct']:>5.2f} {themes_str:40s} "
              f"{p['direct_attributed_sessions']:>7d} {p['time_window_sessions']:>7d} "
              f"{p['lift_vs_baseline_pct']:>7.1f} {p['normalized_score']:>6.1f}")

    print()
    print("=== Recommendation ===")
    print(f"  Top themes for next post: {recommended_themes[:3]}")
    print(f"  Top caption examples:")
    for cap in top_caption_examples:
        print(f"    - {cap}")


if __name__ == "__main__":
    main()
