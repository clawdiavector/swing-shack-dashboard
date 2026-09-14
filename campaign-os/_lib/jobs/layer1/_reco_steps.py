"""Internal step functions for insights_reco — ports of generate_*.js scripts."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ._io import as_dict, parse_float, parse_int, read_json, utc_now_iso, fmt_num, js_substring

# ── empty schemas ──────────────────────────────────────────────────────────

def empty_anomaly_alerts() -> dict:
    return {
        "updated": utc_now_iso(),
        "generated": "generate_anomaly_alerts.js",
        "summary": {
            "total_alerts": 0,
            "high_urgency": 0,
            "medium_urgency": 0,
            "low_urgency": 0,
            "today_urgency": 0,
        },
        "alerts": [],
    }


def empty_missed_opportunities() -> dict:
    return {
        "updated": utc_now_iso(),
        "generated": "detect_missed_opportunities.js",
        "count": 0,
        "by_severity": {"high": 0, "medium": 0, "low": 0},
        "by_category": {
            "follow_up_gap": 0,
            "content_gap": 0,
            "seo_gap": 0,
            "conversion_gap": 0,
            "offer_gap": 0,
        },
        "by_owner": {},
        "opportunities": [],
    }


def empty_funnel_leaks() -> dict:
    return {
        "updated": utc_now_iso(),
        "generated": "generate_funnel_leaks.js",
        "summary": {
            "total_leaks": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "most_urgent": "none",
        },
        "leaks": [],
    }


def empty_conversion_attribution() -> dict:
    return {
        "updated": utc_now_iso(),
        "generated": "generate_conversion_attribution.js",
        "summary": {
            "total_ig_posts_analysed": 0,
            "total_ga4_pages": 0,
            "booking_sessions": 0,
            "avg_booking_eng_rate": 0.0,
            "top_converting_service": "n/a",
            "top_converting_cta": "n/a",
            "top_booking_page": "n/a",
            "top_hook_theme": "n/a",
        },
        "cta_performance": [],
        "service_correlation": [],
        "hook_themes": [],
        "top_booking_pages": [],
        "service_coverage": [],
        "quick_wins": [],
    }


def empty_retargeting_recommendations() -> dict:
    return {
        "updated": utc_now_iso(),
        "generated": "generate_retargeting_recommendations.js",
        "summary": {
            "total": 0,
            "by_channel": {},
            "by_expiration": {},
            "by_urgency": {"today": 0, "this_week": 0, "flexible": 0},
            "owner_count": 0,
            "top_action": "none",
        },
        "recommendations": [],
    }


def empty_recommendation_scores() -> dict:
    return {
        "updated": utc_now_iso(),
        "generated": "generate_recommendation_scores.js",
        "summary": {
            "overall_priority_score": 0,
            "do_first_count": 0,
            "retarget_items_scored": 0,
            "top_retarget_score": 0,
            "best_post_score": 0,
            "best_service_score": 0,
        },
        "do_first": [],
        "ranked_items": [],
        "all_items": [],
    }


def empty_recommendation_outcomes() -> dict:
    return {
        "updated": utc_now_iso(),
        "generated": "generate_recommendation_outcomes.js",
        "summary": {
            "total_recommended": 0,
            "executed": 0,
            "won": 0,
            "neutral": 0,
            "lost": 0,
            "not_executed": 0,
            "stale": 0,
            "exec_rate": 0,
            "overall_win_rate": 0,
            "baseline_eng_rate": 0.0,
            "booking_sessions": 0,
        },
        "type_win_rates": [],
        "learned_signals": {
            "best_channel": "retarget_existing",
            "best_channel_rate": 0,
            "worst_channel": "unknown",
            "worst_channel_rate": 0,
            "confidence_adjustments": {},
            "overall_win_rate": 0,
            "exec_rate": 0,
        },
        "best_recommendation": None,
        "worst_recommendation": None,
        "ignored": [],
        "underperformed": [],
        "all_evaluated": [],
    }


def empty_website_insights() -> dict:
    return {
        "updated": utc_now_iso(),
        "data_window": "last_7_days",
        "total_sessions": 0,
        "source_share": {
            "organic_pct": "0",
            "direct_pct": "0",
            "social_pct": "0",
            "organic_sessions": 0,
            "direct_sessions": 0,
            "social_sessions": 0,
            "total": 0,
        },
        "funnel": {
            "booking_pages": {"sessions": 0, "paths": []},
            "checkout_pages": {"sessions": 0, "paths": []},
            "coaching_pages": {"sessions": 0, "paths": []},
            "fitting_pages": {"sessions": 0, "paths": []},
        },
        "weak_ctas": [],
        "top_pages": [],
        "recommendations": [],
        "insights": [],
        "summary": {
            "health_score": "GOOD",
            "critical_count": 0,
            "medium_count": 0,
            "low_count": 0,
            "top_priority": "No critical issues",
        },
    }


def _list_rows(payload: dict, *keys: str) -> int:
    return sum(len(payload.get(k) or []) for k in keys)


# ── 1. anomaly alerts ─────────────────────────────────────────────────────

THEME_KEYWORDS = {
    "slice_fix": ["slice", "hook", "correction", "right", "left"],
    "putting": ["putting", "putt", "green"],
    "fitness": ["fitness", "gym", "flexibility", "body"],
    "simulator": ["simulator", "sim", "indoor"],
    "tournament": ["tournament", "competition", "event"],
}


def step_anomaly_alerts() -> dict:
    ig = as_dict(read_json("ig-analytics.json"))
    ga4 = as_dict(read_json("ga4-metrics.json"))
    seo = as_dict(read_json("seo-rankings.json"))
    outcomes = as_dict(read_json("recommendation-outcomes.json"))

    ig_posts = [p for p in (ig.get("posts") or []) if isinstance(p, dict)]
    ga4_pages = [p for p in (ga4.get("pages") or []) if isinstance(p, dict)]

    def post_ts(p: dict) -> float:
        raw = p.get("timestamp") or p.get("created_at") or 0
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            return 0.0

    sorted_by_date = sorted(ig_posts, key=post_ts, reverse=True)
    recent = sorted_by_date[:7]
    older = sorted_by_date[7:21]

    avg_recent = (
        sum(parse_float(p.get("engagementRate")) for p in recent) / len(recent)
        if recent
        else 0.0
    )
    avg_older = (
        sum(parse_float(p.get("engagementRate")) for p in older) / len(older)
        if older
        else 0.0
    )

    ig_drop = None
    if avg_recent < avg_older * 0.7 and avg_older > 1:
        ig_drop = {
            "type": "ig_performance_drop",
            "alert": "Instagram engagement rate dropping",
            "severity": "high" if avg_recent < avg_older * 0.5 else "medium",
            "evidence": (
                f"Recent 7-post avg: {avg_recent:.2f}% | Previous avg: {avg_older:.2f}% | "
                f"Drop: -{(1 - avg_recent / avg_older) * 100:.0f}%"
            ),
            "likely_cause": "Hook quality drop OR algorithm shift OR audience fatigue",
            "action": "Check last 3 posts for hook quality — compare to top-performing historical posts",
            "owner": "Swing Shack page",
            "urgency": "today",
            "confidence": 5,
        }

    booking_sessions = 0
    booking_page = next(
        (p for p in ga4_pages if "book" in (p.get("path") or "").lower()),
        None,
    )
    if booking_page:
        booking_sessions = parse_int(booking_page.get("sessions"))

    non_booking = [p for p in ga4_pages if "book" not in (p.get("path") or "").lower()]
    avg_other = (
        sum(parse_int(p.get("sessions")) for p in non_booking) / len(non_booking)
        if non_booking
        else 0.0
    )

    booking_collapse = None
    if booking_sessions < avg_other * 0.3 and avg_other > 10:
        booking_collapse = {
            "type": "booking_traffic_collapse",
            "alert": "Booking page traffic abnormally low",
            "severity": "high" if booking_sessions == 0 else "medium",
            "evidence": f"Booking sessions: {booking_sessions} | Site average: {avg_other:.0f}",
            "likely_cause": "No recent IG booking CTA posts OR website UX issue OR booking page down",
            "action": "Check: (1) Is booking page accessible? (2) Did IG posts with booking CTAs go out recently?",
            "owner": "Swing Shack page / Nancy",
            "urgency": "today",
            "confidence": 4,
        }

    ga4_sources = ga4.get("source_medium") or []
    top_sources = sorted(
        [s for s in ga4_sources if isinstance(s, dict)],
        key=lambda s: parse_int(s.get("sessions")),
        reverse=True,
    )[:5]
    social = next(
        (
            s
            for s in top_sources
            if "social" in (s.get("source") or "").lower()
            or "instagram" in (s.get("source") or "").lower()
        ),
        None,
    )
    direct = next(
        (
            s
            for s in top_sources
            if "direct" in (s.get("source") or "").lower()
            or "google" in (s.get("source") or "").lower()
        ),
        None,
    )
    source_swing = None
    if social and direct:
        source_swing = {
            "type": "source_swing",
            "alert": "Social traffic share shifted significantly",
            "severity": "medium",
            "evidence": f"Social: {social.get('sessions')} sessions | Direct: {direct.get('sessions')} sessions",
            "likely_cause": "IG posting schedule change OR Reels vs static mix shift OR reach algorithm change",
            "action": "Compare last 7 days IG posting cadence to previous 7 days",
            "owner": "Swing Shack page",
            "urgency": "this_week",
            "confidence": 3,
        }

    rankings = seo.get("rankings") or seo.get("organic_keywords") or []
    falling = []
    for k in rankings:
        if not isinstance(k, dict):
            continue
        current = parse_int(k.get("current_rank") or k.get("rank"), 999)
        delta = parse_float(k.get("delta") or k.get("delta_7d"))
        if current <= 20 and delta < -3:
            falling.append(
                {
                    "keyword": k.get("keyword") or k.get("term"),
                    "rank": k.get("current_rank") or k.get("rank"),
                    "delta": delta,
                }
            )
    falling = falling[:3]

    seo_drop = None
    if falling:
        seo_drop = {
            "type": "seo_ranking_drop",
            "alert": f"{len(falling)} top keyword(s) dropping in rankings",
            "severity": "high" if any(k["delta"] < -5 for k in falling) else "medium",
            "evidence": " | ".join(
                f'"{k["keyword"]}": {k["rank"]} ({k["delta"]:+.0f})' for k in falling
            ),
            "likely_cause": "Competitor outranking OR content freshness drop OR backlink loss",
            "action": "Audit top dropping pages — add fresh IG content linking to those pages this week",
            "owner": "Swing Shack page",
            "urgency": "this_week",
            "confidence": 4,
        }

    now = datetime.now(timezone.utc).timestamp()
    recent_week = []
    older_posts = []
    for p in ig_posts:
        age = (now - post_ts(p)) / 86400
        if age <= 7:
            recent_week.append(p)
        elif age <= 28:
            older_posts.append(p)

    theme_spikes = []
    for theme, kws in THEME_KEYWORDS.items():
        recent_count = sum(
            1
            for p in recent_week
            if any(k in (p.get("caption") or "").lower() for k in kws)
        )
        older_count = sum(
            1
            for p in older_posts
            if any(k in (p.get("caption") or "").lower() for k in kws)
        )
        if recent_count >= 3 and recent_count > older_count * 2:
            theme_spikes.append(
                {
                    "type": "theme_spike",
                    "alert": f'"{theme}" posting suddenly increased',
                    "severity": "low",
                    "evidence": f"{recent_count} posts in last 7 days vs {older_count} in prior 3 weeks",
                    "likely_cause": "Trending topic OR competitor posting OR seasonal shift",
                    "action": "Review — if genuine trend, create more content. If over-posting, throttle.",
                    "owner": "Swing Shack page",
                    "urgency": "this_week",
                    "confidence": 3,
                }
            )

    summary_out = as_dict(outcomes.get("summary"))
    exec_rate = parse_float(summary_out.get("exec_rate"))
    total_rec = parse_int(summary_out.get("total_recommended"))
    exec_collapse = None
    if exec_rate < 20 and total_rec >= 5:
        exec_collapse = {
            "type": "exec_rate_collapse",
            "alert": f"Recommendation execution rate critically low: {exec_rate}%",
            "severity": "high" if exec_rate < 10 else "medium",
            "evidence": (
                f"{parse_int(summary_out.get('executed'))} of {total_rec} recommended actions executed"
            ),
            "likely_cause": "Recommendations not being actioned OR publishing pipeline bottleneck",
            "action": "Review DO THIS FIRST list — are recommendations reaching the right people?",
            "owner": "Swing Shack page",
            "urgency": "today",
            "confidence": 5,
        }

    sev_order = {"high": 0, "medium": 1, "low": 2}
    all_alerts = sorted(
        [
            a
            for a in [ig_drop, booking_collapse, source_swing, seo_drop, exec_collapse, *theme_spikes]
            if a
        ],
        key=lambda a: sev_order.get(a["severity"], 99),
    )

    return {
        "updated": utc_now_iso(),
        "generated": "generate_anomaly_alerts.js",
        "summary": {
            "total_alerts": len(all_alerts),
            "high_urgency": sum(1 for a in all_alerts if a["severity"] == "high"),
            "medium_urgency": sum(1 for a in all_alerts if a["severity"] == "medium"),
            "low_urgency": sum(1 for a in all_alerts if a["severity"] == "low"),
            "today_urgency": sum(1 for a in all_alerts if a.get("urgency") == "today"),
        },
        "alerts": [{**a, "rank": i + 1} for i, a in enumerate(all_alerts)],
    }


# ── 2. missed opportunities ─────────────────────────────────────────────────

def step_missed_opportunities() -> dict:
    hb = as_dict(read_json("hook-bank.json"))
    ci = as_dict(read_json("content-ideas.json"))
    ig = as_dict(read_json("ig-analytics.json"))
    ga4 = as_dict(read_json("ga4-metrics.json"))
    wi = as_dict(read_json("website-insights.json"))
    rd = as_dict(read_json("reddit-trends.json"))
    yt = as_dict(read_json("youtube-trends.json"))
    seo = as_dict(read_json("seo-rankings.json"))

    opportunities: list[dict] = []
    ig_posts = [p for p in (ig.get("posts") or []) if isinstance(p, dict)]
    ig_caps = [(p.get("caption") or "").lower() for p in ig_posts]

    for w in hb.get("watched_and_worked") or []:
        if not isinstance(w, dict) or parse_float(w.get("ig_proof_score")) < 8:
            continue
        topic = (w.get("youtube_topic_match") or ["unknown"])[0]
        related = [
            i
            for i in (ci.get("ideas") or [])
            if isinstance(i, dict)
            and topic in (i.get("title") or i.get("hook") or "").lower()
        ]
        if len(related) < 2:
            opportunities.append(
                {
                    "type": "hook_winner_not_reused",
                    "category": "follow_up_gap",
                    "severity": "high",
                    "hook": w.get("hook_text"),
                    "topic": topic,
                    "ig_score": w.get("ig_proof_score"),
                    "owner": "Coach Cat",
                    "suggested_fix": (
                        f'Rework the "{topic}" hook into a follow-up Reel this week · '
                        f'IG proof {w.get("ig_proof_score")}.'
                    ),
                    "suggestion": (
                        f'Hook scored {fmt_num(w.get("ig_proof_score"))} on IG. No follow-up posts found for "{topic}". '
                        "Push this angle."
                    ),
                    "why": f'IG proof: {w.get("ig_proof_score")} · strong performer with no refresh',
                }
            )

    ga4_pages = ga4.get("pages") or wi.get("top_pages") or []
    for p in ga4_pages[:10]:
        if not isinstance(p, dict):
            continue
        pg_path = (p.get("path") or "/").replace("/", " ")
        sessions = parse_int(p.get("sessions"))
        if sessions < 20:
            continue
        matched = [
            c
            for c in ig_caps
            if any(w for w in pg_path.split() if len(w) > 3 and w in c)
        ]
        if not matched:
            path = p.get("path") or "/"
            owner = (
                "Divan"
                if "fitting" in path or "club" in path
                else "Nancy / Front Desk"
                if "book" in path or "checkout" in path
                else "Swing Shack page"
            )
            opportunities.append(
                {
                    "type": "traffic_no_content",
                    "category": "content_gap",
                    "severity": "high" if sessions > 50 else "medium",
                    "page": path,
                    "sessions": sessions,
                    "owner": owner,
                    "suggested_fix": (
                        f'Create IG content targeting "{path}" · {sessions} sessions with no social link.'
                    ),
                    "suggestion": f'Page "{path}" gets {sessions} sessions but no IG post links to it. Create content.',
                    "why": f"{sessions} sessions with no social presence",
                }
            )

    for t in rd.get("trends") or []:
        if not isinstance(t, dict) or parse_int(t.get("score")) < 30:
            continue
        title = (t.get("title") or "").lower()
        word = next((w for w in title.split() if len(w) > 4), "")
        matched_post = next((p for p in ig_posts if word and word in (p.get("caption") or "").lower()), None)
        if not matched_post:
            opportunities.append(
                {
                    "type": "reddit_pain_no_ig",
                    "category": "content_gap",
                    "severity": "high" if parse_int(t.get("score")) >= 80 else "medium",
                    "reddit_title": t.get("title"),
                    "subreddit": t.get("subreddit") or "golf",
                    "reddit_score": t.get("score"),
                    "owner": "Swing Shack page",
                    "suggested_fix": (
                        f'Spin r/{t.get("subreddit")} conversation "{t.get("title")}" into an IG post angle this week.'
                    ),
                    "suggestion": f'r/{t.get("subreddit")} is discussing "{t.get("title")}". IG hasn\'t covered this.',
                    "why": f'Reddit score: {t.get("score")} · community pain point uncovered',
                }
            )

    yt_svc_map = {
        "lessons": ["lessons", "swing", "teaching", "coach"],
        "driver": ["driver", "drive", "tee"],
        "short_game": ["putting", "chipping", "pitching", "putt"],
        "fitting": ["fitting", "fitted", "clubs", "irons"],
        "slice_fix": ["slice", "hook", "correction", "fix"],
    }
    for svc, kw_arr in yt_svc_map.items():
        yt_match = [
            v
            for v in (yt.get("top_videos") or [])
            if isinstance(v, dict)
            and any(k in (v.get("title") or "").lower() for k in kw_arr)
        ]
        if not yt_match:
            continue
        ig_match = [c for c in ig_caps if any(k in c for k in kw_arr)]
        if not ig_match:
            opportunities.append(
                {
                    "type": "youtube_trend_no_ig",
                    "category": "content_gap",
                    "severity": "medium",
                    "topic": svc,
                    "yt_video_count": len(yt_match),
                    "yt_examples": [v.get("title") for v in yt_match[:2]],
                    "owner": "Swing Shack page",
                    "suggested_fix": f'Create IG post on "{svc}" · YouTube has {len(yt_match)} trending videos.',
                    "suggestion": f'YouTube has {len(yt_match)} videos on "{svc}" but IG hasn\'t covered it.',
                    "why": f"{len(yt_match)} YouTube videos trending on this topic",
                }
            )

    for kw in (seo.get("rising_keywords") or [])[:5]:
        if not isinstance(kw, dict):
            continue
        keyword = (kw.get("keyword") or kw.get("term") or "").lower()
        if len(keyword) < 4:
            continue
        matched_post = next(
            (p for p in ig_posts if keyword in (p.get("caption") or "").lower()),
            None,
        )
        if not matched_post:
            opportunities.append(
                {
                    "type": "seo_rising_no_content",
                    "category": "seo_gap",
                    "severity": "medium",
                    "keyword": kw.get("keyword") or kw.get("term") or "",
                    "rank": kw.get("current_rank") or "?",
                    "delta": kw.get("delta") or kw.get("delta_7d") or 0,
                    "owner": "Swing Shack page",
                    "suggested_fix": f'Write and schedule IG post targeting "{keyword}" · SEO rank rising.',
                    "suggestion": f'"{kw.get("keyword") or kw.get("term")}" is rising in SEO but no IG post covers it.',
                    "why": f'Rank: {kw.get("current_rank") or "?"}, Delta: +{kw.get("delta") or kw.get("delta_7d") or 0}',
                }
            )

    sale_angles = [
        {"id": "lessons_value", "kw": ["save", "deal", "package", "lesson", "coach"], "label": "Lessons value proposition"},
        {"id": "fitting_promo", "kw": ["fitting", "fitted", "custom"], "label": "Club fitting promotion"},
        {"id": "membership_benefits", "kw": ["member", "membership", "perks", "unlimited"], "label": "Membership benefits"},
        {"id": "event_promo", "kw": ["night golf", "event", "tournament", "competition"], "label": "Events promotion"},
    ]
    ig_text = " ".join(ig_caps)
    for angle in sale_angles:
        if not any(k in ig_text for k in angle["kw"]):
            opportunities.append(
                {
                    "type": "sale_angle_not_pushed",
                    "category": "offer_gap",
                    "severity": "low",
                    "angle_label": angle["label"],
                    "owner": "Swing Shack page",
                    "suggested_fix": f'Schedule a promotional IG post around "{angle["label"]}".',
                    "suggestion": f'"{angle["label"]}" hasn\'t been pushed this week despite relevance.',
                    "why": "No sale/promo angle found in recent IG posts",
                }
            )

    seen: set[str] = set()
    deduped: list[dict] = []
    for o in opportunities:
        key = o["type"] + str(o.get("hook") or o.get("keyword") or o.get("page") or o.get("topic") or "")[:30]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(o)
    deduped = deduped[:12]
    sev_order = {"high": 0, "medium": 1, "low": 2}
    deduped.sort(key=lambda o: sev_order.get(o.get("severity"), 99))

    owners = sorted({o.get("owner") for o in deduped if o.get("owner")})
    return {
        "updated": utc_now_iso(),
        "generated": "detect_missed_opportunities.js",
        "count": len(deduped),
        "by_severity": {
            "high": sum(1 for o in deduped if o.get("severity") == "high"),
            "medium": sum(1 for o in deduped if o.get("severity") == "medium"),
            "low": sum(1 for o in deduped if o.get("severity") == "low"),
        },
        "by_category": {
            "follow_up_gap": sum(1 for o in deduped if o.get("category") == "follow_up_gap"),
            "content_gap": sum(1 for o in deduped if o.get("category") == "content_gap"),
            "seo_gap": sum(1 for o in deduped if o.get("category") == "seo_gap"),
            "conversion_gap": sum(1 for o in deduped if o.get("category") == "conversion_gap"),
            "offer_gap": sum(1 for o in deduped if o.get("category") == "offer_gap"),
        },
        "by_owner": {o: sum(1 for d in deduped if d.get("owner") == o) for o in owners},
        "opportunities": deduped,
    }


# ── 3. funnel leaks ───────────────────────────────────────────────────────

STAGES = {
    "AWARENESS": ["/", "home", "about", "gallery", "photo", "video"],
    "INTEREST": ["lesson", "coach", "fitting", "service", "price", "membership", "program"],
    "INTENT": ["book", "checkout", "contact", "enquiry", "trial", "sign up", "signup", "register"],
    "CONVERSION": ["confirm", "success", "paid", "booking", "tq", "thank"],
}


def _stage_of(path: str | None) -> str:
    p = (path or "").lower()
    for stage, keys in STAGES.items():
        if any(k in p for k in keys):
            return stage
    return "AWARENESS"


def step_funnel_leaks() -> dict:
    ga4 = as_dict(read_json("ga4-metrics.json"))
    ig = as_dict(read_json("ig-analytics.json"))
    missed = as_dict(read_json("missed-opportunities.json"))

    pages = [p for p in (ga4.get("pages") or []) if isinstance(p, dict)]
    ig_posts = [p for p in (ig.get("posts") or []) if isinstance(p, dict)]

    intent_leaks = []
    for p in sorted(
        [p for p in pages if _stage_of(p.get("path")) == "INTENT"],
        key=lambda x: parse_int(x.get("sessions")),
        reverse=True,
    )[:4]:
        eng = parse_float(p.get("engagement_rate"))
        if eng >= 40:
            continue
        sessions = parse_int(p.get("sessions"))
        path = p.get("path")
        intent_leaks.append(
            {
                "type": "high_intent_low_engagement",
                "page": path,
                "sessions": sessions,
                "engRate": eng,
                "severity": "high" if sessions > 50 else "medium",
                "revenue_impact": "HIGH — many sessions, low engagement, likely bouncing",
                "easy_fix": "Add stronger CTA or urgency element on this page",
                "owner": "Nancy / Front Desk"
                if path and ("book" in path or "checkout" in path)
                else "Swing Shack page",
            }
        )

    service_patterns = {
        "Golf Lessons": ["lesson", "coach", "training"],
        "Club Fitting": ["fitting", "fitted", "custom", "club"],
        "Simulator": ["simulator", "sim", "bay"],
        "Membership": ["member", "membership", "perk"],
        "Events": ["event", "competition", "tournament", "night"],
    }
    ig_text = " ".join((p.get("caption") or "").lower() for p in ig_posts)
    service_leaks = []
    for service, kws in service_patterns.items():
        page = next((p for p in pages if any(k in (p.get("path") or "").lower() for k in kws)), None)
        sessions = parse_int(page.get("sessions")) if page else 0
        if not any(k in ig_text for k in kws) and sessions > 20:
            service_leaks.append(
                {
                    "type": "service_page_no_ig",
                    "service": service,
                    "page": (page or {}).get("path") or kws[0],
                    "sessions": sessions,
                    "severity": "high" if sessions > 80 else "medium" if sessions > 40 else "low",
                    "revenue_impact": f"{sessions} sessions with no IG content pushing this service",
                    "easy_fix": f"Create IG post about {service} — GA4 shows {sessions} sessions this week",
                    "owner": "Coach Cat"
                    if service == "Golf Lessons"
                    else "Divan"
                    if service == "Club Fitting"
                    else "Swing Shack page",
                }
            )
    service_leaks.sort(key=lambda x: x["sessions"], reverse=True)
    service_leaks = service_leaks[:4]

    high_save = sorted(
        [
            p
            for p in ig_posts
            if parse_int(p.get("reach")) > 50
            and parse_int(p.get("saveCount")) / max(parse_int(p.get("reach")), 1) > 0.03
        ],
        key=lambda p: parse_int(p.get("saveCount")) / max(parse_int(p.get("reach")), 1),
        reverse=True,
    )
    save_leaks = []
    for p in high_save[:3]:
        caption = (p.get("caption") or "").lower()
        has_cta = any(t in caption for t in ["book", "booking", "link in bio", "reserve", "schedule"])
        save_leaks.append(
            {
                "type": "high_save_no_booking_cta",
                "post_id": p.get("id") or "unknown",
                "reach": parse_int(p.get("reach")),
                "saves": parse_int(p.get("saveCount")),
                "save_rate": round(parse_int(p.get("saveCount")) / max(parse_int(p.get("reach")), 1) * 100, 2),
                "has_booking_cta": has_cta,
                "severity": "low" if has_cta else "high",
                "caption_preview": (p.get("caption") or "")[:80],
                "revenue_impact": (
                    "Low — already has booking CTA"
                    if has_cta
                    else "HIGH — high save rate but no direct booking path"
                ),
                "easy_fix": "Already optimised" if has_cta else "Add direct booking CTA to caption",
                "owner": "Swing Shack page",
            }
        )

    follow_up_leaks = [
        {
            "type": "hook_winner_no_follow_up",
            "topic": o.get("topic"),
            "ig_score": o.get("ig_score"),
            "hook": js_substring(o.get("hook") or "", 60),
            "severity": o.get("severity"),
            "revenue_impact": f'Strong IG hook ({o.get("ig_score")}) with no booking funnel follow-up',
            "easy_fix": o.get("suggested_fix")
            or f'Create follow-up post with direct booking CTA for "{o.get("topic")}"',
            "owner": o.get("owner") or "Coach Cat",
        }
        for o in (missed.get("opportunities") or [])
        if isinstance(o, dict)
        and o.get("category") == "follow_up_gap"
        and parse_float(o.get("ig_score")) >= 8
    ][:3]

    booking_page = next(
        (p for p in pages if any(b in (p.get("path") or "").lower() for b in ("book", "checkout"))),
        None,
    )
    if booking_page:
        b_sessions = parse_int(booking_page.get("sessions"))
        if b_sessions > 30:
            recent_booking = sum(
                1
                for p in ig_posts
                if any(t in (p.get("caption") or "").lower() for t in ["book", "booking", "reserve", "schedule"])
            )
            if recent_booking < 2:
                save_leaks.append(
                    {
                        "type": "booking_traffic_no_retargeting",
                        "page": booking_page.get("path"),
                        "sessions": b_sessions,
                        "severity": "high" if b_sessions > 80 else "medium",
                        "revenue_impact": (
                            f"{b_sessions} sessions on booking page but < 2 booking CTAs in recent IG posts"
                        ),
                        "easy_fix": "Push booking CTA on IG this week — booking page traffic is there",
                        "owner": "Swing Shack page",
                    }
                )

    sev_order = {"high": 0, "medium": 1, "low": 2}
    all_leaks = sorted(
        [*intent_leaks, *service_leaks, *save_leaks, *follow_up_leaks],
        key=lambda l: (
            sev_order.get(l.get("severity"), 99),
            -(l.get("sessions") or l.get("ig_score") or 0),
        ),
    )[:10]
    most_urgent = next((l for l in all_leaks if l.get("severity") == "high"), all_leaks[0] if all_leaks else None)

    return {
        "updated": utc_now_iso(),
        "generated": "generate_funnel_leaks.js",
        "summary": {
            "total_leaks": len(all_leaks),
            "high": sum(1 for l in all_leaks if l.get("severity") == "high"),
            "medium": sum(1 for l in all_leaks if l.get("severity") == "medium"),
            "low": sum(1 for l in all_leaks if l.get("severity") == "low"),
            "most_urgent": (
                f'({most_urgent["severity"]}) {js_substring(most_urgent.get("easy_fix") or "", 60)}'
                if most_urgent
                else "none"
            ),
        },
        "leaks": [{**l, "rank": i + 1} for i, l in enumerate(all_leaks)],
    }


# ── 4. conversion attribution ─────────────────────────────────────────────

CTA_BUCKETS = {
    "BOOKING": ["book", "booking", "book now", "reserve", "schedule", "get started"],
    "LESSONS": ["lesson", "coach", "cat", "dave", "training", "learn"],
    "FITTING": ["fitting", "fitted", "custom driver", "custom iron", "club"],
    "PROMO": ["discount", "save", "deal", "offer", "prize", "win", "free"],
    "ENGAGEMENT": ["link in bio", "comment", "share", "tag", "dm", "follow"],
    "SOFT": ["swingshack", "visit", "try", "come", "experience"],
}

SERVICE_KEYWORDS = {
    "Golf Lessons": ["lesson", "coach", "cat", "dave", "putting", "swing", "short game", "birdie", "handicap"],
    "Club Fitting": ["fitting", "fitted", "driver", "iron", "club", "trackman", "custom"],
    "Simulator": ["simulator", "golf simulator", "sim", "bay", "indoor"],
    "Membership": ["member", "membership", "perks", "unlimited", "practice"],
    "Events": ["event", "competition", "tournament", "night golf", "league"],
}

HOOK_THEMES = [
    {"id": "stats_trackman", "label": "TrackMan / Stats", "keywords": ["trackman", "data", "stat", "number", "metric", "spin", "speed", "drive", "yard", "meter"]},
    {"id": "slice_fix", "label": "Slice Fix", "keywords": ["slice", "hook", "correction", "fix", "right", "left", "loss", "straighten"]},
    {"id": "lessons", "label": "Golf Lessons", "keywords": ["lesson", "coach", "cat", "dave", "training", "improve", "drop", "handicap"]},
    {"id": "putting", "label": "Putting", "keywords": ["putting", "putt", "green", "distance", "reading"]},
    {"id": "fitting", "label": "Club Fitting", "keywords": ["fitting", "fitted", "driver", "custom", "iron", "club", "spec"]},
    {"id": "contest", "label": "Contest / Promo", "keywords": ["win", "prize", "driver", "free", "trophy", "night", "event"]},
    {"id": "membership", "label": "Membership", "keywords": ["member", "perk", "unlimited", "save", "deal"]},
    {"id": "simulator", "label": "Simulator", "keywords": ["simulator", "sim", "indoor", "rain", "weather", "winter"]},
]

BOOKING_PAGES = ["book", "checkout", "membership", "contact", "lesson", "fitting", "pricing", "coaching"]


def _bucket_cta(caption: str) -> str:
    lower = (caption or "").lower()
    for bucket, terms in CTA_BUCKETS.items():
        if any(t in lower for t in terms):
            return bucket
    return "SOFT"


def _normalise_ig_posts() -> tuple[list[dict], str]:
    ig_raw = as_dict(read_json("ig-analytics.json"))
    ig_business = as_dict(read_json("ig-business-analytics.json"))
    biz_media = [
        m
        for m in (ig_business.get("media") or [])
        if isinstance(m, dict)
        and isinstance(m.get("metrics"), dict)
        and parse_int(m["metrics"].get("reach")) > 0
    ]
    if biz_media:
        posts = [
            {
                "id": m.get("id"),
                "caption": m.get("caption_preview") or "",
                "hook_id": m.get("hook_id") or "",
                "timestamp": m.get("timestamp") or "",
                "media_type": m.get("media_type") or "",
                "reach": parse_int(m["metrics"].get("reach")),
                "likes": parse_int(m["metrics"].get("likes")),
                "comments": parse_int(m["metrics"].get("comments")),
                "saves": parse_int(m["metrics"].get("saved")),
                "shares": parse_int(m["metrics"].get("shares")),
                "engagementRate": parse_float(m.get("engagement_rate_pct")),
                "source": "ig-business-analytics",
            }
            for m in biz_media
        ]
        return posts, "ig-business-analytics"
    posts = [
        {
            "id": p.get("id") or p.get("postId"),
            "caption": p.get("captionPreview") or p.get("caption") or "",
            "hook_id": p.get("hook_id") or "",
            "timestamp": p.get("timestamp") or "",
            "media_type": p.get("format_type") or "",
            "reach": parse_int(p.get("reach")),
            "likes": parse_int(p.get("likes")),
            "comments": parse_int(p.get("comments")),
            "saves": parse_int(p.get("saves")),
            "shares": parse_int(p.get("shares")),
            "engagementRate": parse_float(p.get("engagementRate") or p.get("engagement_rate")),
            "source": "ig-analytics",
        }
        for p in (ig_raw.get("posts") or [])
        if isinstance(p, dict)
    ]
    return posts, "ig-analytics"


def step_conversion_attribution() -> dict:
    ga4 = as_dict(read_json("ga4-metrics.json"))
    ig_posts, _source = _normalise_ig_posts()

    ga4_pages = [dict(p) for p in (ga4.get("pages") or []) if isinstance(p, dict)]
    for p in ga4_pages:
        if "engagement_rate" not in p and p.get("engRate"):
            parsed = parse_float(str(p.get("engRate")).replace("%", ""))
            p["engagement_rate"] = 0 if parsed != parsed else parsed / 100

    def is_booking(page: dict) -> bool:
        path = (page.get("path") or "").lower()
        return any(bp in path for bp in BOOKING_PAGES)

    booking_pages = [p for p in ga4_pages if is_booking(p)]
    total_booking_sessions = sum(parse_int(p.get("sessions")) for p in booking_pages)
    avg_booking_eng = (
        sum(parse_float(p.get("engagement_rate")) for p in booking_pages) / len(booking_pages)
        if booking_pages
        else 0.0
    )
    top_booking_pages = sorted(
        [
            {
                "path": p.get("path"),
                "sessions": parse_int(p.get("sessions")),
                "engRate": parse_float(p.get("engagement_rate")),
                "isBooking": True,
            }
            for p in booking_pages
        ],
        key=lambda x: x["sessions"],
        reverse=True,
    )[:5]

    cta_performance: dict[str, dict] = {}
    for p in ig_posts[:30]:
        bucket = _bucket_cta(p.get("caption") or "")
        if bucket not in cta_performance:
            cta_performance[bucket] = {
                "count": 0,
                "totalReach": 0,
                "totalLikes": 0,
                "totalSaves": 0,
                "totalComments": 0,
                "totalEngRate": 0.0,
                "posts": [],
            }
        reach = parse_int(p.get("reach"))
        likes = parse_int(p.get("likeCount"))
        saves = parse_int(p.get("saveCount"))
        comments = parse_int(p.get("commentsCount") or p.get("commentCount"))
        eng = parse_float(p.get("engagementRate"))
        b = cta_performance[bucket]
        b["count"] += 1
        b["totalReach"] += reach
        b["totalLikes"] += likes
        b["totalSaves"] += saves
        b["totalComments"] += comments
        b["totalEngRate"] += eng
        b["posts"].append(
            {
                "id": p.get("id"),
                "reach": reach,
                "likes": likes,
                "saves": saves,
                "comments": comments,
                "engRate": eng,
                "caption": (p.get("caption") or "")[:60],
            }
        )

    for b in cta_performance.values():
        cnt = b["count"]
        b["avgReach"] = b["totalReach"] / cnt if cnt else 0
        b["avgLikes"] = b["totalLikes"] / cnt if cnt else 0
        b["avgSaves"] = b["totalSaves"] / cnt if cnt else 0
        b["avgComments"] = b["totalComments"] / cnt if cnt else 0
        b["avgEngRate"] = b["totalEngRate"] / cnt if cnt else 0
        b["saveRate"] = (b["avgSaves"] / b["avgReach"] * 100) if b["avgReach"] else 0
        b["conversion_signal"] = (
            (b["avgSaves"] * 2 + b["avgComments"]) / b["avgReach"] * 100 if b["avgReach"] else 0
        )

    ig_text = " ".join((p.get("caption") or "").lower() for p in ig_posts)
    service_correlation = []
    for service, kws in SERVICE_KEYWORDS.items():
        matching = [p for p in ig_posts if any(k in (p.get("caption") or "").lower() for k in kws)]
        avg_eng = (
            sum(parse_float(p.get("engagementRate")) for p in matching) / len(matching)
            if matching
            else 0.0
        )
        total_reach = sum(parse_int(p.get("reach")) for p in matching)
        saves = sum(parse_int(p.get("saveCount")) for p in matching)
        reach30 = sum(parse_int(p.get("reach")) for p in ig_posts[:30])
        reach_share = (total_reach / reach30 * 100) if reach30 else 0
        service_correlation.append(
            {
                "service": service,
                "post_count": len(matching),
                "reach_share": round(reach_share, 1),
                "avg_engagement": round(avg_eng, 2),
                "total_reach": total_reach,
                "total_saves": saves,
                "save_rate": round(saves / total_reach * 100, 2) if total_reach else 0,
                "ig_signal": round(avg_eng * (1 if matching else 0.3), 2),
            }
        )
    service_correlation.sort(key=lambda s: s["ig_signal"], reverse=True)

    hook_theme_perf = []
    for theme in HOOK_THEMES:
        posts = [
            p
            for p in ig_posts
            if any(k in (p.get("caption") or "").lower() for k in theme["keywords"])
        ]
        avg_eng = (
            sum(parse_float(p.get("engagementRate")) for p in posts) / len(posts) if posts else 0.0
        )
        avg_save = sum(parse_int(p.get("saveCount")) for p in posts) / len(posts) if posts else 0.0
        total_r = sum(parse_int(p.get("reach")) for p in posts)
        total_saves = sum(parse_int(p.get("saveCount")) for p in posts)
        hook_theme_perf.append(
            {
                "theme_id": theme["id"],
                "theme_label": theme["label"],
                "post_count": len(posts),
                "avg_engagement": round(avg_eng, 2),
                "avg_saves": round(avg_save, 1),
                "save_rate": round(total_saves / total_r * 100, 2) if total_r else 0,
                "total_reach": total_r,
                "conversion_proxy": round(avg_eng + avg_save * 0.5, 2),
            }
        )
    hook_theme_perf.sort(key=lambda t: t["conversion_proxy"], reverse=True)

    cta_rankings = sorted(
        [
            {
                "cta_type": bucket,
                "post_count": data["count"],
                "avg_eng_rate": round(data["avgEngRate"], 2),
                "avg_save_rate": round(data["saveRate"], 2),
                "conversion_signal": round(data["conversion_signal"], 3),
                "conversion_rank": 0,
            }
            for bucket, data in cta_performance.items()
        ],
        key=lambda r: r["conversion_signal"],
        reverse=True,
    )
    for i, row in enumerate(cta_rankings):
        row["conversion_rank"] = i + 1

    service_coverage = []
    for service, kws in SERVICE_KEYWORDS.items():
        booking_kw = service.lower().split()[0]
        ig_mentioned = any(k in ig_text for k in kws)
        ga4_has = any(booking_kw in (p.get("path") or "").lower() for p in ga4_pages)
        post_count = sum(1 for p in ig_posts if any(k in (p.get("caption") or "").lower() for k in kws))
        sessions = sum(
            parse_int(p.get("sessions"))
            for p in ga4_pages
            if booking_kw in (p.get("path") or "").lower()
        )
        service_coverage.append(
            {
                "service": service,
                "has_ig_content": ig_mentioned,
                "has_booking_page": ga4_has,
                "ig_post_count": post_count,
                "ga4_sessions": sessions,
                "coverage_score": (2 if ig_mentioned else 0) + (1 if ga4_has else 0),
            }
        )

    top_service = service_correlation[0] if service_correlation else {"service": "n/a", "ig_signal": 0}
    top_cta = cta_rankings[0] if cta_rankings else {"cta_type": "n/a", "conversion_signal": 0}
    top_page = top_booking_pages[0] if top_booking_pages else {"path": "n/a", "sessions": 0}
    top_theme = hook_theme_perf[0] if hook_theme_perf else {"theme_label": "n/a", "conversion_proxy": 0}

    return {
        "updated": utc_now_iso(),
        "generated": "generate_conversion_attribution.js",
        "summary": {
            "total_ig_posts_analysed": len(ig_posts[:30]),
            "total_ga4_pages": len(ga4_pages),
            "booking_sessions": total_booking_sessions,
            "avg_booking_eng_rate": round(avg_booking_eng, 2),
            "top_converting_service": top_service["service"],
            "top_converting_cta": top_cta["cta_type"],
            "top_booking_page": top_page["path"],
            "top_hook_theme": top_theme["theme_label"],
        },
        "cta_performance": cta_rankings,
        "service_correlation": service_correlation,
        "hook_themes": hook_theme_perf,
        "top_booking_pages": top_booking_pages,
        "service_coverage": service_coverage,
        "quick_wins": [
            {
                "service": s["service"],
                "ig_signal": s["ig_signal"],
                "save_rate": s["save_rate"],
                "action": (
                    f'Push {s["service"]} - {s["post_count"]} posts, '
                    f'{s["save_rate"]}% save rate, {s["avg_engagement"]}% avg eng'
                ),
            }
            for s in service_correlation
            if s["ig_signal"] > 2 and s["save_rate"] > 1
        ][:3],
    }


# ── 5. retargeting recommendations ────────────────────────────────────────

def _build_retarget_hook(o: dict) -> str:
    topic = o.get("topic") or ""
    if "lesson" in topic:
        return "Still working on your swing? Here's what actually changes it."
    if "driver" in topic:
        return "Your driver data is telling a story. TrackMan tells you how to fix it."
    if "putt" in topic:
        return "One putting session changed everything. Here's what Cat found."
    return "One session. Major difference. Book yours."


def _build_service_hook(l: dict) -> str:
    svc = l.get("service") or ""
    mapping = {
        "Golf Lessons": "Your handicap didn't drop by itself. Here's what actually changes it.",
        "Club Fitting": "Off-the-rack clubs are costing you yards. Here's what TrackMan found.",
        "Simulator": "Rain, heat, winter — the sim doesn't care. Your game still improves.",
        "Membership": "Unlimited practice. 15% off everything. The membership that pays for itself.",
        "Events": "This week's competition: lowest net score wins a custom driver fitting.",
    }
    return mapping.get(svc, f"You've been thinking about {svc} long enough. Here's where to start.")


def _build_service_cta(svc: str) -> str:
    mapping = {
        "Golf Lessons": "Book your first lesson · swingshack.co.za/membership · Coach Cat & Dave",
        "Club Fitting": "Get your clubs custom fitted · swingshack.co.za/membership · TrackMan powered",
        "Simulator": "Practice year-round in the sim · swingshack.co.za/book · From R250/session",
        "Membership": "Unlimited practice · 15% off everything · swingshack.co.za/membership",
        "Events": "Enter this week's competition · swingshack.co.za/events · Prizes every week",
    }
    return mapping.get(svc, "Book your session · swingshack.co.za/membership")


def _rework_hook(hook: str, _topic: str) -> str:
    lower = (hook or "").lower()
    if "trackman" in lower or "meter" in lower:
        return "Your numbers don't lie. Neither does the fix. One TrackMan session — book it."
    if "?" in hook:
        return hook.rstrip("?") + "? Here's exactly how to fix it. Book your session."
    return f"{hook[:50]} — and here's exactly how to fix it. Book your session."


def step_retargeting_recommendations() -> dict:
    leaks = as_dict(read_json("funnel-leaks.json"))
    missed = as_dict(read_json("missed-opportunities.json"))
    plan = as_dict(read_json("post-plan.json"))
    planned_hooks = {
        (p.get("hook") or "").lower()[:40]
        for p in (plan.get("plan") or [])
        if isinstance(p, dict)
    }

    follow_up_gaps = []
    for o in (missed.get("opportunities") or []):
        if not isinstance(o, dict) or o.get("category") != "follow_up_gap":
            continue
        if parse_float(o.get("ig_score")) < 7:
            continue
        topic = o.get("topic") or ""
        score = parse_float(o.get("ig_score"))
        hook_prefix = (o.get("hook") or "").lower()[:40]
        already = any(hook_prefix[:20] in h[:20] for h in planned_hooks if h)
        channel = "IG Reel" if any(x in topic for x in ("lesson", "putt", "short")) else "IG Static"
        follow_up_gaps.append(
            {
                "type": "retarget_existing",
                "action": "Re-run with booking CTA",
                "topic": topic,
                "original_hook": o.get("hook"),
                "original_score": score,
                "suggested_hook": _build_retarget_hook(o),
                "suggested_cta": "Book your session · swingshack.co.za/membership",
                "format": "reel" if channel == "IG Reel" else "static",
                "channel": channel,
                "expected_outcome": {"type": "bookings", "delta": "+15-25%", "label": "+15-25% bookings vs. no CTA"},
                "expiration_window": "today" if score >= 9 else "48h" if score >= 8 else "this_week",
                "source_evidence": f"Hook scored {fmt_num(score)} on IG but no booking follow-up exists",
                "urgency": "today" if score >= 9 else "this_week",
                "owner": o.get("owner") or "Coach Cat",
                "why": f"IG score {fmt_num(score)} with no conversion CTA in follow-up",
                "already_planned": already,
            }
        )
    follow_up_gaps = follow_up_gaps[:4]

    save_gaps = [
        {
            "type": "add_booking_cta",
            "action": "Add booking CTA to high-save content",
            "post_id": l.get("post_id"),
            "reach": l.get("reach"),
            "saves": l.get("saves"),
            "save_rate": l.get("save_rate"),
            "caption_preview": l.get("caption_preview"),
            "suggested_hook": None,
            "suggested_cta": "Ready to fix your game? Book a session → swingshack.co.za/membership",
            "format": "caption_update",
            "channel": "IG Story" if parse_float(l.get("save_rate")) > 4 else "IG Caption update",
            "expected_outcome": {"type": "clicks", "delta": "+8-12%", "label": "+8-12% link clicks from saves"},
            "expiration_window": "today" if parse_int(l.get("saves")) > 10 else "48h",
            "source_evidence": f'{l.get("saves")} saves ({l.get("save_rate")}%) but no booking path',
            "urgency": "today" if parse_float(l.get("save_rate")) > 5 else "this_week",
            "owner": "Swing Shack page",
            "why": f'{l.get("saves")} saves leaking without a booking path',
        }
        for l in (leaks.get("leaks") or [])
        if isinstance(l, dict)
        and l.get("type") == "high_save_no_booking_cta"
        and not l.get("has_booking_cta")
    ][:3]

    svc_map = {
        "Golf Lessons": "IG Reel",
        "Club Fitting": "IG Static",
        "Simulator": "IG Story",
        "Membership": "IG Static",
        "Events": "IG Static",
    }
    service_reminders = []
    for l in (leaks.get("leaks") or []):
        if not isinstance(l, dict) or l.get("type") != "service_page_no_ig":
            continue
        sessions = parse_int(l.get("sessions"))
        exp = "today" if sessions > 80 else "48h" if sessions > 40 else "this_week"
        service_reminders.append(
            {
                "type": "new_service_reminder",
                "action": "Publish service reminder post",
                "service": l.get("service"),
                "page": l.get("page"),
                "sessions": sessions,
                "suggested_hook": _build_service_hook(l),
                "suggested_cta": _build_service_cta(l.get("service") or ""),
                "format": "static",
                "channel": svc_map.get(l.get("service") or "", "IG Static"),
                "expected_outcome": {"type": "bookings", "delta": "+10-20%", "label": "+10-20% sessions from IG push"},
                "expiration_window": exp,
                "source_evidence": f'{sessions} GA4 sessions on {l.get("page")} with no IG coverage this week',
                "urgency": "today" if sessions > 80 else "this_week" if sessions > 40 else "flexible",
                "owner": l.get("owner"),
                "why": f"{sessions} sessions with no social conversion path",
            }
        )
    service_reminders = service_reminders[:3]

    booking_retarget = [
        {
            "type": "push_booking_cta",
            "action": "Push booking CTA — traffic is hot",
            "sessions": l.get("sessions"),
            "suggested_hook": "Your clubs are waiting. Your handicap won't fix itself. ⛳",
            "suggested_cta": "Book a session · swingshack.co.za/bookings · From R250",
            "format": "static",
            "channel": "IG Static",
            "expected_outcome": {"type": "bookings", "delta": "+20-35%", "label": "+20-35% booking rate from IG push"},
            "expiration_window": "today",
            "source_evidence": f'{l.get("sessions")} sessions on booking page but 0 booking CTAs in recent IG posts',
            "urgency": l.get("severity"),
            "owner": l.get("owner"),
            "why": "Booking page traffic hot with no retargeting",
        }
        for l in (leaks.get("leaks") or [])
        if isinstance(l, dict) and l.get("type") == "booking_traffic_no_retargeting"
    ][:1]

    win_back = [
        {
            "type": "rework_angle",
            "action": "Rework hook angle for stronger booking intent",
            "topic": o.get("topic"),
            "original_hook": o.get("hook"),
            "original_score": o.get("ig_score"),
            "suggested_hook": _rework_hook(o.get("hook") or "", o.get("topic") or ""),
            "suggested_cta": "Book your lesson · swingshack.co.za/membership · Catherine & Dave",
            "format": "static",
            "channel": "IG Static",
            "expected_outcome": {"type": "bookings", "delta": "+8-15%", "label": "+8-15% bookings from stronger hook"},
            "expiration_window": "this_week",
            "source_evidence": f'Hook scored {fmt_num(o.get("ig_score"))} — moderate, needs booking intent upgrade',
            "urgency": "this_week",
            "owner": o.get("owner") or "Swing Shack page",
            "why": f'Score {fmt_num(o.get("ig_score"))} — reword with direct booking urgency',
        }
        for o in (missed.get("opportunities") or [])
        if isinstance(o, dict)
        and o.get("category") == "follow_up_gap"
        and 6 <= parse_float(o.get("ig_score")) < 8
    ][:2]

    promo_gaps = [
        {
            "type": "promo_plus_booking",
            "action": "Pair contest hook with direct booking CTA",
            "topic": o.get("topic") or o.get("angle_label") or "contest",
            "hook": o.get("hook") or o.get("suggestion"),
            "suggested_hook": "Lowest net score wins a custom driver fitting. Or get one anyway.",
            "suggested_cta": "Enter now · Or book your fitting → swingshack.co.za/membership",
            "format": "static",
            "channel": "IG Static",
            "expected_outcome": {"type": "awareness", "delta": "+reach + bookings", "label": "+reach (contest) + bookings (CTA)"},
            "expiration_window": "this_week",
            "source_evidence": "Contest drives reach; booking CTA converts high-intent audience",
            "urgency": "this_week",
            "owner": "Swing Shack page",
            "why": "Contest hooks get reach but no conversion — pair with direct CTA",
        }
        for o in (missed.get("opportunities") or [])
        if isinstance(o, dict)
        and (o.get("category") == "offer_gap" or "contest" in (o.get("type") or ""))
    ][:2]

    all_recs = [
        *booking_retarget,
        *save_gaps,
        *service_reminders,
        *[f for f in follow_up_gaps if not f.get("already_planned")],
        *win_back,
        *promo_gaps,
    ][:12]

    seen: set[str] = set()
    deduped = []
    for r in all_recs:
        key = r["type"] + str(r.get("topic") or r.get("service") or r.get("post_id") or "")[:20]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    urgency_order = {"today": 0, "48h": 1, "this_week": 2, "flexible": 3}
    deduped.sort(key=lambda r: urgency_order.get(r.get("expiration_window"), 99))

    exp_window: dict[str, int] = {}
    for r in deduped:
        w = r.get("expiration_window") or "flexible"
        exp_window[w] = exp_window.get(w, 0) + 1

    channels = sorted({r.get("channel") for r in deduped if r.get("channel")})
    return {
        "updated": utc_now_iso(),
        "generated": "generate_retargeting_recommendations.js",
        "summary": {
            "total": len(deduped),
            "by_channel": {ch: sum(1 for r in deduped if r.get("channel") == ch) for ch in channels},
            "by_expiration": exp_window,
            "by_urgency": {
                "today": sum(1 for r in deduped if r.get("urgency") == "today"),
                "this_week": sum(1 for r in deduped if r.get("urgency") == "this_week"),
                "flexible": sum(1 for r in deduped if r.get("urgency") == "flexible"),
            },
            "owner_count": len({r.get("owner") for r in deduped if r.get("owner")}),
            "top_action": f'{deduped[0]["action"]} ({deduped[0]["channel"]})' if deduped else "none",
        },
        "recommendations": [{**r, "rank": i + 1} for i, r in enumerate(deduped)],
    }


# ── 6. recommendation scores ────────────────────────────────────────────

URGENCY_SCORE = {"today": 5, "48h": 4, "this_week": 3, "flexible": 2, "evergreen": 1}
REVENUE_MAP = {"bookings": 5, "clicks": 4, "saves": 3, "reminders": 3, "awareness": 2}


def _ease_score(channel: str | None) -> int:
    ch = (channel or "").lower()
    if "caption" in ch:
        return 5
    if "story" in ch:
        return 4
    if "reel" in ch:
        return 3
    if "carousel" in ch:
        return 2
    if "email" in ch or "website" in ch:
        return 2
    return 3


def _confidence_score(rec: dict, outcomes: dict | None) -> int:
    src = rec.get("source_evidence") or ""
    num_match = re.search(r"(\d+)", src)
    base_num = int(num_match.group(1)) if num_match else 50
    signal_strength = min(base_num / 40, 5)
    ig_match = re.search(r"score\s+(\d+\.?\d*)", src, re.I)
    ig_score = float(ig_match.group(1)) if ig_match else 0.0
    learned_adj = 0.0
    if outcomes:
        adj_map = (outcomes.get("learned_signals") or {}).get("confidence_adjustments") or {}
        adj = adj_map.get(rec.get("type"))
        if isinstance(adj, dict):
            if adj.get("adjustment") == "+0.5":
                learned_adj = 0.5
            elif adj.get("adjustment") == "-1.0":
                learned_adj = -1.0
    if ig_score >= 9:
        base_conf = 5
    elif ig_score >= 7:
        base_conf = 4
    elif signal_strength >= 4:
        base_conf = 4
    elif signal_strength >= 2:
        base_conf = 3
    else:
        base_conf = 2
    return max(1, min(5, int(round(base_conf + learned_adj))))


def step_recommendation_scores() -> dict:
    retarget = as_dict(read_json("retargeting-recommendations.json"))
    sales = as_dict(read_json("sales-priority.json"))
    plan = as_dict(read_json("post-plan.json"))
    leaks = as_dict(read_json("funnel-leaks.json"))
    outcomes = read_json("recommendation-outcomes.json")
    outcomes_dict = as_dict(outcomes) if outcomes else None

    retarget_items = []
    for rec in retarget.get("recommendations") or []:
        if not isinstance(rec, dict):
            continue
        rev = REVENUE_MAP.get((rec.get("expected_outcome") or {}).get("type"), 3)
        urg = URGENCY_SCORE.get(rec.get("expiration_window"), 3)
        ease = _ease_score(rec.get("channel"))
        conf = _confidence_score(rec, outcomes_dict)
        score = round(rev * urg * ease * conf / 20, 2)
        outcome_type = (rec.get("expected_outcome") or {}).get("type") or "?"
        retarget_items.append(
            {
                **rec,
                "score": score,
                "breakdown": {
                    "revenue_impact": {"value": rev, "label": f"{outcome_type} ({rev}/5)"},
                    "urgency": {"value": urg, "label": f'{rec.get("expiration_window")} ({urg}/5)'},
                    "ease": {"value": ease, "label": f'{rec.get("channel")} ({ease}/5)'},
                    "confidence": {"value": conf, "label": f"signal-based ({conf}/5)"},
                },
            }
        )

    plan_items = [p for p in (plan.get("plan") or []) if isinstance(p, dict)]
    next_post = next((p for p in plan_items if p.get("status") == "ready"), plan_items[0] if plan_items else None)
    best_post = (
        {
            **next_post,
            "score": next_post.get("freshness_score") or 7,
            "reason": f'Freshness {next_post.get("freshness_score") or 7}/10 · {next_post.get("objective")} · {next_post.get("format")}',
            "type": "post",
        }
        if next_post
        else None
    )

    top_service = (sales.get("priorities") or [None])[0]
    best_service = (
        {
            "service": top_service.get("label"),
            "score": top_service.get("score"),
            "reason": f'{top_service.get("score")}/10 — {(top_service.get("reasons") or [""])[0]}',
            "cta": top_service.get("recommended_cta"),
            "priority": top_service.get("priority_level"),
            "type": "service",
        }
        if isinstance(top_service, dict)
        else None
    )

    best_retarget = max(retarget_items, key=lambda r: r["score"], default=None)
    funnel_leak = (leaks.get("leaks") or [None])[0]
    top_leak = (
        {
            **funnel_leak,
            "score": min(parse_int(funnel_leak.get("sessions")) / 20, 10) if funnel_leak.get("sessions") else 6,
            "type": "funnel_leak",
            "reason": funnel_leak.get("easy_fix") or funnel_leak.get("suggestion"),
            "suggested_cta": "Book a session · swingshack.co.za/bookings · From R250",
        }
        if isinstance(funnel_leak, dict)
        else None
    )

    do_first = [
        item
        for item in [
            {
                "slot": "post",
                "label": "Post this first",
                "emoji": "🎯",
                "item": best_post,
                "score_note": f'Freshness {best_post["score"]}/10' if best_post else None,
            },
            {
                "slot": "service",
                "label": "Push this service",
                "emoji": "💰",
                "item": best_service,
                "score_note": f'{best_service["score"]}/10' if best_service else None,
            },
            {
                "slot": "retarget",
                "label": "Retarget this first",
                "emoji": "🔁",
                "item": best_retarget,
                "score_note": f'score {fmt_num(best_retarget["score"])}' if best_retarget else None,
            },
            {
                "slot": "leak",
                "label": "Fix this leak",
                "emoji": "⚠️",
                "item": top_leak,
                "score_note": f'{top_leak.get("sessions")} sessions' if top_leak and top_leak.get("sessions") else None,
            },
        ]
        if item["item"]
    ]

    overall = (
        round(sum(d["item"]["score"] for d in do_first) / len(do_first), 1) if do_first else 0
    )
    ranked_items = sorted(retarget_items, key=lambda r: r["score"], reverse=True)[:8]
    all_items = sorted(retarget_items, key=lambda r: r["score"], reverse=True)

    return {
        "updated": utc_now_iso(),
        "generated": "generate_recommendation_scores.js",
        "summary": {
            "overall_priority_score": overall,
            "do_first_count": len(do_first),
            "retarget_items_scored": len(retarget_items),
            "top_retarget_score": best_retarget["score"] if best_retarget else 0,
            "best_post_score": best_post["score"] if best_post else 0,
            "best_service_score": best_service["score"] if best_service else 0,
        },
        "do_first": do_first,
        "ranked_items": ranked_items,
        "all_items": all_items,
    }


# ── 7. recommendation outcomes ────────────────────────────────────────────

def _make_rec_id(rec_type: str, topic: str | None, hook: str | None) -> str:
    raw = f"{rec_type}:{(topic or hook or '')[:30].lower().strip()}"
    h = 0
    for ch in raw:
        h = ((h << 5) - h) + ord(ch)
        h &= 0xFFFFFFFF
    if h >= 0x80000000:
        h -= 0x100000000
    return f"rec_{abs(h):08x}"


def step_recommendation_outcomes() -> dict:
    ig = as_dict(read_json("ig-analytics.json"))
    ga4 = as_dict(read_json("ga4-metrics.json"))
    retarget = as_dict(read_json("retargeting-recommendations.json"))
    plan = as_dict(read_json("post-plan.json"))
    sales = as_dict(read_json("sales-priority.json"))

    ig_posts = [p for p in (ig.get("posts") or []) if isinstance(p, dict)]
    ga4_pages = [p for p in (ga4.get("pages") or []) if isinstance(p, dict)]

    all_recommendations: list[dict] = []
    for p in plan.get("plan") or []:
        if not isinstance(p, dict) or not p.get("hook"):
            continue
        all_recommendations.append(
            {
                "recommendation_id": _make_rec_id("post_plan", p.get("hook"), None),
                "source": "post_plan",
                "type": "post_plan",
                "topic": (p.get("topics") or [p.get("objective") or "general"])[0],
                "hook": p.get("hook"),
                "cta": p.get("cta"),
                "channel": "IG Static",
                "objective": p.get("objective"),
                "day": p.get("day"),
                "date": p.get("date"),
                "owner": p.get("owner"),
                "urgency": p.get("urgency"),
                "score": p.get("freshness_score") or 5,
                "expiration_window": "today",
                "expected_outcome": {"type": "awareness", "label": "reach + engagement"},
                "source_evidence": f'Post plan: {p.get("day")} · {p.get("format")}',
                "created_at": utc_now_iso(),
                "status": "recommended",
            }
        )

    for r in retarget.get("recommendations") or []:
        if not isinstance(r, dict):
            continue
        rec = {
            "recommendation_id": _make_rec_id(r.get("type"), r.get("topic") or r.get("service"), r.get("suggested_hook")),
            "source": "retarget",
            "type": r.get("type"),
            "hook": r.get("suggested_hook") or r.get("hook"),
            "cta": r.get("suggested_cta"),
            "channel": r.get("channel"),
            "urgency": r.get("urgency"),
            "expiration_window": r.get("expiration_window"),
            "expected_outcome": r.get("expected_outcome"),
            "source_evidence": r.get("source_evidence"),
            "created_at": r.get("updated") or utc_now_iso(),
            "status": "recommended",
        }
        # JS JSON.stringify drops undefined — omit missing score/topic keys.
        topic = r.get("topic") or r.get("service")
        if topic is not None:
            rec["topic"] = topic
        if r.get("score") is not None:
            rec["score"] = r.get("score")
        all_recommendations.append(rec)

    for i, s in enumerate((sales.get("priorities") or [])[:3]):
        if not isinstance(s, dict):
            continue
        all_recommendations.append(
            {
                "recommendation_id": _make_rec_id("service_push", s.get("label"), None),
                "source": "service_push",
                "type": "service_push",
                "topic": s.get("label"),
                "hook": f'Push {s.get("label")} — {(s.get("reasons") or [""])[0]}',
                "cta": s.get("recommended_cta"),
                "channel": "IG Static",
                "urgency": "today" if s.get("priority_level") == "HIGH" else "this_week",
                "score": s.get("score"),
                "expiration_window": "today" if s.get("priority_level") == "HIGH" else "48h",
                "expected_outcome": {"type": "bookings", "label": "+10-20% booking rate"},
                "source_evidence": f'Service priority #{i + 1} · score {s.get("score")}/10',
                "created_at": utc_now_iso(),
                "status": "recommended",
            }
        )

    ig_caps = [
        {
            **p,
            # Match JS: only `caption` (seed uses captionPreview — JS leaves caption empty).
            "captionLower": (p.get("caption") or "").lower(),
            "hook": js_substring(p.get("caption") or "", 80),
        }
        for p in ig_posts
    ]
    recent = ig_caps[:30]
    baseline = {
        "avgEngRate": sum(parse_float(p.get("engagementRate")) for p in recent) / max(len(recent), 1),
        "avgReach": sum(parse_int(p.get("reach")) for p in recent) / max(len(recent), 1),
        "avgSaves": sum(parse_int(p.get("saveCount")) for p in recent) / max(len(recent), 1),
        "avgLikes": sum(parse_int(p.get("likeCount")) for p in recent) / max(len(recent), 1),
    }

    booking_page = next((p for p in ga4_pages if "book" in (p.get("path") or "").lower()), None)
    booking_sessions = parse_int(booking_page.get("sessions")) if booking_page else 0

    def hook_similarity(r_hook: str | None, p_caption: str | None) -> float:
        if not r_hook or not p_caption:
            return 0.0
        r_words = {w for w in r_hook.lower().split() if len(w) > 3}
        p_words = {w for w in p_caption.lower().split() if len(w) > 3}
        if not r_words:
            return 0.0
        return sum(1 for w in r_words if w in p_words) / len(r_words)

    def cta_match(r_cta: str | None, p_caption: str | None) -> float:
        if not r_cta or not p_caption:
            return 0.0
        terms = ["book", "booking", "lesson", "coach", "fitting", "swingshack", "membership", "simulator"]
        r_m = sum(1 for t in terms if t in r_cta.lower())
        p_m = sum(1 for t in terms if t in p_caption.lower())
        return 1.0 if r_m > 0 and p_m > 0 else 0.0

    def eng_delta(eng_rate: float) -> float:
        return round(parse_float(eng_rate) - baseline["avgEngRate"], 2)

    def outcome_status(eng_rate: float, reach: int, saves: int, rec: dict) -> str:
        expected = (rec.get("expected_outcome") or {}).get("type") or "awareness"
        delta = eng_delta(eng_rate)
        save_rate = (saves / reach * 100) if reach else 0.0
        if expected == "bookings":
            if save_rate > 2 or delta > 1:
                return "won"
            if save_rate > 0.5 or delta > -1:
                return "neutral"
            return "lost"
        if expected == "clicks":
            if save_rate > 1.5:
                return "won"
            if save_rate > 0.5:
                return "neutral"
            return "lost"
        if delta > 1.5:
            return "won"
        if delta > -2:
            return "neutral"
        return "lost"

    evaluated = []
    now = datetime.now(timezone.utc)
    for rec in all_recommendations:
        try:
            created = datetime.fromisoformat(str(rec.get("created_at", "")).replace("Z", "+00:00"))
            days_old = (now - created).total_seconds() / 86400
        except (TypeError, ValueError):
            days_old = 0
        if days_old > 14:
            evaluated.append({**rec, "status": "stale", "executed": False, "outcome_status": "not_executed"})
            continue

        best_match = None
        best_score = 0.0
        for post in recent:
            # Faithful to JS: match against post.caption only (not captionPreview).
            caption = post.get("caption")
            h_sim = hook_similarity(rec.get("hook"), caption)
            c_match = cta_match(rec.get("cta"), caption)
            type_bonus = 0.2 if rec.get("type") == "post_plan" and rec.get("topic") and rec["topic"].lower() in post["captionLower"] else 0.0
            score = h_sim * 0.6 + c_match * 0.3 + type_bonus
            if score > best_score and score > 0.2:
                best_score = score
                best_match = post

        if not best_match:
            evaluated.append(
                {
                    **rec,
                    "status": "not_executed",
                    "executed": False,
                    "outcome_status": "not_executed",
                    "matched_post_id": None,
                    "match_confidence": round(best_score, 2),
                }
            )
            continue

        eng_rate = parse_float(best_match.get("engagementRate"))
        reach = parse_int(best_match.get("reach"))
        likes = parse_int(best_match.get("likeCount"))
        saves = parse_int(best_match.get("saveCount"))
        comments = parse_int(best_match.get("commentsCount") or best_match.get("commentCount"))
        evaluated.append(
            {
                **rec,
                "status": "executed",
                "executed": True,
                "outcome_status": outcome_status(eng_rate, reach, saves, rec),
                "matched_post_id": best_match.get("id") or "unknown",
                "match_confidence": round(best_score, 2),
                "metrics": {
                    "reach": reach,
                    "likes": likes,
                    "saves": saves,
                    "comments": comments,
                    "engagement_rate": eng_rate,
                    "delta_vs_baseline": eng_delta(eng_rate),
                    "save_rate": round(saves / reach * 100, 2) if reach else 0,
                },
                "posted_at": best_match.get("timestamp") or best_match.get("created_at") or rec.get("created_at"),
            }
        )

    executed_recs = [r for r in evaluated if r.get("executed")]
    by_type: dict[str, dict] = {}
    for r in executed_recs:
        t = r.get("type") or "unknown"
        by_type.setdefault(t, {"total": 0, "won": 0, "neutral": 0, "lost": 0})
        by_type[t]["total"] += 1
        status = r.get("outcome_status")
        if status in by_type[t]:
            by_type[t][status] += 1

    type_win_rates = sorted(
        [
            {
                "type": t,
                "total": d["total"],
                "won": d["won"],
                "neutral": d["neutral"],
                "lost": d["lost"],
                "win_rate": round(d["won"] / d["total"] * 100, 1) if d["total"] else 0,
            }
            for t, d in by_type.items()
        ],
        key=lambda x: x["win_rate"],
        reverse=True,
    )

    won = sum(1 for r in evaluated if r.get("outcome_status") == "won")
    neutral = sum(1 for r in evaluated if r.get("outcome_status") == "neutral")
    lost = sum(1 for r in evaluated if r.get("outcome_status") == "lost")
    not_exec = sum(1 for r in evaluated if r.get("outcome_status") == "not_executed")
    stale = sum(1 for r in evaluated if r.get("status") == "stale")
    non_stale = [r for r in evaluated if r.get("status") != "stale"]
    exec_rate = round(len(executed_recs) / len(non_stale) * 100, 1) if non_stale else 0.0

    performed = sorted(
        [r for r in executed_recs if r.get("metrics")],
        key=lambda r: (r.get("metrics") or {}).get("delta_vs_baseline") or 0,
        reverse=True,
    )
    best_rec = performed[0] if performed else None
    worst_rec = performed[-1] if performed else None
    ignored = [r for r in evaluated if r.get("status") == "not_executed"][:5]
    underperformed = [r for r in executed_recs if r.get("outcome_status") == "lost"][:3]

    learned = {
        "best_channel": type_win_rates[0]["type"] if type_win_rates else "retarget_existing",
        "best_channel_rate": type_win_rates[0]["win_rate"] if type_win_rates else 0,
        "worst_channel": type_win_rates[-1]["type"] if type_win_rates else "unknown",
        "worst_channel_rate": type_win_rates[-1]["win_rate"] if type_win_rates else 0,
        "confidence_adjustments": {
            r["type"]: {
                "observed_win_rate": r["win_rate"],
                "expected_won": (
                    "confidence_appropriate"
                    if r["won"] > r["lost"]
                    else "confidence_too_high"
                    if r["won"] < r["lost"]
                    else "neutral"
                ),
                "adjustment": "+0.5" if r["win_rate"] > 60 else "-1.0" if r["win_rate"] < 30 else "none",
            }
            for r in type_win_rates
        },
        "overall_win_rate": round(won / len(executed_recs) * 100, 1) if executed_recs else 0,
        "exec_rate": exec_rate,
    }

    return {
        "updated": utc_now_iso(),
        "generated": "generate_recommendation_outcomes.js",
        "summary": {
            "total_recommended": len(evaluated),
            "executed": len(executed_recs),
            "won": won,
            "neutral": neutral,
            "lost": lost,
            "not_executed": not_exec,
            "stale": stale,
            "exec_rate": exec_rate,
            "overall_win_rate": learned["overall_win_rate"],
            "baseline_eng_rate": round(baseline["avgEngRate"], 2),
            "booking_sessions": booking_sessions,
        },
        "type_win_rates": type_win_rates,
        "learned_signals": learned,
        "best_recommendation": (
            {
                "id": best_rec.get("recommendation_id"),
                "hook": best_rec.get("hook"),
                "type": best_rec.get("type"),
                "delta": (best_rec.get("metrics") or {}).get("delta_vs_baseline"),
                "eng_rate": (best_rec.get("metrics") or {}).get("engagement_rate"),
                "reach": (best_rec.get("metrics") or {}).get("reach"),
            }
            if best_rec
            else None
        ),
        "worst_recommendation": (
            {
                "id": worst_rec.get("recommendation_id"),
                "hook": worst_rec.get("hook"),
                "type": worst_rec.get("type"),
                "delta": (worst_rec.get("metrics") or {}).get("delta_vs_baseline"),
                "eng_rate": (worst_rec.get("metrics") or {}).get("engagement_rate"),
            }
            if worst_rec
            else None
        ),
        "ignored": [
            {"id": r.get("recommendation_id"), "hook": r.get("hook"), "type": r.get("type"), "reason": "no_matching_post_found"}
            for r in ignored
        ],
        "underperformed": [
            {
                "id": r.get("recommendation_id"),
                "hook": r.get("hook"),
                "type": r.get("type"),
                "delta": (r.get("metrics") or {}).get("delta_vs_baseline"),
                "reason": "below_baseline_engagement",
            }
            for r in underperformed
        ],
        "all_evaluated": evaluated,
    }


# ── 8. website insights ───────────────────────────────────────────────────

def step_website_insights() -> dict:
    ga4 = as_dict(read_json("ga4-metrics.json"))
    geo = as_dict(read_json("geo-audit.json"))

    pages = [p for p in (ga4.get("pages") or []) if isinstance(p, dict)]
    total_sessions = parse_int(ga4.get("total_sessions"))

    weak_ctas = []
    for p in sorted(
        [p for p in pages if parse_float(p.get("engRate")) < 35 and parse_int(p.get("sessions")) >= 10],
        key=lambda x: parse_int(x.get("sessions")),
        reverse=True,
    )[:5]:
        weak_ctas.append(
            {
                "page": p.get("path"),
                "sessions": p.get("sessions"),
                "engagement": p.get("engRate"),
                "severity": "HIGH" if parse_int(p.get("sessions")) > 50 else "MEDIUM",
                "likely_issue": "No CTA visible above fold" if parse_float(p.get("engRate")) < 20 else "Weak or missing CTA",
                "fix": f'Add prominent CTA to {p.get("path")}',
            }
        )

    sources = ga4.get("sources") or []
    organic_sessions = sum(
        parse_int(s.get("sessions"))
        for s in sources
        if isinstance(s, dict) and "google" in (s.get("source") or "").lower()
    )
    direct_sessions = sum(
        parse_int(s.get("sessions")) for s in sources if isinstance(s, dict) and s.get("source") == "direct"
    )
    social_sessions = sum(
        parse_int(s.get("sessions"))
        for s in sources
        if isinstance(s, dict)
        and any(x in (s.get("source") or "").lower() for x in ("instagram", "facebook", "tiktok", "twitter", "linkedin"))
    )
    source_share = {
        "organic_pct": f"{organic_sessions / total_sessions * 100:.1f}" if total_sessions else "0",
        "direct_pct": f"{direct_sessions / total_sessions * 100:.1f}" if total_sessions else "0",
        "social_pct": f"{social_sessions / total_sessions * 100:.1f}" if total_sessions else "0",
        "organic_sessions": organic_sessions,
        "direct_sessions": direct_sessions,
        "social_sessions": social_sessions,
        "total": total_sessions,
    }

    booking_pages = [p for p in pages if "book" in (p.get("path") or "")]
    checkout_pages = [
        p
        for p in pages
        if any(x in (p.get("path") or "") for x in ("checkout", "pricing", "membership"))
    ]
    coaching_pages = [p for p in pages if any(x in (p.get("path") or "") for x in ("coach", "lesson"))]
    fitting_pages = [p for p in pages if any(x in (p.get("path") or "") for x in ("fitting", "club"))]
    funnel = {
        "booking_pages": {
            "sessions": sum(parse_int(p.get("sessions")) for p in booking_pages),
            "paths": [p.get("path") for p in booking_pages],
        },
        "checkout_pages": {
            "sessions": sum(parse_int(p.get("sessions")) for p in checkout_pages),
            "paths": [p.get("path") for p in checkout_pages],
        },
        "coaching_pages": {
            "sessions": sum(parse_int(p.get("sessions")) for p in coaching_pages),
            "paths": [p.get("path") for p in coaching_pages],
        },
        "fitting_pages": {
            "sessions": sum(parse_int(p.get("sessions")) for p in fitting_pages),
            "paths": [p.get("path") for p in fitting_pages],
        },
    }

    structured_recs: list[dict] = []
    insights: list[str] = []

    if weak_ctas:
        high = [w for w in weak_ctas if w.get("severity") == "HIGH"]
        structured_recs.append(
            {
                "issue": "High-traffic pages with weak CTA",
                "severity": "HIGH" if high else "MEDIUM",
                "evidence": (
                    f'{len(high)} page(s) with >50 sessions but <20% engagement. Pages: '
                    + "; ".join(f'{w["page"]} ({w["sessions"]} sess, {w["engagement"]} eng)' for w in weak_ctas)
                ),
                "recommended_fix": (
                    'Add prominent "Book Now" CTA to: '
                    + ", ".join(w["page"] for w in weak_ctas)
                    + ". Test button contrast, size, and above-fold placement."
                ),
                "source_metric": "ga4.pages.engagementRate",
            }
        )
        insights.append(f"⚠️ {len(weak_ctas)} pages with high traffic but weak CTAs")

    booking_sess = funnel["booking_pages"]["sessions"]
    checkout_sess = funnel["checkout_pages"]["sessions"]
    if booking_sess > 0 and checkout_sess > 0:
        ratio = checkout_sess / booking_sess
        structured_recs.append(
            {
                "issue": "Booking funnel drop-off detected",
                "severity": "HIGH" if ratio < 0.2 else "MEDIUM" if ratio < 0.3 else "LOW",
                "evidence": (
                    f"{booking_sess} booking page sessions → {checkout_sess} checkout sessions "
                    f"({ratio * 100:.1f}% conversion rate)"
                ),
                "recommended_fix": (
                    'URGENT: Review booking flow for friction. Likely causes: form too long, page speed, or unclear next step. Test a single-field "Book a Session" CTA first.'
                    if ratio < 0.2
                    else "Review booking confirmation flow. Ensure checkout page loads fast and has minimal form fields."
                ),
                "source_metric": "ga4.funnel.booking_to_checkout_ratio",
            }
        )
        insights.append(f"⚠️ Booking funnel: {booking_sess} → {checkout_sess} checkout ({ratio * 100:.0f}% conv)")

    if organic_sessions > 0:
        structured_recs.append(
            {
                "issue": "Organic traffic without clear booking path",
                "severity": "MEDIUM" if organic_sessions > 50 else "LOW",
                "evidence": f"{organic_sessions} organic sessions ({source_share['organic_pct']}% of all traffic)",
                "recommended_fix": (
                    'Ensure every high-engagement page has a "Book a TrackMan Session" CTA visible in first viewport scroll. '
                    "TrackMan keyword intent = high commercial intent."
                ),
                "source_metric": "ga4.sessions.organic",
            }
        )

    missing_geo = [
        t
        for t in (geo.get("geo_terms") or [])
        if isinstance(t, dict)
        and not any((t.get("term") or "").split()[0].lower() in (p.get("path") or "").lower() for p in pages)
    ][:3]
    if missing_geo:
        structured_recs.append(
            {
                "issue": "Geo search terms without dedicated landing pages",
                "severity": "MEDIUM",
                "evidence": (
                    f'{len(missing_geo)} high-value geo terms with no matching page: '
                    + ", ".join(t.get("term") for t in missing_geo)
                ),
                "recommended_fix": (
                    "Create dedicated landing pages for: "
                    + ", ".join(f'"{t.get("term")}"' for t in missing_geo)
                    + '. Use city + service + "Johannesburg" in title and H1.'
                ),
                "source_metric": "geo.terms.missing_coverage",
            }
        )
        insights.append(f"📍 {len(missing_geo)} geo targets without dedicated pages")

    ga4_insights = ga4.get("insights") or {}
    if total_sessions > 100 and not (ga4_insights.get("recommendations") or []):
        structured_recs.append(
            {
                "issue": "High GA4 sessions but zero recommendations generated",
                "severity": "LOW",
                "evidence": f"{total_sessions} sessions tracked but 0 recommendations in ga4-metrics.json",
                "recommended_fix": (
                    "Check GA4 account: ensure engagement events (scroll, CTA click, form submit) are firing. "
                    "Check Property ID 427380680 has Data API enabled."
                ),
                "source_metric": "ga4.insights.count",
            }
        )

    if total_sessions > 100 and not pages:
        structured_recs.append(
            {
                "issue": "GA4 reports sessions but no page data",
                "severity": "MEDIUM",
                "evidence": f"{total_sessions} total sessions but 0 pages in GA4 response",
                "recommended_fix": (
                    "Check GA4 Data API dimensions: pagePath dimension may be blocked or require different scope. "
                    "Test with sessions dimension only."
                ),
                "source_metric": "ga4.pages.count",
            }
        )

    top_pages = sorted(
        [p for p in pages if parse_float(p.get("engRate")) > 50 and parse_int(p.get("sessions")) > 10],
        key=lambda p: parse_float(p.get("engRate")),
        reverse=True,
    )[:3]
    if top_pages:
        insights.append(
            "✅ Top: " + ", ".join(f'{p.get("path")} ({p.get("engRate")} eng)' for p in top_pages)
        )
    else:
        insights.append("ℹ️ No pages with >50% engagement and >10 sessions — benchmark is high")

    critical = sum(1 for r in structured_recs if r.get("severity") == "HIGH")
    medium = sum(1 for r in structured_recs if r.get("severity") == "MEDIUM")
    low = sum(1 for r in structured_recs if r.get("severity") == "LOW")
    health = "NEEDS_ATTENTION" if critical else "FAIR" if medium else "GOOD"
    top_priority = next((r["issue"] for r in structured_recs if r.get("severity") == "HIGH"), None)
    if not top_priority:
        top_priority = next((r["issue"] for r in structured_recs if r.get("severity") == "MEDIUM"), "No critical issues")

    return {
        "updated": utc_now_iso(),
        "data_window": ga4.get("data_window") or "last_7_days",
        "total_sessions": total_sessions,
        "source_share": source_share,
        "funnel": funnel,
        "weak_ctas": weak_ctas,
        "top_pages": [
            {"path": p.get("path"), "sessions": p.get("sessions"), "engagement": p.get("engRate")} for p in top_pages
        ],
        "recommendations": structured_recs,
        "insights": insights,
        "summary": {
            "health_score": health,
            "critical_count": critical,
            "medium_count": medium,
            "low_count": low,
            "top_priority": top_priority,
        },
    }


def count_reco_rows(outputs: dict[str, dict]) -> int:
    """Sum primary list lengths across all eight reco outputs."""
    total = 0
    total += len(outputs["anomaly-alerts.json"].get("alerts") or [])
    total += len(outputs["missed-opportunities.json"].get("opportunities") or [])
    total += len(outputs["funnel-leaks.json"].get("leaks") or [])
    conv = outputs["conversion-attribution.json"]
    total += len(conv.get("cta_performance") or [])
    total += len(conv.get("service_correlation") or [])
    total += len(conv.get("hook_themes") or [])
    total += len(conv.get("top_booking_pages") or [])
    total += len(conv.get("service_coverage") or [])
    total += len(conv.get("quick_wins") or [])
    total += len(outputs["retargeting-recommendations.json"].get("recommendations") or [])
    scores = outputs["recommendation-scores.json"]
    total += len(scores.get("do_first") or [])
    total += len(scores.get("ranked_items") or [])
    total += len(scores.get("all_items") or [])
    outcomes = outputs["recommendation-outcomes.json"]
    total += len(outcomes.get("all_evaluated") or [])
    total += len(outcomes.get("type_win_rates") or [])
    total += len(outcomes.get("ignored") or [])
    total += len(outcomes.get("underperformed") or [])
    wi = outputs["website-insights.json"]
    total += len(wi.get("weak_ctas") or [])
    total += len(wi.get("top_pages") or [])
    total += len(wi.get("recommendations") or [])
    total += len(wi.get("insights") or [])
    return total
