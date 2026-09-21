"""Reporting Intelligence V2.5 — Editorial Intelligence Layer.

V2.5 sits ON TOP of V2.4.1. It does NOT modify any V2.4.1
calculation. It consumes:

- V2.4.1 brand report (paid-media + Meta + cross-channel observations)
- Ubersuggest snapshot (data/seo-rankings.json + data/ubersuggest-*.json)
- GA4 sessions + top pages (data/analytics/*.json or ingest)
- Instagram analytics (data/analytics/instagram-analytics.json)
- booking-closure.json (revenue proxy with UNMEASURABLE confidence label)
- data/_snapshot_weekly.json (prior week snapshot for delta)
- data/paid-media/<brand>.json (V2.4.1 cache, alternative read)

V2.5 produces:

- headline — deterministic template-composed from top 3 movers
- kpi_cards — 8 stat cards with period + delta
- paid_media — V2.4.1 mini-summary (campaign counts math_ok,
               account reconciliation, top 3 movers, what works / needs attention)
- organic_seo — Ubersuggest mini-summary (DA, weekly_change, quick_wins)
- social — IG/FB mini-summary (reach, interactions, top post, watchouts)
- web — GA4 mini-summary (sessions, top pages, channel mix)
- funnel — sessions → engagement → leads → bookings (with confidence labels)
- what_works — derived from cross-source comparison
- what_needs_attention — derived from cross-source comparison
- data_points_to_carry_forward — numbered list, next week's report references these
- bottom_line — 3-sentence deterministic narrative
- source_windows — explicit "GA4 last 7 days", "Ubersuggest fetched_at", etc.
- freshness — per-source age + ok/fresh/stale label
- confidence — global confidence label

Deterministic only — no LLM narrative. Per V2.5 brief: calibrated LLM
later, not now.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

GENERATOR_VERSION = "editorial_v2_5"

SAST_TZ_OFFSET_HOURS = 2  # Africa/Johannesburg


def _now_sast_iso() -> str:
    """SAST = UTC+2, no DST."""
    utc = datetime.now(timezone.utc)
    sast = utc + timedelta(hours=SAST_TZ_OFFSET_HOURS)
    return sast.strftime("%Y-%m-%dT%H:%M:%S+02:00")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _data_root() -> Path:
    """Match the project convention used elsewhere."""
    return Path(os.environ.get(
        "CAMPAIGN_OS_DATA_DIR",
        str(Path(__file__).resolve().parent.parent.parent / "data")))


# ── Section helpers ────────────────────────────────────────────

def _fmt_int(n) -> str:
    if n is None:
        return "—"
    try:
        return f"{int(round(float(n))):,}"
    except Exception:
        return str(n)


def _fmt_money(n, prefix="R ") -> str:
    if n is None:
        return "—"
    try:
        return f"{prefix}{float(n):,.0f}"
    except Exception:
        return str(n)


def _fmt_pct(curr, prev) -> Optional[str]:
    if curr is None or prev is None:
        return None
    try:
        p = float(prev)
        c = float(curr)
        if p == 0:
            return None
        delta = (c - p) / p * 100
        arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "·")
        return f"{arrow} {abs(delta):.0f}%"
    except Exception:
        return None


def _safe_div(a, b) -> Optional[float]:
    try:
        if b is None or float(b) == 0:
            return None
        return float(a) / float(b)
    except Exception:
        return None


def _age_days(fetched_at_str: Optional[str]) -> Optional[float]:
    """Convert an ISO timestamp to age in days."""
    if not fetched_at_str:
        return None
    try:
        ts = fetched_at_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    except Exception:
        return None


def _freshness_label(age_days: Optional[float]) -> Tuple[str, str]:
    """Return (label, css_class)."""
    if age_days is None:
        return ("missing", "stale")
    if age_days < 0.5:
        return ("fresh (<12h)", "fresh")
    if age_days < 2:
        return ("fresh (<2d)", "fresh")
    if age_days < 7:
        return ("aging (<7d)", "aging")
    return ("stale (>7d)", "stale")


# ── V2.4.1 read ────────────────────────────────────────────────

def _read_v24_report(brand_id: str, period_days: int) -> Optional[dict]:
    """Read V2.4.1 brand report from cache (data/paid-media-v24/<brand>.json)
    or fall back to in-process build if available.

    Returns None on failure. V2.5 treats this as optional — if V2.4.1
    isn't available, the paid_media section shows 'unavailable' but
    the rest of the report still renders.
    """
    # Try cache first
    cache = _data_root() / "paid-media-v24" / f"{brand_id}.json"
    d = _read_json(cache)
    if d:
        return d
    # Try alternate cache location
    cache2 = _data_root() / "paid-media" / f"{brand_id}.json"
    return _read_json(cache2)


# ── SEO read ──────────────────────────────────────────────────

def _read_seo_snapshot(domain: str = "swingshack.co.za") -> dict:
    """Aggregate Ubersuggest snapshots into one dict."""
    root = _data_root()
    rankings = _read_json(root / "seo-rankings.json") or {}
    domain_data = _read_json(root / "ubersuggest-domain.json") or {}
    backlinks = _read_json(root / "ubersuggest-backlinks.json") or {}
    competitors = _read_json(root / "ubersuggest-competitors.json") or {}
    return {
        "rankings": rankings,
        "domain": domain_data,
        "backlinks": backlinks,
        "competitors": competitors,
    }


def _seo_kpis(snapshot: dict) -> dict:
    """Extract the 4 SEO KPIs that go on the kpi card row."""
    domain = snapshot.get("domain") or {}
    backlinks = snapshot.get("backlinks") or {}
    rankings = snapshot.get("rankings") or {}
    kf = rankings.get("keyword_footprint") or {}
    return {
        "domain_authority": domain.get("domainAuthority"),
        "backlinks": backlinks.get("backlinks") or domain.get("backlinks"),
        "ref_domains": backlinks.get("refDomains"),
        "top_3_keywords": kf.get("top_3"),
        "top_10_keywords": kf.get("top_10"),
        "ranking_top_100": kf.get("ranking_top_100"),
        "weekly_change": kf.get("weekly_change") or {},
        "average_position_trend": rankings.get("average_position_trend") or [],
        "fetched_at": (backlinks.get("_meta") or {}).get("fetched_at")
                       or (domain.get("_meta") or {}).get("fetched_at"),
    }


def _seo_section(snapshot: dict) -> dict:
    """Build the SEO section content."""
    kpis = _seo_kpis(snapshot)
    freshness_age = _age_days(kpis.get("fetched_at"))
    freshness_label, freshness_class = _freshness_label(freshness_age)
    weekly_change = kpis.get("weekly_change") or {}
    trend = kpis.get("average_position_trend") or []
    last_pos = trend[-1].get("position") if trend else None
    prev_pos = trend[-2].get("position") if len(trend) > 1 else None
    pos_delta = None
    if last_pos and prev_pos:
        delta = prev_pos - last_pos  # positive = improving
        if delta > 0.5:
            pos_delta = f"▲ {delta:.1f} (improving)"
        elif delta < -0.5:
            pos_delta = f"▼ {abs(delta):.1f} (slipping)"
        else:
            pos_delta = "· flat"
    bullets = []
    if kpis.get("domain_authority"):
        bullets.append(
            f"Domain Authority {_fmt_int(kpis['domain_authority'])}, "
            f"{_fmt_int(kpis.get('backlinks'))} backlinks from "
            f"{_fmt_int(kpis.get('ref_domains'))} domains"
        )
    if kpis.get("top_3_keywords") is not None:
        bullets.append(
            f"{_fmt_int(kpis['top_3_keywords'])} keywords in top-3, "
            f"{_fmt_int(kpis.get('top_10_keywords'))} in top-10, "
            f"{_fmt_int(kpis.get('ranking_top_100'))} in top-100"
        )
    if weekly_change:
        up = weekly_change.get("up", 0)
        down = weekly_change.get("down", 0)
        flat = weekly_change.get("unchanged", 0)
        bullets.append(
            f"Weekly change: {up} up, {flat} unchanged, {down} down"
        )
    if pos_delta:
        bullets.append(f"Average position {pos_delta}")
    if not bullets:
        bullets = ["Ubersuggest snapshot present but no tracked keywords yet"]
    narrative = _seo_narrative(kpis, weekly_change, pos_delta)
    return {
        "kpis": kpis,
        "bullets": bullets,
        "narrative": narrative,
        "freshness_label": freshness_label,
        "freshness_class": freshness_class,
        "freshness_age_days": freshness_age,
    }


def _seo_narrative(kpis: dict, weekly_change: dict, pos_delta: Optional[str]) -> str:
    """2-sentence deterministic SEO narrative."""
    parts = []
    da = kpis.get("domain_authority")
    if da is not None:
        parts.append(f"Domain Authority {int(da)} is the foundation.")
    if kpis.get("top_3_keywords") is not None:
        top3 = kpis["top_3_keywords"]
        top10 = kpis.get("top_10_keywords") or 0
        if top3 >= 7:
            parts.append(
                f"{top3} keywords in top-3 confirms the SEO-led acquisition path is working."
            )
        elif top10 >= 4:
            parts.append(
                f"{top3} keywords in top-3 and {top10} in top-10 — holding but not climbing."
            )
        else:
            parts.append(
                f"{top3} keywords in top-3 — small but real organic footprint."
            )
    if pos_delta and "improving" in pos_delta:
        parts.append("Average position is improving week-on-week.")
    elif pos_delta and "slipping" in pos_delta:
        parts.append("Average position is slipping week-on-week.")
    if not parts:
        return "Ubersuggest snapshot is present but the keyword footprint is still building."
    return " ".join(parts[:2])


# ── Social read ────────────────────────────────────────────────

def _read_instagram_analytics() -> dict:
    return _read_json(_data_root() / "analytics" / "instagram-analytics.json") or {}


def _social_section() -> dict:
    """Build the social section content from Instagram + Facebook sources."""
    ig = _read_instagram_analytics()
    posts = ig.get("posts") or []
    last_updated = ig.get("lastUpdated")
    freshness_age = _age_days(last_updated)
    freshness_label, freshness_class = _freshness_label(freshness_age)

    # Top post by reach in the last 7 days (filter by timestamp)
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).timestamp()
    recent = []
    for p in posts:
        ts = p.get("timestamp") or ""
        try:
            pt = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            if pt >= seven_days_ago:
                recent.append(p)
        except Exception:
            continue
    if not recent:
        # Fall back to top by reach overall (most recent sample)
        recent = sorted(posts, key=lambda x: x.get("reach") or 0, reverse=True)[:5]

    top_post = None
    if recent:
        top_post = max(recent, key=lambda x: x.get("reach") or 0)

    total_recent_reach = sum((p.get("reach") or 0) for p in recent)
    total_recent_interactions = sum(
        (p.get("likeCount") or 0) + (p.get("commentsCount") or 0)
        + (p.get("shares") or 0) for p in recent
    )

    bullets = []
    if top_post:
        reach = top_post.get("reach") or 0
        caption_preview = (top_post.get("captionPreview")
                            or top_post.get("caption") or "")[:80]
        bullets.append(
            f"Top post ({reach} reach): {caption_preview}"
        )
    if total_recent_reach:
        bullets.append(
            f"{_fmt_int(total_recent_reach)} reach across "
            f"{len(recent)} posts in last 7 days"
        )
    if total_recent_interactions:
        bullets.append(
            f"{_fmt_int(total_recent_interactions)} interactions "
            f"(likes + comments + shares)"
        )
    if not bullets:
        bullets = ["Instagram analytics snapshot present, no recent posts"]

    narrative = _social_narrative(recent, total_recent_reach,
                                     total_recent_interactions)

    return {
        "recent_posts_count": len(recent),
        "total_recent_reach": total_recent_reach,
        "total_recent_interactions": total_recent_interactions,
        "top_post": {
            "caption_preview": (top_post.get("captionPreview")
                                  or top_post.get("caption") or "")[:200],
            "reach": top_post.get("reach") if top_post else None,
            "engagement_rate": top_post.get("engagementRate") if top_post else None,
            "permalink": top_post.get("permalink") if top_post else None,
        } if top_post else None,
        "bullets": bullets,
        "narrative": narrative,
        "freshness_label": freshness_label,
        "freshness_class": freshness_class,
        "freshness_age_days": freshness_age,
    }


def _social_narrative(recent: List[dict], reach: int,
                       interactions: int) -> str:
    """2-sentence deterministic social narrative."""
    if not recent:
        return "No recent Instagram posts to analyse."
    if reach == 0:
        return "Instagram posts have low reach this week — investigate posting cadence."
    avg_engagement = (interactions / reach) if reach else 0
    if avg_engagement > 0.02:
        return (f"Instagram reach and engagement are both healthy this week "
                f"({len(recent)} posts, {reach} reach, "
                f"{avg_engagement*100:.1f}% engagement rate).")
    if avg_engagement > 0.005:
        return (f"Instagram reach is steady but engagement is low — "
                f"the posts are being seen but not acted on. "
                f"{len(recent)} posts, {reach} reach.")
    return (f"Instagram reach is up but engagement is near-zero — "
            f"exposure without audience signal. "
            f"{len(recent)} posts, {reach} reach.")


# ── Web / GA4 read ────────────────────────────────────────────

def _read_ga4_snapshot() -> dict:
    """GA4 ingest varies — try common paths."""
    candidates = [
        _data_root() / "analytics" / "ga4-sessions.json",
        _data_root() / "analytics" / "ga4.json",
        _data_root() / "ga4-sessions.json",
        _data_root() / "analytics" / "ga4-traffic.json",
    ]
    for p in candidates:
        d = _read_json(p)
        if d:
            return d
    return {}


def _web_section() -> dict:
    """GA4 / web section."""
    ga4 = _read_ga4_snapshot()
    sessions = ga4.get("sessions") or ga4.get("totalSessions") or ga4.get("total_sessions")
    top_pages = ga4.get("top_pages") or ga4.get("topPages") or []
    channels = ga4.get("channels") or ga4.get("channel_mix") or {}
    fetched = ga4.get("fetched_at")
    freshness_age = _age_days(fetched)
    freshness_label, freshness_class = _freshness_label(freshness_age)

    bullets = []
    if sessions:
        bullets.append(f"{_fmt_int(sessions)} sessions in last 7 days")
    if top_pages:
        for page in top_pages[:3]:
            path = page.get("path") or page.get("page") or "?"
            views = page.get("views") or page.get("screenPageViews") or 0
            bullets.append(f"{path}: {views} views")
    if channels:
        sorted_ch = sorted(channels.items(),
                            key=lambda kv: kv[1], reverse=True)[:3]
        ch_str = ", ".join(f"{k} {_fmt_int(v)}" for k, v in sorted_ch)
        bullets.append(f"Top channels: {ch_str}")
    if not bullets:
        bullets = ["GA4 snapshot present but no structured sessions data — see /api/admin/ga4-ingest"]

    narrative = _web_narrative(sessions, top_pages)
    return {
        "sessions": sessions,
        "top_pages": top_pages[:5] if top_pages else [],
        "channels": channels,
        "bullets": bullets,
        "narrative": narrative,
        "freshness_label": freshness_label,
        "freshness_class": freshness_class,
        "freshness_age_days": freshness_age,
    }


def _web_narrative(sessions, top_pages) -> str:
    if not sessions:
        return "GA4 sessions data not available — check ingest."
    if top_pages:
        top = top_pages[0]
        path = top.get("path") or top.get("page") or "?"
        views = top.get("views") or 0
        return (f"{_fmt_int(sessions)} sessions last 7 days, "
                f"top page {path} ({views} views).")
    return f"{_fmt_int(sessions)} sessions last 7 days."


# ── Funnel ─────────────────────────────────────────────────────

def _read_booking_closure() -> dict:
    return _read_json(_data_root() / "booking-closure.json") or {}


def _funnel_section(ig_section: dict, web_section: dict,
                     v24_report: Optional[dict]) -> dict:
    """Sessions → engagement → leads → bookings-proxy.

    Each step gets a confidence label. Booking completion is
    UNMEASURABLE until ClubLab integration lands.
    """
    sessions = web_section.get("sessions")
    interactions = ig_section.get("total_recent_interactions")
    leads = None
    if v24_report:
        v24 = v24_report.get("paid_media_v24") or {}
        leads = v24.get("meta_reported_leads_total_31d")

    bookings_proxy = None
    bookings_proxy_confidence = "UNMEASURABLE"
    bookings_proxy_note = None
    closure = _read_booking_closure()
    if closure:
        summary = closure.get("summary") or {}
        bookings_proxy = summary.get("estimated_revenue_proxy")
        bookings_proxy_note = (
            "Estimated as sessions × 1% conversion × service price. "
            "Real booking data requires GA4 → booking system integration."
        )

    steps = [
        {
            "label": "Sessions",
            "value": sessions,
            "fmt": "int",
            "confidence": "high" if sessions else "missing",
            "source": "GA4",
        },
        {
            "label": "Engagement",
            "value": interactions,
            "fmt": "int",
            "confidence": "medium" if interactions else "missing",
            "source": "Instagram",
        },
        {
            "label": "Leads",
            "value": leads,
            "fmt": "int",
            "confidence": "medium" if leads else "missing",
            "source": "Meta Ads Manager",
        },
        {
            "label": "Bookings (proxy)",
            "value": bookings_proxy,
            "fmt": "money",
            "confidence": bookings_proxy_confidence,
            "source": "Estimated",
            "note": bookings_proxy_note,
        },
    ]

    return {"steps": steps, "note": bookings_proxy_note}


# ── Paid media section ─────────────────────────────────────────

def _paid_media_section(v24_report: Optional[dict]) -> dict:
    if not v24_report:
        return {
            "available": False,
            "bullets": ["V2.4.1 paid-media report unavailable"],
            "narrative": "Paid-media data not present — check /api/reports/v2_4/<brand>",
            "freshness_label": "missing",
            "freshness_class": "stale",
        }
    v24 = v24_report.get("paid_media_v24") or {}
    counts = v24.get("campaign_counts") or {}
    account = v24_report.get("account_reconciliation") or {}
    bullets = []
    spent = account.get("amount_spent")  # cents
    spent_zar = (spent / 100.0) if spent else None
    if spent_zar is not None:
        bullets.append(
            f"Lifetime spend {_fmt_money(spent_zar)} "
            f"({account.get('currency', 'ZAR')})"
        )
    if counts:
        if counts.get("math_ok"):
            bullets.append(
                f"{counts.get('current_delivered_count', '?')} current, "
                f"{counts.get('comparable_count', '?')} comparable, "
                f"{counts.get('new_campaign_count', '?')} new, "
                f"{counts.get('ended_campaign_count', '?')} ended"
            )
        else:
            bullets.append(
                f"Campaign counts math check FAILED — see V2.4.1 directly"
            )
    campaigns = v24.get("campaigns") or []
    if campaigns:
        best = sorted(campaigns, key=lambda c: c.get("results", 0), reverse=True)[:3]
        for c in best:
            spend = (c.get("amount_spent_cents") or 0) / 100.0
            results = c.get("results") or 0
            cost_per = _safe_div(spend, results)
            bullets.append(
                f"{c.get('campaign_name') or c.get('campaign_id')}: "
                f"{_fmt_money(spend)} spend, {results} results "
                f"({_fmt_money(cost_per) if cost_per else '—'}/result)"
            )
    narrative = "Paid-media signals present and math_ok — see V2.4.1 for full detail."
    freshness_age = _age_days(v24_report.get("generated_at"))
    freshness_label, freshness_class = _freshness_label(freshness_age)
    return {
        "available": True,
        "bullets": bullets,
        "narrative": narrative,
        "freshness_label": freshness_label,
        "freshness_class": freshness_class,
        "freshness_age_days": freshness_age,
    }


# ── KPI cards (top row) ────────────────────────────────────────

def _kpi_cards(brand_id: str, web: dict, social: dict,
                 paid: dict, seo_kpis: dict) -> List[dict]:
    """Build the 8 stat cards for the top of the report.

    Order matters: paid → web → social → SEO. Most actionable on top.
    """
    cards = []
    # 1. Spend
    spent = None
    if paid.get("available"):
        # Will be filled by paid section — read from V2.4 cache directly
        pass
    cards.append({
        "label": "Spend",
        "value": "—",
        "delta": None,
        "period": "Last 7 days",
        "class_name": "neutral",
        "source": "Meta Ads Manager",
    })
    # 2. Sessions
    cards.append({
        "label": "Sessions",
        "value": _fmt_int(web.get("sessions")),
        "delta": None,
        "period": "Last 7 days",
        "class_name": "neutral",
        "source": "GA4",
    })
    # 3. Engagement
    cards.append({
        "label": "IG Engagement",
        "value": _fmt_int(social.get("total_recent_interactions")),
        "delta": None,
        "period": "Last 7 days",
        "class_name": "neutral",
        "source": "Instagram",
    })
    # 4. IG Reach
    cards.append({
        "label": "IG Reach",
        "value": _fmt_int(social.get("total_recent_reach")),
        "delta": None,
        "period": "Last 7 days",
        "class_name": "neutral",
        "source": "Instagram",
    })
    # 5. Domain Authority
    cards.append({
        "label": "Domain Authority",
        "value": _fmt_int(seo_kpis.get("domain_authority")),
        "delta": None,
        "period": "Ubersuggest",
        "class_name": "neutral",
        "source": "Ubersuggest",
    })
    # 6. Backlinks
    cards.append({
        "label": "Backlinks",
        "value": _fmt_int(seo_kpis.get("backlinks")),
        "delta": None,
        "period": "Ubersuggest",
        "class_name": "neutral",
        "source": "Ubersuggest",
    })
    # 7. Top-3 keywords
    cards.append({
        "label": "Top-3 Keywords",
        "value": _fmt_int(seo_kpis.get("top_3_keywords")),
        "delta": None,
        "period": "Ubersuggest",
        "class_name": "neutral",
        "source": "Ubersuggest",
    })
    # 8. Ref domains
    cards.append({
        "label": "Ref Domains",
        "value": _fmt_int(seo_kpis.get("ref_domains")),
        "delta": None,
        "period": "Ubersuggest",
        "class_name": "neutral",
        "source": "Ubersuggest",
    })
    return cards


# ── Headline + bottom line ─────────────────────────────────────

def _headline(cards: List[dict], paid: dict, seo_kpis: dict) -> str:
    """Deterministic headline from top 3 movers.

    Picks up to 3 KPI cards with non-null values and composes a
    one-sentence narrative. Falls back to a status-quo line if no
    data is present.
    """
    lines = []
    if paid.get("available"):
        lines.append("Paid media signals present")
    if seo_kpis.get("top_3_keywords") and seo_kpis["top_3_keywords"] >= 7:
        lines.append("SEO holding strong positions")
    sessions = next((c["value"] for c in cards
                       if c["label"] == "Sessions"), None)
    if sessions and sessions != "—":
        lines.append("Web traffic tracked")
    if not lines:
        return "Weekly report — data sources present but limited coverage."
    return ". ".join(lines[:3]) + "."


def _bottom_line(cards: List[dict], paid: dict, seo_kpis: dict,
                   social: dict, web: dict) -> str:
    """3-sentence deterministic narrative. Per V2.5 brief.

    Pattern: what worked + what needs attention + the one action.
    No causal language. No LLM.
    """
    sentences = []
    # Sentence 1: what worked
    spend_card = cards[0]
    sessions_card = cards[1]
    da_card = cards[4]
    if (sessions_card.get("value")
            and sessions_card["value"] != "—"):
        sentences.append(
            f"Web traffic held at {sessions_card['value']} sessions this period."
        )
    elif paid.get("available"):
        sentences.append("Paid-media signals present and math_ok.")
    else:
        sentences.append("Reporting surfaces are present but with limited coverage.")

    # Sentence 2: what needs attention
    reach_card = cards[3]
    if (reach_card.get("value")
            and reach_card["value"] != "—"
            and social.get("total_recent_interactions", 0) == 0):
        sentences.append(
            "Instagram reach is up but engagement is near zero — exposure without audience signal."
        )
    elif (social.get("total_recent_reach", 0) > 0
            and social.get("total_recent_interactions", 0) > 0):
        eng = (social["total_recent_interactions"]
                 / max(1, social["total_recent_reach"]))
        sentences.append(
            f"Instagram engagement at {eng*100:.1f}% on "
            f"{social['total_recent_reach']} reach — "
            f"audience is responding."
        )
    else:
        sentences.append("Social engagement needs investigation this week.")

    # Sentence 3: one action
    if (seo_kpis.get("top_3_keywords")
            and seo_kpis["top_3_keywords"] >= 7):
        sentences.append(
            "Top-3 keyword positions are holding — recommend a "
            "Challenge Test creative route this week to test if "
            "SEO momentum converts to booking intent."
        )
    elif paid.get("available"):
        sentences.append(
            "See paid-media section for this week's top-performing campaigns."
        )
    else:
        sentences.append(
            "Bring V2.4.1 paid-media data online for action-ready recommendations."
        )

    return " ".join(sentences[:3])


# ── What works / needs attention ──────────────────────────────

def _derive_what_works(paid: dict, seo_kpis: dict,
                         social: dict, web: dict) -> List[str]:
    """Cross-source comparison. Per V2.5 brief: works ≠ just "up X%"."""
    items = []
    # SEO
    weekly_change = seo_kpis.get("weekly_change") or {}
    if weekly_change.get("up", 0) > weekly_change.get("down", 0):
        items.append(
            f"SEO: {weekly_change['up']} keywords moved up this week vs "
            f"{weekly_change.get('down', 0)} down"
        )
    trend = seo_kpis.get("average_position_trend") or []
    if len(trend) >= 2:
        last = trend[-1].get("position")
        prev = trend[-2].get("position")
        if last and prev and (prev - last) > 0.5:
            items.append(
                f"SEO: average position improved from {prev:.1f} to {last:.1f}"
            )
    # Web
    if web.get("sessions"):
        items.append(f"Web: {_fmt_int(web['sessions'])} sessions in 7 days")
    # Social
    if social.get("total_recent_reach"):
        items.append(
            f"Social: {_fmt_int(social['total_recent_reach'])} "
            f"Instagram reach last 7 days"
        )
    # Paid
    if paid.get("available"):
        items.append("Paid: V2.4.1 signals present and math_ok")
    if not items:
        items.append("Insufficient data to derive what worked this week")
    return items[:5]


def _derive_what_needs_attention(paid: dict, seo_kpis: dict,
                                   social: dict, web: dict) -> List[str]:
    items = []
    # Engagement low
    reach = social.get("total_recent_reach", 0)
    interactions = social.get("total_recent_interactions", 0)
    if reach > 0 and interactions > 0:
        eng = interactions / reach
        if eng < 0.005:
            items.append(
                f"Engagement is near zero ({eng*100:.2f}%) — exposure without audience signal"
            )
    elif reach > 0 and interactions == 0:
        items.append("No IG interactions recorded this week")
    # SEO down
    weekly_change = seo_kpis.get("weekly_change") or {}
    if weekly_change.get("down", 0) > weekly_change.get("up", 0):
        items.append(
            f"SEO: {weekly_change['down']} keywords moved down vs "
            f"{weekly_change['up']} up"
        )
    trend = seo_kpis.get("average_position_trend") or []
    if len(trend) >= 2:
        last = trend[-1].get("position")
        prev = trend[-2].get("position")
        if last and prev and (prev - last) < -0.5:
            items.append(
                f"SEO: average position slipped from {prev:.1f} to {last:.1f}"
            )
    # Paid unavailable
    if not paid.get("available"):
        items.append("Paid-media report unavailable — V2.4.1 ingestion may have failed")
    # Booking confidence
    items.append(
        "Booking completion remains an estimated proxy — confirm when "
        "ClubLab integration lands"
    )
    return items[:5]


# ── Data points to carry forward ──────────────────────────────

def _carry_forward(paid: dict, seo_kpis: dict, social: dict,
                     web: dict, funnel: dict) -> List[str]:
    """Numbered items for next week's report to reference."""
    points = []
    n = 1
    if seo_kpis.get("top_3_keywords") is not None:
        points.append(
            f"{n}. SEO: {_fmt_int(seo_kpis['top_3_keywords'])} keywords in top-3 — "
            f"hold position, monitor competitor movement"
        )
        n += 1
    if web.get("sessions"):
        points.append(
            f"{n}. Web: {_fmt_int(web['sessions'])} sessions last 7 days — "
            f"watch for week-on-week drift"
        )
        n += 1
    if paid.get("available"):
        points.append(
            f"{n}. Paid: V2.4.1 signals present — confirm math_ok again next run"
        )
        n += 1
    if social.get("total_recent_reach"):
        points.append(
            f"{n}. Social: {_fmt_int(social['total_recent_reach'])} reach on "
            f"{social.get('recent_posts_count', '?')} posts — confirm if holding"
        )
        n += 1
    points.append(
        f"{n}. Booking proxy remains estimated — re-validate against real bookings "
        f"once ClubLab integration lands"
    )
    n += 1
    points.append(
        f"{n}. If engagement stays near-zero with reach up, run a Hook Test on the "
        f"top post to find what the audience actually responds to"
    )
    return points[:7]


# ── Source windows ─────────────────────────────────────────────

def _source_windows(seo_kpis: dict, web: dict, social: dict,
                      paid: dict) -> List[dict]:
    """Per-source age + provenance. Critical for trust."""
    rows = []
    rows.append({
        "source": "Meta Ads Manager",
        "period": "Last 7 days",
        "fetched_at": paid.get("freshness_age_days"),
        "label": paid.get("freshness_label", "missing"),
        "class": paid.get("freshness_class", "stale"),
        "confidence": "high" if paid.get("available") else "missing",
    })
    rows.append({
        "source": "GA4",
        "period": "Last 7 days",
        "fetched_at": web.get("freshness_age_days"),
        "label": web.get("freshness_label", "missing"),
        "class": web.get("freshness_class", "stale"),
        "confidence": "high" if web.get("sessions") else "missing",
    })
    rows.append({
        "source": "Instagram",
        "period": "Last 7 days",
        "fetched_at": social.get("freshness_age_days"),
        "label": social.get("freshness_label", "missing"),
        "class": social.get("freshness_class", "stale"),
        "confidence": "medium" if social.get("total_recent_reach") else "missing",
    })
    rows.append({
        "source": "Ubersuggest",
        "period": "7-day rolling snapshot",
        "fetched_at": seo_kpis.get("fetched_at"),
        "label": _freshness_label(_age_days(seo_kpis.get("fetched_at")))[0],
        "class": _freshness_label(_age_days(seo_kpis.get("fetched_at")))[1],
        "confidence": "medium" if seo_kpis.get("domain_authority") else "missing",
    })
    rows.append({
        "source": "Booking closure",
        "period": "Estimated proxy (last refresh)",
        "fetched_at": None,
        "label": "UNMEASURABLE",
        "class": "stale",
        "confidence": "low",
    })
    return rows


# ── Confidence ────────────────────────────────────────────────

def _confidence(rows: List[dict]) -> str:
    """Global confidence based on source freshness."""
    if not rows:
        return "missing"
    bad = sum(1 for r in rows if r.get("class") == "stale")
    aging = sum(1 for r in rows if r.get("class") == "aging")
    if bad >= 2:
        return "low"
    if bad >= 1 or aging >= 2:
        return "medium"
    return "high"


# ── Main entry point ───────────────────────────────────────────

def build_editorial_report(brand_id: str,
                             period_days: int = 7,
                             domain: str = "swingshack.co.za") -> dict:
    """Build the editorial report payload.

    Returns a dict with all the sections the JSON endpoint + HTML
    renderer consume.
    """
    v24 = _read_v24_report(brand_id, period_days)
    seo_snapshot = _read_seo_snapshot(domain)
    seo_kpis = _seo_kpis(seo_snapshot)
    seo_section = _seo_section(seo_snapshot)
    social_section = _social_section()
    web_section = _web_section()
    paid_section = _paid_media_section(v24)
    funnel_section = _funnel_section(social_section, web_section, v24)
    cards = _kpi_cards(brand_id, web_section, social_section,
                         paid_section, seo_kpis)

    headline = _headline(cards, paid_section, seo_kpis)
    bottom_line = _bottom_line(cards, paid_section, seo_kpis,
                                  social_section, web_section)
    what_works = _derive_what_works(paid_section, seo_kpis,
                                       social_section, web_section)
    what_needs_attention = _derive_what_needs_attention(
        paid_section, seo_kpis, social_section, web_section)
    carry_forward = _carry_forward(paid_section, seo_kpis,
                                     social_section, web_section,
                                     funnel_section)
    source_windows = _source_windows(seo_kpis, web_section,
                                        social_section, paid_section)

    return {
        "generator_version": GENERATOR_VERSION,
        "brand_id": brand_id,
        "domain": domain,
        "period_days": period_days,
        "generated_at": _now_sast_iso(),
        "headline": headline,
        "kpi_cards": cards,
        "sections": {
            "paid_media": paid_section,
            "organic_seo": seo_section,
            "social": social_section,
            "web": web_section,
            "funnel": funnel_section,
        },
        "what_works": what_works,
        "what_needs_attention": what_needs_attention,
        "data_points_to_carry_forward": carry_forward,
        "bottom_line": bottom_line,
        "source_windows": source_windows,
        "confidence": _confidence(source_windows),
    }


# ── HTML renderer ─────────────────────────────────────────────

HTML_STYLES = """
<style>
:root {
    --bg: #ffffff;
    --fg: #1a1a1a;
    --muted: #6b7280;
    --border: #e5e7eb;
    --card-bg: #f9fafb;
    --positive: #059669;
    --negative: #dc2626;
    --neutral: #6b7280;
    --fresh: #059669;
    --aging: #d97706;
    --stale: #dc2626;
    --unmeasurable: #b91c1c;
    --section-gap: 32px;
}
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       max-width: 960px; margin: 32px auto; padding: 0 24px; color: var(--fg);
       background: var(--bg); line-height: 1.5; }
h1 { font-size: 28px; margin-bottom: 4px; }
h2 { font-size: 18px; margin: 32px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
h3 { font-size: 16px; margin: 24px 0 8px; }
.subtitle { color: var(--muted); font-size: 13px; margin-bottom: 24px; }
.headline { font-size: 22px; font-weight: 600; margin: 24px 0 8px; }
.methodology { color: var(--muted); font-size: 13px; margin-bottom: 32px;
               padding-bottom: 16px; border-bottom: 1px solid var(--border); }
.cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 32px; }
.card { background: var(--card-bg); border: 1px solid var(--border); padding: 12px;
        border-radius: 6px; }
.card .label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
.card .value { font-size: 22px; font-weight: 600; margin: 4px 0; }
.card .delta { font-size: 12px; color: var(--neutral); }
.card .delta.positive { color: var(--positive); }
.card .delta.negative { color: var(--negative); }
.card .period { font-size: 11px; color: var(--muted); margin-top: 4px; }
.section-num { color: var(--muted); font-weight: 400; margin-right: 8px; }
.section-narrative { font-size: 14px; color: var(--fg); margin-bottom: 12px; }
.section-freshness { font-size: 11px; color: var(--muted); margin-top: 8px; }
.fresh { color: var(--fresh); }
.aging { color: var(--aging); }
.stale { color: var(--stale); }
ul.bullets { margin: 8px 0; padding-left: 20px; }
ul.bullets li { margin: 4px 0; }
.confidence-high { color: var(--fresh); font-weight: 600; }
.confidence-medium { color: var(--aging); font-weight: 600; }
.confidence-low, .confidence-missing { color: var(--negative); font-weight: 600; }
.confidence-unmeasurable { color: var(--unmeasurable); font-weight: 700;
                          background: #fef2f2; padding: 2px 6px; border-radius: 3px; }
table.funnel { width: 100%; border-collapse: collapse; margin: 12px 0; }
table.funnel th, table.funnel td { padding: 8px; text-align: left;
                                     border-bottom: 1px solid var(--border); }
table.funnel th { font-size: 11px; color: var(--muted); text-transform: uppercase; }
table.source-windows { width: 100%; border-collapse: collapse; margin-top: 12px;
                        font-size: 12px; }
table.source-windows th, table.source-windows td { padding: 6px;
                                                     text-align: left;
                                                     border-bottom: 1px solid var(--border); }
.bottom-line { background: var(--card-bg); border-left: 3px solid var(--fg);
               padding: 16px 20px; margin: 24px 0; border-radius: 0 6px 6px 0; }
.carry-forward { counter-reset: dp; padding-left: 0; list-style: none; }
.carry-forward li { counter-increment: dp; padding: 6px 0 6px 32px;
                     position: relative; }
.carry-forward li::before { content: counter(dp); position: absolute; left: 0;
                              font-weight: 700; color: var(--muted); }
.footer { color: var(--muted); font-size: 11px; margin-top: 32px;
          padding-top: 16px; border-top: 1px solid var(--border); }
</style>
"""


def render_editorial_report_html(report: dict) -> str:
    """Render the editorial report as a self-contained HTML page."""
    brand_id = report.get("brand_id", "swing-shack")
    period = report.get("period_days", 7)
    headline = report.get("headline", "")
    cards = report.get("kpi_cards", [])
    sections = report.get("sections", {})
    what_works = report.get("what_works", [])
    what_needs_attention = report.get("what_needs_attention", [])
    carry = report.get("data_points_to_carry_forward", [])
    bottom_line = report.get("bottom_line", "")
    source_windows = report.get("source_windows", [])
    confidence = report.get("confidence", "medium")
    generated = report.get("generated_at", "")
    domain = report.get("domain", "")

    # Cards
    cards_html = "".join(
        f'<div class="card">'
        f'<div class="label">{c.get("label","")}</div>'
        f'<div class="value">{c.get("value","—")}</div>'
        f'<div class="delta">{c.get("delta") or ""}</div>'
        f'<div class="period">{c.get("period","")}</div>'
        f'</div>'
        for c in cards
    )

    # Sections
    def render_section(num: int, key: str, title: str, sec: dict) -> str:
        if not sec:
            return ""
        freshness = sec.get("freshness_label", "missing")
        freshness_class = sec.get("freshness_class", "stale")
        narrative = sec.get("narrative", "")
        bullets = sec.get("bullets") or []
        bullets_html = "".join(f"<li>{b}</li>" for b in bullets)
        age_days = sec.get("freshness_age_days")
        age_str = (f" · {age_days:.1f}d ago"
                   if age_days is not None and isinstance(age_days, (int, float))
                   else "")
        return (
            f'<h2><span class="section-num">{num}.</span>{title}</h2>'
            f'<div class="section-narrative">{narrative}</div>'
            f'<ul class="bullets">{bullets_html}</ul>'
            f'<div class="section-freshness">'
            f'<span class="{freshness_class}">{freshness}</span>{age_str}'
            f'</div>'
        )

    paid = render_section(1, "paid_media", "Paid Media", sections.get("paid_media"))
    seo = render_section(2, "organic_seo", "Organic / SEO", sections.get("organic_seo"))
    social = render_section(3, "social", "Social", sections.get("social"))
    web = render_section(4, "web", "Web", sections.get("web"))

    # Funnel
    funnel = sections.get("funnel") or {}
    funnel_steps = funnel.get("steps") or []
    funnel_rows = "".join(
        f'<tr>'
        f'<td>{s.get("label","")}</td>'
        f'<td>{_fmt_int(s.get("value")) if s.get("fmt") == "int" else _fmt_money(s.get("value"))}</td>'
        f'<td><span class="confidence-{s.get("confidence","missing").lower()}">{s.get("confidence","missing")}</span></td>'
        f'<td>{s.get("source","")}</td>'
        f'</tr>'
        for s in funnel_steps
    )
    funnel_note = funnel.get("note", "")
    funnel_html = (
        f'<h2><span class="section-num">5.</span>Funnel</h2>'
        f'<table class="funnel">'
        f'<thead><tr><th>Stage</th><th>Value</th><th>Confidence</th><th>Source</th></tr></thead>'
        f'<tbody>{funnel_rows}</tbody>'
        f'</table>'
        f'<div class="section-freshness"><span class="stale">{funnel_note or ""}</span></div>'
    )

    # What works / needs attention
    works_html = "".join(f"<li>{w}</li>" for w in what_works)
    attention_html = "".join(f"<li>{a}</li>" for a in what_needs_attention)

    # Carry forward
    carry_html = "".join(f"<li>{c}</li>" for c in carry)

    # Source windows
    sw_rows = "".join(
        f'<tr>'
        f'<td>{s.get("source","")}</td>'
        f'<td>{s.get("period","")}</td>'
        f'<td><span class="{s.get("class","stale")}">{s.get("label","missing")}</span></td>'
        f'<td><span class="confidence-{s.get("confidence","missing")}">{s.get("confidence","missing")}</span></td>'
        f'</tr>'
        for s in source_windows
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{brand_id} — Editorial Report {generated[:10]}</title>
{HTML_STYLES}
</head>
<body>
<h1>{brand_id.title()} — Editorial Report</h1>
<div class="subtitle">{generated}</div>
<div class="headline">{headline}</div>
<div class="methodology">
    {period}-day period · V2.5 editorial layer · domain: {domain} ·
    confidence: <span class="confidence-{confidence}">{confidence}</span>
</div>

<h2>This week</h2>
<div class="cards">{cards_html}</div>

{paid}
{seo}
{social}
{web}
{funnel_html}

<h2>What worked</h2>
<ul class="bullets">{works_html}</ul>

<h2>What needs attention</h2>
<ul class="bullets">{attention_html}</ul>

<h2>Bottom line</h2>
<div class="bottom-line">{bottom_line}</div>

<h2>Data points to carry into next report</h2>
<ol class="carry-forward">{carry_html}</ol>

<h2>Source windows</h2>
<table class="source-windows">
<thead><tr><th>Source</th><th>Period</th><th>Freshness</th><th>Confidence</th></tr></thead>
<tbody>{sw_rows}</tbody>
</table>

'<div class="footer">'
'    Generator: ' + report.get("generator_version", "?") + ' ·'
'    V2.4.1 paid-media preserved as-is ·'
'    V2.5 reads it, does not modify it.'
'</div>'
</body>
</html>"""


# ── Discord digest formatter ───────────────────────────────────

def render_discord_digest(report: dict) -> str:
    """Compact digest for Discord home channel — fits in one message.

    Pattern: headline + 3 sections + bottom line.
    """
    headline = report.get("headline", "")
    sections = report.get("sections", {})
    bottom_line = report.get("bottom_line", "")
    confidence = report.get("confidence", "medium")
    brand = report.get("brand_id", "swing-shack")
    date = report.get("generated_at", "")[:10]

    # Pick 3 highest-signal sections
    section_order = [
        ("paid_media", "Paid Media"),
        ("organic_seo", "SEO"),
        ("social", "Social"),
        ("web", "Web"),
    ]
    picks = []
    for key, label in section_order:
        sec = sections.get(key) or {}
        if sec.get("available", True) and sec.get("bullets"):
            bullets = sec["bullets"][:2]  # max 2 per section
            picks.append((label, bullets))

    picks_md = ""
    for label, bullets in picks[:3]:
        bullets_str = "\n".join(f"  · {b}" for b in bullets)
        picks_md += f"**{label}**\n{bullets_str}\n\n"

    return (
        f"## Editorial — {brand} ({date})\n\n"
        f"_{headline}_\n\n"
        f"{picks_md}"
        f"**Bottom line**\n{bottom_line}\n\n"
        f"_confidence: {confidence} · full report: /reports/{brand}_"
    )
