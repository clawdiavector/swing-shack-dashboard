"""
portfolio.py — Marketing Portfolio Balance Layer.

This is the brain that judges the MIX, not the pieces.

Where audit.py judges each item (keep/update/retire), portfolio.py
judges the collection: are we putting effort in the right places?

It answers six questions:

  1. Where is effort going? (strategic areas + funnel stages)
  2. Where are customers going? (demand-side behaviour)
  3. What are we overdoing? (theme concentration + fatigue)
  4. What are we underdoing? (high-performer themes with little share)
  5. What are we missing? (search, behaviour, platform, CRM, product, geo gaps)
  6. Marketing vs Advertising balance — where do they reinforce each other?

Plus:
  - Strategic coverage per market move (Strong/Moderate/Weak)
  - Priority vs Effort matrix (under-supported / distraction flags)
  - Opportunity cost simulator (what does adding X displace)
  - Monthly strategy meeting (KEEP/KILL/SCALE/FIX/MISSING/BET)
"""

from __future__ import annotations

import json
import os
import datetime
from pathlib import Path
from typing import Any, Optional, List, Dict
from collections import defaultdict

import sys
HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE))

from strategy_store import (
    load_strategy,
    save_strategy,
    upsert_lesson,
    compute_strategy_density,
)

# ─── Strategic area taxonomy ──────────────────────────────────────────
STRATEGIC_AREAS = {
    "brand": ["brand", "identity", "positioning", "awareness", "lifestyle", "values", "voice", "look"],
    "authority": ["authority", "expert", "thought", "education", "knowledge", "insight", "tip", "tutorial", "trackman", "fitting", "data", "numbers", "coach"],
    "acquisition": ["acquisition", "reach", "discover", "new audience", "awareness", "impressions"],
    "conversion": ["conversion", "booking", "cta", "book now", "reserve", "call", "buy", "purchase", "sign-up"],
    "retention": ["retention", "loyalty", "winback", "reactivate", "returning", "member", "vip", "repeat"],
    "seo": ["seo", "search", "keyword", "rank", "google", "organic"],
    "crm": ["crm", "email", "newsletter", "lifecycle", "automation", "broadcast"],
    "community": ["community", "member", "club", "group", "tribe", "social", "ugc", "user-generated"],
    "partnerships": ["partnership", "collab", "joint", "together", "ambassador", "sponsor"],
    "product_education": ["product", "feature", "spec", "demo", "how it works", "use case", "review", "comparison"],
    "promotions": ["promo", "offer", "discount", "sale", "deal", "limited", "save"],
}

FUNNEL_STAGES = ["awareness", "consideration", "intent", "conversion", "retention"]


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


def _today_date() -> datetime.date:
    return datetime.datetime.now(datetime.timezone.utc).date()


# ─── Classification ──────────────────────────────────────────────────

def classify_strategic_areas(text: str) -> List[str]:
    """Given any text (title, theme, content_theme), return which
    strategic areas it most likely serves."""
    text_lower = (text or "").lower()
    if not text_lower:
        return []
    matches = []
    for area, keywords in STRATEGIC_AREAS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            matches.append((area, score))
    matches.sort(key=lambda x: -x[1])
    # Top 2 areas — most specific + secondary
    return [m[0] for m in matches[:2]] or ["brand"]


def classify_funnel_stage(text: str, workhorse: str = "marketing") -> List[str]:
    """Map text/workhorse to funnel stages."""
    text_lower = (text or "").lower()
    stages = []

    intent_keywords = {
        "awareness": ["awareness", "reach", "discover", "first time", "never tried", "introduction", "intro to"],
        "consideration": ["think about", "considering", "comparing", "vs", "alternative", "should I", "research"],
        "intent": ["looking for", "want to", "planning to", "ready to", "interested in booking", "thinking about fitting"],
        "conversion": ["book", "reserve", "buy", "purchase", "cta", "call now", "sign up", "register"],
        "retention": ["again", "come back", "next time", "loyalty", "member", "vip", "returning"],
    }

    for stage, keywords in intent_keywords.items():
        if any(kw in text_lower for kw in keywords):
            stages.append(stage)

    # Workhorse hints
    if workhorse == "advertising" and not stages:
        stages = ["consideration", "intent"]
    elif not stages:
        # Default based on content type hints
        if any(w in text_lower for w in ["tip", "education", "learn", "trackman", "data"]):
            stages = ["consideration"]
        elif any(w in text_lower for w in ["post", "reel", "story"]):
            stages = ["awareness"]
        else:
            stages = ["awareness"]

    return stages[:2]


# ─── Effort allocation ───────────────────────────────────────────────

def compute_effort_allocation(brand_id: str = "swing-shack", period: str = "month") -> Dict[str, Any]:
    """Compute where marketing effort is going this period.
    period: 'month' (current) or 'quarter' (current Q)"""
    s = load_strategy(brand_id)
    cd = _load_campaign_data()
    today = _today_date()
    if period == "month":
        period_start = today.replace(day=1)
        period_end = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
    else:  # quarter
        q = (today.month - 1) // 3
        period_start = datetime.date(today.year, q * 3 + 1, 1)
        period_end_month = q * 3 + 3
        if period_end_month == 12:
            period_end = datetime.date(today.year, 12, 31)
        else:
            period_end = (datetime.date(today.year, period_end_month + 1, 1) - datetime.timedelta(days=1))

    # Collect items active in this period
    items = []
    for b in s.get("bets", []):
        if b.get("status") not in ("in_flight", "planned"):
            continue
        bs = _parse_date(b.get("start_date"))
        be = _parse_date(b.get("target_end_date"))
        if not bs or not be:
            continue
        if be < period_start or bs > period_end:
            continue
        items.append({
            "id": b["id"], "type": "bet", "title": b["title"],
            "workhorse": b.get("workhorse", "marketing"),
            "themes": b.get("content_themes", []),
            "kpi": b.get("primary_kpi", ""),
            "horizon": b.get("horizon", "quarter"),
        })
    for m in s.get("market_moves", []):
        if m.get("status") not in ("active", "planned"):
            continue
        bs = _parse_date(m.get("start_date"))
        be = _parse_date(m.get("target_end_date"))
        if not bs or not be:
            continue
        if be < period_start or bs > period_end:
            continue
        items.append({
            "id": m["id"], "type": "move", "title": m["title"],
            "workhorse": m.get("workhorse", "marketing"),
            "themes": m.get("thesis", "").split() if m.get("thesis") else [],
            "kpi": m.get("what_proves_it", ""),
            "horizon": "year",
        })

    # Add campaigns
    if isinstance(cd, dict):
        for cid, c in cd.get("campaigns", {}).items():
            identity = c.get("identity", {}) or {}
            if identity.get("status") != "active":
                continue
            items.append({
                "id": cid, "type": "campaign", "title": identity.get("name", cid),
                "workhorse": identity.get("workhorse", "marketing"),
                "themes": identity.get("themes", []) or [],
                "kpi": identity.get("primaryGoal", ""),
                "horizon": "quarter",
            })

    # Classify each item
    for item in items:
        text_blob = " ".join([item["title"], " ".join(item.get("themes", [])), item.get("kpi", "")])
        item["strategic_areas"] = classify_strategic_areas(text_blob)
        item["funnel_stages"] = classify_funnel_stage(text_blob, item.get("workhorse", "marketing"))

    # Tally
    area_count = defaultdict(int)
    funnel_count = defaultdict(int)
    for item in items:
        for area in item["strategic_areas"]:
            area_count[area] += 1
        for stage in item["funnel_stages"]:
            funnel_count[stage] += 1

    total = len(items)
    area_pct = {k: round(100 * v / max(total, 1)) for k, v in sorted(area_count.items(), key=lambda x: -x[1])}
    funnel_pct = {k: round(100 * funnel_count.get(k, 0) / max(total, 1)) for k in FUNNEL_STAGES}

    # Theme concentration — count items per theme, not word frequencies
    theme_count = defaultdict(int)
    for item in items:
        # Mark this item as covering each of its themes
        seen_themes = set()
        for theme in item.get("themes", []):
            t = (theme or "").lower().strip()
            if t and t not in seen_themes:
                theme_count[t] += 1
                seen_themes.add(t)
        # If item has no themes, count its title as the theme (deduped)
        if not seen_themes and item.get("title"):
            t = item["title"].lower().strip()
            if t:
                theme_count[t] += 1
    total_items_with_themes = sum(1 for i in items if i.get("themes"))
    # Theme concentration is % of items that touch this theme
    if total_items_with_themes > 0:
        theme_pct = {k: round(100 * v / total_items_with_themes) for k, v in sorted(theme_count.items(), key=lambda x: -x[1])[:10]}
    else:
        theme_pct = {}

    # Marketing vs Advertising split
    mkt_count = sum(1 for i in items if i["workhorse"] != "advertising")
    adv_count = sum(1 for i in items if i["workhorse"] == "advertising")
    mkt_pct = round(100 * mkt_count / max(total, 1))
    adv_pct = round(100 * adv_count / max(total, 1))

    return {
        "period": period,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "total_items": total,
        "by_strategic_area": area_pct,
        "by_funnel_stage": funnel_pct,
        "theme_concentration": theme_pct,
        "marketing_vs_advertising": {"marketing_pct": mkt_pct, "advertising_pct": adv_pct},
        "items_summary": [
            {"id": i["id"], "type": i["type"], "title": i["title"], "workhorse": i["workhorse"],
             "strategic_areas": i["strategic_areas"], "funnel_stages": i["funnel_stages"]}
            for i in items
        ],
    }


def _parse_date(s) -> Optional[datetime.date]:
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _load_campaign_data() -> Optional[dict]:
    for path_str in [
        os.environ.get("DATA_DIR", "") + "/campaign-data.json",
        str(Path(__file__).resolve().parents[2] / "data" / "campaign-data.json"),
    ]:
        if not path_str or path_str == "/campaign-data.json":
            continue
        try:
            with open(path_str) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
    return None


# ─── Demand profile ──────────────────────────────────────────────────

def compute_demand_profile(brand_id: str = "swing-shack") -> Dict[str, Any]:
    """Pull the customer-behaviour signals — what are customers doing?"""
    signals = []

    # GA4 signals
    ga4 = _load_json("ga4-metrics.json")
    if isinstance(ga4, dict):
        pages = ga4.get("pages") or ga4.get("top_pages") or []
        for page in pages[:5]:
            url = page.get("path") or page.get("url") or page.get("page") or ""
            sessions = page.get("sessions") or page.get("pageviews") or 0
            if isinstance(sessions, str):
                try: sessions = int(sessions.replace(",", ""))
                except ValueError: sessions = 0
            signals.append({
                "source": "ga4", "type": "page_traffic",
                "label": url, "value": sessions,
                "intent": "intent" if "book" in url or "fitting" in url else "consideration",
            })
        # Source breakdown
        for source in (ga4.get("sources") or [])[:3]:
            label = source.get("source") or source.get("name") or ""
            sessions = source.get("sessions") or 0
            signals.append({
                "source": "ga4", "type": "traffic_source",
                "label": label, "value": sessions,
                "intent": "acquisition",
            })

    # Instagram analytics signals
    ig = _load_json("ig-analytics.json")
    if isinstance(ig, dict):
        posts = ig.get("posts") or ig.get("data") or []
        # Aggregate by topic_cluster
        cluster_metrics = defaultdict(lambda: {"reach": 0, "engagement": 0, "count": 0})
        for p in posts:
            cluster = (p.get("topic_cluster") or p.get("cluster") or "").lower()
            if not cluster:
                continue
            reach = p.get("reach") or 0
            engagement = p.get("engagement") or p.get("engagementRate") or 0
            if isinstance(engagement, str):
                try: engagement = float(engagement.replace("%", ""))
                except (ValueError, TypeError): engagement = 0
            cluster_metrics[cluster]["reach"] += reach
            cluster_metrics[cluster]["engagement"] += engagement
            cluster_metrics[cluster]["count"] += 1
        for cluster, metrics in sorted(cluster_metrics.items(), key=lambda x: -x[1]["reach"]):
            if not cluster:
                continue
            avg_engagement = metrics["engagement"] / max(metrics["count"], 1)
            signals.append({
                "source": "ig", "type": "topic_cluster",
                "label": cluster,
                "value": metrics["reach"],
                "engagement_rate": round(avg_engagement, 2),
                "intent": "consideration",
                "posts_count": metrics["count"],
            })

    # SEO signals
    seo = _load_json("seo-data.json")
    if isinstance(seo, dict):
        for kw in (seo.get("keywords") or [])[:5]:
            signals.append({
                "source": "seo", "type": "search_keyword",
                "label": kw.get("query") or kw.get("keyword", ""),
                "value": kw.get("impressions") or kw.get("position", 0),
                "intent": "intent",
            })

    return {"signals": signals, "computed_at": _now_iso()}


def _load_json(filename: str) -> Optional[dict]:
    """Try to load a data file from the data dir."""
    for path_str in [
        os.environ.get("DATA_DIR", "") + f"/{filename}",
        str(Path(__file__).resolve().parents[2] / "data" / filename),
    ]:
        if not path_str or path_str == f"/{filename}":
            continue
        try:
            with open(path_str) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
    return None


# ─── Demand / Content mismatch ──────────────────────────────────────

def compute_demand_mismatch(brand_id: str = "swing-shack") -> Dict[str, Any]:
    """Compare where effort goes vs where customers are showing intent."""
    effort = compute_effort_allocation(brand_id, "month")
    demand = compute_demand_profile(brand_id)

    # Build effort-by-area
    effort_by_area = effort["by_strategic_area"]

    # Build demand-by-area (map signals to strategic areas)
    demand_by_area = defaultdict(float)
    for sig in demand["signals"]:
        label = (sig.get("label") or "").lower()
        if not label:
            continue
        areas = classify_strategic_areas(label)
        # Weight by intent value
        weight = float(sig.get("value") or 0)
        if sig.get("source") == "ig" and sig.get("engagement_rate"):
            weight = sig["engagement_rate"] * 100  # normalize for engagement
        for area in areas:
            demand_by_area[area] += weight

    # Normalize demand to percentages
    total_demand = sum(demand_by_area.values())
    if total_demand > 0:
        demand_pct = {k: round(100 * v / total_demand) for k, v in demand_by_area.items()}
    else:
        demand_pct = {}

    # Find mismatches: high demand, low effort
    mismatches = []
    all_areas = set(effort_by_area.keys()) | set(demand_pct.keys())
    for area in all_areas:
        e = effort_by_area.get(area, 0)
        d = demand_pct.get(area, 0)
        gap = d - e
        if abs(gap) >= 10:  # significant mismatch
            mismatches.append({
                "area": area,
                "effort_pct": e,
                "demand_pct": d,
                "gap": gap,
                "direction": "undersupported" if gap > 0 else "over_supported",
                "summary": f"{area}: effort {e}% vs demand {d}% (gap {gap:+}%)",
            })
    mismatches.sort(key=lambda m: -abs(m["gap"]))

    # Demand-side narrative
    narrative = _build_mismatch_narrative(mismatches, effort_by_area)

    return {
        "computed_at": _now_iso(),
        "effort_by_area": effort_by_area,
        "demand_by_area": demand_pct,
        "mismatches": mismatches,
        "narrative": narrative,
    }


def _build_mismatch_narrative(mismatches: List[Dict], effort: Dict) -> str:
    if not mismatches:
        return "Effort and demand are aligned. No major gaps."
    top = mismatches[0]
    if top["direction"] == "undersupported":
        return (
            f"{top['area']} shows strong demand ({top['demand_pct']}%) but only "
            f"{top['effort_pct']}% of marketing effort is dedicated to it. "
            f"Recommendation: increase {top['area']} activity before adding more awareness."
        )
    else:
        return (
            f"{top['area']} receives {top['effort_pct']}% of marketing effort while "
            f"demand is only {top['demand_pct']}%. "
            f"Recommendation: redistribute effort toward higher-demand areas."
        )


# ─── Theme concentration & over/under-support ──────────────────────

def detect_over_support(brand_id: str = "swing-shack") -> List[Dict[str, Any]]:
    """Find themes that are over-represented in the current calendar."""
    effort = compute_effort_allocation(brand_id, "month")
    themes = effort["theme_concentration"]
    over = []
    for theme, pct in themes.items():
        if pct >= 25:
            over.append({
                "theme": theme,
                "calendar_share_pct": pct,
                "verdict": "deliberate_dominance" if pct >= 35 else "approaching_fat",
                "summary": f"{theme} accounts for {pct}% of this month's calendar.",
            })
    return sorted(over, key=lambda x: -x["calendar_share_pct"])


def detect_under_support(brand_id: str = "swing-shack") -> List[Dict[str, Any]]:
    """Find high-performer themes that receive little calendar share.
    Uses IG topic_cluster engagement vs calendar share."""
    demand = compute_demand_profile(brand_id)
    effort = compute_effort_allocation(brand_id, "month")

    # Build IG engagement by cluster
    ig_clusters = {}
    for sig in demand["signals"]:
        if sig.get("source") == "ig" and sig.get("type") == "topic_cluster":
            ig_clusters[sig["label"]] = sig.get("engagement_rate", 0)

    # Build calendar share by theme (rough — match theme names to clusters)
    theme_share = effort["theme_concentration"]

    under = []
    for cluster, engagement in ig_clusters.items():
        if engagement < 2.5:  # below engagement threshold
            continue
        # Find calendar share for this cluster (loose match)
        share = 0
        for theme, pct in theme_share.items():
            if cluster in theme or theme in cluster:
                share = max(share, pct)
        if share < 10:  # less than 10% calendar share
            under.append({
                "theme": cluster,
                "engagement_rate": engagement,
                "calendar_share_pct": share,
                "verdict": "under_supported",
                "summary": f"{cluster} performs at {engagement}% engagement but only {share}% calendar share.",
            })
    return sorted(under, key=lambda x: -x["engagement_rate"])


# ─── Opportunity engine ──────────────────────────────────────────────

def detect_opportunities(brand_id: str = "swing-shack") -> List[Dict[str, Any]]:
    """Find opportunities that don't currently exist in the strategy or calendar."""
    s = load_strategy(brand_id)
    demand = compute_demand_profile(brand_id)
    effort = compute_effort_allocation(brand_id, "month")
    cd = _load_campaign_data()

    opportunities = []
    active_themes = set(effort["theme_concentration"].keys())
    active_areas = set(effort["by_strategic_area"].keys())

    # 1. Search opportunity: keyword with impressions but no content
    for sig in demand["signals"]:
        if sig.get("source") == "seo" and sig.get("type") == "search_keyword":
            keyword = sig["label"].lower()
            if keyword and not any(keyword in t.lower() for t in active_themes):
                opportunities.append({
                    "id": f"opp-search-{keyword}",
                    "type": "search",
                    "signal": f"SEO keyword '{keyword}' has {sig.get('value')} impressions but no content supports it.",
                    "evidence": [f"seo-data.json: {sig.get('value')} impressions for '{keyword}'"],
                    "current_effort": "No active bet covers this keyword.",
                    "strategic_fit": "Could support awareness or authority building.",
                    "hypothesis": f"Publishing content around '{keyword}' would capture intent traffic.",
                    "confidence": "medium" if sig.get("value", 0) > 100 else "low",
                    "actions": ["create_bet", "watch", "ignore"],
                })

    # 2. Behaviour opportunity: high booking traffic but no retargeting
    has_booking_cta_bet = any("cta" in (b.get("title", "") + " ".join(b.get("content_themes", []))).lower() for b in s.get("bets", []))
    booking_signal = next((sig for sig in demand["signals"] if "book" in sig.get("label", "").lower()), None)
    if booking_signal and not has_booking_cta_bet:
        opportunities.append({
            "id": "opp-booking-retarget",
            "type": "behaviour",
            "signal": f"Booking-page traffic is rising ({booking_signal.get('value')} sessions) but no retargeting campaign is active.",
            "evidence": ["ga4-metrics.json: /bookings/ has rising traffic"],
            "current_effort": "Booking-page retargeting bet is in flight, but opportunity could expand.",
            "strategic_fit": "Directly supports market move 'Own the serious golfer who wants measurable improvement'.",
            "hypothesis": "A retargeting campaign targeting visitors of /bookings/ would lift conversion.",
            "confidence": "high",
            "actions": ["create_bet", "watch", "ignore"],
        })

    # 3. Content opportunity: high-performer cluster with little future activity
    high_perf = [sig for sig in demand["signals"] if sig.get("source") == "ig" and sig.get("engagement_rate", 0) >= 3.5]
    for sig in high_perf[:3]:
        cluster = sig["label"]
        # Check if any upcoming bet covers this cluster
        covered = any(cluster in t for t in active_themes)
        if not covered:
            opportunities.append({
                "id": f"opp-cluster-{cluster}",
                "type": "content",
                "signal": f"IG cluster '{cluster}' averages {sig['engagement_rate']}% engagement but no future content planned.",
                "evidence": [f"ig-analytics.json: avg {sig['engagement_rate']}% engagement across {sig.get('posts_count')} posts"],
                "current_effort": "No active bet has this cluster in content_themes.",
                "strategic_fit": "Authority / educational content — directly supports the 'measurable improvement' market move.",
                "hypothesis": f"Scaling {cluster} content from {sig.get('posts_count')} to 12+ posts/quarter would compound engagement.",
                "confidence": "high" if sig["engagement_rate"] >= 4 else "medium",
                "actions": ["create_bet", "watch", "ignore"],
            })

    # 4. Platform opportunity: platform with best downstream but less effort
    platform_signals = defaultdict(lambda: {"sessions": 0, "items": 0})
    for sig in demand["signals"]:
        if sig.get("source") == "ga4" and sig.get("type") == "traffic_source":
            src = sig["label"].lower()
            platform_signals[src]["sessions"] += float(sig.get("value", 0))
    # Items per platform via channel (rough)
    platform_items = defaultdict(int)
    for b in s.get("bets", []):
        for theme in b.get("content_themes", []):
            t = theme.lower()
            if "instagram" in t or "ig" in t or "reel" in t:
                platform_items["instagram"] += 1
            elif "facebook" in t or "fb" in t:
                platform_items["facebook"] += 1
            elif "google" in t or "gbp" in t or "seo" in t:
                platform_items["google"] += 1
    # Find a platform with high sessions but low items
    for src, data in platform_signals.items():
        if data["sessions"] > 100 and platform_items.get(src, 0) < 2:
            opportunities.append({
                "id": f"opp-platform-{src}",
                "type": "platform",
                "signal": f"Platform '{src}' drives {int(data['sessions'])} sessions with only {platform_items.get(src, 0)} active items.",
                "evidence": [f"ga4-metrics.json: {src} = {int(data['sessions'])} sessions"],
                "current_effort": f"Only {platform_items.get(src, 0)} bets reference '{src}' in content_themes.",
                "strategic_fit": "Channel balance — should reflect traffic contribution.",
                "hypothesis": f"Adding 2-3 more {src}-focused bets would capitalise on proven traffic source.",
                "confidence": "medium",
                "actions": ["create_bet", "watch", "ignore"],
            })

    # 5. CRM opportunity: existing customer behaviour with no retention activity
    has_retention_bet = any("retention" in (b.get("title", "") + " ".join(b.get("content_themes", []))).lower() for b in s.get("bets", []))
    if not has_retention_bet:
        # Check if any data suggests repeat customers
        opportunities.append({
            "id": "opp-retention",
            "type": "crm",
            "signal": "No active retention / winback bet — but customers repeat visits to the booking page.",
            "evidence": ["ga4-metrics.json: returning user sessions visible"],
            "current_effort": "0% retention-themed bets in flight.",
            "strategic_fit": "Lifecycle / loyalty workhorses.",
            "hypothesis": "A win-back email sequence or member-only content would lift repeat bookings.",
            "confidence": "medium",
            "actions": ["create_bet", "watch", "ignore"],
        })

    # 6. Product opportunity: page engagement without campaign support
    product_pages = [sig for sig in demand["signals"] if sig.get("source") == "ga4" and "book" not in sig.get("label", "").lower() and sig.get("intent") == "intent"]
    for page in product_pages[:2]:
        url = page["label"].lower()
        if not any(url in t for t in active_themes):
            opportunities.append({
                "id": f"opp-product-{url}",
                "type": "product",
                "signal": f"Page '{url}' shows strong engagement ({page.get('value')} sessions) but no current campaign targets it.",
                "evidence": [f"ga4-metrics.json: {url} = {page.get('value')} sessions"],
                "current_effort": "No active bet or campaign references this URL.",
                "strategic_fit": "Conversion / product education.",
                "hypothesis": f"A dedicated campaign around {url} would convert intent traffic into bookings.",
                "confidence": "medium",
                "actions": ["create_bet", "watch", "ignore"],
            })

    return opportunities


# ─── Strategic coverage ────────────────────────────────────────────────

def compute_strategic_coverage(brand_id: str = "swing-shack") -> Dict[str, Any]:
    """For each active market move, count supporting bets/posts/campaigns this month."""
    s = load_strategy(brand_id)
    today = _today_date()
    month_start = today.replace(day=1)
    month_end = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
    cd = _load_campaign_data()

    coverage = []
    for m in s.get("market_moves", []):
        if m.get("status") not in ("active", "planned"):
            continue
        move_id = m["id"]

        # Count supporting bets
        supporting_bets = [b for b in s.get("bets", [])
                           if b.get("links_to_market_move") == move_id
                           and b.get("status") in ("in_flight", "planned")]
        active_this_month = []
        for b in supporting_bets:
            bs = _parse_date(b.get("start_date"))
            be = _parse_date(b.get("target_end_date"))
            if bs and be and not (be < month_start or bs > month_end):
                active_this_month.append(b)

        # Supporting campaigns
        supporting_campaigns = []
        if isinstance(cd, dict):
            for cid, c in cd.get("campaigns", {}).items():
                if c.get("identity", {}).get("linksToMarketMove") == move_id:
                    supporting_campaigns.append(cid)

        # Heuristic: count posts/themes this month
        posts_this_month = 0
        for b in active_this_month:
            posts_this_month += len(b.get("content_themes", [])) or 2  # assume ~2 posts per theme

        # Coverage rating
        total_support = len(active_this_month) + len(supporting_campaigns) + posts_this_month
        if total_support >= 6:
            rating = "strong"
            comment = "Multiple bets and campaigns supporting this move."
        elif total_support >= 3:
            rating = "moderate"
            comment = "Some bets in flight but room to grow."
        elif total_support >= 1:
            rating = "weak"
            comment = "Only one piece of activity supports this move."
        else:
            rating = "orphan"
            comment = "No active activity supports this move."

        coverage.append({
            "move_id": move_id,
            "title": m["title"],
            "status": m.get("status"),
            "active_bets_count": len(active_this_month),
            "campaigns_count": len(supporting_campaigns),
            "posts_themes_count": posts_this_month,
            "coverage_rating": rating,
            "comment": comment,
            "active_bets": [{"id": b["id"], "title": b["title"]} for b in active_this_month],
        })

    return {
        "month": month_start.isoformat(),
        "coverage": coverage,
    }


# ─── Priority vs Effort matrix ──────────────────────────────────────

def compute_priority_vs_effort(brand_id: str = "swing-shack") -> Dict[str, Any]:
    """For each market move, compute strategic priority (from status/hypothesis
    quality) vs execution effort (count of supporting bets/posts)."""
    coverage = compute_strategic_coverage(brand_id)
    s = load_strategy(brand_id)

    matrix = []
    for c in coverage["coverage"]:
        # Strategic priority heuristic
        m = next((m for m in s.get("market_moves", []) if m["id"] == c["move_id"]), None)
        if not m:
            continue
        # Priority: active + in_flight bets > planned only
        active_bets = [b for b in s.get("bets", []) if b.get("links_to_market_move") == c["move_id"] and b.get("status") == "in_flight"]
        if m.get("status") == "active" and active_bets:
            priority = "high"
        elif m.get("status") == "active":
            priority = "medium"
        else:
            priority = "low"

        # Effort heuristic: count supporting items
        effort_count = c["active_bets_count"] + c["campaigns_count"]
        if effort_count >= 3:
            effort = "high"
        elif effort_count >= 1:
            effort = "medium"
        else:
            effort = "low"

        # Flag mismatches
        flag = None
        if priority == "high" and effort == "low":
            flag = "under_supported_strategy"
        elif priority == "low" and effort == "high":
            flag = "possible_distraction"

        matrix.append({
            "move_id": c["move_id"],
            "title": c["title"],
            "strategic_priority": priority,
            "execution_effort": effort,
            "flag": flag,
            "active_bets": c["active_bets_count"],
            "campaigns": c["campaigns_count"],
        })

    return {"matrix": matrix}


# ─── Marketing vs Advertising balance ──────────────────────────────

def compute_marketing_vs_advertising_balance(brand_id: str = "swing-shack") -> Dict[str, Any]:
    """Show where Marketing and Advertising work together vs where they don't."""
    s = load_strategy(brand_id)
    today = _today_date()

    mkt_bets = [b for b in s.get("bets", []) if b.get("workhorse") != "advertising" and b.get("status") in ("in_flight", "planned")]
    adv_bets = [b for b in s.get("bets", []) if b.get("workhorse") == "advertising" and b.get("status") in ("in_flight", "planned")]

    # For each marketing bet, check if any advertising bet supports its goals
    mismatches = []
    for mb in mkt_bets:
        mb_theme = " ".join(mb.get("content_themes", [])).lower()
        mb_kpi = (mb.get("primary_kpi") or "").lower()
        # Find ad bet that retargets the same audience
        supported = any(
            mb_theme in " ".join(ab.get("content_themes", [])).lower() or
            mb_kpi in (ab.get("primary_kpi") or "").lower()
            for ab in adv_bets
        )
        if not supported and mb.get("horizon") in ("quarter", "month"):
            mismatches.append({
                "marketing_bet": mb["title"],
                "marketing_themes": mb.get("content_themes", []),
                "advertising_support": "none",
                "summary": f"Marketing '{mb['title']}' has no advertising support.",
            })

    return {
        "marketing_count": len(mkt_bets),
        "advertising_count": len(adv_bets),
        "mismatches": mismatches,
    }


# ─── Opportunity cost simulator ────────────────────────────────────

def simulate_opportunity_cost(brand_id: str, proposed: Dict[str, Any]) -> Dict[str, Any]:
    """What would adding a proposed bet do to the portfolio?"""
    effort = compute_effort_allocation(brand_id, "month")
    before_areas = dict(effort["by_strategic_area"])
    before_themes = dict(effort["theme_concentration"])
    total_before = effort["total_items"]

    # Build the proposed item
    proposed_themes = proposed.get("themes", [])
    proposed_areas = classify_strategic_areas(" ".join([proposed.get("title", "")] + proposed_themes))

    # Simulate: add this item, recompute percentages
    # Areas: items can have 1-2 areas each, so total area-slots = sum
    total_area_slots_before = sum(v for v in before_areas.values())
    # Estimate after slots
    total_area_slots_after = total_area_slots_before + len(proposed_areas)
    after_areas = dict(before_areas)
    for area in proposed_areas:
        after_areas[area] = after_areas.get(area, 0) + 1
    if total_area_slots_after > 0:
        after_areas = {k: round(100 * v / total_area_slots_after) for k, v in after_areas.items()}
    else:
        after_areas = {}

    after_themes = dict(before_themes)
    for t in proposed_themes:
        t_low = (t or "").lower().strip()
        if t_low:
            after_themes[t_low] = after_themes.get(t_low, 0) + 1
    total_themes_after = sum(after_themes.values()) or 1
    after_themes = {k: round(100 * v / total_themes_after) for k, v in after_themes.items()}

    # Find likely displaced areas (the smallest areas that don't include the proposed)
    displaced = []
    for area, pct in sorted(before_areas.items(), key=lambda x: x[1])[:3]:
        if area not in proposed_areas:
            displaced.append({
                "area": area,
                "before_pct": pct,
                "after_pct": after_areas.get(area, 0),
                "displaced_pct": pct - after_areas.get(area, 0),
            })

    # Concentration check
    concentration_warning = None
    for theme, new_pct in sorted(after_themes.items(), key=lambda x: -x[1])[:3]:
        if new_pct >= 40:
            concentration_warning = (
                f"Adding this bet would push '{theme}' to {new_pct}% of calendar share "
                f"— strategic dominance or fatigue risk?"
            )
            break

    return {
        "proposed": proposed,
        "before": {"areas": before_areas, "themes": before_themes, "total_items": total_before},
        "after": {"areas": after_areas, "themes": after_themes, "total_items": total_after},
        "displaced": displaced,
        "concentration_warning": concentration_warning,
        "recommendation": (
            "Acceptable — fits current mix."
            if not concentration_warning and not any(d["displaced_pct"] >= 5 for d in displaced)
            else "Review trade-offs before adding."
        ),
    }


# ─── Monthly strategy meeting generator ────────────────────────────

def generate_monthly_meeting(brand_id: str = "swing-shack") -> Dict[str, Any]:
    """The meeting Christelle wants the OS to prepare: KEEP / KILL / SCALE / FIX / MISSING / BET."""
    s = load_strategy(brand_id)

    # KEEP: high audit score, in_flight bets with strong evidence
    keep = []
    for b in s.get("bets", []):
        if b.get("status") == "in_flight":
            ev_count = len(b.get("evidence", []))
            if ev_count >= 1:
                keep.append({"bet": b["title"], "reason": f"{ev_count} pieces of evidence, in flight."})

    # KILL: bets past decision_date with disproved status
    kill = []
    for b in s.get("bets", []):
        if b.get("decision", {}).get("outcome") == "kill":
            kill.append({"bet": b["title"], "reason": b["decision"].get("note", "")})
        elif b.get("status") in ("lost", "killed"):
            kill.append({"bet": b["title"], "reason": "Status set to lost/killed."})

    # SCALE: bets with strengthening trend
    from strategy_store import compute_trend_signal
    scale = []
    for b in s.get("bets", []):
        if b.get("status") not in ("in_flight", "planned"):
            continue
        trend = compute_trend_signal(brand_id, b["id"], "bet")
        if trend.get("signal") == "strengthening":
            scale.append({"bet": b["title"], "reason": trend.get("reason", "")})

    # FIX: bets with weakening trend (not yet disproved)
    fix = []
    for b in s.get("bets", []):
        if b.get("status") not in ("in_flight", "planned"):
            continue
        trend = compute_trend_signal(brand_id, b["id"], "bet")
        if trend.get("signal") == "weakening":
            fix.append({"bet": b["title"], "reason": trend.get("reason", "")})

    # MISSING: opportunities from the opportunity engine
    missing = detect_opportunities(brand_id)

    # BET: under-supported themes that warrant a new bet
    under = detect_under_support(brand_id)
    bet_proposals = []
    for u in under[:3]:
        bet_proposals.append({
            "theme": u["theme"],
            "hypothesis": f"Increase {u['theme']} content from current share to 3 pieces/month.",
            "evidence": f"{u['engagement_rate']}% engagement vs {u['calendar_share_pct']}% calendar share.",
        })

    return {
        "month": _today_date().strftime("%B %Y"),
        "keep": keep,
        "kill": kill,
        "scale": scale,
        "fix": fix,
        "missing": missing,
        "bet": bet_proposals,
    }


# ─── Opportunity decisions (Ignore → memory) ───────────────────────

def record_opportunity_decision(brand_id: str, opportunity_id: str, decision: str, note: str = "") -> Dict[str, Any]:
    """Record a Create bet / Watch / Ignore decision for an opportunity.
    'Ignore' writes to strategic memory so the OS doesn't nag weekly."""
    s = load_strategy(brand_id)
    opp_decisions = s.setdefault("opportunity_decisions", [])
    opp_decisions.append({
        "opportunity_id": opportunity_id,
        "decision": decision,
        "note": note,
        "decided_at": _today(),
    })
    save_strategy(s, brand_id)
    if decision == "ignore":
        upsert_lesson(brand_id, {
            "category": "data_suggests_test_next",
            "claim": f"Opportunity {opportunity_id} explicitly ignored. {note}".strip(),
            "evidence": [{"source": "opportunity_decision", "value": f"ignored: {note[:120]}", "as_of": _today()}],
            "from_opportunity": opportunity_id,
        })
    return {"ok": True, "strategy": s}


# ─── Markdown render ────────────────────────────────────────────────

def render_portfolio_markdown(data: Dict[str, Any], section: str = "summary") -> str:
    md = []
    if section in ("summary", "all"):
        md.append("## Marketing portfolio")
        md.append("")
        if data.get("effort_by_area"):
            md.append("**Effort by strategic area (this month):**")
            for area, pct in sorted(data["effort_by_area"].items(), key=lambda x: -x[1]):
                md.append(f"- {area}: {pct}%")
            md.append("")
        if data.get("theme_concentration"):
            top_theme = max(data["theme_concentration"].items(), key=lambda x: x[1])
            if top_theme[1] >= 25:
                md.append(f"**Theme concentration:** '{top_theme[0]}' = {top_theme[1]}% — deliberate or fatigue?")
                md.append("")
    return "\n".join(md)


def render_meeting_markdown(meeting: Dict[str, Any]) -> str:
    md = []
    md.append(f"## Monthly strategy meeting · {meeting['month']}")
    md.append("")

    md.append("### KEEP")
    if meeting["keep"]:
        for k in meeting["keep"][:5]:
            md.append(f"- **{k['bet']}** — {k['reason']}")
    else:
        md.append("_No clear keepers._")
    md.append("")

    md.append("### KILL")
    if meeting["kill"]:
        for k in meeting["kill"][:5]:
            md.append(f"- **{k['bet']}** — {k['reason'][:100]}")
    else:
        md.append("_Nothing on the kill list._")
    md.append("")

    md.append("### SCALE")
    if meeting["scale"]:
        for k in meeting["scale"][:5]:
            md.append(f"- **{k['bet']}** — {k['reason'][:120]}")
    else:
        md.append("_No clear scale candidates._")
    md.append("")

    md.append("### FIX")
    if meeting["fix"]:
        for k in meeting["fix"][:5]:
            md.append(f"- **{k['bet']}** — {k['reason'][:120]}")
    else:
        md.append("_Nothing to fix._")
    md.append("")

    md.append("### MISSING")
    if meeting["missing"]:
        for m in meeting["missing"][:5]:
            md.append(f"- **[{m['type']}]** {m['signal'][:120]}")
            md.append(f"  Hypothesis: {m['hypothesis'][:120]}")
            md.append(f"  Confidence: {m['confidence']}")
    else:
        md.append("_No clear opportunities._")
    md.append("")

    md.append("### BET")
    if meeting["bet"]:
        for b in meeting["bet"][:3]:
            md.append(f"- **{b['theme']}** — {b['hypothesis'][:100]}")
            md.append(f"  _Evidence:_ {b['evidence'][:100]}")
    else:
        md.append("_No new bet proposals._")

    return "\n".join(md)


# ─── CLI ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    brand = sys.argv[1] if len(sys.argv) > 1 else "swing-shack"
    effort = compute_effort_allocation(brand)
    print(render_portfolio_markdown(effort, "all"))
    print()
    mismatch = compute_demand_mismatch(brand)
    print(f"Mismatch narrative: {mismatch['narrative']}")
    print()
    meeting = generate_monthly_meeting(brand)
    print(render_meeting_markdown(meeting))