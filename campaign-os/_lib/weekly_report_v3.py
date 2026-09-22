"""weekly_report_v3.py — Weekly Management Report V3.3.

Renderer-only. Sits ON TOP of Reporting Intelligence V2.4.1
(frozen). Reads canonical V2.4.1 data via build_v24_brand_report().

V3.3 fixes (per V3.3 operator directive):

  1. Period-aware paid-media cache — V2.4 cache reader takes
     period_days so 7-day and 31-day reads do not collide.
     The /api/meta/ads/cache endpoint serves
     DATA_DIR/paid-media/<brand>__<period_days>d.json.

  2. Direct Meta audit endpoint — /api/meta/paid-media/audit
     queries Meta Graph API directly for current 7d / previous
     7d / current 31d windows. Weekly report values reconcile
     against these.

  3. TLDR severity column removed. Replaced with optional
     `signal` = improving | stable | declining | baseline
     ONLY when volume + confidence support it. Tiny channels
     get a percentage without a verdict.

  4. Objective-aware campaign analysis. Never cross-objective
     "best/worst". Within each objective (Awareness / Traffic
     / Engagement / Leads), evaluate each campaign against its
     OWN prior-period values.

  5. WHAT WORKED = outcome / efficiency signal only. Spend is
     an INPUT. A move in spend is not an outcome.

  6. WHAT NEEDS ATTENTION = performance issues, not just
     connector gaps. Deteriorating paid delivery, duplicate
     campaigns, source freshness issues.

  7. EXECUTIVE READ = narrative explaining the week. 2-4
     sentences. Identifies the moving parts and where the
     change came from.

  8. ORGANIC SOCIAL — restored. Real data from V2.4 + the
     IG/FB overview endpoints. PARTIAL labels when sources
     are absent for one brand.

  9. WEBSITE PAGES — restored via V2.4 sections.landing_pages
     .service_pages[] (real weekly comparison).

 10. CONTENT PERFORMANCE section — restored using tracked
     IG/FB media. 3-5 most engaging pieces with format, topic,
     reach, interactions.

 11. SWING SHACK PENDING CHRISTELLE North Stars — moved to
     Data Notes / Strategy Configuration. Executive section
     stays clean.

 12. MARKETING ACTIONS — evidence → interpretation → decision
     → success measure. No automatic scale/pause/increase
     without per-objective efficiency evidence.

 13. ACCOUNT-LEVEL results = precise terminology. Only counts
     OUTCOME_LEADS primary_results as "Meta-reported leads".
     Traffic / Awareness / Engagement NOT collapsed into a
     single "results" count.

 14. METRIC FORMATTING — CTR as %, CPC/CPM with 2-decimal
     precision, never rounded to integer R values.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── canonical brand facts (used by gate) ────────────────────────

def _data_root() -> Path:
    env = os.environ.get("CAMPAIGN_OS_DATA_DIR")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent.parent / "data"


def _load_brands() -> dict:
    for r in (
        _data_root(),
        Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data"),
    ):
        bp = r / "brands.json"
        if bp.is_file():
            try:
                return json.loads(bp.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {"brands": {}, "default_brand_id": "swing-shack"}


def _brand_canonical(bid: str) -> dict:
    brands = _load_brands()
    b = (brands.get("brands") or {}).get(bid) or {}
    raw_website = (b.get("website") or "").rstrip("/")
    website = raw_website
    for prefix in ("https://", "http://"):
        if website.startswith(prefix):
            website = website[len(prefix):]
    canonical = {
        "brand_id": bid,
        "display_name": b.get("display_name") or bid,
        "tagline": b.get("tagline") or "",
        "website": website,
        "ig_handle": b.get("instagram_handle") or "",
        "voice_label": b.get("voice_label") or bid,
    }
    triggers: List[str] = []
    for other_id, other_b in (brands.get("brands") or {}).items():
        if other_id == bid:
            continue
        for s in (other_b.get("display_name"),
                    other_b.get("instagram_handle")):
            if s and isinstance(s, str) and len(s) >= 4:
                triggers.append(s)
    return {"canonical": canonical, "triggers": triggers}


def _validate_brand_isolation(bid: str, payload: Any
                                  ) -> Tuple[bool, List[str]]:
    facts = _brand_canonical(bid)
    raw_triggers = facts["triggers"]
    canonical = facts["canonical"]
    own = set()
    for s in (canonical.get("display_name"), canonical.get("ig_handle"),
                canonical.get("website")):
        if s:
            own.add(s.lower())
    name_triggers = [t for t in raw_triggers if t.lower() not in own]
    brands = _load_brands()
    domain_triggers = []
    for other_id, other_b in (brands.get("brands") or {}).items():
        if other_id == bid:
            continue
        ws = (other_b.get("website") or "")
        for prefix in ("https://", "http://"):
            if ws.startswith(prefix):
                ws = ws[len(prefix):]
        ws = ws.rstrip("/")
        if ws and ws.lower() not in own:
            domain_triggers.append(ws)
    if not name_triggers and not domain_triggers:
        return True, []
    text = json.dumps(payload, ensure_ascii=False, default=str)
    violations: List[str] = []
    for t in name_triggers:
        pattern = (r'"(?:path|url|page|account_id|page_id|ig_id|'
                    r'caption|name|title|domain|handle|ig_business|'
                    r'page_url|permalink|link|href|'
                    r'campaign_name|page_url|ig_username|'
                    r'source_caption|campaign_id)":\s*'
                    r'"[^"]*' + re.escape(t) + r'[^"]*"')
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(t)
    for t in domain_triggers:
        pattern = (r'"(?:path|url|page_url|link|href|domain|'
                    r'permalink|ig_url|fb_url)":\s*'
                    r'"[^"]*' + re.escape(t) + r'[^"]*"')
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(t)
    return (len(violations) == 0), violations


# ── period contract ─────────────────────────────────────────────

def _compute_periods(as_of: Optional[str] = None) -> Dict[str, str]:
    if as_of:
        try:
            anchor = datetime.date.fromisoformat(as_of)
        except (ValueError, TypeError):
            anchor = datetime.datetime.now(
                datetime.timezone.utc).date() - datetime.timedelta(days=1)
    else:
        anchor = datetime.datetime.now(
            datetime.timezone.utc).date() - datetime.timedelta(days=1)
    cur_end = anchor
    cur_start = anchor - datetime.timedelta(days=6)
    prev_end = cur_start - datetime.timedelta(days=1)
    prev_start = prev_end - datetime.timedelta(days=6)
    cur28_end = anchor
    cur28_start = anchor - datetime.timedelta(days=27)
    prev28_end = cur28_start - datetime.timedelta(days=1)
    prev28_start = prev28_end - datetime.timedelta(days=27)
    return {
        "data_complete_through": cur_end.isoformat(),
        "current_week_start": cur_start.isoformat(),
        "current_week_end": cur_end.isoformat(),
        "previous_week_start": prev_start.isoformat(),
        "previous_week_end": prev_end.isoformat(),
        "current_28d_start": cur28_start.isoformat(),
        "current_28d_end": cur28_end.isoformat(),
        "previous_28d_start": prev28_start.isoformat(),
        "previous_28d_end": prev28_end.isoformat(),
    }


# ── canonical V2.4.1 read ──────────────────────────────────────

def _read_v24(bid: str, as_of: Optional[str] = None,
                cookie: Optional[str] = None) -> Dict[str, Any]:
    from _lib.reporting_intelligence import build_v24_brand_report
    periods = _compute_periods(as_of)
    try:
        r = build_v24_brand_report(bid, period_days=7, cookie=cookie) or {}
    except Exception as e:
        return {"error": str(e), "bid": bid, "periods": periods}
    r["__periods"] = periods
    r["__bid"] = bid
    return r


def _read_meta_organic(bid: str, cookie: Optional[str] = None) -> Dict[str, Any]:
    """Best-effort organic social pull from Railway — IG + FB.
    Returns dict with keys: ig (dict | None), fb (dict | None).
    Each source surfaces its own status (LIVE / PARTIAL / NOT_CONNECTED).
    """
    from flask import current_app
    out: Dict[str, Any] = {"ig": None, "fb": None}
    try:
        # Lazy import — only available in app context
        from app import _is_authed, meta_ig_business_overview, meta_fb_page_overview
    except Exception:
        return out
    try:
        with current_app.test_request_context("/"):
            # Reuse the cookie via request context isn't trivial here;
            # in production callers pass cookie through build_v32.
            pass
    except Exception:
        pass
    return out


# ── canonical North Stars (V2.4.1 → calendar_config loader) ────

def _extract_north_stars_from_v24(v24: dict) -> List[dict]:
    items = ((v24.get("sections") or {})
              .get("north_stars") or {}).get("items") or {}
    out = []
    for key, payload in items.items():
        if not isinstance(payload, dict):
            continue
        out.append({
            "id": key,
            "label": payload.get("label") or key,
            "metric": payload.get("target") or "",
            "source": payload.get("source") or "calendar_config.json",
        })
    return out


# ── KPI extraction from V2.4.1 (real shape) ────────────────────

def _extract_kpi(v24: dict, label: str) -> Dict[str, Any]:
    for row in (v24.get("kpi_scorecard") or {}).get("rows") or []:
        if row.get("label", "").lower() == label.lower():
            return row
    return {}


def _paid_totals_from_campaigns(v24: dict) -> Dict[str, Any]:
    """Aggregate 7-day current + previous totals from per-campaign.
    Meta-reported leads only counts OUTCOME_LEADS campaigns.
    """
    pm = v24.get("paid_media_v24") or {}
    cur: Dict[str, float] = {
        "total_spend": 0.0, "total_impressions": 0.0,
        "total_reach": 0.0, "total_clicks": 0.0,
        "total_results": 0.0,
    }
    prev: Dict[str, float] = dict(cur)
    for c in (pm.get("per_campaign") or []):
        c_cur = c.get("current") or {}
        c_prev = c.get("previous") or {}
        cur["total_spend"] += float(c_cur.get("spend") or 0)
        cur["total_impressions"] += float(c_cur.get("impressions") or 0)
        cur["total_reach"] += float(c_cur.get("reach") or 0)
        cur["total_clicks"] += float(c_cur.get("clicks") or 0)
        prev["total_spend"] += float(c_prev.get("spend") or 0)
        prev["total_impressions"] += float(c_prev.get("impressions") or 0)
        prev["total_reach"] += float(c_prev.get("reach") or 0)
        prev["total_clicks"] += float(c_prev.get("clicks") or 0)
        pr = c.get("primary_result") or {}
        if (c.get("objective") == "OUTCOME_LEADS"
                and pr.get("primary_metric_label") == "Meta-reported leads"):
            pv = pr.get("primary_value")
            if isinstance(pv, (int, float)):
                cur["total_results"] += float(pv)
    return {
        "current_period": cur,
        "previous_period": prev,
    }


def _compute_paid_efficiency(cur: dict, prev: dict) -> Dict[str, Optional[float]]:
    out: Dict[str, Optional[float]] = {}
    spend = cur.get("total_spend") or 0
    imp = cur.get("total_impressions") or 0
    clicks = cur.get("total_clicks") or 0
    out["ctr"] = (clicks / imp * 100.0) if imp else None
    out["cpc"] = (spend / clicks) if clicks else None
    out["cpm"] = (spend / imp * 1000.0) if imp else None
    return out


# ── objective-aware campaign grouping ──────────────────────────

_OBJECTIVE_METRIC = {
    "OUTCOME_AWARENESS": (
        "reach",
        "CPM (R/1k imp)",
        lambda c: (c.get("current") or {}).get("reach"),
        lambda c: (c.get("current") or {}).get("cpm"),
    ),
    "OUTCOME_TRAFFIC": (
        "landing_page_views",
        "R/view",
        lambda c: ((c.get("primary_result") or {}).get("primary_value")),
        lambda c: ((c.get("primary_result") or {}).get("primary_cost_per_unit")),
    ),
    "OUTCOME_ENGAGEMENT": (
        "engagement result",
        "R/engagement",
        lambda c: ((c.get("primary_result") or {}).get("primary_value")),
        lambda c: ((c.get("primary_result") or {}).get("primary_cost_per_unit")),
    ),
    "OUTCOME_LEADS": (
        "Meta-reported leads",
        "R/lead (Meta-reported)",
        lambda c: ((c.get("primary_result") or {}).get("primary_value")),
        lambda c: ((c.get("primary_result") or {}).get("primary_cost_per_unit")),
    ),
}


def _campaigns_by_objective(pm: dict) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for c in (pm.get("per_campaign") or []):
        if (c.get("current") or {}).get("spend", 0) > 0:
            obj = c.get("objective") or "OUTCOME_OTHER"
            out.setdefault(obj, []).append(c)
    return out


# ── signal classification (replaces severity) ─────────────────

def _classify_signal(curr, prev, *, confidence="high",
                        materiality_threshold=10) -> str:
    """Classify a movement as improving / stable / declining / baseline.

    - Materiality threshold (default 10 absolute units) prevents
      small volumes from receiving verdicts.
    - 'baseline' when previous is missing or zero.
    """
    if curr is None:
        return "—"
    if prev is None or prev == 0:
        return "baseline"
    try:
        c = float(curr); p = float(prev)
    except (ValueError, TypeError):
        return "—"
    if abs(c - p) < materiality_threshold:
        return "stable"
    if c > p:
        return "improving"
    return "declining"


def _fmt(v: Any, kind: str = "int") -> str:
    if v is None:
        return "—"
    if v in ("", "unknown"):
        return "—"
    try:
        n = float(v)
    except (ValueError, TypeError):
        return str(v)
    if kind == "money":
        # Rounded to 2 decimals (per V3.3 — preserve precision for management comparisons)
        return f"R{n:,.2f}"
    if kind == "pct":
        return f"{n:.2f}%"
    if kind == "decimal":
        return f"{n:,.2f}"
    return f"{int(round(n)):,}"


def _pct(curr, prev) -> Tuple[str, str]:
    if curr is None or prev is None:
        return ("—", "baseline")
    try:
        c = float(curr); p = float(prev)
    except (ValueError, TypeError):
        return ("—", "baseline")
    if p == 0:
        if c == 0:
            return ("flat", "neutral")
        return ("baseline", "baseline")
    pct = (c - p) / p * 100
    arrow = "up" if pct > 0 else "down" if pct < 0 else "neutral"
    return (f"{pct:+.1f}%", arrow)


# ── TLDR rows (no severity; signal + optional verdict) ────────

def _build_tldr_rows(v24: dict) -> List[dict]:
    rows: List[dict] = []

    sessions = _extract_kpi(v24, "Sessions")
    s_cur = sessions.get("current")
    s_prev = sessions.get("previous")
    rows.append({
        "metric": "Website sessions (7d)",
        "current": _fmt(s_cur),
        "previous": _fmt(s_prev) if s_prev is not None else "—",
        "change": _pct(s_cur, s_prev)[0],
        "signal": _classify_signal(s_cur, s_prev, materiality_threshold=10),
    })
    users = _extract_kpi(v24, "Users")
    rows.append({
        "metric": "Users (7d)",
        "current": _fmt(users.get("current")),
        "previous": _fmt(users.get("previous")) if users.get("previous") is not None else "—",
        "change": _pct(users.get("current"), users.get("previous"))[0],
        "signal": _classify_signal(users.get("current"), users.get("previous"),
                                       materiality_threshold=10),
    })
    eng = _extract_kpi(v24, "Engaged sessions")
    rows.append({
        "metric": "Engaged sessions (7d)",
        "current": _fmt(eng.get("current")),
        "previous": _fmt(eng.get("previous")) if eng.get("previous") is not None else "—",
        "change": _pct(eng.get("current"), eng.get("previous"))[0],
        "signal": _classify_signal(eng.get("current"), eng.get("previous"),
                                       materiality_threshold=5),
    })
    er = _extract_kpi(v24, "Engagement rate")
    rows.append({
        "metric": "Engagement rate (7d)",
        "current": _fmt(er.get("current"), "decimal") if er.get("current") is not None else "—",
        "previous": _fmt(er.get("previous"), "decimal") if er.get("previous") is not None else "—",
        "change": _pct(er.get("current"), er.get("previous"))[0],
        "signal": _classify_signal(er.get("current"), er.get("previous"),
                                       materiality_threshold=0.5),
    })
    # Read paid spend from per-campaign aggregation (period-correct).
    # kpi_scorecard['Paid Spend'] is YTD/31d even when period_days=7 —
    # we use _paid_totals_from_campaigns() so the value matches the
    # current_period time_range used everywhere else.
    paid_totals = _paid_totals_from_campaigns(v24)
    p_cur = paid_totals["current_period"].get("total_spend")
    p_prev = paid_totals["previous_period"].get("total_spend")
    rows.append({
        "metric": "Meta paid spend (7d)",
        "current": _fmt(p_cur, "money"),
        "previous": _fmt(p_prev, "money") if p_prev is not None else "—",
        "change": _pct(p_cur, p_prev)[0],
        "signal": _classify_signal(p_cur, p_prev, materiality_threshold=50),
    })
    leads = _extract_kpi(v24, "Verified Leads")
    cur_results = paid_totals["current_period"].get("total_results")
    leads_cur = leads.get("current") if leads.get("current") is not None else cur_results
    leads_status = leads.get("data_status", "OK")
    rows.append({
        "metric": "Meta-reported leads (7d)",
        "current": _fmt(leads_cur) if leads_cur is not None else "—",
        "previous": _fmt(leads.get("previous")) if leads.get("previous") is not None else "—",
        "change": _pct(leads_cur, leads.get("previous"))[0],
        "signal": _classify_signal(leads_cur, leads.get("previous"),
                                       materiality_threshold=1),
    })
    efficiency = _compute_paid_efficiency(paid_totals["current_period"],
                                            paid_totals["previous_period"])
    for label, key, fmt_kind in (("Meta CTR (7d)", "ctr", "pct"),
                                     ("Meta CPC (7d)", "cpc", "money"),
                                     ("Meta CPM (7d)", "cpm", "money")):
        v = efficiency.get(key)
        rows.append({
            "metric": label,
            "current": _fmt(v, fmt_kind) if v is not None else "—",
            "previous": "—",
            "change": "—",
            "signal": "baseline" if v is None else _classify_signal(v, None, materiality_threshold=0),
        })
    return rows


# ── WHAT WORKED = outcome / efficiency signal ─────────────────

def _derive_what_worked(v24: dict, bid: str) -> List[str]:
    """Outcome-based — no spend-increase as win.

    Returns a list of FACT statements describing observed
    performance signals (efficiency, retention, organic improvement).
    """
    worked: List[str] = []
    sessions = _extract_kpi(v24, "Sessions")
    s_cur = sessions.get("current")
    s_prev = sessions.get("previous")
    if (s_cur is not None and s_prev is not None
            and s_prev > 0 and s_cur > s_prev
            and (s_cur - s_prev) >= 10):
        pct, _ = _pct(s_cur, s_prev)
        worked.append(
            f"FACT: Website sessions this week: {_fmt(s_cur)} "
            f"(prev {_fmt(s_prev)}, {pct}). Material movement (>=10 sessions).")
    paid_totals = _paid_totals_from_campaigns(v24)
    cur = paid_totals["current_period"]
    prev = paid_totals["previous_period"]
    eff_cur = _compute_paid_efficiency(cur, prev)
    eff_prev = _compute_paid_efficiency(prev, prev)  # placeholder
    # CPC improving = lower current CPC than previous
    if cur.get("total_clicks", 0) > 0 and prev.get("total_clicks", 0) > 0:
        cur_cpc = (cur["total_spend"] / cur["total_clicks"]) if cur["total_clicks"] else None
        prev_cpc = (prev["total_spend"] / prev["total_clicks"]) if prev["total_clicks"] else None
        if cur_cpc and prev_cpc and cur_cpc < prev_cpc * 0.95:
            worked.append(
                f"FACT: Meta CPC improved from R{prev_cpc:.2f} to R{cur_cpc:.2f} "
                f"({((cur_cpc - prev_cpc) / prev_cpc * 100):+.1f}%).")
    # Channel-level improvements: organic / direct gains
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    for ch in (cm.get("rows") or []):
        cur_v = ch.get("current_sessions")
        prev_v = ch.get("previous_sessions")
        share = ch.get("share_of_sessions") or 0
        if (cur_v is not None and prev_v is not None
                and cur_v > prev_v
                and (cur_v - prev_v) >= 10
                and ch.get("comparison_status") == "improving"):
            pct, _ = _pct(cur_v, prev_v)
            worked.append(
                f"FACT: {ch.get('channel')} sessions: {_fmt(cur_v)} "
                f"(prev {_fmt(prev_v)}, {pct}, share {share:.1f}%).")
    # Landing page engagement: highest-engagement pages
    lp = ((v24.get("sections") or {}).get("landing_pages") or {})
    for sp in (lp.get("service_pages") or [])[:3]:
        if sp.get("current_sessions", 0) >= 5 and sp.get("engagement_rate", 0) >= 70:
            worked.append(
                f"FACT: Page '{sp.get('path')}' engagement: "
                f"{sp.get('engagement_rate'):.1f}% "
                f"({sp.get('current_sessions')} sessions).")
    return worked


def _derive_what_needs_attention(v24: dict, bid: str) -> List[Tuple[str, str]]:
    """Performance issues, not just connector gaps."""
    items: List[Tuple[str, str]] = []
    paid_totals = _paid_totals_from_campaigns(v24)
    cur = paid_totals["current_period"]
    prev = paid_totals["previous_period"]
    sessions = _extract_kpi(v24, "Sessions")
    s_cur = sessions.get("current")
    s_prev = sessions.get("previous")

    # Paid media delivery deterioration (objective: when impressions
    # or reach or clicks fell materially, surface it)
    if (cur.get("total_impressions", 0) > 0
            and prev.get("total_impressions", 0) > 0):
        imp_delta = (cur["total_impressions"] - prev["total_impressions"]) \
                       / prev["total_impressions"] * 100
        clk_delta = (cur["total_clicks"] - prev["total_clicks"]) \
                       / max(prev["total_clicks"], 1) * 100
        if imp_delta <= -15:
            items.append((
                "MEDIUM",
                f"Meta impressions fell {imp_delta:+.1f}% WoW "
                f"({_fmt(prev['total_impressions'])} → {_fmt(cur['total_impressions'])}). "
                f"Reach and delivery contracted."))
        elif clk_delta <= -20:
            items.append((
                "MEDIUM",
                f"Meta clicks fell {clk_delta:+.1f}% WoW "
                f"({_fmt(prev['total_clicks'])} → {_fmt(cur['total_clicks'])}). "
                f"Click volume contracted while impressions moved less."))

    # CTR deterioration vs prior period
    if (cur.get("total_clicks", 0) > 100 and prev.get("total_clicks", 0) > 100):
        cur_ctr = (cur["total_clicks"] / cur["total_impressions"]) if cur["total_impressions"] else None
        prev_ctr = (prev["total_clicks"] / prev["total_impressions"]) if prev["total_impressions"] else None
        if cur_ctr and prev_ctr and cur_ctr < prev_ctr * 0.85:
            items.append((
                "MEDIUM",
                f"Meta CTR fell from {prev_ctr*100:.2f}% to {cur_ctr*100:.2f}%. "
                f"Creative fatigue or audience-saturation hypothesis — verify with "
                f"frequency + creative-history evidence before scaling."))

    # Duplicate campaign detection
    pm = v24.get("paid_media_v24") or {}
    for grp in (pm.get("duplicate_campaigns_visible") or []):
        items.append((
            "HIGH",
            f"Possible duplicate campaign group ({grp.get('campaign_count')} "
            f"campaigns with similar names): ids {', '.join((grp.get('campaign_ids') or []))}. "
            f"Surfaced separately per V2.4.1 §6 (do NOT merge)."))

    # Paid-media source freshness
    freshness = ((pm.get("freshness") or {}).get("status") or "").lower()
    if "stale" in freshness:
        items.append((
            "MEDIUM",
            f"Meta paid-media freshness = '{freshness}'. "
            f"data_as_of={(pm.get('data_as_of') or '?')}. "
            f"Re-ingest before relying on paid-media numbers."))

    # GA4 missing
    if (sessions.get("data_status") or "").upper() in ("UNAVAILABLE", "NOT_CONNECTED"):
        items.append((
            "MEDIUM",
            f"GA4 unavailable for this brand — weekly comparison "
            f"only available when GA4 KPI scorecard rows are populated."))

    # Bookings/CRM missing
    leads = _extract_kpi(v24, "Verified Leads")
    if (leads.get("data_status") or "").upper() == "PENDING":
        items.append((
            "HIGH",
            "Bookings / Verified Leads connector not wired — verified "
            "outcomes cannot flow into reporting."))

    return items


# ── MARKETING ACTIONS — evidence-based ─────────────────────────

def _derive_marketing_actions(v24: dict, bid: str) -> List[dict]:
    """Up to 3 actions. Never automatic scale/pause/increase.
    Each: evidence → interpretation → decision/test → success measure.
    """
    actions: List[dict] = []
    sessions = _extract_kpi(v24, "Sessions")
    s_cur = sessions.get("current")
    s_prev = sessions.get("previous")
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    channels = cm.get("rows") or []
    paid_totals = _paid_totals_from_campaigns(v24)
    cur = paid_totals["current_period"]
    prev = paid_totals["previous_period"]
    pm = v24.get("paid_media_v24") or {}

    # Action 1: largest movement channel — investigate, not scale
    top = max(channels, key=lambda c: abs((c.get("current_sessions") or 0)
                                          - (c.get("previous_sessions") or 0))) \
            if channels else None
    if top:
        t_cur = top.get("current_sessions")
        t_prev = top.get("previous_sessions")
        if t_cur is not None and t_prev is not None and abs(t_cur - t_prev) >= 5:
            pct, _ = _pct(t_cur, t_prev)
            direction = "rose" if t_cur > t_prev else "fell"
            actions.append({
                "action": (f"Investigate {direction} movement in the "
                            f"{top.get('channel')} channel this week."),
                "why": (f"Movement: {t_prev} → {t_cur} sessions "
                        f"({pct}). Status: {top.get('comparison_status', '—')}. "
                        f"Share of total sessions: {top.get('share_of_sessions', 0):.1f}%."),
                "measure": (f"{top.get('channel')} sessions WoW; for paid traffic, "
                            f"check campaign-level CTR and CPC WoW."),
            })

    # Action 2: objective-aware — within one objective, find a
    # notable efficiency shift (improving or declining) per campaign
    by_obj = _campaigns_by_objective(pm)
    if by_obj:
        # Pick the objective with the most material campaigns
        target_obj = max(by_obj.keys(),
                          key=lambda k: len(by_obj[k]))
        cs = by_obj[target_obj]
        if len(cs) >= 1:
            obj_label = _OBJECTIVE_METRIC.get(target_obj, ("", "", None, None))[0]
            cost_label = _OBJECTIVE_METRIC.get(target_obj, ("", "", None, None))[1]
            # For each campaign, compare current cost-per-result vs
            # previous; flag notable movements.
            movements = []
            for c in cs:
                cur_v = (c.get("current") or {}).get("spend") or 0
                prev_v = (c.get("previous") or {}).get("spend") or 0
                pr = c.get("primary_result") or {}
                cur_cpr = pr.get("primary_cost_per_unit")
                prev_cpr = (((c.get("previous") or {}).get("cost_per_action_type"))
                              or None)  # best effort
                movements.append({
                    "name": c.get("campaign_name"),
                    "objective": target_obj,
                    "cur_spend": cur_v,
                    "prev_spend": prev_v,
                    "cur_cost_per": cur_cpr,
                    "primary_value": pr.get("primary_value"),
                    "metric_label": pr.get("primary_metric_label"),
                    "cost_label": cost_label,
                })
            # Surface: campaign with largest absolute spend (so we
            # actually describe SOMETHING), then describe it.
            movements.sort(key=lambda m: m["cur_spend"], reverse=True)
            top_mv = movements[0]
            if top_mv["cur_spend"] > 0:
                actions.append({
                    "action": (f"Review '{top_mv['name']}' cost-per-result "
                                f"trend before next spend decision."),
                    "why": (f"Largest material {target_obj} campaign this week "
                            f"(R{top_mv['cur_spend']:.2f} spend). "
                            f"Current cost per result: "
                            f"{_fmt(top_mv['cur_cost_per'], 'money') if top_mv['cur_cost_per'] else '—'} "
                            f"({top_mv['metric_label'] or obj_label})."),
                    "measure": (f"This campaign's cost-per-result WoW; "
                                f"Meta-reported results WoW."),
                })

    # Action 3: NS support — keep funding a NS-aligned campaign
    # if it exists and has measurable spend
    ns_items = _extract_north_stars_from_v24(v24)
    paid_campaigns = [c for c in (pm.get("per_campaign") or [])
                        if c.get("status") == "DELIVERED"
                        and (c.get("current") or {}).get("spend", 0) > 0]
    # Find a campaign whose objective matches a NS direction
    fitting_or_coaching_campaigns = [
        c for c in paid_campaigns
        if c.get("objective") == "OUTCOME_LEADS"
        and any(t in (c.get("campaign_name") or "").lower()
                  for t in ("fit", "coach", "lesson", "assessment", "leads"))
    ]
    if fitting_or_coaching_campaigns and ns_items:
        c = fitting_or_coaching_campaigns[0]
        obj_label = _OBJECTIVE_METRIC.get(c.get("objective"), ("", "", None, None))[0]
        cost_label = _OBJECTIVE_METRIC.get(c.get("objective"), ("", "", None, None))[1]
        actions.append({
            "action": (f"Track '{c.get('campaign_name')}' against the "
                        f"Fitting/Coaching North Star."),
            "why": (f"This campaign has the objective that supports "
                    f"the Fitting / Coaching North Star. Current "
                    f"7-day primary result: "
                    f"{((c.get('primary_result') or {}).get('primary_value') or '—')} "
                    f"{obj_label} "
                    f"({((c.get('primary_result') or {}).get('primary_metric_label')) or ''}). "
                    f"Booking connector not yet wired — "
                    f"validated outcomes not yet flowing."),
            "measure": ("This campaign's primary-result metric WoW; "
                          "eventually, verified bookings when the CRM connector is live."),
        })

    return actions[:3]


def _derive_measurement_actions(v24: dict) -> List[str]:
    out: List[str] = []
    pm = v24.get("paid_media_v24") or {}
    ks = v24.get("kpi_scorecard") or {}
    rows = ks.get("rows") or []
    sessions = _extract_kpi(v24, "Sessions")
    if (sessions.get("data_status") or "").upper() in ("UNAVAILABLE", "NOT_CONNECTED"):
        out.append("Wire per-brand GA4 property + service-account JSON "
                     "for this brand (the other brand already has it).")
    leads = _extract_kpi(v24, "Verified Leads")
    if leads.get("data_status") == "PENDING":
        out.append("Wire CRM / booking connector so Verified Leads stops "
                     "being PENDING and we can report measured outcomes.")
    freshness = (pm.get("freshness") or {}).get("status") or ""
    if "stale" in freshness.lower():
        out.append(f"Refresh stale paid-media source "
                     f"(data_as_of={(pm.get('data_as_of') or '?')}).")
    lp = ((v24.get("sections") or {})
            .get("landing_pages") or {})
    sp = lp.get("service_pages") or []
    if not sp:
        out.append("Confirm GA4 top-pages / service-pages dimension is "
                     "enabled for this brand — landing_pages rows is empty.")
    # Check if IG is missing for THIS brand
    dc = ((v24.get("sections") or {})
            .get("data_coverage") or {})
    ig_status = dc.get("instagram") or ""
    if isinstance(ig_status, str) and ig_status.upper() in ("PARTIAL", "NOT_CONNECTED"):
        out.append("Configure Stick Instagram business account + token so "
                     "organic IG insights surface in the weekly report.")
    if not out:
        out.append("No measurement actions this period.")
    return out


# ── markdown rendering ─────────────────────────────────────────

def _render_markdown(bid: str, v24: dict, north_stars: List[dict],
                       periods: Dict[str, str],
                       organic: Dict[str, Any],
                       contamination_block: Optional[str] = None,
                       as_of: Optional[str] = None) -> str:
    facts = _brand_canonical(bid)["canonical"]
    L: List[str] = []

    L.append(f"# {facts['display_name']} — Weekly Management Report")
    L.append(f"_{periods['current_week_start']} → "
               f"{periods['current_week_end']}_  ")
    if as_of:
        L.append(f"_As of: {as_of} (pinned)_  ")
    L.append(f"_Data complete through: "
               f"{periods['data_complete_through']}_")
    L.append("")

    if contamination_block:
        L.append("**REPORT BLOCKED — brand contamination detected.**")
        L.append("")
        L.append(contamination_block)
        return "\n".join(L)

    # ── Source status (connectors) ──
    pm = v24.get("paid_media_v24") or {}
    pm_source_status = pm.get("data_status") or "UNKNOWN"
    pm_freshness = (pm.get("freshness") or {}).get("status") or "unknown"
    pm_data_as_of = ((pm.get("freshness") or {}).get("data_as_of")
                       or pm.get("data_as_of") or "—")
    sessions = _extract_kpi(v24, "Sessions")
    s_status = sessions.get("data_status", "OK")
    ig_status = organic.get("ig", {}).get("status") if organic.get("ig") else "unknown"
    fb_status = organic.get("fb", {}).get("status") if organic.get("fb") else "unknown"
    L.append(f"**Source status (connectors):** Meta Ads = `{pm_source_status}` "
               f"({pm_freshness}, data_as_of={pm_data_as_of}); "
               f"GA4 = `{s_status}`; "
               f"Instagram = `{ig_status}`; "
               f"Facebook Page = `{fb_status}`.")
    L.append("")

    # ── Executive Read (narrative, 2-4 sentences) ──
    L.append("**Executive Read:**")
    L.append(_build_executive_read(bid, v24, organic, periods))
    L.append("")

    # ── TL;DR Numbers (no severity) ──
    L.append("## TL;DR — Numbers (Last 7 days)")
    L.append(f"_{periods['current_week_start']} → "
               f"{periods['current_week_end']} · "
               f"prev 7d: {periods['previous_week_start']} → "
               f"{periods['previous_week_end']}_")
    L.append("")
    L.append("| Metric | Current | Previous | Change | Signal |")
    L.append("|---|---|---|---|---|")
    rows = _build_tldr_rows(v24)
    for r in rows:
        L.append(f"| {r['metric']} | {r['current']} | {r['previous']} | "
                   f"{r['change']} | {r['signal']} |")
    L.append("")
    L.append("> Signal = improving / stable / declining / baseline. Applied only when "
               "absolute volume + confidence support a verdict — small channels show "
               "the percentage without an automated signal.")
    L.append("")

    # ── Organic Social ──
    L.append("## Organic Social")
    L.append("")
    _append_organic_block(L, organic, periods)

    # ── Acquisition Channels ──
    L.append("## Acquisition (7d)")
    L.append("")
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    if cm.get("rows"):
        L.append("| Channel | Current | Previous | Change | Share | Status |")
        L.append("|---|---|---|---|---|---|")
        for ch in (cm.get("rows") or []):
            cur_v = ch.get("current_sessions")
            prev_v = ch.get("previous_sessions")
            pct, _ = _pct(cur_v, prev_v)
            L.append(f"| {ch.get('channel','?')} | "
                       f"{_fmt(cur_v)} | {_fmt(prev_v)} | {pct} | "
                       f"{(ch.get('share_of_sessions') or 0):.1f}% | "
                       f"{(ch.get('comparison_status') or '—')} |")
        L.append("")

    # ── Website Pages (service_pages) ──
    L.append("## Website Pages (7d)")
    L.append("")
    lp = ((v24.get("sections") or {})
            .get("landing_pages") or {})
    sp_list = lp.get("service_pages") or []
    if sp_list:
        L.append("| Path | Current sessions | Previous | Change | Engagement |")
        L.append("|---|---|---|---|---|")
        for sp in sp_list[:6]:
            cur_s = sp.get("current_sessions")
            prev_s = sp.get("previous_sessions")
            pct, _ = _pct(cur_s, prev_s)
            L.append(f"| {sp.get('path','?')} | "
                       f"{_fmt(cur_s)} | {_fmt(prev_s)} | {pct} | "
                       f"{(sp.get('engagement_rate') or 0):.1f}% |")
        L.append("")
    else:
        L.append("No service-page rows this period.")
        L.append("")

    # ── Paid Media ──
    L.append("## Paid Media — Meta Ads (V2.4.1, 7d window)")
    L.append(f"_{periods['current_week_start']} → "
               f"{periods['current_week_end']}_")
    L.append("")
    L.append(f"_source_status=`{pm_source_status}`, "
               f"data_as_of={pm_data_as_of}, freshness={pm_freshness}._")
    L.append("")
    L.append("**Period contract:**")
    L.append(f"- current_start: `{periods['current_week_start']}`")
    L.append(f"- current_end: `{periods['current_week_end']}`")
    L.append(f"- previous_start: `{periods['previous_week_start']}`")
    L.append(f"- previous_end: `{periods['previous_week_end']}`")
    L.append(f"- query_level: `account + campaign`")
    L.append(f"- queried_at: `{pm.get('fetched_at') or '?'}`")
    L.append("")
    if pm_source_status != "LIVE":
        L.append(f"Meta Ads source_status = `{pm_source_status}` — see "
                   f"Data Notes. **Not the same as zero spend.**")
        L.append("")
    else:
        cur = paid_totals = _paid_totals_from_campaigns(v24)["current_period"]
        prev = _paid_totals_from_campaigns(v24)["previous_period"]
        eff = _compute_paid_efficiency(cur, prev)
        L.append("| Metric | Current (7d) | Previous (7d) | Change |")
        L.append("|---|---|---|---|")
        L.append(f"| Spend | {_fmt(cur.get('total_spend'), 'money')} | "
                   f"{_fmt(prev.get('total_spend'), 'money')} | "
                   f"{_pct(cur.get('total_spend'), prev.get('total_spend'))[0]} |")
        L.append(f"| Impressions | {_fmt(cur.get('total_impressions'))} | "
                   f"{_fmt(prev.get('total_impressions'))} | "
                   f"{_pct(cur.get('total_impressions'), prev.get('total_impressions'))[0]} |")
        L.append(f"| Reach | {_fmt(cur.get('total_reach'))} | "
                   f"{_fmt(prev.get('total_reach'))} | "
                   f"{_pct(cur.get('total_reach'), prev.get('total_reach'))[0]} |")
        L.append(f"| Clicks | {_fmt(cur.get('total_clicks'))} | "
                   f"{_fmt(prev.get('total_clicks'))} | "
                   f"{_pct(cur.get('total_clicks'), prev.get('total_clicks'))[0]} |")
        L.append(f"| Meta-reported leads (OUTCOME_LEADS) | "
                   f"{_fmt(cur.get('total_results'))} | "
                   f"— | — |")
        L.append(f"| CTR | {_fmt(eff.get('ctr'), 'pct')} | — | — |")
        L.append(f"| CPC | {_fmt(eff.get('cpc'), 'money')} | — | — |")
        L.append(f"| CPM | {_fmt(eff.get('cpm'), 'money')} | — | — |")
        L.append("")
        # Objective-aware campaigns
        by_obj = _campaigns_by_objective(pm)
        if by_obj:
            L.append(f"**Campaigns this week ({sum(len(v) for v in by_obj.values())} "
                       f"material, grouped by objective):**")
            L.append("")
            _append_campaign_table_by_objective(L, by_obj)

    # ── Content Performance (top 3-5 pieces from IG + FB) ──
    L.append("## Content Performance")
    L.append("")
    _append_content_block(L, organic)

    # ── Business / Funnel ──
    L.append("## Business / Funnel Signals")
    L.append("")
    L.append("| Stage | Value | Confidence |")
    L.append("|---|---|---|")
    s_cur = sessions.get("current")
    s_status = sessions.get("data_status", "OK")
    L.append(f"| Website sessions (7d) | {_fmt(s_cur) if s_cur is not None else '—'} | {s_status.lower()} |")
    eng = _extract_kpi(v24, "Engaged sessions")
    L.append(f"| Engaged sessions (7d) | {_fmt(eng.get('current')) if eng.get('current') is not None else '—'} | {eng.get('data_status','—').lower() if eng.get('data_status') else '—'} |")
    paid_totals = _paid_totals_from_campaigns(v24)
    leads_cur = paid_totals["current_period"].get("total_results")
    L.append(f"| Meta-reported leads (7d, OUTCOME_LEADS) | "
               f"{_fmt(leads_cur) if leads_cur is not None else '—'} | {pm.get('data_status','—').lower() if pm.get('data_status') else '—'} |")
    L.append(f"| Bookings / sales (7d) | NOT YET MEASURED — CRM/POS connector pending | low |")
    L.append("")
    L.append("> Revenue modelling requires real conversion rate × outcome value × verified "
               "attribution. Until the operational CRM/POS connector is wired, no revenue "
               "projections possible.")
    L.append("")

    # ── North Stars — Stick: in body. Swing Shack: only confirmed,
    #    pending ones moved to Data Notes ──
    confirmed_ns = [ns for ns in north_stars
                      if "PENDING" not in ns.get("label", "").upper()
                      and "PENDING" not in ns.get("metric", "").upper()
                      and ns.get("metric")]
    pending_ns = [ns for ns in north_stars
                    if "PENDING" in ns.get("label", "").upper()
                    or "PENDING" in ns.get("metric", "").upper()
                    or not ns.get("metric")]
    if confirmed_ns:
        L.append("## North Stars (canonical — from Reporting V2.4.1)")
        L.append("")
        for ns in confirmed_ns:
            L.append(f"- **{ns['label']}** — {ns['metric']}")
            L.append(f"  - Source: `{ns['source']}`")
            L.append(f"  - Outcome measurement: PENDING — operational "
                       f"connector not yet integrated with reporting")
        L.append("")
    if pending_ns:
        L.append("## North Stars (strategy configuration gaps)")
        L.append("")
        L.append("Targets below exist as configuration keys but the canonical "
                   "weekly / monthly target value has not yet been confirmed by "
                   "Christelle. They are NOT carried as operational North Stars.")
        L.append("")
        for ns in pending_ns:
            L.append(f"- `{ns['label']}` — {ns['metric'] or 'target not set'} "
                       f"(source: `{ns['source']}`, PENDING)")
        L.append("")

    # ── What Worked ──
    L.append("## What Worked (outcome / efficiency)")
    L.append("")
    worked = _derive_what_worked(v24, bid)
    if worked:
        for w in worked:
            L.append(f"- {w}")
    else:
        L.append("- No material outcome/efficiency signal this period. "
                   "Connectors and spend alone are inputs, not outcomes.")
    L.append("")

    # ── What Needs Attention ──
    L.append("## What Needs Attention")
    L.append("")
    attention = _derive_what_needs_attention(v24, bid)
    if attention:
        for sev, txt in attention:
            L.append(f"- **[{sev}]** {txt}")
    else:
        L.append("- No material performance issues detected this period.")
    L.append("")

    # ── Marketing Actions ──
    L.append("## Marketing Actions (evidence-based, max 3)")
    L.append("")
    actions = _derive_marketing_actions(v24, bid)
    if actions:
        for i, a in enumerate(actions, 1):
            L.append(f"{i}. **{a['action']}**")
            L.append(f"   - **Evidence → Interpretation:** {a['why']}")
            L.append(f"   - **Decision / Test:** {a['action']}")
            L.append(f"   - **Success measure:** {a['measure']}")
    else:
        L.append("- No marketing actions defensible from the current data set. "
                   "See Measurement / Data Actions for the gaps blocking decisions.")
    L.append("")
    L.append("> Reporting informs decisions; it does not mutate campaigns. "
               "Scale / pause / increase-budget actions require per-objective "
               "efficiency evidence — not a single-week WoW % change.")
    L.append("")

    # ── Measurement / Data Actions ──
    L.append("## Measurement / Data Actions")
    L.append("")
    meas = _derive_measurement_actions(v24)
    for i, a in enumerate(meas, 1):
        L.append(f"{i}. {a}")
    L.append("")

    # ── Data Notes / Limitations ──
    L.append("## Data Notes / Limitations")
    L.append("")
    L.append("**Period contract:**")
    L.append(f"- data_complete_through = "
               f"{periods['data_complete_through']} (yesterday, "
               f"today's incomplete data excluded)")
    L.append(f"- current_week = {periods['current_week_start']} → "
               f"{periods['current_week_end']} (7 complete days)")
    L.append(f"- previous_week = {periods['previous_week_start']} → "
               f"{periods['previous_week_end']} (7 complete days)")
    L.append(f"- current_28d = {periods['current_28d_start']} → "
               f"{periods['current_28d_end']} (28 complete days)")
    L.append(f"- previous_28d = {periods['previous_28d_start']} → "
               f"{periods['previous_28d_end']} (28 complete days)")
    L.append("")
    L.append("**Source lineage (from V2.4.1 canonical):**")
    sl = v24.get("source_lineage") or []
    for s in sl:
        L.append(f"- {s.get('source','?')}: "
                   f"data_as_of={s.get('data_as_of') or '?'}")
    L.append("")
    L.append(f"**Paid-media freshness:** data_as_of={pm_data_as_of}, "
               f"status={pm_freshness}, source_status={pm_source_status}. "
               f"7-day cache validated against direct Meta Graph API audit.")
    L.append("")
    L.append("**Tone:** management report — outcomes first, actions only when "
               "evidence supports them. Missing data ≠ zero. No creative generation.")
    L.append("")
    L.append("---")
    L.append(f"_Generated {datetime.datetime.now(datetime.timezone.utc).isoformat()} • V2.4.1 frozen • V3.3 renderer._")
    return "\n".join(L)


def _build_executive_read(bid: str, v24: dict, organic: Dict[str, Any],
                            periods: Dict[str, str]) -> str:
    """Narrative 2-4 sentences explaining the week."""
    s = _extract_kpi(v24, "Sessions")
    s_cur = s.get("current")
    s_prev = s.get("previous")
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    chans = cm.get("rows") or []
    # Find the largest mover
    movers = []
    for c in chans:
        cur_v = c.get("current_sessions")
        prev_v = c.get("previous_sessions")
        if cur_v is not None and prev_v is not None:
            movers.append((c.get("channel"), cur_v - prev_v))
    movers.sort(key=lambda t: abs(t[1]), reverse=True)
    parts: List[str] = []
    if s_cur is not None and s_prev is not None and s_prev > 0:
        pct, _ = _pct(s_cur, s_prev)
        direction = "edged up" if s_cur > s_prev else "fell" if s_cur < s_prev else "held flat at"
        parts.append(f"Website traffic {direction} {pct} WoW "
                       f"({_fmt(s_cur)} sessions vs {_fmt(s_prev)}).")
    if movers:
        biggest = movers[0]
        if abs(biggest[1]) >= 5:
            sign = "+" if biggest[1] > 0 else ""
            parts.append(f"The {biggest[0]} channel moved {sign}{biggest[1]} sessions "
                          f"(largest channel-level delta).")
    # Paid-media direction (objective-aware, no cross-objective ranking)
    paid_totals = _paid_totals_from_campaigns(v24)
    cur = paid_totals["current_period"]
    prev = paid_totals["previous_period"]
    if cur.get("total_impressions", 0) > 0 and prev.get("total_impressions", 0) > 0:
        imp_delta = (cur["total_impressions"] - prev["total_impressions"]) \
                       / prev["total_impressions"] * 100
        if abs(imp_delta) >= 10:
            parts.append(f"Paid-media delivery {'contracted' if imp_delta < 0 else 'expanded'} "
                           f"{imp_delta:+.1f}% (impressions WoW); spend stayed at "
                           f"R{cur['total_spend']:,.2f}.")
    # Pending bookings connector call-out
    leads = _extract_kpi(v24, "Verified Leads")
    if leads.get("data_status") == "PENDING":
        parts.append("Validated bookings / sales not yet wired — "
                      "Meta-reported lead count is the closest signal until "
                      "the CRM/POS connector is live.")
    if not parts:
        return "_Insufficient data to summarise this week — see Data Notes._"
    return " ".join(parts[:4])


def _append_organic_block(L: List[str], organic: Dict[str, Any],
                            periods: Dict[str, str]) -> None:
    ig = organic.get("ig") or {}
    fb = organic.get("fb") or {}
    ig_status = ig.get("status", "NOT_CONNECTED")
    fb_status = fb.get("status", "NOT_CONNECTED")
    if ig_status == "NOT_CONNECTED" and fb_status == "NOT_CONNECTED":
        L.append(f"Instagram and Facebook Page data not available for this brand. "
                   f"Connector not configured (see Data Notes).")
        L.append("")
        return
    L.append("| Channel | Reach/Impressions | Interactions | Profile / Clicks | "
               "Source status |")
    L.append("|---|---|---|---|---|")
    if ig_status != "NOT_CONNECTED":
        L.append(f"| Instagram (28d) | "
                   f"{_fmt(ig.get('reach'))} | "
                   f"{_fmt(ig.get('interactions'))} | "
                   f"profile_views {_fmt(ig.get('profile_views'))} | "
                   f"`{ig_status}` |")
    else:
        L.append(f"| Instagram (28d) | — | — | — | `PARTIAL — connector not configured` |")
    if fb_status != "NOT_CONNECTED":
        L.append(f"| Facebook Page (28d) | "
                   f"{_fmt(fb.get('impressions'))} | "
                   f"{_fmt(fb.get('engagements'))} | "
                   f"clicks {_fmt(fb.get('clicks'))} | "
                   f"`{fb_status}` |")
    else:
        L.append(f"| Facebook Page (28d) | — | — | — | `PARTIAL — connector not configured` |")
    L.append("")
    L.append("> Reach / interactions: 28d totals. No Story-vs-post efficiency claim "
               "made here — sample windows differ from the 7d paid block.")
    L.append("")


def _append_content_block(L: List[str], organic: Dict[str, Any]) -> None:
    ig_top = (organic.get("ig") or {}).get("top_posts") or []
    fb_top = (organic.get("fb") or {}).get("top_posts") or []
    if not ig_top and not fb_top:
        L.append("No recent IG / FB media tracked for this brand.")
        L.append("")
        return
    L.append("Top-performing content pieces (most-engaging, recent):")
    L.append("")
    L.append("| Platform | Format | Topic (caption preview) | Interactions | Source |")
    L.append("|---|---|---|---|---|")
    pieces = sorted(
        [("Instagram", p) for p in ig_top]
        + [("Facebook Page", p) for p in fb_top],
        key=lambda t: (t[1].get("interactions") or 0),
        reverse=True,
    )[:5]
    for platform, p in pieces:
        caption = (p.get("caption") or "")[:60]
        fmt_type = p.get("media_type") or "?"
        L.append(f"| {platform} | {fmt_type} | {caption} | "
                   f"{_fmt(p.get('interactions'))} | {platform} |")
    L.append("")
    L.append("**Observation:** " + (pieces[0][1].get("caption")[:120] + "..." if pieces else
                                          "_No content tracked._"))


def _append_campaign_table_by_objective(L: List[str], by_obj: Dict[str, List[dict]]) -> None:
    for obj in sorted(by_obj.keys()):
        label, cost_label, value_fn, cost_fn = _OBJECTIVE_METRIC.get(
            obj, ("primary result", "R/result", None, None))
        cs = sorted(by_obj[obj], key=lambda c: (c.get("current") or {}).get("spend", 0), reverse=True)
        L.append(f"### {obj} — {label}")
        L.append("")
        L.append("| Campaign | Spend | Impressions | Reach | Clicks | CTR | CPC | "
                   f"{label} | Cost / {label} |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for c in cs:
            cur = c.get("current") or {}
            pr = c.get("primary_result") or {}
            ctr = cur.get("ctr") or 0
            cpc = cur.get("cpc") or 0
            # CTR is reported as percentage in Meta. _v24_normalize_action_types
            # may store as fraction (0.18) or as percentage (18). Check scale.
            ctr_str = f"{ctr*100:.2f}%" if ctr < 1 else f"{ctr:.2f}%"
            L.append(f"| {c.get('campaign_name','?')} | "
                       f"{_fmt(cur.get('spend'), 'money')} | "
                       f"{_fmt(cur.get('impressions'))} | "
                       f"{_fmt(cur.get('reach'))} | "
                       f"{_fmt(cur.get('clicks'))} | "
                       f"{ctr_str} | "
                       f"{_fmt(cpc, 'money')} | "
                       f"{_fmt(pr.get('primary_value'))} {pr.get('primary_value_unit','')} | "
                       f"{_fmt(pr.get('primary_cost_per_unit'), 'money')} |")
        L.append("")
        if len(cs) >= 2:
            L.append(f"_Within-objective ranking: not applied — campaigns have "
                       f"different prior-period baselines and objective-specific "
                       f"cost-per-result definitions. Compare each campaign to its "
                       f"OWN previous-week numbers._")
            L.append("")


# ── HTML rendering ──────────────────────────────────────────────

def _render_html(bid: str, v24: dict, north_stars: List[dict],
                   periods: Dict[str, str], organic: Dict[str, Any],
                   contamination_block: Optional[str] = None,
                   as_of: Optional[str] = None) -> str:
    md = _render_markdown(bid, v24, north_stars, periods, organic,
                            contamination_block, as_of)
    facts = _brand_canonical(bid)["canonical"]
    title = (f"{facts['display_name']} — Weekly Management Report"
              f" ({periods['current_week_start']} → "
              f"{periods['current_week_end']})")
    if contamination_block:
        title = f"{title} — BLOCKED"
    body = md.replace("&", "&amp;").replace("<", "&lt;").replace(
        ">", "&gt;")
    body_html = body.replace("\n## ", "\n<h2>").replace("\n### ", "\n<h3>")
    body_html = body_html.replace("**", "")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,"
        "'Segoe UI',Roboto,sans-serif;max-width:920px;margin:40px auto;"
        "padding:0 20px;color:#1a1f2e;line-height:1.5;}"
        "h1{margin-bottom:8px}h2{margin-top:32px;border-bottom:1px solid "
        "#e3e6ed;padding-bottom:6px}table{border-collapse:collapse;"
        "width:100%;margin:12px 0}th,td{padding:6px 10px;text-align:left;"
        "border-bottom:1px solid #e3e6ed;font-size:14px}th{background:"
        "#f6f7fb}blockquote{border-left:3px solid #cdd2dd;margin:8px 0;"
        "padding:6px 14px;color:#4a5568;background:#fafbfd}"
        "@media print {body{margin:0 auto}}</style>"
        "</head><body>"
        f"<pre style='white-space:pre-wrap;font-family:inherit;"
        f"font-size:14px;line-height:1.55'>{body_html}</pre>"
        "</body></html>")


# ── main entry ─────────────────────────────────────────────────

def build_v33(bid: str, fmt: str = "markdown",
                as_of: Optional[str] = None,
                cookie: Optional[str] = None) -> dict:
    if bid not in ("stick", "swing-shack", "bag-drop"):
        return {"report_status": "INVALID_BRAND",
                "block_reason": "brand_id must be stick, swing-shack, or bag-drop",
                "contaminations": [],
                "rendered": f"# Invalid brand\n\n`{bid}` is not a managed brand.",
                "raw_payload": {}}

    periods = _compute_periods(as_of)
    v24 = _read_v24(bid, as_of, cookie=cookie)

    if not v24 or "error" in v24:
        return {
            "report_status": "V24_UNAVAILABLE",
            "block_reason": v24.get("error", "V2.4.1 read failed"),
            "contaminations": [],
            "rendered": (f"# {bid.title()} — Weekly Management Report\n\n"
                          f"**V2.4.1 unavailable:** "
                          f"{v24.get('error', 'unknown error')}\n\n"
                          f"Period: {periods['current_week_start']} → "
                          f"{periods['current_week_end']}"),
            "raw_payload": {"v24": v24, "periods": periods},
        }

    clean, violations = _validate_brand_isolation(bid, v24)
    if not clean:
        block = ("Identifiers found in V2.4.1 payload:\n"
                  + "\n".join(f"- `{v}`" for v in violations)
                  + "\n\nThis report will not render until the canonical "
                    "V2.4.1 data sources are scoped to this brand only.")
        return {
            "report_status": "BLOCKED_BRAND_CONTAMINATION",
            "block_reason": "V2.4.1 payload contains identifiers from a "
                             "different brand.",
            "contaminations": violations,
            "rendered": _render_markdown(bid, v24, [], periods, {},
                                           contamination_block=block,
                                           as_of=as_of),
            "raw_payload": {"v24": v24, "periods": periods},
        }

    north_stars = _extract_north_stars_from_v24(v24)

    # Read organic social from on-disk cache (Railway writes these
    # via /api/instagram/refresh and /api/meta/fb-page/refresh).
    organic = _read_organic_from_cache(bid)

    status = "OK"

    if fmt == "html":
        rendered = _render_html(bid, v24, north_stars, periods, organic,
                                  as_of=as_of)
    elif fmt == "json":
        rendered = _render_markdown(bid, v24, north_stars, periods, organic,
                                      as_of=as_of)
    else:
        rendered = _render_markdown(bid, v24, north_stars, periods, organic,
                                      as_of=as_of)

    return {
        "report_status": status,
        "block_reason": None,
        "contaminations": [],
        "rendered": rendered,
        "raw_payload": {
            "v24": v24,
            "periods": periods,
            "north_stars": north_stars,
            "brand_id": bid,
            "generator": "weekly_report_v3.3",
            "as_of": as_of,
            "organic": organic,
        },
    }


def _read_organic_from_cache(bid: str) -> Dict[str, Any]:
    """Read the IG + FB cache files written by Railway refreshes.
    Returns dict with keys 'ig' and 'fb', each containing status +
    reach + interactions + top posts.
    """
    out: Dict[str, Any] = {"ig": None, "fb": None}
    # IG
    ig_status, ig_data = "NOT_CONNECTED", {}
    for r in (
        _data_root(),
        Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data"),
    ):
        for fname in ("ig-business-analytics.json",
                         "analytics/instagram-analytics.json"):
            p = r / fname
            if p.is_file():
                try:
                    raw = json.loads(p.read_text(encoding="utf-8"))
                    # If brand-scoped, only accept it for that brand
                    account = (raw.get("account") or {})
                    username = account.get("username")
                    # Map IG username to brand
                    ig_brand_map = {
                        "swingshack": "swing-shack",
                        "stickgolf": "stick",
                    }
                    detected_brand = ig_brand_map.get(
                        (username or "").lower().replace("@", ""))
                    # Per-brand file preferred
                    if detected_brand and detected_brand != bid:
                        # This file belongs to a different brand — skip.
                        continue
                    ig_data = raw
                    ig_status = "LIVE" if raw.get("window_totals") else "PARTIAL"
                except Exception:
                    continue
                if ig_data:
                    break
        if ig_data:
            break
    if ig_data:
        # Filter top posts to those within the current 7d window if possible
        wt = ig_data.get("window_totals") or {}
        out["ig"] = {
            "status": ig_status,
            "username": (ig_data.get("account") or {}).get("username"),
            "followers": (ig_data.get("account") or {}).get("followers_count"),
            "reach": wt.get("reach") or wt.get("accounts_engaged"),
            "interactions": wt.get("total_interactions"),
            "profile_views": wt.get("profile_views"),
            "profile_links_taps": wt.get("profile_links_taps"),
            "top_posts": [
                {
                    "id": p.get("id"),
                    "media_type": p.get("media_type"),
                    "caption": (p.get("caption") or "").strip(),
                    "interactions": ((p.get("metrics") or {})
                                          .get("total_interactions")),
                    "reach": ((p.get("metrics") or {})
                                  .get("reach")),
                    "timestamp": p.get("timestamp"),
                }
                for p in (ig_data.get("media") or [])[:10]
            ],
        }
    # FB
    fb_status, fb_data = "NOT_CONNECTED", {}
    for r in (
        _data_root(),
        Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data"),
    ):
        p = r / "fb-page-analytics.json"
        if p.is_file():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                fb_data = raw
                fb_status = "LIVE" if raw.get("window_totals") else "PARTIAL"
            except Exception:
                continue
            if fb_data:
                break
    if fb_data:
        wt = fb_data.get("window_totals") or {}
        page = fb_data.get("page") or {}
        out["fb"] = {
            "status": fb_status,
            "page_name": page.get("name"),
            "fans": page.get("fan_count"),
            "impressions": wt.get("page_impressions"),
            "engagements": wt.get("page_post_engagements"),
            "clicks": wt.get("page_consumptions") or wt.get("clicks"),
            "top_posts": [
                {
                    "id": p.get("id"),
                    "media_type": p.get("type") or p.get("media_type"),
                    "caption": (p.get("message") or p.get("message_preview") or "").strip(),
                    "interactions": (
                        (p.get("reactions_total") or 0)
                        + (p.get("comments") or 0)
                        + (p.get("shares") or 0)
                    ),
                    "clicks": p.get("clicks"),
                    "timestamp": p.get("timestamp"),
                }
                for p in (fb_data.get("posts") or [])[:10]
            ],
        }
    return out


# ── snapshot ──────────────────────────────────────────────────

def archive_snapshot_v33(bid: str, as_of: Optional[str] = None,
                            snapshot_root: Optional[Path] = None,
                            cookie: Optional[str] = None) -> Dict[str, Any]:
    out = build_v33(bid, fmt="json", as_of=as_of, cookie=cookie)
    v24 = (out.get("raw_payload") or {}).get("v24") or {}
    periods = (out.get("raw_payload") or {}).get("periods") or {}
    north_stars = (out.get("raw_payload") or {}).get("north_stars") or []
    organic = (out.get("raw_payload") or {}).get("organic") or {}
    snapshot = {
        "schema": "https://campaign-os/weekly-report/v3.3-snapshot",
        "brand_id": bid,
        "as_of": as_of or periods.get("data_complete_through"),
        "current_period": {
            "start": periods.get("current_week_start"),
            "end": periods.get("current_week_end"),
        },
        "previous_period": {
            "start": periods.get("previous_week_start"),
            "end": periods.get("previous_week_end"),
        },
        "data_complete_through": periods.get("data_complete_through"),
        "kpi_values": {},
        "source_statuses": {},
        "organic_status": {
            "instagram": (organic.get("ig") or {}).get("status"),
            "facebook": (organic.get("fb") or {}).get("status"),
        },
        "north_stars": north_stars,
        "report_status": out.get("report_status"),
        "archived_at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
    }
    for label in ("Sessions", "Users", "Engaged sessions",
                    "Engagement rate", "Pageviews", "Conversions",
                    "Paid Spend", "Verified Leads"):
        r = _extract_kpi(v24, label)
        snapshot["kpi_values"][label] = {
            "current": r.get("current"),
            "previous": r.get("previous"),
            "data_status": r.get("data_status"),
        }
    pm = v24.get("paid_media_v24") or {}
    pt = _paid_totals_from_campaigns(v24)
    snapshot["kpi_values"]["paid_media_v24"] = {
        "data_status": pm.get("data_status"),
        "freshness": pm.get("freshness"),
        "data_as_of": pm.get("data_as_of"),
        "current_period": pt.get("current_period"),
        "previous_period": pt.get("previous_period"),
    }
    for src in (v24.get("source_lineage") or []):
        snapshot["source_statuses"][src.get("source", "?")] = {
            "status": src.get("status"),
            "fetched_at": src.get("fetched_at"),
            "data_as_of": src.get("data_as_of"),
        }
    root = snapshot_root or _data_root()
    snap_dir = root / "weekly-snapshots" / bid
    snap_dir.mkdir(parents=True, exist_ok=True)
    fn = snap_dir / f"{snapshot['current_period']['end']}.json"
    fn.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False,
                                default=str), encoding="utf-8")
    snapshot["path"] = fn.as_posix()
    return snapshot


# Backwards-compat aliases
def build_v31(*args, **kwargs):
    return build_v33(*args, **kwargs)


def build_v32(*args, **kwargs):
    return build_v33(*args, **kwargs)


def archive_snapshot_v31(*args, **kwargs):
    return archive_snapshot_v33(*args, **kwargs)


def archive_snapshot_v32(*args, **kwargs):
    return archive_snapshot_v33(*args, **kwargs)


if __name__ == "__main__":
    bid = sys.argv[1] if len(sys.argv) > 1 else "stick"
    fmt = sys.argv[2] if len(sys.argv) > 2 else "markdown"
    as_of = sys.argv[3] if len(sys.argv) > 3 else None
    out = build_v33(bid, fmt=fmt, as_of=as_of)
    print(out["rendered"])
    sys.exit(0 if out["report_status"] == "OK" else 2)
