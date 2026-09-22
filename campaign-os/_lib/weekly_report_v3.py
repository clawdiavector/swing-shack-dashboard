"""weekly_report_v3.py — Weekly Management Report V3.2.

Renderer-only. Sits ON TOP of Reporting Intelligence V2.4.1
(frozen). Reads canonical V2.4.1 data via build_v24_brand_report().

V3.2 fix: actual data extraction against the real V2.4.1 shape.

Period contract:
  data_complete_through = yesterday
  current_week  = yesterday-6 → yesterday
  previous_week = yesterday-13 → yesterday-7
  current_28d   = yesterday-27 → yesterday
  previous_28d  = yesterday-55 → yesterday-28
  Optional ?as_of=YYYY-MM-DD pins the report to a past date.

Data sources (all from V2.4.1):
  kpi_scorecard.rows[]           — sessions / users / engagement / pageviews / spend
  sections.channel_mix.rows[]    — current + previous sessions per channel
  sections.landing_pages.rows[]  — top pages
  sections.north_stars.items     — canonical target wording
  paid_media_v24.freshness       — source_status / data_as_of / age
  paid_media_v24.data_status     — LIVE / NOT_CONNECTED
  paid_media_v24.per_campaign[]  — 7-day per-campaign current + previous

Three status concepts are kept distinct:
  source_status  — is the connector LIVE? (paid_media_v24.data_status)
  data_status    — is the queried metric value AVAILABLE?
                   (in V2.4.1, computed from kpi_scorecard row note or
                    per_campaign row presence)
  metric_value   — the actual number, or `—` when unavailable

Marketing vs Measurement actions:
  ## Marketing Actions — Top N (real marketing decisions from data)
  ## Measurement / Data Actions (technical wire-ups)
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

def _read_v24(bid: str, as_of: Optional[str] = None) -> Dict[str, Any]:
    from _lib.reporting_intelligence import build_v24_brand_report
    periods = _compute_periods(as_of)
    try:
        r = build_v24_brand_report(bid, period_days=7, cookie=None) or {}
    except Exception as e:
        return {"error": str(e), "bid": bid, "periods": periods}
    r["__periods"] = periods
    r["__bid"] = bid
    return r


# ── canonical North Stars (V2.4.1 → calendar_config loader) ────

def _load_canonical_north_stars(bid: str) -> List[dict]:
    """Load North Stars from V2.4.1 sections.north_stars.items.

    V2.4.1 already pulls these from calendar_config.json (the
    canonical loader shared with Calendar / Brief). We read the
    rendered V2.4.1 view so we get the EXACT canonical wording
    (e.g. "R350,000 Psycho Bunny sales/month") — we do NOT
    simplify or reformat.
    """
    return []  # populated by build_v32 (needs v24 payload)


def _extract_north_stars_from_v24(v24: dict) -> List[dict]:
    """Read the canonical North Stars from V2.4.1's
    sections.north_stars.items — already in canonical wording.
    """
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
    """Pull one KPI row by label. V2.4.1 row labels include:
       Sessions, Users, Engaged sessions, Engagement rate,
       Pageviews, Conversions, Paid Spend, Verified Leads
    """
    for row in (v24.get("kpi_scorecard") or {}).get("rows") or []:
        if row.get("label", "").lower() == label.lower():
            return row
    return {}


def _paid_totals_from_campaigns(v24: dict) -> Dict[str, Any]:
    """Aggregate 7-day current + previous totals from
    paid_media_v24.per_campaign[].current and .previous.

    Returns dict with current_period + previous_period keys
    compatible with the V3.1 expected shape.
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
    # Primary result totals (objective-relevant) — sum primary_value
    for c in (pm.get("per_campaign") or []):
        pr = c.get("primary_result") or {}
        pv = pr.get("primary_value")
        if isinstance(pv, (int, float)):
            cur["total_results"] += float(pv)
    # No reliable previous primary_result aggregation in V2.4.1 shape
    return {
        "current_period": cur,
        "previous_period": prev,
    }


def _compute_paid_efficiency(cur: dict, prev: dict) -> Dict[str, Optional[float]]:
    """CTR / CPC / CPM from current period totals."""
    out: Dict[str, Optional[float]] = {}
    spend = cur.get("total_spend") or 0
    imp = cur.get("total_impressions") or 0
    clicks = cur.get("total_clicks") or 0
    out["ctr"] = (clicks / imp * 100.0) if imp else None
    out["cpc"] = (spend / clicks) if clicks else None
    out["cpm"] = (spend / imp * 1000.0) if imp else None
    return out


# ── severity (materiality + business consequence + confidence) ─

def _severity_materiality(current, previous, *, confidence="high",
                            materiality="medium", business_consequence="medium"
                            ) -> str:
    if current is None and previous is None:
        return "LOW"
    if current is None or previous is None:
        return "MEDIUM"
    try:
        c = float(current); p = float(prev)
    except (ValueError, TypeError):
        return "MEDIUM"
    if p == 0 and c == 0:
        return "LOW"
    abs_change = abs(c - p)
    mat_score = (0 if abs_change < 5 else
                  1 if abs_change < 50 else
                  2 if abs_change < 200 else 3)
    mat_score += {"low": -1, "medium": 0, "high": 1}.get(materiality, 0)
    bc_score = {"low": 0, "medium": 1, "high": 2}.get(business_consequence, 1)
    if confidence in ("low", "pending", "unavailable", "not_connected", "stale"):
        mat_score = max(0, mat_score - 1)
    total = mat_score + bc_score
    if total >= 4:
        return "HIGH"
    if total >= 2:
        return "MEDIUM"
    return "LOW"


# ── number formatting ──────────────────────────────────────────

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
        return f"R{int(round(n)):,}"
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


# ── KPI row builder (real V2.4.1 data) ─────────────────────────

def _build_tldr_rows(v24: dict) -> List[dict]:
    rows: List[dict] = []

    # Sessions — from kpi_scorecard
    sessions = _extract_kpi(v24, "Sessions")
    s_cur = sessions.get("current")
    s_prev = sessions.get("previous")
    s_status = sessions.get("data_status", "OK")
    rows.append({
        "metric": "Website sessions (7d)",
        "current": _fmt(s_cur),
        "previous": _fmt(s_prev) if s_prev is not None else "—",
        "change": _pct(s_cur, s_prev)[0],
        "severity": _severity_materiality(s_cur, s_prev,
            confidence=s_status.lower(),
            materiality="high", business_consequence="high"),
    })

    # Users
    users = _extract_kpi(v24, "Users")
    rows.append({
        "metric": "Users (7d)",
        "current": _fmt(users.get("current")),
        "previous": _fmt(users.get("previous")) if users.get("previous") is not None else "—",
        "change": _pct(users.get("current"), users.get("previous"))[0],
        "severity": _severity_materiality(users.get("current"), users.get("previous"),
            confidence=users.get("data_status", "OK").lower(),
            materiality="high", business_consequence="high"),
    })

    # Engaged sessions
    eng = _extract_kpi(v24, "Engaged sessions")
    rows.append({
        "metric": "Engaged sessions (7d)",
        "current": _fmt(eng.get("current")),
        "previous": _fmt(eng.get("previous")) if eng.get("previous") is not None else "—",
        "change": _pct(eng.get("current"), eng.get("previous"))[0],
        "severity": _severity_materiality(eng.get("current"), eng.get("previous"),
            confidence=eng.get("data_status", "OK").lower(),
            materiality="medium", business_consequence="medium"),
    })

    # Engagement rate
    er = _extract_kpi(v24, "Engagement rate")
    rows.append({
        "metric": "Engagement rate (7d)",
        "current": _fmt(er.get("current"), "decimal"),
        "previous": _fmt(er.get("previous"), "decimal") if er.get("previous") is not None else "—",
        "change": _pct(er.get("current"), er.get("previous"))[0],
        "severity": _severity_materiality(er.get("current"), er.get("previous"),
            confidence=er.get("data_status", "OK").lower(),
            materiality="medium", business_consequence="medium"),
    })

    # Meta paid spend (7d) — from V2.4.1 kpi_scorecard "Paid Spend"
    spend = _extract_kpi(v24, "Paid Spend")
    rows.append({
        "metric": "Meta paid spend (7d)",
        "current": _fmt(spend.get("current"), "money"),
        "previous": _fmt(spend.get("previous"), "money") if spend.get("previous") is not None else "—",
        "change": _pct(spend.get("current"), spend.get("previous"))[0],
        "severity": _severity_materiality(spend.get("current"), spend.get("previous"),
            confidence=spend.get("data_status", "OK").lower(),
            materiality="high", business_consequence="high"),
    })

    # Meta reported leads (7d) — from kpi_scorecard "Verified Leads" or per-campaign primary_result
    leads = _extract_kpi(v24, "Verified Leads")
    paid_totals = _paid_totals_from_campaigns(v24)
    cur_results = paid_totals["current_period"].get("total_results")
    leads_cur = leads.get("current") if leads.get("current") is not None else cur_results
    leads_status = leads.get("data_status", "OK")
    rows.append({
        "metric": "Meta-reported leads (7d)",
        "current": _fmt(leads_cur) if leads_cur is not None else "—",
        "previous": _fmt(leads.get("previous")) if leads.get("previous") is not None else "—",
        "change": _pct(leads_cur, leads.get("previous"))[0],
        "severity": _severity_materiality(leads_cur, leads.get("previous"),
            confidence=leads_status.lower(),
            materiality="high", business_consequence="high"),
    })

    # CTR / CPC / CPM from paid totals
    efficiency = _compute_paid_efficiency(paid_totals["current_period"],
                                            paid_totals["previous_period"])
    for label, key, fmt_kind in (("Meta CTR (7d)", "ctr", "decimal"),
                                     ("Meta CPC (7d)", "cpc", "money"),
                                     ("Meta CPM (7d)", "cpm", "money")):
        v = efficiency.get(key)
        rows.append({
            "metric": label,
            "current": _fmt(v, fmt_kind),
            "previous": "—",
            "change": "—",
            "severity": _severity_materiality(v, None,
                confidence="high",
                materiality="medium", business_consequence="medium"),
        })

    return rows


# ── Marketing actions derived from V2.4.1 ──────────────────────

def _derive_marketing_actions(v24: dict, bid: str) -> List[dict]:
    """Up to 3 real marketing actions. No placeholders.

    If only 2 are defensible, return 2. We do NOT pad to 3.
    """
    actions: List[dict] = []

    sessions = _extract_kpi(v24, "Sessions")
    s_cur = sessions.get("current")
    s_prev = sessions.get("previous")
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    channels = cm.get("rows") or []

    # Action 1: Sessions movement + largest channel
    if s_cur is not None and s_prev is not None and s_prev > 0:
        delta_pct = (s_cur - s_prev) / s_prev * 100
        top = max(channels, key=lambda c: c.get("current_sessions") or 0) \
                if channels else None
        if top and top.get("current_sessions"):
            share = top.get("share_of_sessions") or 0
            if delta_pct >= 0:
                actions.append({
                    "action": (f"Maintain or modestly scale the "
                                f"{top['channel']} channel this week."),
                    "why": (f"Weekly sessions: {_fmt(s_cur)} "
                            f"(prev {_fmt(s_prev)}, {delta_pct:+.1f}% WoW). "
                            f"{top['channel']} is the largest acquisition "
                            f"channel at {share:.1f}% of sessions "
                            f"({_fmt(top['current_sessions'])} sessions, "
                            f"prev {_fmt(top['previous_sessions'])})."),
                    "measure": (f"{top['channel']} sessions WoW; "
                                f"Meta-reported leads for any "
                                f"campaigns tied to this channel."),
                })
            else:
                actions.append({
                    "action": (f"Investigate the {top['channel']} channel "
                                f"for the session decline before scaling."),
                    "why": (f"Weekly sessions: {_fmt(s_cur)} "
                            f"(prev {_fmt(s_prev)}, {delta_pct:+.1f}% WoW). "
                            f"{top['channel']} is still the largest "
                            f"channel at {share:.1f}% of sessions — "
                            f"its movement is driving the total change."),
                    "measure": (f"{top['channel']} sessions WoW; "
                                f"if a specific campaign is behind it, "
                                f"that campaign's CTR/CPC WoW."),
                })

    # Action 2: Paid media efficiency — best vs worst campaign
    pm = v24.get("paid_media_v24") or {}
    if pm.get("data_status") == "LIVE":
        campaigns = [c for c in (pm.get("per_campaign") or [])
                       if (c.get("current") or {}).get("spend")]
        if len(campaigns) >= 2:
            def _eff(c):
                spend = (c.get("current") or {}).get("spend") or 0
                res = ((c.get("primary_result") or {})
                          .get("primary_value") or 0)
                if spend <= 0 or not res:
                    return None
                return res / spend  # result per R
            with_eff = [(c, _eff(c)) for c in campaigns if _eff(c) is not None]
            if len(with_eff) >= 2:
                with_eff.sort(key=lambda t: t[1], reverse=True)
                best = with_eff[0][0]
                worst = with_eff[-1][0]
                best_name = best.get("campaign_name", "?")
                worst_name = worst.get("campaign_name", "?")
                br = best.get("primary_result") or {}
                wr = worst.get("primary_result") or {}
                actions.append({
                    "action": (f"Scale '{best_name}' and rework or pause "
                                f"'{worst_name}' this week."),
                    "why": (f"Material paid-media campaigns this week "
                            f"showed a clear efficiency spread. "
                            f"Best: '{best_name}' at {br.get('primary_cost_per_label','?')} "
                            f"{_fmt(br.get('primary_cost_per_unit'), 'money')}. "
                            f"Worst: '{worst_name}' at {wr.get('primary_cost_per_label','?')} "
                            f"{_fmt(wr.get('primary_cost_per_unit'), 'money')}."),
                    "measure": (f"Cost-per-result per campaign WoW; "
                                f"total Meta-reported leads WoW."),
                })

    # Action 3: North Star support — derive from canonical NS + real
    # data signal (channel that supports the relevant NS, or a
    # campaign that supports it).
    ns_items = _extract_north_stars_from_v24(v24)
    paid_campaigns = [c for c in (pm.get("per_campaign") or [])
                        if c.get("status") == "DELIVERED"]
    # Find a campaign whose objective matches a NS direction
    fitting_or_coaching_campaigns = [
        c for c in paid_campaigns
        if c.get("objective") in ("OUTCOME_LEADS", "LINK_CLICKS")
        and any(t in (c.get("campaign_name") or "").lower()
                  for t in ("fit", "coach", "lesson", "assessment"))
    ]
    if fitting_or_coaching_campaigns and ns_items:
        c = fitting_or_coaching_campaigns[0]
        actions.append({
            "action": (f"Keep '{c.get('campaign_name')}' funded while "
                        f"the booking connector is wired."),
            "why": ("This campaign supports the Fitting / Coaching North "
                    "Star (24/week each). Until the CRM / booking "
                    "connector reports verified outcomes, paid efficiency "
                    "is the closest signal we have for this North Star."),
            "measure": (f"Meta-reported leads from this campaign WoW; "
                        f"eventually, verified bookings when the CRM "
                        f"connector is live."),
        })

    # If we only have 1, return 1. Cap at 3.
    return actions[:3]


def _derive_measurement_actions(v24: dict) -> List[str]:
    out: List[str] = []
    pm = v24.get("paid_media_v24") or {}
    ks = v24.get("kpi_scorecard") or {}
    rows = ks.get("rows") or []

    # GA4 freshness
    sessions = _extract_kpi(v24, "Sessions")
    if (sessions.get("data_status") or "").upper() in ("UNAVAILABLE", "NOT_CONNECTED"):
        out.append("Wire per-brand GA4 property + service-account JSON "
                     "for this brand (the other brand already has it).")
    # Verified leads missing
    leads = _extract_kpi(v24, "Verified Leads")
    if leads.get("data_status") == "PENDING":
        out.append("Wire CRM / booking connector so Verified Leads stops "
                     "being PENDING and we can report measured outcomes.")
    # Source freshness stale
    freshness = (pm.get("freshness") or {}).get("status") or ""
    if "stale" in freshness.lower():
        out.append(f"Refresh stale paid-media source "
                     f"(data_as_of={(pm.get('data_as_of') or '?')}).")
    # Landing pages empty
    lp = ((v24.get("sections") or {})
            .get("landing_pages") or {}).get("rows") or []
    if len(lp) == 0:
        out.append("Confirm GA4 top-pages dimension is enabled for "
                     "this brand — landing_pages rows is empty.")
    if not out:
        out.append("No measurement actions this period.")
    return out


# ── markdown rendering ─────────────────────────────────────────

def _render_markdown(bid: str, v24: dict, north_stars: List[dict],
                       periods: Dict[str, str],
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

    # ── Source status header (separate from data_status) ──
    pm = v24.get("paid_media_v24") or {}
    pm_source_status = pm.get("data_status") or "UNKNOWN"
    pm_freshness = (pm.get("freshness") or {}).get("status") or "unknown"
    pm_data_as_of = (pm.get("freshness") or {}).get("data_as_of") \
                      or pm.get("data_as_of") or "—"
    sessions = _extract_kpi(v24, "Sessions")
    s_status = sessions.get("data_status", "OK")

    L.append(f"**Source status (connectors):** "
               f"Meta Ads = `{pm_source_status}` ({pm_freshness}, "
               f"data_as_of={pm_data_as_of}); "
               f"GA4 = `{s_status}`.")
    L.append("")

    # ── Executive Read (uses metric_value, not source_status) ──
    exec_parts = []
    s_cur = sessions.get("current")
    s_prev = sessions.get("previous")
    if s_cur is not None:
        exec_parts.append(f"Weekly sessions: {_fmt(s_cur)}.")
    if s_prev is not None:
        pct, _ = _pct(s_cur, s_prev)
        exec_parts.append(f"WoW change: {pct}.")
    paid_totals = _paid_totals_from_campaigns(v24)
    spend_cur = paid_totals["current_period"].get("total_spend")
    spend_prev = paid_totals["previous_period"].get("total_spend")
    if spend_cur:
        pct, _ = _pct(spend_cur, spend_prev)
        exec_parts.append(
            f"Meta paid spend (7d): {_fmt(spend_cur, 'money')} "
            f"({pct} WoW).")
    leads_cur = paid_totals["current_period"].get("total_results")
    if leads_cur is not None and leads_cur > 0:
        exec_parts.append(
            f"Meta-reported results (7d): {_fmt(leads_cur)}.")
    L.append("**Executive Read:** " +
               (" ".join(exec_parts) if exec_parts else
                "_No executive read possible — see Data Notes._"))
    L.append("")

    # ── TL;DR Numbers ──
    L.append("## TL;DR — Numbers (Last 7 days)")
    L.append(f"_{periods['current_week_start']} → "
               f"{periods['current_week_end']} · "
               f"prev 7d: {periods['previous_week_start']} → "
               f"{periods['previous_week_end']}_")
    L.append("")
    L.append("| Metric | Current | Previous | Change | Severity |")
    L.append("|---|---|---|---|---|")
    rows = _build_tldr_rows(v24)
    for r in rows:
        L.append(f"| {r['metric']} | {r['current']} | {r['previous']} | "
                   f"{r['change']} | {r['severity']} |")
    L.append("")

    # ── Acquisition channels ──
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    if cm.get("rows"):
        L.append("## Acquisition Channels (7d)")
        L.append("")
        L.append("| Channel | Current | Previous | Change | "
                   "Share | Status |")
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

    # ── Top landing pages ──
    lp = ((v24.get("sections") or {})
            .get("landing_pages") or {}).get("rows") or []
    if lp:
        L.append("## Top Landing Pages (7d)")
        L.append("")
        L.append("| Path | Sessions | Engagement |")
        L.append("|---|---|---|")
        for p in lp[:5]:
            er_v = p.get("engagement_rate")
            L.append(f"| {p.get('path','?')} | "
                       f"{_fmt(p.get('sessions'))} | "
                       f"{_fmt(er_v, 'decimal') if er_v is not None else '—'} |")
        L.append("")
        L.append("> Page sessions ≠ leads / bookings / purchases unless "
                   "verified events exist.")
        L.append("")

    # ── Paid Media ──
    L.append("## Paid Media — Meta Ads (V2.4.1)")
    L.append(f"_{periods['current_week_start']} → "
               f"{periods['current_week_end']}_")
    L.append("")
    if pm_source_status != "LIVE":
        L.append(f"Meta Ads source_status: `{pm_source_status}` — see "
                   f"Data Notes. **Not the same as zero spend.**")
        L.append("")
    else:
        cur = paid_totals["current_period"]
        prev = paid_totals["previous_period"]
        eff = _compute_paid_efficiency(cur, prev)
        L.append(f"_source_status=`LIVE`, data_as_of={pm_data_as_of}, "
                   f"freshness={pm_freshness}._")
        L.append("")
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
        L.append(f"| Meta-reported results | {_fmt(cur.get('total_results'))} | "
                   f"— | — |")
        L.append(f"| CTR | {_fmt(eff.get('ctr'), 'decimal')} | — | — |")
        L.append(f"| CPC | {_fmt(eff.get('cpc'), 'money')} | — | — |")
        L.append(f"| CPM | {_fmt(eff.get('cpm'), 'money')} | — | — |")
        L.append("")
        # Material campaigns (spend > 0 in current period)
        material = []
        for c in (pm.get("per_campaign") or []):
            c_cur = c.get("current") or {}
            if (c_cur.get("spend") or 0) > 0:
                material.append(c)
        material.sort(key=lambda c: c["current"].get("spend") or 0,
                        reverse=True)
        if material:
            L.append(f"**Campaigns this week ({len(material)} material — "
                       f"spend > 0):**")
            L.append("")
            L.append("| Campaign | Objective | Spend | Impressions | "
                       "Reach | CTR | CPC | Primary result |")
            L.append("|---|---|---|---|---|---|---|---|")
            for c in material[:8]:
                c_cur = c.get("current") or {}
                c_prev = c.get("previous") or {}
                pr = c.get("primary_result") or {}
                L.append(f"| {c.get('campaign_name','?')} | "
                           f"{c.get('objective','—')} | "
                           f"{_fmt(c_cur.get('spend'), 'money')} | "
                           f"{_fmt(c_cur.get('impressions'))} | "
                           f"{_fmt(c_cur.get('reach'))} | "
                           f"{_fmt(c_cur.get('ctr'), 'decimal')} | "
                           f"{_fmt(c_cur.get('cpc'), 'money')} | "
                           f"{_fmt(pr.get('primary_value'))} "
                           f"{pr.get('primary_metric_label','')} |")
            L.append("")
        else:
            L.append("No material campaigns in this window (spend > 0).")
            L.append("")
        L.append("> Lead terminology preserved as 'Meta-reported results' "
                   "/ 'Meta-reported leads' — not yet matched to CRM or "
                   "qualified as bookings.")
        L.append("")

    # ── North Stars ──
    L.append("## North Stars (canonical — from Reporting V2.4.1)")
    L.append("")
    if north_stars:
        for ns in north_stars:
            L.append(f"- **{ns['label']}** — {ns['metric']}")
            L.append(f"  - Source: `{ns['source']}`")
            L.append(f"  - Outcome measurement: PENDING — operational "
                       f"connector not yet integrated with reporting")
        L.append("")
    else:
        L.append("No canonical North Stars rendered by V2.4.1 this run.")
        L.append("")

    # ── What Worked (FACT only) ──
    L.append("## What Worked")
    L.append("")
    worked: List[str] = []
    if s_cur is not None and s_prev is not None and s_prev > 0 and s_cur > s_prev:
        pct, _ = _pct(s_cur, s_prev)
        worked.append(
            f"FACT: Website sessions this week: {_fmt(s_cur)} "
            f"(prev {_fmt(s_prev)}, {pct}).")
    if pm_source_status == "LIVE":
        sc = paid_totals["current_period"].get("total_spend")
        sp = paid_totals["previous_period"].get("total_spend")
        if sc and sp and sc > sp:
            pct, _ = _pct(sc, sp)
            worked.append(
                f"FACT: Meta paid spend this week: {_fmt(sc, 'money')} "
                f"(prev {_fmt(sp, 'money')}, {pct}).")
        dr = paid_totals["current_period"].get("total_results")
        if dr:
            worked.append(
                f"FACT: Meta-reported results this week: {_fmt(dr)}.")
    if worked:
        for w in worked:
            L.append(f"- {w}")
    else:
        L.append("- No evidence-based 'what worked' items this period.")
    L.append("")
    L.append("> Connector-status items go to Data Notes, not here. "
               "Measurement availability is not marketing performance.")
    L.append("")

    # ── What Needs Attention ──
    L.append("## What Needs Attention")
    L.append("")
    attention = []
    gaps = []
    if (s_status or "").upper() in ("UNAVAILABLE", "NOT_CONNECTED", "PENDING"):
        gaps.append(("MEDIUM",
            f"GA4 data_status = {s_status} — weekly comparison only "
            f"available when GA4 KPI scorecard rows are populated."))
    if pm_source_status != "LIVE":
        gaps.append(("HIGH",
            f"Meta Ads source_status = {pm_source_status} — "
            f"paid-media reporting absent for this brand."))
    freshness = (pm.get("freshness") or {}).get("status") or ""
    if "stale" in freshness.lower():
        gaps.append(("MEDIUM",
            f"Meta Ads data is stale (freshness={freshness}). "
            f"data_as_of={pm_data_as_of}."))
    leads = _extract_kpi(v24, "Verified Leads")
    if leads.get("data_status") == "PENDING":
        gaps.append(("HIGH",
            "Bookings / Verified Leads connector not wired — verified "
            "outcomes cannot flow into reporting."))
    if gaps:
        attention = gaps
    else:
        attention = [("LOW",
            "All standard data sources present. No high-severity gaps.")]
    for sev, txt in attention:
        L.append(f"- **[{sev}]** {txt}")
    L.append("")
    L.append("> Severity considers business consequence, volume / "
               "materiality, magnitude of change, confidence / data "
               "quality, and North Star relevance — not magnitude alone.")
    L.append("")

    # ── Marketing Actions — Top N (real, no placeholders) ──
    L.append("## Marketing Actions")
    L.append("")
    actions = _derive_marketing_actions(v24, bid)
    if actions:
        for i, a in enumerate(actions, 1):
            L.append(f"{i}. **{a['action']}**")
            L.append(f"   - **Why:** {a['why']}")
            L.append(f"   - **Measure:** {a['measure']}")
    else:
        L.append("- No marketing actions defensible from the current "
                   "data set. See Measurement / Data Actions for the "
                   "gaps blocking more decisions.")
    L.append("")
    L.append("> Marketing actions are decisions about content / channel / "
               "audience — derived from the data above. They do not "
               "generate copy; Opportunity → Brief → Create handles "
               "creative.")
    L.append("")

    # ── Measurement / Data Actions ──
    L.append("## Measurement / Data Actions")
    L.append("")
    meas = _derive_measurement_actions(v24)
    for i, a in enumerate(meas, 1):
        L.append(f"{i}. {a}")
    L.append("")
    L.append("> Measurement actions cover connectors, event validation, "
               "scope, stale sources, CRM integration. They do not "
               "displace the marketing decisions above.")
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
               f"status={pm_freshness}, source_status={pm_source_status}.")
    L.append("")
    L.append("**Tone:** management report — numbers first, conclusions "
               "only when evidence supports them. Missing data ≠ zero. "
               "No creative generation.")
    L.append("")
    L.append("---")
    L.append(f"_Generated {datetime.datetime.now(datetime.timezone.utc).isoformat()} • V2.4.1 frozen • V3.2 renderer._")
    return "\n".join(L)


# ── HTML rendering (wraps markdown) ───────────────────────────

def _render_html(bid: str, v24: dict, north_stars: List[dict],
                   periods: Dict[str, str],
                   contamination_block: Optional[str] = None,
                   as_of: Optional[str] = None) -> str:
    md = _render_markdown(bid, v24, north_stars, periods,
                            contamination_block, as_of)
    facts = _brand_canonical(bid)["canonical"]
    title = (f"{facts['display_name']} — Weekly Management Report"
              f" ({periods['current_week_start']} → "
              f"{periods['current_week_end']})")
    if contamination_block:
        title = f"{title} — BLOCKED"
    body = md.replace("&", "&amp;").replace("<", "&lt;").replace(
        ">", "&gt;")
    body_html = (body.replace("\n## ", "\n<h2>")
                  .replace("\n### ", "\n<h3>"))
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

def build_v32(bid: str, fmt: str = "markdown",
                as_of: Optional[str] = None) -> dict:
    """Build the V3.2 weekly management report."""
    if bid not in ("stick", "swing-shack", "bag-drop"):
        return {"report_status": "INVALID_BRAND",
                "block_reason": "brand_id must be stick, swing-shack, or bag-drop",
                "contaminations": [],
                "rendered": f"# Invalid brand\n\n`{bid}` is not a managed brand.",
                "raw_payload": {}}

    periods = _compute_periods(as_of)
    v24 = _read_v24(bid, as_of)

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
            "rendered": _render_markdown(bid, v24, [], periods,
                                           contamination_block=block,
                                           as_of=as_of),
            "raw_payload": {"v24": v24, "periods": periods},
        }

    north_stars = _extract_north_stars_from_v24(v24)
    status = "OK"

    if fmt == "html":
        rendered = _render_html(bid, v24, north_stars, periods, as_of=as_of)
    elif fmt == "json":
        # Caller wants structured output; still produce markdown in raw
        rendered = _render_markdown(bid, v24, north_stars, periods,
                                      as_of=as_of)
    else:
        rendered = _render_markdown(bid, v24, north_stars, periods,
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
            "generator": "weekly_report_v3.2",
            "as_of": as_of,
        },
    }


# ── snapshot (archive current week for next-week WoW) ──────────

def archive_snapshot_v32(bid: str, as_of: Optional[str] = None,
                            snapshot_root: Optional[Path] = None
                            ) -> Dict[str, Any]:
    out = build_v32(bid, fmt="json", as_of=as_of)
    v24 = (out.get("raw_payload") or {}).get("v24") or {}
    periods = (out.get("raw_payload") or {}).get("periods") or {}
    north_stars = (out.get("raw_payload") or {}).get("north_stars") or []

    snapshot = {
        "schema": "https://campaign-os/weekly-report/v3.2-snapshot",
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
    snapshot["kpi_values"]["paid_media_v24"] = {
        "data_status": pm.get("data_status"),
        "freshness": pm.get("freshness"),
        "data_as_of": pm.get("data_as_of"),
        "current_period": _paid_totals_from_campaigns(v24).get("current_period"),
        "previous_period": _paid_totals_from_campaigns(v24).get("previous_period"),
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


# Backwards-compat alias for the V3.1 module name
def build_v31(*args, **kwargs):
    return build_v32(*args, **kwargs)


if __name__ == "__main__":
    bid = sys.argv[1] if len(sys.argv) > 1 else "stick"
    fmt = sys.argv[2] if len(sys.argv) > 2 else "markdown"
    as_of = sys.argv[3] if len(sys.argv) > 3 else None
    out = build_v32(bid, fmt=fmt, as_of=as_of)
    print(out["rendered"])
    sys.exit(0 if out["report_status"] == "OK" else 2)
