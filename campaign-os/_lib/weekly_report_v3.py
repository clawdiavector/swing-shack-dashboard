"""weekly_report_v3.py — Weekly Marketing Report V3.4.

Renderer-only. Sits on top of Reporting Intelligence V2.4.1
(frozen). Reads canonical V2.4.1 data via build_v24_brand_report().

V3.4 change: language. The numbers come from the same V2.4.1
pipeline as V3.3. The structure is reorganised for Herman:

  # <Brand> Weekly Marketing Report
  <date range>

  ## This week at a glance            — headline numbers + plain summary
  ## Website traffic                  — sessions, users, engagement
  ## Where visitors came from         — acquisition channels
  ## Advertising                      — Meta spend + campaigns grouped by purpose
  ## Website pages                    — top landing pages
  ## Social media                     — Instagram + Facebook reach / interactions
  ## Best content                     — top 3–5 IG/FB pieces with one observation
  ## What worked                      — real positive results, no spend increases
  ## What needs attention             — real performance issues
  ## What we should do this week      — up to 3 actions, plain English
  ## Business targets                 — North Stars + honest data status
  ## Data still missing               — connector gaps, technical limitations

Words banned from the management report (operator's V3.4 directive):
  delta, materiality, objective-aware, period contract,
  primary result, source status, query, attribution, cadence,
  connector (in body — OK in "Data still missing"), downstream,
  baseline signal, contracted delivery, rose movement,
  channel-level delta, source_status, data_status, query_level,
  period_adapted, freshness, comparator, etc.

Technical logs may keep technical terminology. The management
report does not.
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
    return {
        "data_complete_through": cur_end.isoformat(),
        "current_week_start": cur_start.isoformat(),
        "current_week_end": cur_end.isoformat(),
        "previous_week_start": prev_start.isoformat(),
        "previous_week_end": prev_end.isoformat(),
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


# ── V2.4.1 extractors ──────────────────────────────────────────

def _extract_kpi(v24: dict, label: str) -> Dict[str, Any]:
    for row in (v24.get("kpi_scorecard") or {}).get("rows") or []:
        if row.get("label", "").lower() == label.lower():
            return row
    return {}


def _paid_totals_from_campaigns(v24: dict) -> Dict[str, Any]:
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


# ── North Stars from V2.4.1 ─────────────────────────────────────

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


# ── objective → plain-English grouping ──────────────────────────

_OBJECTIVE_GROUP = {
    "OUTCOME_AWARENESS": ("Awareness campaigns",
                            "people reached", "people", "cost per 1,000 reached"),
    "OUTCOME_TRAFFIC": ("Website traffic campaigns",
                          "website visits", "visits", "cost per website visit"),
    "LINK_CLICKS": ("Website traffic campaigns",
                      "website visits", "visits", "cost per website visit"),
    "OUTCOME_ENGAGEMENT": ("Engagement campaigns",
                              "engagements", "engagements", "cost per engagement"),
    "OUTCOME_LEADS": ("Lead campaigns",
                       "leads", "leads", "cost per lead"),
    "OUTCOME_SALES": ("Sales campaigns",
                        "purchases", "purchases", "cost per purchase"),
    "OUTCOME_APP": ("App campaigns",
                      "app events", "events", "cost per app event"),
}


def _objective_group_label(obj: str) -> Tuple[str, str, str, str]:
    """Return (group_title, primary_metric_noun, primary_metric_unit,
    cost_label) — operator-facing English, not technical."""
    return _OBJECTIVE_GROUP.get(obj, ("Other campaigns", "results", "results",
                                       "cost per result"))


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
        return f"R{n:,.2f}"
    if kind == "money_round":
        return f"R{n:,.0f}"
    if kind == "pct":
        return f"{n:.2f}%"
    if kind == "decimal":
        return f"{n:,.2f}"
    if kind == "money_per":
        # e.g. R3.01
        if n >= 100:
            return f"R{n:,.0f}"
        return f"R{n:,.2f}"
    return f"{int(round(n)):,}"


def _change(curr, prev) -> Tuple[str, str]:
    """Plain-English movement description: up/down/flat/neutral."""
    if curr is None or prev is None:
        return ("same as baseline", "neutral")
    try:
        c = float(curr); p = float(prev)
    except (ValueError, TypeError):
        return ("same as baseline", "neutral")
    if p == 0:
        if c == 0:
            return ("no change", "neutral")
        return ("no comparison available", "baseline")
    if c > p:
        return ("up", "up")
    if c < p:
        return ("down", "down")
    return ("flat", "neutral")


def _change_word(curr, prev) -> str:
    """up / down / flat / no change."""
    word, _ = _change(curr, prev)
    return word


def _pct_word(curr, prev) -> str:
    """Plain-English +/- percentage phrase."""
    if curr is None or prev is None:
        return ""
    try:
        c = float(curr); p = float(prev)
    except (ValueError, TypeError):
        return ""
    if p == 0:
        return ""
    pct = (c - p) / p * 100
    if pct > 0:
        return f"up {pct:.1f}%"
    if pct < 0:
        return f"down {abs(pct):.1f}%"
    return "no change"


# ── reading organic cache (IG + FB) ─────────────────────────────

def _read_organic_from_cache(bid: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ig": None, "fb": None}
    ig_data = {}
    ig_brand_map = {
        "swingshack": "swing-shack",
        "stickgolf": "stick",
    }
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
                    username = ((raw.get("account") or {})
                                  .get("username") or "")
                    detected = ig_brand_map.get(
                        username.lower().replace("@", ""))
                    if detected and detected != bid:
                        continue
                    ig_data = raw
                except Exception:
                    continue
                if ig_data:
                    break
        if ig_data:
            break
    if ig_data:
        wt = ig_data.get("window_totals") or {}
        out["ig"] = {
            "status": "LIVE" if wt else "PARTIAL",
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
                    "caption": (p.get("caption_preview")
                                  or p.get("caption") or "").strip(),
                    "interactions": ((p.get("metrics") or {})
                                          .get("total_interactions")),
                    "reach": ((p.get("metrics") or {})
                                  .get("reach")),
                    "timestamp": p.get("timestamp"),
                }
                for p in (ig_data.get("media") or [])[:10]
            ],
        }
    fb_data = {}
    for r in (
        _data_root(),
        Path("/Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard/data"),
    ):
        p = r / "fb-page-analytics.json"
        if p.is_file():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                fb_data = raw
            except Exception:
                continue
            if fb_data:
                break
    if fb_data:
        wt = fb_data.get("window_totals") or {}
        page = fb_data.get("page") or {}
        out["fb"] = {
            "status": "LIVE" if wt else "PARTIAL",
            "page_name": page.get("name"),
            "fans": page.get("fan_count"),
            "impressions": wt.get("page_impressions"),
            "engagements": wt.get("page_post_engagements"),
            "clicks": wt.get("page_consumptions") or wt.get("clicks"),
            "top_posts": [
                {
                    "id": p.get("id"),
                    "media_type": p.get("type") or p.get("media_type"),
                    "caption": (p.get("message")
                                  or p.get("message_preview") or "").strip(),
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


# ── executive read ─────────────────────────────────────────────

def _build_executive_read(bid: str, v24: dict, organic: Dict[str, Any],
                            periods: Dict[str, str]) -> str:
    s = _extract_kpi(v24, "Sessions")
    s_cur = s.get("current")
    s_prev = s.get("previous")
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    chans = cm.get("rows") or []
    movers = []
    for c in chans:
        cur_v = c.get("current_sessions")
        prev_v = c.get("previous_sessions")
        if cur_v is not None and prev_v is not None:
            movers.append((c.get("channel"), cur_v - prev_v))
    movers.sort(key=lambda t: abs(t[1]), reverse=True)

    paid_totals = _paid_totals_from_campaigns(v24)
    cur = paid_totals["current_period"]
    prev = paid_totals["previous_period"]

    parts: List[str] = []
    if s_cur is not None and s_prev is not None and s_prev > 0:
        pct = (s_cur - s_prev) / s_prev * 100
        if abs(s_cur - s_prev) >= 10:
            if pct > 0:
                parts.append(
                    f"Website traffic increased by {abs(s_cur - s_prev)} sessions "
                    f"({pct:.1f}% more) compared with last week.")
            elif pct < 0:
                parts.append(
                    f"Website traffic fell by {abs(s_cur - s_prev)} sessions "
                    f"({abs(pct):.1f}% less) compared with last week.")
            else:
                parts.append(
                    f"Website traffic was the same as last week "
                    f"({_fmt(s_cur)} sessions).")
        else:
            parts.append(
                f"Website traffic stayed about the same as last week "
                f"({_fmt(s_cur)} vs {_fmt(s_prev)}).")
    if movers:
        biggest = movers[0]
        if abs(biggest[1]) >= 5:
            sign_word = "more" if biggest[1] > 0 else "fewer"
            sign_n = abs(biggest[1])
            parts.append(
                f"The {biggest[0]} channel brought {sign_n} {sign_word} "
                f"sessions than last week.")
    if (cur.get("total_impressions", 0) > 0
            and prev.get("total_impressions", 0) > 0):
        imp_pct = ((cur["total_impressions"] - prev["total_impressions"])
                     / prev["total_impressions"] * 100)
        if abs(imp_pct) >= 10:
            if imp_pct > 0:
                parts.append(
                    f"Meta ads reached {abs(imp_pct):.1f}% more people this week "
                    f"than last week.")
            else:
                parts.append(
                    f"Meta ads reached {abs(imp_pct):.1f}% fewer people this week "
                    f"than last week — paid delivery should be watched.")
    leads = _extract_kpi(v24, "Verified Leads")
    if leads.get("data_status") == "PENDING":
        parts.append("We still cannot tell how many Meta leads turned into real "
                       "bookings.", )
    if not parts:
        return ("Not enough data yet to summarise the week. Check Data still "
                "missing below.")
    return " ".join(parts[:4])


# ── "this week at a glance" headline ────────────────────────────

def _build_headline(bid: str, v24: dict, organic: Dict[str, Any]) -> List[str]:
    """A handful of headline numbers in plain English."""
    s = _extract_kpi(v24, "Sessions")
    s_cur = s.get("current")
    s_prev = s.get("previous")
    paid_totals = _paid_totals_from_campaigns(v24)
    cur = paid_totals["current_period"]
    prev = paid_totals["previous_period"]
    leads_cur = paid_totals["current_period"].get("total_results")
    lines: List[str] = []
    # Website sessions
    if s_cur is not None:
        if s_prev is not None and s_prev > 0 and (s_cur - s_prev) >= 5:
            pct = (s_cur - s_prev) / s_prev * 100
            direction = "up" if pct > 0 else "down"
            lines.append(
                f"Website sessions: {_fmt(s_cur)} ({direction} "
                f"{abs(pct):.1f}% compared with last week)")
        else:
            lines.append(f"Website sessions: {_fmt(s_cur)} this week")
    # Top channel
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    chans = cm.get("rows") or []
    paid_social = next((c for c in chans
                          if c.get("channel") == "Paid Social"), None)
    organic_search = next((c for c in chans
                            if c.get("channel") == "Organic Search"), None)
    if paid_social and paid_social.get("current_sessions") is not None:
        ps_cur = paid_social["current_sessions"]
        ps_prev = paid_social.get("previous_sessions")
        pct = _pct_word(ps_cur, ps_prev)
        if pct:
            lines.append(
                f"Paid Social: {_fmt(ps_cur)} sessions ({pct} compared with "
                f"last week)")
        else:
            lines.append(
                f"Paid Social: {_fmt(ps_cur)} sessions this week")
    if organic_search and organic_search.get("current_sessions") is not None:
        os_cur = organic_search["current_sessions"]
        os_prev = organic_search.get("previous_sessions")
        pct = _pct_word(os_cur, os_prev)
        if pct:
            lines.append(
                f"Organic Search (Google): {_fmt(os_cur)} sessions "
                f"({pct} compared with last week)")
        else:
            lines.append(
                f"Organic Search (Google): {_fmt(os_cur)} sessions this week")
    if cur.get("total_spend", 0) > 0:
        spend_cur = cur["total_spend"]
        spend_prev = prev.get("total_spend")
        pct = _pct_word(spend_cur, spend_prev)
        if pct:
            lines.append(
                f"Meta ad spend: {_fmt(spend_cur, 'money')} ({pct} compared "
                f"with last week)")
        else:
            lines.append(
                f"Meta ad spend: {_fmt(spend_cur, 'money')} this week")
    if leads_cur is not None:
        lines.append(f"Meta leads: {_fmt(leads_cur)} this week")
    return lines


# ── website traffic section ────────────────────────────────────

def _build_website_traffic(v24: dict) -> List[str]:
    L: List[str] = []
    L.append("## Website traffic")
    L.append("")
    s = _extract_kpi(v24, "Sessions")
    u = _extract_kpi(v24, "Users")
    e = _extract_kpi(v24, "Engaged sessions")
    er = _extract_kpi(v24, "Engagement rate")
    pv = _extract_kpi(v24, "Pageviews")
    bullets: List[str] = []
    for label, kpi in (("Sessions", s), ("Users", u),
                         ("Engaged sessions", e),
                         ("Engagement rate", er),
                         ("Pageviews", pv)):
        cur_v = kpi.get("current")
        prev_v = kpi.get("previous")
        if cur_v is None:
            continue
        kind = "decimal" if label == "Engagement rate" else "int"
        line = f"- **{label}:** {_fmt(cur_v, kind)} this week"
        pct = _pct_word(cur_v, prev_v)
        if pct:
            line += f" ({pct} compared with last week, "
            line += f"was {_fmt(prev_v, kind)})"
        bullets.append(line)
    if not bullets:
        L.append("Website traffic numbers not available this week.")
        L.append("")
        return L
    L.extend(bullets)
    L.append("")
    return L


# ── where visitors came from ───────────────────────────────────

def _build_acquisition(v24: dict) -> List[str]:
    L: List[str] = []
    L.append("## Where visitors came from")
    L.append("")
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    chans = cm.get("rows") or []
    if not chans:
        L.append("No visitor-source data this week.")
        L.append("")
        return L
    chans_sorted = sorted(chans, key=lambda c: c.get("current_sessions") or 0,
                            reverse=True)
    for c in chans_sorted:
        cur_v = c.get("current_sessions")
        prev_v = c.get("previous_sessions")
        share = c.get("share_of_sessions") or 0
        if cur_v is None:
            continue
        line = f"- **{c.get('channel','?')}:** {_fmt(cur_v)} sessions this week"
        pct = _pct_word(cur_v, prev_v)
        if pct:
            line += f" ({pct} compared with last week, was {_fmt(prev_v)})"
        line += f" — {share:.1f}% of all sessions"
        L.append(line)
    L.append("")
    return L


# ── advertising section ────────────────────────────────────────

def _build_advertising(v24: dict) -> List[str]:
    L: List[str] = []
    L.append("## Advertising")
    L.append("")
    pm = v24.get("paid_media_v24") or {}
    if (pm.get("data_status") or "").upper() != "LIVE":
        L.append("Advertising is not connected for this brand.")
        L.append("")
        return L
    paid_totals = _paid_totals_from_campaigns(v24)
    cur = paid_totals["current_period"]
    prev = paid_totals["previous_period"]
    eff = _compute_paid_efficiency(cur, prev)
    # Top totals in plain English
    L.append("**This week on Meta ads:**")
    L.append("")
    L.append(f"- Total spend: {_fmt(cur.get('total_spend'), 'money')} "
               f"({_pct_word(cur.get('total_spend'), prev.get('total_spend'))} "
               f"compared with last week)")
    L.append(f"- People reached: {_fmt(cur.get('total_reach'))} "
               f"({_pct_word(cur.get('total_reach'), prev.get('total_reach'))} "
               f"compared with last week)")
    L.append(f"- Total clicks on ads: {_fmt(cur.get('total_clicks'))} "
               f"({_pct_word(cur.get('total_clicks'), prev.get('total_clicks'))} "
               f"compared with last week)")
    if cur.get("total_impressions", 0) > 0:
        ctr = (cur.get("total_clicks") or 0) / cur["total_impressions"] * 100
        L.append(f"- Average click-through rate: {ctr:.2f}% "
                   f"(people who clicked the ad after seeing it)")
    if cur.get("total_clicks", 0) > 0:
        cpc = (cur.get("total_spend") or 0) / cur["total_clicks"]
        L.append(f"- Average cost per click: R{cpc:,.2f}")
    L.append(f"- Meta leads (from lead campaigns): "
               f"{_fmt(cur.get('total_results'))}")
    L.append("")
    # Group campaigns by objective → plain-English label
    by_obj: Dict[str, List[dict]] = {}
    for c in (pm.get("per_campaign") or []):
        if (c.get("current") or {}).get("spend", 0) > 0:
            obj = c.get("objective") or "OUTCOME_OTHER"
            by_obj.setdefault(obj, []).append(c)
    if by_obj:
        L.append("**Campaigns running this week, grouped by what they try to do:**")
        L.append("")
        for obj in sorted(by_obj.keys()):
            group_title, pm_noun, pm_unit, cost_label = _objective_group_label(obj)
            cs = sorted(by_obj[obj],
                          key=lambda c: (c.get("current") or {}).get("spend", 0),
                          reverse=True)
            L.append(f"### {group_title}")
            L.append("")
            for c in cs:
                cur_c = c.get("current") or {}
                pr = c.get("primary_result") or {}
                spend = cur_c.get("spend") or 0
                # Primary value
                pv = pr.get("primary_value")
                pmu = pr.get("primary_value_unit", "")
                pml = pr.get("primary_metric_label", "")
                # Cost per primary
                cpr = pr.get("primary_cost_per_unit")
                L.append(f"- **{c.get('campaign_name','?')}**")
                L.append(f"  - Spend this week: {_fmt(spend, 'money')}")
                # Primary result line — plain-English by objective
                if obj == "OUTCOME_AWARENESS":
                    L.append(f"  - People reached: {_fmt(pv) if pv is not None else '—'}")
                    if cpr is not None:
                        L.append(f"  - Cost per 1,000 people reached: "
                                   f"{_fmt(cpr, 'money_per')}")
                elif obj in ("OUTCOME_TRAFFIC", "LINK_CLICKS"):
                    L.append(f"  - Website visits from this ad: "
                               f"{_fmt(pv) if pv is not None else '—'}")
                    if cpr is not None:
                        L.append(f"  - Cost per website visit: "
                                   f"{_fmt(cpr, 'money_per')}")
                elif obj == "OUTCOME_ENGAGEMENT":
                    L.append(f"  - Engagements: "
                               f"{_fmt(pv) if pv is not None else '—'}")
                    if cpr is not None:
                        L.append(f"  - Cost per engagement: "
                                   f"{_fmt(cpr, 'money_per')}")
                elif obj == "OUTCOME_LEADS":
                    L.append(f"  - Leads: "
                               f"{_fmt(pv) if pv is not None else '—'}")
                    if cpr is not None:
                        L.append(f"  - Cost per lead: "
                                   f"{_fmt(cpr, 'money_per')}")
                elif obj == "OUTCOME_SALES":
                    L.append(f"  - Purchases: "
                               f"{_fmt(pv) if pv is not None else '—'}")
                    if cpr is not None:
                        L.append(f"  - Cost per purchase: "
                                   f"{_fmt(cpr, 'money_per')}")
                else:
                    label_noun = (pml or "result").replace(
                        "_", " ").replace("landing page views",
                                            "website visits")
                    L.append(f"  - {label_noun}: "
                               f"{_fmt(pv) if pv is not None else '—'}")
                    if cpr is not None:
                        L.append(f"  - Cost per result: "
                                   f"{_fmt(cpr, 'money_per')}")
                # Reach / impressions summary line for context
                if obj != "OUTCOME_AWARENESS":
                    reach = cur_c.get("reach")
                    if reach:
                        L.append(f"  - People reached: {_fmt(reach)}")
                L.append("")
    return L


# ── website pages ──────────────────────────────────────────────

def _build_website_pages(v24: dict) -> List[str]:
    L: List[str] = []
    L.append("## Website pages")
    L.append("")
    lp = ((v24.get("sections") or {})
            .get("landing_pages") or {})
    sp_list = lp.get("service_pages") or []
    # Filter out zero/zero pages unless something notable
    sp_filtered = [sp for sp in sp_list
                     if (sp.get("current_sessions") or 0) > 0]
    if not sp_filtered:
        L.append("No significant website page activity this week.")
        L.append("")
        return L
    sp_filtered = sorted(sp_filtered,
                          key=lambda s: s.get("current_sessions") or 0,
                          reverse=True)[:6]
    L.append("Pages that got visits this week (top 6):")
    L.append("")
    for sp in sp_filtered:
        cur_s = sp.get("current_sessions")
        prev_s = sp.get("previous_sessions")
        eng = sp.get("engagement_rate") or 0
        line = f"- **{sp.get('path','?')}** — {_fmt(cur_s)} sessions"
        pct = _pct_word(cur_s, prev_s)
        if pct:
            line += f" this week ({pct} compared with last week, was {_fmt(prev_s)})"
        line += f". Engagement: {eng:.1f}%"
        L.append(line)
    L.append("")
    return L


# ── social media ───────────────────────────────────────────────

def _build_social_media(bid: str, organic: Dict[str, Any],
                          periods: Dict[str, str]) -> List[str]:
    L: List[str] = []
    L.append("## Social media")
    L.append("")
    ig = organic.get("ig") or {}
    fb = organic.get("fb") or {}
    ig_status = ig.get("status", "NOT_CONNECTED")
    fb_status = fb.get("status", "NOT_CONNECTED")
    if ig_status == "NOT_CONNECTED" and fb_status == "NOT_CONNECTED":
        L.append("Social media reporting is not yet connected for this brand.")
        L.append("")
        return L
    if ig_status != "NOT_CONNECTED":
        L.append("**Instagram (last 28 days):**")
        L.append("")
        if ig.get("interactions") is not None:
            L.append(f"- Total interactions: {_fmt(ig.get('interactions'))}")
        if ig.get("reach") is not None:
            L.append(f"- People reached: {_fmt(ig.get('reach'))}")
        if ig.get("profile_views") is not None:
            L.append(f"- Profile visits: {_fmt(ig.get('profile_views'))}")
        if ig.get("followers") is not None:
            L.append(f"- Followers: {_fmt(ig.get('followers'))}")
        L.append("")
    else:
        L.append("**Instagram:** reporting is not fully set up yet (see Data "
                   "still missing below).")
        L.append("")
    if fb_status != "NOT_CONNECTED":
        L.append("**Facebook page (last 28 days):**")
        L.append("")
        if fb.get("engagements") is not None:
            L.append(f"- Engagements: {_fmt(fb.get('engagements'))}")
        if fb.get("impressions") is not None:
            L.append(f"- Impressions: {_fmt(fb.get('impressions'))}")
        if fb.get("clicks") is not None:
            L.append(f"- Clicks: {_fmt(fb.get('clicks'))}")
        if fb.get("fans") is not None:
            L.append(f"- Page fans: {_fmt(fb.get('fans'))}")
        L.append("")
    else:
        L.append("**Facebook page:** reporting is incomplete (see Data still "
                   "missing below).")
        L.append("")
    return L


# ── best content ───────────────────────────────────────────────

def _build_best_content(bid: str, organic: Dict[str, Any]) -> List[str]:
    L: List[str] = []
    L.append("## Best content")
    L.append("")
    ig_top = (organic.get("ig") or {}).get("top_posts") or []
    fb_top = (organic.get("fb") or {}).get("top_posts") or []
    pieces = sorted(
        [("Instagram", p) for p in ig_top]
        + [("Facebook", p) for p in fb_top],
        key=lambda t: (t[1].get("interactions") or 0),
        reverse=True,
    )[:5]
    if not pieces:
        L.append("No content pieces available for this brand.")
        L.append("")
        return L
    # Convert platform → English
    plat_label = {"Instagram": "Instagram", "Facebook": "Facebook page"}
    for platform, p in pieces:
        media_type = p.get("media_type") or "post"
        type_word = {"VIDEO": "Reel/Video", "IMAGE": "Image",
                       "CAROUSEL_ALBUM": "Carousel",
                       "REEL": "Reel"}.get(media_type, media_type)
        caption_short = (p.get("caption") or "").replace("\n", " ")
        if len(caption_short) > 80:
            caption_short = caption_short[:77] + "..."
        L.append(f"- **{plat_label.get(platform, platform)} — {type_word}:** "
                   f"{caption_short or '(no caption)'}")
        L.append(f"  - People reached: {_fmt(p.get('reach'))}")
        L.append(f"  - Interactions: {_fmt(p.get('interactions'))}")
        L.append("")
    # One short observation
    if len(pieces) >= 2:
        top = pieces[0]
        second = pieces[1]
        top_label = (top[1].get("caption") or "")[:60]
        second_label = (second[1].get("caption") or "")[:60]
        L.append("**Observation:** The post with the most interactions this "
                   f"period was from {top[0]}. "
                   f"{'It had a higher reach than the others.' if top[1].get('reach', 0) > second[1].get('reach', 0) else 'Its reach was similar to the others.'} "
                   "Drawing a strong pattern from one post would be "
                   "premature — keep watching over the next few weeks.")
        L.append("")
    return L


# ── what worked / what needs attention ─────────────────────────

def _build_what_worked(v24: dict, bid: str) -> List[str]:
    """Plain-English positive results. Spend-increases are NOT wins."""
    L: List[str] = []
    L.append("## What worked")
    L.append("")
    items: List[str] = []
    # Sessions up materially
    s = _extract_kpi(v24, "Sessions")
    s_cur = s.get("current")
    s_prev = s.get("previous")
    if (s_cur is not None and s_prev is not None
            and s_prev > 0 and s_cur > s_prev
            and (s_cur - s_prev) >= 10):
        pct = (s_cur - s_prev) / s_prev * 100
        items.append(
            f"Website sessions increased from {_fmt(s_prev)} to "
            f"{_fmt(s_cur)} ({pct:.1f}% more than last week).")
    # Channels that improved
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    for ch in (cm.get("rows") or []):
        cur_v = ch.get("current_sessions")
        prev_v = ch.get("previous_sessions")
        if (cur_v is not None and prev_v is not None
                and cur_v > prev_v
                and (cur_v - prev_v) >= 10
                and ch.get("comparison_status") == "improving"):
            share = ch.get("share_of_sessions") or 0
            items.append(
                f"{ch.get('channel')} brought more visitors this week "
                f"({_fmt(cur_v)} sessions, up from {_fmt(prev_v)}, "
                f"{share:.1f}% of all sessions).")
    # Landing pages with high engagement
    lp = ((v24.get("sections") or {}).get("landing_pages") or {})
    for sp in (lp.get("service_pages") or [])[:3]:
        if sp.get("current_sessions", 0) >= 5 and sp.get("engagement_rate", 0) >= 70:
            items.append(
                f"The page '{sp.get('path')}' had strong engagement "
                f"({sp.get('engagement_rate'):.1f}% of visitors interacted "
                f"with it, from {_fmt(sp.get('current_sessions'))} sessions).")
    # Cost improvements in Meta (CPC down)
    paid_totals = _paid_totals_from_campaigns(v24)
    cur = paid_totals["current_period"]
    prev = paid_totals["previous_period"]
    if (cur.get("total_clicks", 0) > 50
            and prev.get("total_clicks", 0) > 50):
        cur_cpc = ((cur.get("total_spend") or 0)
                     / cur["total_clicks"]) if cur["total_clicks"] else None
        prev_cpc = ((prev.get("total_spend") or 0)
                      / prev["total_clicks"]) if prev["total_clicks"] else None
        if cur_cpc and prev_cpc and cur_cpc < prev_cpc * 0.95:
            items.append(
                f"Cost per click on Meta ads went down: last week was "
                f"R{prev_cpc:,.2f} per click, this week is "
                f"R{cur_cpc:,.2f}.")
    if not items:
        items.append("Nothing stood out clearly as a positive result this week.")
    for it in items:
        L.append(f"- {it}")
    L.append("")
    return L


def _build_what_needs_attention(v24: dict, bid: str) -> List[str]:
    L: List[str] = []
    L.append("## What needs attention")
    L.append("")
    items: List[str] = []
    paid_totals = _paid_totals_from_campaigns(v24)
    cur = paid_totals["current_period"]
    prev = paid_totals["previous_period"]
    s = _extract_kpi(v24, "Sessions")
    # Channel regressions (material only)
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    for ch in (cm.get("rows") or []):
        cur_v = ch.get("current_sessions")
        prev_v = ch.get("previous_sessions")
        share = ch.get("share_of_sessions") or 0
        if (cur_v is not None and prev_v is not None
                and cur_v < prev_v
                and (prev_v - cur_v) >= 10
                and share >= 10):
            items.append(
                f"{ch.get('channel')} sessions fell from {_fmt(prev_v)} to "
                f"{_fmt(cur_v)} last week — worth checking why.")
    # Paid-media impressions / clicks contracted materially
    if (cur.get("total_impressions", 0) > 0
            and prev.get("total_impressions", 0) > 0):
        imp_pct = ((cur["total_impressions"] - prev["total_impressions"])
                     / prev["total_impressions"] * 100)
        clk_pct = ((cur["total_clicks"] - prev["total_clicks"])
                     / max(prev["total_clicks"], 1) * 100)
        if imp_pct <= -15:
            items.append(
                f"Meta ads reached {abs(imp_pct):.1f}% fewer people this week "
                f"({_fmt(prev['total_impressions'])} → "
                f"{_fmt(cur['total_impressions'])} impressions). "
                f"This is a meaningful drop in delivery.")
        if clk_pct <= -20:
            items.append(
                f"Meta ad clicks fell {abs(clk_pct):.1f}% this week "
                f"({_fmt(prev['total_clicks'])} → "
                f"{_fmt(cur['total_clicks'])}).")
    # Duplicate campaigns
    pm = v24.get("paid_media_v24") or {}
    for grp in (pm.get("duplicate_campaigns_visible") or []):
        items.append(
            f"Two campaigns with the same name are running at the same time "
            f"({grp.get('campaign_count')} campaigns: "
            f"{', '.join((grp.get('campaign_ids') or []))}). "
            f"Check whether both are meant to be active.")
    # CRM / bookings missing — surfaced as a real issue (we cannot
    # measure actual conversions)
    leads = _extract_kpi(v24, "Verified Leads")
    if leads.get("data_status") == "PENDING":
        items.append(
            "We still cannot tell how many Meta leads turned into real "
            "bookings — the bookings link to marketing is not in place.")
    # GA4 missing for this brand
    if (s.get("data_status") or "").upper() in ("UNAVAILABLE", "NOT_CONNECTED"):
        items.append(
            "Website analytics for this brand is not fully connected yet, "
            "so the traffic numbers above may be incomplete.")
    if not items:
        items.append("Nothing important is asking for attention right now.")
    for it in items:
        L.append(f"- {it}")
    L.append("")
    return L


# ── what we should do this week ────────────────────────────────

def _build_actions(v24: dict, bid: str) -> List[str]:
    L: List[str] = []
    L.append("## What we should do this week")
    L.append("")
    actions: List[dict] = []
    s = _extract_kpi(v24, "Sessions")
    cm = (v24.get("sections") or {}).get("channel_mix") or {}
    paid_totals = _paid_totals_from_campaigns(v24)
    cur = paid_totals["current_period"]
    prev = paid_totals["previous_period"]
    pm = v24.get("paid_media_v24") or {}

    # Action 1: largest mover channel
    chans = cm.get("rows") or []
    top_mover = None
    if chans:
        candidates = [(c, abs((c.get("current_sessions") or 0)
                                - (c.get("previous_sessions") or 0)))
                       for c in chans]
        candidates = [c for c in candidates if c[1] >= 5]
        if candidates:
            candidates.sort(key=lambda t: t[1], reverse=True)
            top_mover = candidates[0][0]
    if top_mover:
        cur_v = top_mover.get("current_sessions")
        prev_v = top_mover.get("previous_sessions")
        chan = top_mover.get("channel")
        share = top_mover.get("share_of_sessions") or 0
        direction = "increased" if cur_v > prev_v else "fell"
        if direction == "increased":
            suggestion = (
                f"check which pages and search terms brought the extra "
                f"traffic, then use those topics in upcoming content")
        else:
            suggestion = (
                f"check why the change happened before scaling or pausing "
                f"anything")
        actions.append({
            "what": (f"Watch the {chan} channel closely this week."),
            "why": (f"{chan} {direction} this week "
                      f"({_fmt(prev_v)} → {_fmt(cur_v)} sessions, "
                      f"{share:.1f}% of all sessions)."),
            "watch": suggestion,
        })
    # Action 2: largest active lead campaign — its cost-per-lead
    lead_campaigns = [c for c in (pm.get("per_campaign") or [])
                       if c.get("objective") == "OUTCOME_LEADS"
                       and (c.get("current") or {}).get("spend", 0) > 0]
    if lead_campaigns:
        lead_campaigns.sort(
            key=lambda c: (c.get("current") or {}).get("spend", 0),
            reverse=True)
        c = lead_campaigns[0]
        spend = (c.get("current") or {}).get("spend") or 0
        pr = c.get("primary_result") or {}
        leads_count = pr.get("primary_value")
        cpr = pr.get("primary_cost_per_unit")
        if cpr is not None and leads_count is not None:
            actions.append({
                "what": (f"Keep monitoring '{c.get('campaign_name','?')}' "
                          f"this week."),
                "why": (f"It produced {_fmt(leads_count)} leads at "
                          f"{_fmt(cpr, 'money_per')} per lead."),
                "watch": ("compare cost per lead with last week before "
                            "deciding whether to increase its budget"),
            })
    # Action 3: NS-aligned campaign — describe its actual traffic
    # signal (landing_page_views or leads) before any budget call
    fitting_or_coaching_campaigns = [
        c for c in (pm.get("per_campaign") or [])
        if (c.get("current") or {}).get("spend", 0) > 0
        and any(t in (c.get("campaign_name") or "").lower()
                  for t in ("fit", "coach", "lesson", "assessment", "leads"))
    ]
    if fitting_or_coaching_campaigns:
        c = fitting_or_coaching_campaigns[0]
        obj = c.get("objective")
        spend = (c.get("current") or {}).get("spend") or 0
        pr = c.get("primary_result") or {}
        pv = pr.get("primary_value")
        pml = pr.get("primary_metric_label")
        if obj == "OUTCOME_LEADS" and pv is not None:
            actions.append({
                "what": (f"Keep '{c.get('campaign_name','?')}' running."),
                "why": (f"It is the lead campaign aligned with the "
                          f"Fitting/Coaching business targets — "
                          f"{_fmt(pv)} leads this week."),
                "watch": ("how many of those leads become real bookings "
                            "(once that link is in place)"),
            })
        elif obj == "LINK_CLICKS" and pv is not None:
            actions.append({
                "what": (f"Keep '{c.get('campaign_name','?')}' running."),
                "why": (f"It brought {_fmt(pv)} website visits this week "
                          f"at {(_fmt(pr.get('primary_cost_per_unit'), 'money_per') or '—')} each."),
                "watch": ("how many of those visits reach the booking page "
                            "and how many continue to fill it in"),
            })

    if not actions:
        L.append("- Not enough clear evidence this week to recommend a "
                  "specific action. Wait until next week's data to see the "
                  "trends.")
        L.append("")
        return L
    for i, a in enumerate(actions[:3], 1):
        L.append(f"{i}. {a['what']}")
        L.append(f"   - **Why:** {a['why']}")
        L.append(f"   - **What to watch:** {a['watch']}")
    L.append("")
    return L


# ── business targets ───────────────────────────────────────────

def _build_targets(v24: dict, bid: str) -> List[str]:
    L: List[str] = []
    L.append("## Business targets")
    L.append("")
    ns = _extract_north_stars_from_v24(v24)
    confirmed = [n for n in ns
                  if n.get("metric")
                  and "PENDING" not in (n.get("metric", "") + n.get("label", "")).upper()]
    if confirmed:
        for n in confirmed:
            L.append(f"- **{n['label']}** — {n['metric']}")
        L.append("")
    L.append("Actual business results are not connected yet, so this report "
               "cannot show progress against these targets.")
    L.append("")
    return L


# ── data still missing ────────────────────────────────────────

def _build_data_missing(v24: dict, organic: Dict[str, Any]) -> List[str]:
    L: List[str] = []
    L.append("## Data still missing")
    L.append("")
    items: List[str] = []
    s = _extract_kpi(v24, "Sessions")
    if (s.get("data_status") or "").upper() in ("UNAVAILABLE", "NOT_CONNECTED"):
        items.append("Website analytics is not fully connected for this brand.")
    leads = _extract_kpi(v24, "Verified Leads")
    if leads.get("data_status") == "PENDING":
        items.append("Linking bookings or sales back to marketing leads is "
                       "not yet in place — so we cannot show how many leads "
                       "became real customers.")
    ig = organic.get("ig") or {}
    if ig.get("status") == "NOT_CONNECTED":
        items.append(f"Instagram reporting is not set up yet.")
    elif ig.get("status") == "PARTIAL":
        items.append("Instagram reporting is partly set up but the data is "
                       "not full enough yet.")
    fb = organic.get("fb") or {}
    if fb.get("status") == "PARTIAL":
        items.append("Facebook page reporting is incomplete.")
    elif fb.get("status") == "NOT_CONNECTED":
        items.append("Facebook page reporting is not set up yet.")
    if not items:
        items.append("No missing data sources reported this week.")
    for it in items:
        L.append(f"- {it}")
    L.append("")
    return L


# ── markdown rendering ─────────────────────────────────────────

def _render_markdown(bid: str, v24: dict, organic: Dict[str, Any],
                       periods: Dict[str, str],
                       contamination_block: Optional[str] = None,
                       as_of: Optional[str] = None) -> str:
    facts = _brand_canonical(bid)["canonical"]
    L: List[str] = []
    # Header
    title = f"# {facts['display_name']} Weekly Marketing Report"
    L.append(title)
    L.append(f"_{periods['current_week_start']} → "
               f"{periods['current_week_end']}_  ")
    if as_of:
        L.append(f"_Pinned to: {as_of}_  ")
    L.append("")

    if contamination_block:
        L.append("**REPORT BLOCKED — brand contamination detected.**")
        L.append("")
        L.append(contamination_block)
        return "\n".join(L)

    # This week at a glance
    L.append("## This week at a glance")
    L.append("")
    for line in _build_headline(bid, v24, organic):
        L.append(f"- {line}")
    L.append("")
    # Executive summary narrative (plain English)
    L.append("**What happened this week:**")
    L.append("")
    L.append(_build_executive_read(bid, v24, organic, periods))
    L.append("")
    # Sections in operator-specified order
    L.extend(_build_website_traffic(v24))
    L.extend(_build_acquisition(v24))
    L.extend(_build_advertising(v24))
    L.extend(_build_website_pages(v24))
    L.extend(_build_social_media(bid, organic, periods))
    L.extend(_build_best_content(bid, organic))
    L.extend(_build_what_worked(v24, bid))
    L.extend(_build_what_needs_attention(v24, bid))
    L.extend(_build_actions(v24, bid))
    L.extend(_build_targets(v24, bid))
    L.extend(_build_data_missing(v24, organic))

    # Footer — kept technical (technical log)
    L.append("---")
    L.append(f"_Generated {datetime.datetime.now(datetime.timezone.utc).isoformat()} "
               "• V2.4.1 frozen • V3.4 renderer (plain English)._")
    return "\n".join(L)


# ── HTML rendering ────────────────────────────────────────────

def _render_html(bid: str, v24: dict, organic: Dict[str, Any],
                   periods: Dict[str, str],
                   contamination_block: Optional[str] = None,
                   as_of: Optional[str] = None) -> str:
    md = _render_markdown(bid, v24, organic, periods, contamination_block,
                            as_of)
    facts = _brand_canonical(bid)["canonical"]
    title = (f"{facts['display_name']} Weekly Marketing Report — "
              f"{periods['current_week_start']} → {periods['current_week_end']}")
    if contamination_block:
        title = f"{title} — BLOCKED"
    body = md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    body_html = body.replace("\n## ", "\n<h2>").replace("\n### ", "\n<h3>")
    body_html = body_html.replace("**", "")
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,"
        "'Segoe UI',Roboto,sans-serif;max-width:920px;margin:40px auto;"
        "padding:0 20px;color:#1a1f2e;line-height:1.5;}"
        "h1{margin-bottom:8px}h2{margin-top:32px;border-bottom:1px solid "
        "#e3e6ed;padding-bottom:6px}h3{margin-top:18px;color:#3a4151}"
        "ul{margin:8px 0;padding-left:24px}li{margin:6px 0;font-size:15px}"
        "@media print {body{margin:0 auto}}</style>"
        "</head><body>"
        f"<pre style='white-space:pre-wrap;font-family:inherit;"
        f"font-size:14px;line-height:1.55'>{body_html}</pre>"
        "</body></html>")


# ── main entry ─────────────────────────────────────────────────

def build_v34(bid: str, fmt: str = "markdown",
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
            "rendered": (f"# {bid.title()} Weekly Marketing Report\n\n"
                          f"V2.4.1 unavailable: "
                          f"{v24.get('error', 'unknown error')}"),
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
            "rendered": _render_markdown(bid, v24, {}, periods,
                                           contamination_block=block,
                                           as_of=as_of),
            "raw_payload": {"v24": v24, "periods": periods},
        }
    organic = _read_organic_from_cache(bid)
    status = "OK"
    if fmt == "html":
        rendered = _render_html(bid, v24, organic, periods, as_of=as_of)
    elif fmt == "json":
        rendered = _render_markdown(bid, v24, organic, periods, as_of=as_of)
    else:
        rendered = _render_markdown(bid, v24, organic, periods, as_of=as_of)
    return {
        "report_status": status,
        "block_reason": None,
        "contaminations": [],
        "rendered": rendered,
        "raw_payload": {
            "v24": v24,
            "periods": periods,
            "brand_id": bid,
            "generator": "weekly_report_v3.4",
            "as_of": as_of,
            "organic": organic,
        },
    }


# ── snapshot ──────────────────────────────────────────────────

def archive_snapshot_v34(bid: str, as_of: Optional[str] = None,
                            snapshot_root: Optional[Path] = None,
                            cookie: Optional[str] = None) -> Dict[str, Any]:
    out = build_v34(bid, fmt="json", as_of=as_of, cookie=cookie)
    v24 = (out.get("raw_payload") or {}).get("v24") or {}
    periods = (out.get("raw_payload") or {}).get("periods") or {}
    organic = (out.get("raw_payload") or {}).get("organic") or {}
    snapshot = {
        "schema": "https://campaign-os/weekly-report/v3.4-snapshot",
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
        "organic_status": {
            "instagram": (organic.get("ig") or {}).get("status"),
            "facebook": (organic.get("fb") or {}).get("status"),
        },
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
    root = snapshot_root or _data_root()
    snap_dir = root / "weekly-snapshots" / bid
    snap_dir.mkdir(parents=True, exist_ok=True)
    fn = snap_dir / f"{snapshot['current_period']['end']}.json"
    fn.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False,
                                default=str), encoding="utf-8")
    snapshot["path"] = fn.as_posix()
    return snapshot


# Backwards-compat aliases for older callers in app.py
def build_v31(*args, **kwargs):
    return build_v34(*args, **kwargs)


def build_v32(*args, **kwargs):
    return build_v34(*args, **kwargs)


def build_v33(*args, **kwargs):
    return build_v34(*args, **kwargs)


def archive_snapshot_v31(*args, **kwargs):
    return archive_snapshot_v34(*args, **kwargs)


def archive_snapshot_v32(*args, **kwargs):
    return archive_snapshot_v34(*args, **kwargs)


def archive_snapshot_v33(*args, **kwargs):
    return archive_snapshot_v34(*args, **kwargs)


if __name__ == "__main__":
    bid = sys.argv[1] if len(sys.argv) > 1 else "stick"
    fmt = sys.argv[2] if len(sys.argv) > 2 else "markdown"
    as_of = sys.argv[3] if len(sys.argv) > 3 else None
    out = build_v34(bid, fmt=fmt, as_of=as_of)
    print(out["rendered"])
    sys.exit(0 if out["report_status"] == "OK" else 2)
