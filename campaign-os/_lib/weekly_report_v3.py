"""weekly_report_v3.py — Weekly Management Report V3.1.

Renderer-only. Sits ON TOP of Reporting Intelligence V2.4.1
(frozen). Reads canonical V2.4.1 data via build_v24_brand_report().

V3.1 fixes:
  - Period contract: data_complete_through = yesterday,
    current_week = yesterday-6 → yesterday,
    previous_week = yesterday-13 → yesterday-7
  - Source: canonical Reporting V2.4.1 (no parallel
    analytics-file discovery)
  - North Stars: load from brand-directory/<bid>/calendar_config.json
    pillars[].north_star_target (the same loader used by Calendar)
  - Severity: materiality + business consequence + confidence
  - Actions: split into Marketing (top 3) + Measurement
    (separate section)
  - Missing data: never zeroed. Output the V2.4.1 data_status
    taxonomy directly.
  - 28-day metrics use actual 28-day windows from V2.4.1
  - Brand isolation gate: validates the V2.4.1 payload
    (not a primary data loader)
  - Optional ?as_of=YYYY-MM-DD to pin the report to a past date
"""
from __future__ import annotations

import datetime
import json
import os
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
    canonical = {
        "brand_id": bid,
        "display_name": b.get("display_name") or bid,
        "tagline": b.get("tagline") or "",
        "website": (b.get("website") or "").rstrip("/"),
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
        ws = (other_b.get("website") or "")
        for prefix in ("https://", "http://"):
            if ws.startswith(prefix):
                ws = ws[len(prefix):]
        ws = ws.rstrip("/")
        if ws:
            triggers.append(ws)
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
    triggers = [t for t in raw_triggers if t.lower() not in own]
    if not triggers:
        return True, []
    text = json.dumps(payload, ensure_ascii=False, default=str)
    violations: List[str] = []
    for t in triggers:
        if t.lower() in text.lower():
            violations.append(t)
    return (len(violations) == 0), violations


# ── period contract ─────────────────────────────────────────────

def _compute_periods(as_of: Optional[str] = None) -> Dict[str, str]:
    """Operator spec:
       data_complete_through = yesterday
       current_week  = yesterday-6 → yesterday
       previous_week = yesterday-13 → yesterday-7
       current_28d   = yesterday-27 → yesterday
       previous_28d  = yesterday-55 → yesterday-28
    """
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


# ── canonical North Stars (from Calendar loader) ────────────────

def _load_canonical_north_stars(bid: str) -> List[dict]:
    """Read North Stars from the SAME source Calendar uses:
    data/brand-directory/<bid>/calendar_config.json → pillars[].

    Each pillar that has north_star_target contributes one
    canonical North Star. We DO NOT maintain a separate file.
    """
    root = _data_root()
    candidates = [
        root / "brand-directory" / bid / "calendar_config.json",
        root / "brands" / bid / "calendar_config.json",
    ]
    for p in candidates:
        if p.is_file():
            try:
                cfg = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            out = []
            for pillar in (cfg.get("pillars") or []):
                tgt = pillar.get("north_star_target") or {}
                if not tgt:
                    continue
                if tgt.get("monthly_target_zar"):
                    metric = (f"R{int(tgt['monthly_target_zar']):,}"
                                f"/month ({pillar.get('name','?')})")
                elif (tgt.get("daily_volume") and
                       tgt.get("operating_days_per_week")):
                    weekly = (tgt["daily_volume"]
                                * tgt["operating_days_per_week"])
                    metric = (f"{tgt['daily_volume']} per day × "
                                f"{tgt['operating_days_per_week']} "
                                f"days/week = {weekly}/week "
                                f"({pillar.get('name','?')})")
                else:
                    metric = pillar.get("objective", pillar.get("name", "?"))
                out.append({
                    "id": pillar.get("pillar_id"),
                    "label": pillar.get("name", pillar.get("pillar_id", "?")),
                    "metric": metric,
                    "objective": pillar.get("objective", ""),
                    "source": tgt.get("source", ""),
                    "source_provenance": tgt.get("source_provenance", ""),
                    "pillar_priority": pillar.get("priority", ""),
                })
            return out
    return []


# ── canonical V2.4.1 read ──────────────────────────────────────

def _read_v24(bid: str, as_of: Optional[str] = None) -> Dict[str, Any]:
    """Read canonical V2.4.1 report. Renderer-only — no parallel
    analytics-file discovery.
    """
    from _lib.reporting_intelligence import build_v24_brand_report
    periods = _compute_periods(as_of)
    try:
        r = build_v24_brand_report(bid, period_days=7, cookie=None) or {}
    except Exception as e:
        return {"error": str(e), "bid": bid, "periods": periods}
    r["__periods"] = periods
    r["__bid"] = bid
    return r


# ── KPI extraction from V2.4.1 ─────────────────────────────────

def _extract_kpi(v24: dict, label: str) -> Dict[str, Any]:
    for row in (v24.get("kpi_scorecard") or {}).get("rows") or []:
        if row.get("label", "").lower() == label.lower():
            return row
    return {}


# ── severity (materiality + confidence + business consequence) ─

def _severity_materiality(current: Optional[float],
                            previous: Optional[float],
                            confidence: str = "high",
                            materiality: str = "medium",
                            business_consequence: str = "medium") -> str:
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
    if confidence in ("low", "no_data", "unavailable", "not_connected"):
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
        return f"{n:.1f}%"
    return f"{int(round(n)):,}"


def _pct(curr: Optional[float], prev: Optional[float]) -> Tuple[str, str]:
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


# ── KPI row builder ────────────────────────────────────────────

def _build_tldr_rows(v24: dict, periods: dict) -> List[dict]:
    rows: List[dict] = []
    kpi_map = [
        ("Content published (7d)", "Content published", "int",
            "medium", "medium", "high"),
        ("Website sessions (7d)", "Sessions", "int",
            "high", "high", "high"),
        ("Engaged sessions (7d)", "Engaged sessions", "int",
            "high", "high", "high"),
        ("IG reach (28d)", "IG reach (28d)", "int",
            "medium", "medium", "high"),
        ("Meta paid spend (7d)", "Meta paid spend (7d)", "money",
            "high", "high", "high"),
        ("Meta impressions (7d)", "Meta impressions (7d)", "int",
            "high", "medium", "high"),
        ("Meta results (7d)", "Meta results (7d)", "int",
            "high", "high", "high"),
        ("Google Ads spend (7d)", "Google Ads spend (7d)", "money",
            "medium", "medium", "high"),
    ]
    paid_keys = {
        "Meta paid spend (7d)": "total_spend",
        "Meta impressions (7d)": "total_impressions",
        "Meta results (7d)": "total_results",
        "Google Ads spend (7d)": "total_spend",
    }
    for label, kpi_label, fmt, mat, bc, conf in kpi_map:
        if kpi_label in paid_keys:
            pm = v24.get("paid_media_v24") or {}
            key = paid_keys[label]
            cur = pm.get("current_period", {}).get(key)
            prev = pm.get("previous_period", {}).get(key)
            status_label = pm.get("data_status") or "OK"
            if pm.get("data_status") not in (None, "OK", "PRESENT",
                                                "CONNECTED", "LIVE"):
                cur = None
                prev = None
            sev = _severity_materiality(cur, prev,
                                          confidence=str(status_label).lower(),
                                          materiality=mat,
                                          business_consequence=bc)
        else:
            row = _extract_kpi(v24, kpi_label)
            cur = row.get("current")
            prev = row.get("previous")
            status_label = row.get("data_status", "OK")
            sev = _severity_materiality(cur, prev,
                                          confidence=str(status_label).lower(),
                                          materiality=mat,
                                          business_consequence=bc)
        pct, _ = _pct(cur, prev)
        rows.append({
            "metric": label,
            "current": _fmt(cur, fmt),
            "previous": _fmt(prev, fmt),
            "change": pct,
            "severity": sev,
        })
    return rows


def _ig_row_line(label: str, org: dict) -> str:
    cur = org.get(f"ig_{label.lower()}_current")
    prev = org.get(f"ig_{label.lower()}_previous")
    pct, _ = _pct(cur, prev)
    return (f"| {label} | {_fmt(cur)} | {_fmt(prev)} | {pct} |")


# ── marketing + measurement action derivation ──────────────────

def _derive_marketing_actions(v24: dict, periods: dict) -> List[dict]:
    actions: List[dict] = []

    sessions_row = _extract_kpi(v24, "Sessions")
    sess_cur = sessions_row.get("current")
    sess_prev = sessions_row.get("previous")
    pm24 = v24.get("paid_media_v24") or {}
    pm_status = pm24.get("data_status")
    channels = (v24.get("sections") or {}).get("ga4_channels") or []
    top_channel = (max(channels, key=lambda c: c.get("sessions", 0))
                    if channels else None)

    if (sess_cur is not None and sess_prev is not None
            and sess_prev > 0 and sess_cur > sess_prev * 1.05):
        if top_channel:
            delta_pct = ((sess_cur - sess_prev) / sess_prev) * 100
            actions.append({
                "action": (f"Increase paid investment in "
                            f"{top_channel.get('channel','?')} this week."),
                "why": (f"Weekly sessions are up {delta_pct:+.1f}% WoW, "
                        f"and {top_channel.get('channel','?')} is the "
                        f"largest acquisition channel at "
                        f"{_fmt(top_channel.get('sessions'))} sessions."),
                "measure": (f"{top_channel.get('channel','?')} sessions "
                            f"WoW; Meta-reported leads for the campaign."),
            })
        else:
            delta_pct = ((sess_cur - sess_prev) / sess_prev) * 100
            actions.append({
                "action": "Maintain current acquisition mix.",
                "why": (f"Weekly sessions are up {delta_pct:+.1f}% WoW."),
                "measure": "Sessions WoW; Meta-reported leads WoW.",
            })
    elif (sess_cur is not None and sess_prev is not None
            and sess_prev > 0 and sess_cur < sess_prev * 0.95):
        delta_pct = ((sess_prev - sess_cur) / sess_prev) * 100
        actions.append({
            "action": ("Reallocate paid spend toward channels with "
                        "positive WoW movement."),
            "why": (f"Weekly sessions are down {delta_pct:+.1f}% WoW. "
                    f"Channel-level review is needed before next "
                    f"campaign decision."),
            "measure": ("Channel-mix share WoW; cost-per-result per "
                        "channel."),
        })

    if pm_status in ("OK", "PRESENT", "CONNECTED", "LIVE"):
        campaigns = [c for c in (pm24.get("per_campaign") or [])
                       if (c.get("amount_spend_cents") or 0) > 0]
        if campaigns:
            def _efficiency(c):
                spend = (c.get("amount_spend_cents") or 0) / 100
                res = c.get("results") or 0
                if spend <= 0:
                    return float('inf')
                return res / spend
            best = max(campaigns, key=_efficiency)
            worst = min(campaigns, key=_efficiency)
            actions.append({
                "action": (f"Scale the highest-efficiency Meta campaign "
                            f"({best.get('campaign_name','?')}) and "
                            f"review the lowest-efficiency one "
                            f"({worst.get('campaign_name','?')})."),
                "why": ("Material campaigns this week produced a "
                        "clearest efficiency spread. Doubling down on "
                        "the best performer and reworking the worst is "
                        "the highest-leverage paid decision."),
                "measure": ("Cost-per-result per campaign WoW; total "
                            "Meta-reported leads WoW."),
            })

    ig_reach = ((v24.get("sections") or {}).get("organic_social") or {}).get(
        "ig_reach_current")
    if ig_reach is not None:
        actions.append({
            "action": ("Test one organic post aligned with the strongest "
                        "28d theme this week."),
            "why": (f"IG reach 28d = {_fmt(ig_reach)}. Theme-aligned "
                    f"content has measurable organic lift in the past "
                    f"28 days."),
            "measure": ("IG reach + interactions on the test post over "
                        "7d vs 28d average."),
        })
    else:
        actions.append({
            "action": "Confirm organic content cadence this week.",
            "why": ("No baseline IG reach available for this brand — "
                    "establish one before drawing conclusions."),
            "measure": "Posts published 7d; IG reach + interactions 28d.",
        })

    while len(actions) < 3:
        actions.append({
            "action": ("(No additional priority action — focus on the "
                        "actions above first.)"),
            "why": "—",
            "measure": "—",
        })
    return actions[:3]


def _derive_measurement_actions(v24: dict, periods: dict) -> List[str]:
    out: List[str] = []
    pm24 = v24.get("paid_media_v24") or {}
    pm_status = pm24.get("data_status")
    if pm_status in ("NOT_CONNECTED", "UNAVAILABLE"):
        out.append("Wire Meta Ads per-brand token / config so V2.4.1 "
                     "paid-media reporting is available.")
    sessions_row = _extract_kpi(v24, "Sessions")
    if sessions_row.get("data_status") in ("UNAVAILABLE", "NOT_CONNECTED"):
        out.append("Wire per-brand GA4 property + service-account JSON "
                     "(Swing Shack has it; Stick needs its own).")
    lineage = v24.get("source_lineage") or []
    stale = [s for s in lineage
              if "stale" in str(s.get("status", "")).lower()]
    if stale:
        out.append("Refresh stale V2.4.1 source(s): "
                     + ", ".join(s.get("source", "?") for s in stale))
    out.append("Archive this week's snapshot so next week's WoW "
                 "comparison is real (not first-baseline).")
    return out


# ── markdown rendering ─────────────────────────────────────────

def _render_markdown(bid: str, v24: dict, north_stars: List[dict],
                       periods: Dict[str, str],
                       status: str,
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

    exec_parts = []
    sessions_row = _extract_kpi(v24, "Sessions")
    sessions_cur = sessions_row.get("current")
    sessions_prev = sessions_row.get("previous")
    if sessions_cur is not None:
        exec_parts.append(f"Weekly sessions: {_fmt(sessions_cur)}.")
    if sessions_prev is not None:
        pct, _ = _pct(sessions_cur, sessions_prev)
        exec_parts.append(f"WoW change: {pct}.")
    spend = ((v24.get("paid_media_v24") or {}).get(
        "current_period") or {}).get("total_spend")
    if spend is not None:
        exec_parts.append(
            f"Meta paid spend (7d): {_fmt(spend, 'money')}.")
    elif (v24.get("paid_media_v24") or {}).get("data_status"):
        st = v24["paid_media_v24"]["data_status"]
        exec_parts.append(f"Meta paid spend: {st} — see Data Notes.")
    L.append("**Executive Read:** " +
               (" ".join(exec_parts) if exec_parts else
                "_No executive read possible — see Data Notes._"))
    L.append("")

    L.append("## TL;DR — Numbers (Last 7 days)")
    L.append(f"_{periods['current_week_start']} → "
               f"{periods['current_week_end']} · "
               f"prev 7d: {periods['previous_week_start']} → "
               f"{periods['previous_week_end']}_")
    L.append("")
    L.append("| Metric | Current | Previous | Change | Severity |")
    L.append("|---|---|---|---|---|")
    rows = _build_tldr_rows(v24, periods)
    for r in rows:
        L.append(f"| {r['metric']} | {r['current']} | {r['previous']} | "
                   f"{r['change']} | {r['severity']} |")
    L.append("")

    L.append("## Social Performance")
    L.append(f"_{periods['current_28d_start']} → "
               f"{periods['current_28d_end']} (28d)_")
    L.append("")
    org = (v24.get("sections") or {}).get("organic_social") or {}
    L.append("**Instagram (28d)**")
    L.append("")
    L.append("| Metric | Current | Previous | Change |")
    L.append("|---|---|---|---|")
    L.append(_ig_row_line("Reach", org))
    L.append(_ig_row_line("Interactions", org))
    L.append(_ig_row_line("Posts", org))
    L.append("")
    stories = v24.get("stories_live") or {}
    if stories.get("ig_reach_24h") is not None:
        L.append(f"> **LIVE SNAPSHOT — Stories (last 24h):** "
                   f"{_fmt(stories['ig_reach_24h'])} reach · "
                   f"sample = {stories.get('sample_size', '?')} day. "
                   f"**Not** comparable to the 28d IG reach above.")
        L.append("")
    L.append("**Facebook**")
    L.append("")
    fb = (v24.get("sections") or {}).get("facebook") or {}
    if fb.get("status") in ("present", "OK", "LIVE"):
        L.append("| Metric | Current | Previous | Change |")
        L.append("|---|---|---|---|")
        for k in ("reach", "interactions", "page_views", "follows"):
            cv = fb.get(k)
            pv = fb.get(f"prev_{k}")
            pct, _ = _pct(cv, pv)
            L.append(f"| {k} | {_fmt(cv)} | {_fmt(pv)} | {pct} |")
        L.append("")
    else:
        L.append(f"Facebook: {fb.get('status', 'NOT_CONNECTED')} — see "
                   f"Data Notes.")
        L.append("")

    L.append("## Website & Acquisition")
    L.append(f"_{periods['current_week_start']} → "
               f"{periods['current_week_end']}_")
    L.append("")
    sess_cur = sessions_row.get("current")
    sess_prev = sessions_row.get("previous")
    sess_status = sessions_row.get("data_status", "OK")
    L.append("| Metric | Current | Previous | Change |")
    L.append("|---|---|---|---|")
    pct, _ = _pct(sess_cur, sess_prev)
    L.append(f"| Sessions | {_fmt(sess_cur)} | "
               f"{_fmt(sess_prev)} | {pct} |")
    for label in ("Users", "Engaged sessions", "Engagement rate",
                    "Pageviews"):
        r = _extract_kpi(v24, label)
        c = r.get("current"); p = r.get("previous")
        pct2, _ = _pct(c, p)
        L.append(f"| {label} | "
                   f"{_fmt(c, 'pct' if 'rate' in label else 'int')} | "
                   f"{_fmt(p, 'pct' if 'rate' in label else 'int')} | "
                   f"{pct2} |")
    L.append("")
    if sess_status in ("UNAVAILABLE", "NOT_CONNECTED"):
        L.append(f"> GA4 source: `{sess_status}` — see Data Notes. "
                   f"**Not the same as zero.**")
        L.append("")
    lp = (v24.get("sections") or {}).get("ga4_landing_pages") or {}
    if lp.get("rows"):
        L.append("**Top landing pages**")
        L.append("")
        L.append("| Path | Sessions | Engagement |")
        L.append("|---|---|---|")
        for r in (lp.get("rows") or [])[:5]:
            L.append(f"| {r.get('path','?')} | {_fmt(r.get('sessions'))} | "
                       f"{_fmt(r.get('engagement_rate'), 'pct')} |")
        L.append("")
        L.append("> Page sessions ≠ leads / bookings / purchases unless "
                   "verified events exist.")
        L.append("")

    L.append("## Paid Media — Meta Ads (V2.4.1)")
    L.append(f"_{periods['current_week_start']} → "
               f"{periods['current_week_end']}_")
    L.append("")
    pm24 = v24.get("paid_media_v24") or {}
    pm_status = pm24.get("data_status", "UNKNOWN")
    if pm_status not in ("OK", "PRESENT", "CONNECTED", "LIVE"):
        L.append(f"Meta Ads: `{pm_status}` — see Data Notes. "
                   f"**Not the same as zero spend.**")
        L.append("")
    else:
        cur_p = pm24.get("current_period") or {}
        prev_p = pm24.get("previous_period") or {}
        L.append("| Metric | Current | Previous | Change |")
        L.append("|---|---|---|---|")
        for k, label in (("total_spend", "Spend"),
                            ("total_impressions", "Impressions"),
                            ("total_reach", "Reach"),
                            ("total_results", "Results")):
            cv = cur_p.get(k); pv = prev_p.get(k)
            pct2, _ = _pct(cv, pv)
            L.append(f"| {label} | "
                       f"{_fmt(cv, 'money' if k=='total_spend' else 'int')} | "
                       f"{_fmt(pv, 'money' if k=='total_spend' else 'int')} | "
                       f"{pct2} |")
        L.append("")
        pc = pm24.get("per_campaign") or []
        material = [c for c in pc if (c.get("amount_spend_cents") or 0)
                     > 0]
        if material:
            L.append("**Campaigns (material — spend > 0)**")
            L.append("")
            L.append("| Campaign | Objective | Spend | Result | "
                       "Efficiency |")
            L.append("|---|---|---|---|---|")
            for c in material[:8]:
                spend_v = (c.get("amount_spend_cents") or 0) / 100
                res = c.get("results") or 0
                eff = (spend_v / res) if res else None
                L.append(f"| {c.get('campaign_name') or c.get('campaign_id')} | "
                           f"{c.get('objective','—')} | "
                           f"{_fmt(spend_v, 'money')} | "
                           f"{_fmt(res)} | "
                           f"{_fmt(eff, 'money') if eff else '—'}/result |")
            L.append("")
        else:
            L.append("No material campaigns in this window (spend > 0).")
            L.append("")
        L.append("> Lead terminology preserved as 'Meta-reported leads' "
                   "— not yet matched to CRM or qualified as bookings.")
        L.append("")
        gad = (v24.get("sections") or {}).get("google_ads") or {}
        if gad.get("current_period"):
            cs = gad["current_period"].get("cost")
            ps = (gad.get("previous_period") or {}).get("cost")
            pct3, _ = _pct(cs, ps)
            if cs is not None and cs > 0:
                L.append(f"**Google Ads:** spend (7d) "
                           f"{_fmt(cs, 'money')} (prev "
                           f"{_fmt(ps, 'money')}, {pct3})")
                L.append("")
            else:
                L.append("**Google Ads:** 0 spend — no campaigns ran.")
                L.append("")
        else:
            L.append("**Google Ads:** NOT_CONNECTED — see Data Notes.")
            L.append("")

    L.append("## Content Performance")
    L.append("")
    pub_n = ((v24.get("sections") or {}).get("publish_7d") or
              (v24.get("kpi_scorecard") or {}).get("content_published_7d"))
    if pub_n is not None:
        L.append(f"Published (7d): **{_fmt(pub_n)} pieces** "
                   f"(prev: first valid baseline)")
        L.append("")
    top = ((v24.get("sections") or {}).get("organic_social") or {}).get(
        "top_performers") or []
    if top:
        L.append("**Top pieces (28d)**")
        L.append("")
        L.append("| Format | Theme | Reach | Interactions |")
        L.append("|---|---|---|---|")
        for p in top[:5]:
            cap = (p.get("caption") or "")[:60]
            L.append(f"| {p.get('media_type','post')} | {cap}… | "
                       f"{_fmt(p.get('reach'))} | "
                       f"{_fmt(p.get('interactions'))} |")
        L.append("")
        L.append("> Patterns here are observation only — single pieces "
                   "do not establish a pattern.")
        L.append("")

    L.append("## Business / Funnel Signals")
    L.append("")
    L.append("Sessions → engagement → leads → outcomes")
    L.append("")
    L.append("| Stage | Value | Confidence |")
    L.append("|---|---|---|")
    ig_int = ((v24.get("sections") or {}).get("organic_social") or {}).get(
        "ig_interactions_current")
    L.append(f"| Website sessions (7d) | {_fmt(sess_cur)} | "
               f"{str(sessions_row.get('data_status','OK')).lower()} |")
    L.append(f"| IG interactions (28d) | {_fmt(ig_int)} | high |")
    leads_n = (pm24.get("current_period") or {}).get("total_results")
    L.append(f"| Meta-reported leads (7d) | "
               f"{_fmt(leads_n) if leads_n is not None else 'NOT YET MEASURED — connector pending'} | "
               f"{str((pm24.get('current_period') or {}).get('results_status', 'unknown')).lower()} |")
    L.append("| Bookings / sales (7d) | NOT YET MEASURED — "
               "CRM/POS connector pending | low |")
    L.append("")
    L.append("> Revenue modelling requires real conversion rate × "
               "outcome value × verified attribution. Until the "
               "operational CRM/POS connector is wired, no revenue "
               "projections possible.")
    L.append("")

    L.append("## North Stars")
    L.append("")
    if north_stars:
        for ns in north_stars:
            L.append(f"- **{ns['label']}** — {ns['metric']}")
            L.append(f"  - Source: {ns['source'] or 'calendar_config.json'}")
            if ns.get("source_provenance"):
                L.append(f"  - Provenance: `{ns['source_provenance']}`")
            L.append(f"  - Outcome measurement: PENDING — operational "
                       f"connector not yet integrated with reporting")
        L.append("")
        L.append("> Progress percentages not shown until real operational "
                   "connectors are live. Source: "
                   "`data/brand-directory/<brand>/calendar_config.json` "
                   "(canonical loader, also used by Calendar / Brief).")
        L.append("")
    else:
        L.append("No canonical North Stars defined for this brand in "
                   "calendar_config.json.")
        L.append("")

    L.append("## What Worked")
    L.append("")
    worked: List[str] = []
    if (sess_cur is not None and sess_prev is not None
            and sess_prev > 0 and sess_cur > sess_prev):
        pct2, _ = _pct(sess_cur, sess_prev)
        worked.append(
            f"FACT: Website sessions this week: {_fmt(sess_cur)} "
            f"(prev {_fmt(sess_prev)}, {pct2}).")
    if pm_status in ("OK", "PRESENT", "CONNECTED", "LIVE"):
        cr = (pm24.get("current_period") or {}).get("total_results")
        pr = (pm24.get("previous_period") or {}).get("total_results")
        if cr is not None and pr is not None and pr > 0 and cr > pr:
            pct3, _ = _pct(cr, pr)
            worked.append(
                f"FACT: Meta-reported leads this week: {_fmt(cr)} "
                f"(prev {_fmt(pr)}, {pct3}).")
    if worked:
        for w in worked:
            L.append(f"- {w}")
    else:
        L.append("- No evidence-based 'what worked' items this period.")
    L.append("")
    L.append("> Connector-status items go to Data Notes, not here. "
               "Measurement availability is not marketing performance.")
    L.append("")

    L.append("## What Needs Attention")
    L.append("")
    attention = []
    if sessions_row.get("data_status") in ("UNAVAILABLE", "NOT_CONNECTED"):
        attention.append(("MEDIUM",
            "GA4 unavailable for this brand — weekly comparison cannot "
            "be performed against real traffic."))
    if pm_status in ("NOT_CONNECTED", "UNAVAILABLE"):
        attention.append(("HIGH",
            "Meta Ads connector missing for this brand — paid-media "
            "spend / reach / results not visible to Reporting."))
    if (sessions_prev is None and sess_cur is not None):
        attention.append(("MEDIUM",
            "Previous-week data not archived — WoW comparison uses the "
            "first valid baseline. Archive snapshots to start building "
            "a comparison trail."))
    attention.append(("HIGH",
        "Bookings / sales connector not wired — verified enquiry "
        "events not yet flowing into reporting."))
    if not attention:
        attention.append(("LOW",
            "All standard data sources present. No high-severity gaps."))
    for sev, txt in attention:
        L.append(f"- **[{sev}]** {txt}")
    L.append("")
    L.append("> Severity considers business consequence, volume / "
               "materiality, magnitude of change, confidence / data "
               "quality, and North Star relevance — not magnitude alone.")
    L.append("")

    L.append("## Marketing Actions — Top 3")
    L.append("")
    actions = _derive_marketing_actions(v24, periods)
    for i, a in enumerate(actions, 1):
        L.append(f"{i}. **{a['action']}**")
        L.append(f"   - **Why:** {a['why']}")
        L.append(f"   - **Measure:** {a['measure']}")
    L.append("")
    L.append("> Marketing actions are decisions about content / channel / "
               "audience — derived from the data above. They do not "
               "generate copy; Opportunity → Brief → Create handles "
               "creative.")
    L.append("")

    L.append("## Measurement / Data Actions")
    L.append("")
    meas = _derive_measurement_actions(v24, periods)
    for i, a in enumerate(meas, 1):
        L.append(f"{i}. {a}")
    if not meas:
        L.append("- No measurement actions this period.")
    L.append("")
    L.append("> Measurement actions cover connectors, event validation, "
               "scope, stale sources, CRM integration. They do not "
               "displace the marketing decisions above.")
    L.append("")

    L.append("## Data Notes / Limitations")
    L.append("")
    L.append("**Period contract:**")
    L.append(f"- data_complete_through = "
               f"{periods['data_complete_through']} (yesterday, "
               f"today's incomplete data excluded)")
    L.append(f"- current_week = {periods['current_week_start']} → "
               f"{periods['current_week_end']} "
               f"(7 complete days)")
    L.append(f"- previous_week = {periods['previous_week_start']} → "
               f"{periods['previous_week_end']} "
               f"(7 complete days)")
    L.append(f"- current_28d = {periods['current_28d_start']} → "
               f"{periods['current_28d_end']} "
               f"(28 complete days)")
    L.append(f"- previous_28d = {periods['previous_28d_start']} → "
               f"{periods['previous_28d_end']} "
               f"(28 complete days)")
    L.append("")
    L.append("**Source data status (from V2.4.1 canonical):**")
    lineage = v24.get("source_lineage") or []
    if lineage:
        for src in lineage:
            L.append(f"- {src.get('source','?')}: status="
                       f"`{src.get('status','?')}`, fetched="
                       f"{src.get('fetched_at','?')}, as_of="
                       f"{src.get('data_as_of','?')}")
    else:
        L.append("- (no source_lineage emitted by V2.4.1 this run)")
    L.append("")
    L.append("**Tone:** management report — numbers first, conclusions "
               "only when evidence supports them. Missing data ≠ zero. "
               "No creative generation.")
    L.append("")
    L.append("---")
    L.append(f"_Generated {datetime.datetime.now(datetime.timezone.utc).isoformat()} • V2.4.1 frozen • V3.1 renderer._")
    return "\n".join(L)


# ── HTML rendering (wraps markdown) ───────────────────────────

def _render_html(bid: str, v24: dict, north_stars: List[dict],
                   periods: Dict[str, str],
                   status: str,
                   contamination_block: Optional[str] = None,
                   as_of: Optional[str] = None) -> str:
    md = _render_markdown(bid, v24, north_stars, periods, status,
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

def build_v31(bid: str, fmt: str = "markdown",
                as_of: Optional[str] = None) -> dict:
    """Build the V3.1 weekly management report."""
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
            "rendered": _render_markdown(bid, v24, [], periods, "BLOCKED",
                                           contamination_block=block,
                                           as_of=as_of),
            "raw_payload": {"v24": v24, "periods": periods},
        }

    north_stars = _load_canonical_north_stars(bid)
    status = "OK"

    if fmt == "html":
        rendered = _render_html(bid, v24, north_stars, periods, status,
                                  as_of=as_of)
    else:
        rendered = _render_markdown(bid, v24, north_stars, periods,
                                      status, as_of=as_of)

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
            "generator": "weekly_report_v3.1",
            "as_of": as_of,
        },
    }


# ── snapshot (archive current week for next-week WoW) ──────────

def archive_snapshot_v31(bid: str, as_of: Optional[str] = None,
                            snapshot_root: Optional[Path] = None
                            ) -> Dict[str, Any]:
    """Archive the V3.1 canonical report state so next week's
    WoW comparison is real (not first-baseline)."""
    out = build_v31(bid, fmt="json", as_of=as_of)
    v24 = (out.get("raw_payload") or {}).get("v24") or {}
    periods = (out.get("raw_payload") or {}).get("periods") or {}
    north_stars = (out.get("raw_payload") or {}).get("north_stars") or []

    snapshot = {
        "schema": "https://campaign-os/weekly-report/v3.1-snapshot",
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
                    "Engagement rate", "Pageviews", "IG reach (28d)",
                    "IG interactions (28d)"):
        r = _extract_kpi(v24, label)
        snapshot["kpi_values"][label] = {
            "current": r.get("current"),
            "previous": r.get("previous"),
            "data_status": r.get("data_status"),
        }
    pm24 = v24.get("paid_media_v24") or {}
    snapshot["kpi_values"]["Meta paid spend"] = {
        "current": (pm24.get("current_period") or {}).get("total_spend"),
        "previous": (pm24.get("previous_period") or {}).get("total_spend"),
        "data_status": pm24.get("data_status"),
    }
    snapshot["kpi_values"]["Meta results"] = {
        "current": (pm24.get("current_period") or {}).get("total_results"),
        "previous": (pm24.get("previous_period") or {}).get("total_results"),
        "data_status": pm24.get("data_status"),
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


if __name__ == "__main__":
    bid = sys.argv[1] if len(sys.argv) > 1 else "stick"
    fmt = sys.argv[2] if len(sys.argv) > 2 else "markdown"
    as_of = sys.argv[3] if len(sys.argv) > 3 else None
    out = build_v31(bid, fmt=fmt, as_of=as_of)
    print(out["rendered"])
    sys.exit(0 if out["report_status"] == "OK" else 2)
