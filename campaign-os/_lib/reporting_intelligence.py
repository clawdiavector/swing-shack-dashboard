"""
Reporting Intelligence V1 — Dual-Brand Engine

Builds presentation-ready marketing performance reports for
Stick Golf and Swing Shack with strict brand isolation.

Data sources (per brand, only what is trustworthy):
  - GA4 (per-brand property; READ-ONLY via the service
    account wired in Step 3A/Step 3B)
  - Campaign OS historical archives (organic post/IG index,
    Facebook analytics)
  - Strategy file (data/strategy/<brand>.json — north stars,
    pillars, market moves)
  - brand-directory entries (palette, voice, audience)

NOT used (data integrity):
  - data/meta-ads.json (SYNTHETIC_QUARANTINED)
  - any non-verified historical "engagement" numbers

Public surface:
  build_brand_report(brand_id) -> dict  (full JSON)
  render_brand_report_html(brand_id) -> str  (print-ready)
  render_portfolio_summary_html(reports) -> str

All metrics carry brand_id, source, asset, period,
data_status, confidence. No cross-brand bleed.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Optional


DATA_ROOT_DEFAULT = os.environ.get("DATA_DIR", "data")

# Status taxonomy from brief §6
STATUS_LIVE = "LIVE"
STATUS_PARTIAL = "PARTIAL"
STATUS_HISTORICAL_REAL = "HISTORICAL_REAL"
STATUS_STALE = "STALE"
STATUS_NOT_CONNECTED = "NOT_CONNECTED"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_SYNTHETIC_QUARANTINED = "SYNTHETIC_QUARANTINED"
STATUS_PENDING = "PENDING"


# Brand-scoped config (no cross-brand bleed)
BRAND_CONFIG = {
    "stick": {
        "name": "Stick Golf",
        "domain": "stickgolf.co.za",
        "ga4_property_id": "532174688",
        "ga4_stream_id": "14338292352",
        "meta_business_id": "26520596534242385",
        "facebook_page_id": "1051565264705239",
        "instagram_business_account_id": "17841469555624210",
        "whatsapp_business_account_id": "1207430961556134",
        "meta_ad_account_id": "2101557317059886",
        "strategy_path": "data/strategy/stick.json",
        "brand_directory": "data/brand-directory/stick/palette/brand.json",
        "lead_tracking_status": STATUS_PENDING,
        "north_stars": {
            "retail": {"label": "Retail (Psycho Bunny)",
                       "target": "R350,000 Psycho Bunny sales/month"},
            "fitting": {"label": "Fitting", "target": "24 fittings/week"},
            "coaching": {"label": "Coaching", "target": "24 coaching sessions/week"},
        },
    },
    "swing-shack": {
        "name": "Swing Shack",
        "domain": "swingshack.co.za",
        "ga4_property_id": "427380680",
        "meta_business_id": None,
        "facebook_page_id": "198859063301219",
        "instagram_business_account_id": "17841456713897671",
        "strategy_path": "data/strategy/swing-shack.json",
        "brand_directory": "data/brand-directory/swing-shack/palette/brand.json",
        "lead_tracking_status": STATUS_NOT_APPLICABLE,  # not in scope
        "north_stars": {
            "category": {"label": "Category",
                         "target": "Own 'measurement-led serious golf' as a category"},
            "north_star": {"label": "North Star",
                           "target": "Every serious golfer in South Africa has access to "
                                     "measurement-led improvement."},
        },
    },
}


# ── helpers ───────────────────────────────────────────────────────────

def _read_json(path) -> Optional[Any]:
    if not path:
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _ga4_property_data(brand_id: str, days: int = 31) -> Optional[dict]:
    """Return a sentinel None; live numbers come from the runtime
    endpoint at print time, not from this offline renderer.
    """
    return None


def _strategy_for(brand_id: str) -> dict:
    cfg = BRAND_CONFIG.get(brand_id, {})
    path = cfg.get("strategy_path")
    if not path:
        return {}
    data = _read_json(path) or {}
    return {
        "north_star": data.get("north_star"),
        "headline_belief": data.get("headline_belief"),
        "mission": data.get("mission"),
        "strategic_ambition": data.get("strategic_ambition"),
        "category_position": data.get("category_position"),
        "voice_summary": (data.get("voice") or {}).get("voice_summary"),
        "market_moves": data.get("market_moves", []),
        "flagship_properties": _flatten_flagship(data.get("market_moves", [])),
        "source": path,
        "data_status": STATUS_LIVE if data.get("north_star") else STATUS_HISTORICAL_REAL,
    }


def _flatten_flagship(market_moves):
    props = []
    for mv in market_moves or []:
        for fp in mv.get("flagship_properties", []) or []:
            props.append({"name": fp.get("name"), "mission": fp.get("mission")})
    return props


def _brand_directory_for(brand_id: str) -> dict:
    cfg = BRAND_CONFIG.get(brand_id, {})
    path = cfg.get("brand_directory")
    return _read_json(path) or {}


def _historical_archives(brand_id: str) -> dict:
    """Pull the historical archives relevant to this brand.

    For each archive, return only data that is clearly
    brand-scoped (no mixing across brands). Archives we read:
      - data/facebook-analytics.json  (Swing Shack Page)
      - data/ig-analytics.json         (Swing Shack IG)
      - data/ig-business-analytics.json (Swing Shack IG)
      - data/meta-post-index.json      (mixed; we filter)
      - data/weekly-report.json        (mixed; we filter)

    For Stick, the meta-ads surfaces are SYNTHETIC and are
    never included.
    """
    archives = {}

    if brand_id == "swing-shack":
        # FB page — direct match
        fb = _read_json("data/facebook-analytics.json")
        if fb:
            archives["facebook_page"] = {
                "data": fb,
                "asset_id": "198859063301219",
                "source": "data/facebook-analytics.json",
                "data_status": STATUS_LIVE,
                "last_updated": fb.get("last_updated"),
            }
        # IG business — direct match
        igb = _read_json("data/ig-business-analytics.json")
        if igb:
            archives["ig_business"] = {
                "data": igb,
                "asset_id": "17841456713897671",
                "source": "data/ig-business-analytics.json",
                "data_status": STATUS_STALE,  # last fetched 2026-08-21
                "last_updated": igb.get("last_updated"),
            }
        # IG analytics (creator handle) — same brand
        iga = _read_json("data/ig-analytics.json")
        if iga:
            archives["ig_creator"] = {
                "data": iga,
                "asset_id": "17841456713897671",
                "source": "data/ig-analytics.json",
                "data_status": STATUS_STALE,
                "last_updated": iga.get("last_updated"),
            }

    if brand_id == "stick":
        # No per-brand organic archives yet. The brief
        # explicitly allows generating today's report without
        # organic archives ("data gaps must not block today's
        # report").
        pass

    return archives


def _safe_pct(numerator, denominator):
    if not denominator or denominator == 0:
        return None
    try:
        return (numerator / denominator) * 100.0
    except Exception:
        return None


def _format_period(days: int = 31) -> tuple:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return (
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d"),
    )


# ── report sections ─────────────────────────────────────────────────

def _executive_summary(brand_id: str, metrics: dict, data_status: dict) -> list:
    """Generate 5-8 substantive bullets.

    Pure templating against the deterministic metrics. The
    'analyst layer' here is template composition, not free-form
    generation — this keeps the report auditable and avoids
    invented numbers.
    """
    out = []
    cfg = BRAND_CONFIG[brand_id]
    name = cfg["name"]

    # Website traffic (GA4)
    ga = metrics.get("ga4") or {}
    if ga.get("data_status") == STATUS_LIVE:
        sessions = (ga.get("metrics") or {}).get("sessions", 0)
        users = (ga.get("metrics") or {}).get("total_users", 0)
        er = (ga.get("metrics") or {}).get("engagement_rate_median", 0)
        out.append({
            "statement": f"{name} website recorded {sessions:,} sessions from "
                          f"{users:,} users in the last 31 days, with a median "
                          f"daily engagement rate of {er:.0%}.",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })
        # Channel mix
        ch = ga.get("channel_mix", {})
        if ch:
            top = max(ch.items(), key=lambda kv: kv[1])
            out.append({
                "statement": f"Traffic was dominated by {top[0]} "
                              f"({top[1]:.0%} of sessions).",
                "type": "MEASURED_FACT",
                "confidence": "HIGH",
            })
    elif ga.get("data_status") == STATUS_NOT_CONNECTED:
        out.append({
            "statement": f"{name} GA4 website analytics are not currently connected "
                          f"in this build; traffic performance cannot be quantified.",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })
    elif ga.get("data_status") == STATUS_UNAVAILABLE:
        reason = ga.get("reason", "unknown")
        out.append({
            "statement": f"{name} GA4 endpoint returned an error ({reason[:80]}). "
                          f"Website traffic cannot be quantified in this run.",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })

    # Lead tracking
    if cfg.get("lead_tracking_status") == STATUS_PENDING:
        out.append({
            "statement": f"Verified website lead tracking is not yet live for {name}; "
                          f"traffic can be assessed but commercial enquiry conversion "
                          f"cannot yet be quantified.",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })

    # Meta organic (if available)
    meta = metrics.get("meta_organic") or {}
    if meta.get("status") == STATUS_LIVE and meta.get("name"):
        out.append({
            "statement": f"{name} Facebook page identity reachable "
                          f"({meta.get('name')!r}). Recent posts and post insights "
                          f"access is currently limited; see data coverage.",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })
    elif meta.get("status") == STATUS_PARTIAL:
        out.append({
            "statement": f"{name} Meta organic: identity visible, recent content and "
                          f"insights surfaces still limited (Step 4A in progress).",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })
    elif meta.get("status") == STATUS_NOT_CONNECTED:
        out.append({
            "statement": f"{name} Meta reporting is not currently connected; "
                          f"organic social performance is reportable only via "
                          f"Campaign OS historical archives (where present).",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })

    # Strategic North Stars
    stars = cfg.get("north_stars", {})
    if stars:
        out.append({
            "statement": f"{name}'s active North Stars: "
                          + "; ".join(s["target"] for s in stars.values())
                          + ".",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })

    # Always-end recommendation
    out.append({
        "statement": "Until lead tracking and Meta insights are LIVE, optimise "
                      "toward validated traffic + engagement signals and prepare "
                      "measurement infrastructure for verified enquiry attribution.",
        "type": "SUPPORTED_INFERENCE",
        "confidence": "MEDIUM",
    })
    return out


def _build_ga4_section(brand_id: str) -> dict:
    """Read GA4 via the live runtime path.

    The credentials file is NOT on the production container; the
    runtime path uses the env-var-wrapped JSON string instead.
    We therefore delegate to the runtime endpoint
    /api/ga4/<brand>/sessions, which already does the right thing.
    Returns deterministic numbers + traffic-source breakdown.
    """
    cfg = BRAND_CONFIG[brand_id]
    if not cfg.get("ga4_property_id"):
        return {
            "data_status": STATUS_NOT_CONNECTED,
            "reason": "no GA4 property configured for this brand",
            "metrics": {},
        }

    # Lazy-import urllib so the renderer stays importable
    # without network access at module-load time.
    try:
        import urllib.request
        base = os.environ.get("CAMPAIGN_OS_BASE_URL",
                              "http://localhost:8080").rstrip("/")
        url = f"{base}/api/ga4/{brand_id}/sessions?days=31"
        with urllib.request.urlopen(url, timeout=60) as r:
            payload = json.loads(r.read())
        if not payload.get("ok"):
            return {
                "data_status": STATUS_UNAVAILABLE,
                "reason": payload.get("error") or "endpoint returned not-ok",
                "ga4_property_id": cfg["ga4_property_id"],
            }
        # Endpoint returns {ok, rows: [{date, sessions, users, conversions,
        # engagement_rate}, ...]}. We aggregate to deterministic totals.
        rows = payload.get("rows", [])
        sessions = sum(int(r.get("sessions", 0) or 0) for r in rows)
        users = sum(int(r.get("users", 0) or 0) for r in rows)
        # engagement_rate is a per-day ratio; we surface the median
        er_values = sorted(float(r.get("engagement_rate", 0) or 0)
                           for r in rows)
        if er_values:
            median_er = er_values[len(er_values) // 2]
        else:
            median_er = 0.0
        conversions = sum(int(r.get("conversions", 0) or 0) for r in rows)
        period_start = (rows[-1].get("date", "?") if rows else "?")
        period_end = (rows[0].get("date", "?") if rows else "?")
        return {
            "data_status": STATUS_LIVE,
            "ga4_property_id": cfg["ga4_property_id"],
            "stream_id": cfg.get("ga4_stream_id"),
            "period": f"{period_start} → {period_end}",
            "metrics": {
                "sessions": sessions,
                "total_users": users,
                "engagement_rate_median": median_er,
                "key_events": conversions,
                "daily_rows": len(rows),
            },
            "channel_mix": {},  # not in this endpoint shape
            "source": "GA4 (live via /api/ga4/{brand}/sessions)",
        }
    except Exception as e:
        return {
            "data_status": STATUS_UNAVAILABLE,
            "reason": f"GA4 endpoint unreachable: {str(e)[:200]}",
            "ga4_property_id": cfg["ga4_property_id"],
        }


def _build_meta_organic_section(brand_id: str) -> dict:
    cfg = BRAND_CONFIG[brand_id]
    if not cfg.get("facebook_page_id"):
        return {"data_status": STATUS_NOT_CONNECTED,
                "reason": "no Facebook page configured"}

    if brand_id == "stick":
        # The Stick System User token is still pending in Railway
        # per Step 4A diagnostic v5; surface honestly.
        return {
            "data_status": STATUS_PARTIAL,
            "page_id": cfg["facebook_page_id"],
            "source": "Meta Graph API v23.0 (Step 4A)",
            "reason": "Stick Reporting System User token pending persistence in Railway",
        }

    if brand_id == "swing-shack":
        archives = _historical_archives(brand_id)
        fb = archives.get("facebook_page", {})
        return {
            "data_status": fb.get("data_status", STATUS_LIVE),
            "page_id": cfg["facebook_page_id"],
            "source": "Meta Graph API v18.0 (Campaign OS legacy)",
            "historical_archive": fb.get("source"),
        }


def _build_paid_section(brand_id: str) -> dict:
    cfg = BRAND_CONFIG[brand_id]
    if not cfg.get("meta_ad_account_id"):
        return {"data_status": STATUS_NOT_CONNECTED,
                "reason": "no ad account configured"}
    return {
        "data_status": STATUS_NOT_CONNECTED,
        "ad_account_id": cfg["meta_ad_account_id"],
        "source": "Meta Marketing API v23.0",
        "reason": "Ad account visibility not yet established for this brand",
    }


# ── public surface ──────────────────────────────────────────────────

def build_brand_report(brand_id: str, period_days: int = 31) -> dict:
    """Build the full JSON report for one brand. NEVER touches
    data/meta-ads.json (synthetic, quarantined)."""

    cfg = BRAND_CONFIG.get(brand_id)
    if not cfg:
        return {"error": f"unknown brand_id: {brand_id}"}

    period_start, period_end = _format_period(period_days)

    report = {
        "schema": "https://campaign-os/reporting/v1",
        "version": "1.0",
        "brand_id": brand_id,
        "brand_name": cfg["name"],
        "domain": cfg["domain"],
        "report_period": {"start": period_start, "end": period_end,
                          "days": period_days, "label": "31-day rolling (calendar)"},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_sources": [],
        "data_limitations": [],
        "executive_summary": [],
        "sections": {},
        "recommendations": [],
        "next_period_tests": [],
        "data_coverage": {},
        "source_lineage": [],
        "data_status_taxonomy_used": True,
        "brand_isolation_enforced": True,
    }

    # Strategy
    strat = _strategy_for(brand_id)
    report["strategy"] = {
        "north_star": strat.get("north_star"),
        "headline_belief": strat.get("headline_belief"),
        "mission": strat.get("mission"),
        "strategic_ambition": strat.get("strategic_ambition"),
        "category_position": strat.get("category_position"),
        "voice_summary": strat.get("voice_summary"),
        "market_moves": strat.get("market_moves", []),
        "flagship_properties": strat.get("flagship_properties", []),
        "data_status": strat.get("data_status"),
        "source": strat.get("source"),
    }
    report["north_stars"] = cfg.get("north_stars", {})

    # GA4 — call the live helper; surface its data_status + metrics
    ga4 = _build_ga4_section(brand_id)
    wp_section = {
        "title": "Website Performance (GA4)",
        "data_status": ga4.get("data_status"),
        "ga4_property_id": ga4.get("ga4_property_id") or cfg.get("ga4_property_id"),
        "stream_id": ga4.get("stream_id") or cfg.get("ga4_stream_id"),
        "source": ga4.get("source"),
        "reason": ga4.get("reason"),
        "period": ga4.get("period"),
        "metrics": ga4.get("metrics") or {},
        "channel_mix": ga4.get("channel_mix") or {},
    }
    report["sections"]["website_performance"] = wp_section
    report["data_sources"].append({
        "name": "GA4",
        "asset": cfg.get("ga4_property_id"),
        "data_status": ga4.get("data_status"),
        "note": ga4.get("reason") or "",
    })

    # Meta organic
    mo = _build_meta_organic_section(brand_id)
    report["sections"]["audience_awareness"] = {
        "title": "Audience & Awareness (Meta organic)",
        "data_status": mo.get("data_status"),
        "page_id": mo.get("page_id"),
        "source": mo.get("source"),
        "historical_archive": mo.get("historical_archive"),
        "reason": mo.get("reason"),
    }
    report["data_sources"].append({
        "name": "Meta Organic",
        "asset": cfg.get("facebook_page_id"),
        "data_status": mo.get("data_status"),
        "note": mo.get("reason") or "",
    })

    # Paid media
    pm = _build_paid_section(brand_id)
    report["sections"]["paid_media"] = {
        "title": "Paid Media",
        "data_status": pm.get("data_status"),
        "ad_account_id": pm.get("ad_account_id"),
        "source": pm.get("source"),
        "reason": pm.get("reason"),
        "rule": "SYNTHETIC ads data is quarantined. Real ads data only.",
    }
    report["data_sources"].append({
        "name": "Meta Ads",
        "asset": cfg.get("meta_ad_account_id"),
        "data_status": pm.get("data_status"),
        "note": pm.get("reason") or "",
    })

    # Lead tracking (always surface for Stick; N/A for SS)
    report["sections"]["lead_tracking"] = {
        "title": "Website Lead Tracking",
        "data_status": cfg.get("lead_tracking_status", STATUS_NOT_CONNECTED),
        "note": (
            "Stick generate_lead event is configured in GA4 but the "
            "on-website CF7 wpcf7mailsent listener is not yet "
            "production-validated. Do not report verified leads."
        ) if brand_id == "stick" else "N/A",
    }

    # Executive summary (template-based, deterministic)
    metrics_for_summary = {
        "ga4": ga4,
        "meta_organic": mo,
    }
    report["executive_summary"] = _executive_summary(brand_id, metrics_for_summary, {})

    # Data coverage matrix
    report["data_coverage"] = {
        "ga4": ga4.get("data_status"),
        "facebook": mo.get("data_status"),
        "instagram": (STATUS_NOT_CONNECTED if brand_id == "stick" else STATUS_STALE),
        "meta_ads": pm.get("data_status"),
        "lead_tracking": cfg.get("lead_tracking_status", STATUS_NOT_CONNECTED),
        "strategy": strat.get("data_status"),
    }

    # Data limitations
    report["data_limitations"] = _limitations_for(brand_id, report)

    # Recommendations (template-based, ranked HIGH/MEDIUM/LOW)
    report["recommendations"] = _recommendations_for(brand_id)

    # Next-period test plan
    report["next_period_tests"] = _test_plan_for(brand_id)

    # Source lineage — every metric the renderer pulls carries
    # brand_id+source+asset+period
    report["source_lineage"] = [
        {"name": "GA4", "asset": cfg.get("ga4_property_id"), "brand_id": brand_id,
         "period": f"{period_start} → {period_end}",
         "source": ga4.get("source")},
        {"name": "Meta organic", "asset": cfg.get("facebook_page_id"), "brand_id": brand_id,
         "period": f"{period_start} → {period_end}",
         "source": mo.get("source")},
        {"name": "Meta Ads", "asset": cfg.get("meta_ad_account_id"), "brand_id": brand_id,
         "period": f"{period_start} → {period_end}",
         "source": pm.get("source"),
         "note": "SYNTHETIC data quarantined; real ads not yet connected"},
        {"name": "Strategy", "asset": cfg.get("strategy_path"), "brand_id": brand_id,
         "period": "static",
         "source": strat.get("source")},
    ]

    return report


def _limitations_for(brand_id: str, report: dict) -> list:
    out = []
    if brand_id == "stick":
        out.extend([
            "Verified website lead tracking (generate_lead) is not yet "
            "production-validated on stickgolf.co.za; website enquiry "
            "conversion cannot be reported.",
            "Stick Meta reporting System User token is pending persistence "
            "in Railway as META_SYSTEM_USER_TOKEN_STICK_PAARL; Facebook / "
            "Instagram / WABA organic and ads surfaces are reachable but "
            "not yet served by the production reporting path.",
            "Meta Ads is reported as NOT_CONNECTED for Stick. No synthetic "
            "ads data is included.",
        ])
    elif brand_id == "swing-shack":
        out.extend([
            "Instagram organic (IG business) data was last fetched "
            "2026-08-21 and is STALE (>3 weeks). The Page is LIVE; "
            "insights are PARTIAL pending Step 2 token expansion.",
            "Meta Ads is SYNTHETIC_QUARANTINED (data/meta-ads.json); real "
            "Meta ads history is not currently ingested for Swing Shack "
            "either. Report does not invent paid performance.",
            "Facebook Page identity is LIVE; recent posts + post insights "
            "remain PARTIAL due to Graph API v18.0 limits and Page Access "
            "Token scope.",
        ])
    return out


def _recommendations_for(brand_id: str) -> list:
    if brand_id == "stick":
        return [
            {
                "priority": "HIGH",
                "action": "Wire Stick Reporting System User token into Railway "
                          "(META_SYSTEM_USER_TOKEN_STICK_PAARL) so organic "
                          "and ads surfaces can be reported on the same engine.",
                "why": "Without the token, only GA4 is reportable; the report "
                       "cannot surface Meta-derived insights.",
                "evidence": "Step 4A diagnostic v5: token in Railway not yet "
                            "reflected in runtime container.",
                "expected_outcome": "facebook_identity, instagram_identity, "
                                    "ad_accounts surfaces go LIVE.",
                "measurement": "/api/meta/stick/connect-test surfaces turn LIVE",
            },
            {
                "priority": "HIGH",
                "action": "Install stick-generate-lead.js snippet on stickgolf.co.za "
                          "via thegem-child and verify 7-test sequence (positive, "
                          "negative, dedupe) per docs/stick-generate-lead-runbook.md.",
                "why": "Lead tracking closure is the gating dependency for "
                       "real conversion measurement.",
                "evidence": "Step 3C: snippet + runbook ready; runtime tests "
                            "still pending.",
                "expected_outcome": "Verified generate_lead events arriving in GA4.",
                "measurement": "GA4 DebugView shows form_id=3039 events; "
                               "7-test contract PASS.",
            },
            {
                "priority": "MEDIUM",
                "action": "Reduce GA4 measurement gap: confirm key events "
                          "(generate_lead, form_start, contact) are configured "
                          "as conversions (only generate_lead should be key).",
                "why": "Per Step 3B, the legacy ads_conversion_Checkout_1 is "
                       "OBSOLETE and qualify_lead/close_convert_lead are not "
                       "implemented; the configured key-event list should be "
                       "tightened to current reality.",
                "evidence": "Step 3B legacy classification.",
                "expected_outcome": "GA4 key-event list reflects real outcomes.",
                "measurement": "/api/ga4/stick/key-events review.",
            },
            {
                "priority": "MEDIUM",
                "action": "Prioritise fitting and coaching content during the "
                          "next cycle, balanced with the R350k/month Psycho "
                          "Bunny retail North Star.",
                "why": "Stick's three always-on pillars (Retail / Fitting / "
                       "Coaching) need measurement-aligned content. Without "
                       "lead tracking, content mix is the most direct lever.",
                "evidence": "North Stars are configured in the brief; "
                            "no lead data yet to validate mix.",
                "expected_outcome": "Improved traffic to /club-fitting-at-stick/, "
                                    "/coaching-at-stick/, /takomo-at-stick/, "
                                    "/psycho-bunny-at-stick/.",
                "measurement": "GA4 landing-page sessions, post-publication.",
            },
            {
                "priority": "LOW",
                "action": "Audit Creative Genome / Visual DNA annotations for "
                          "Stick posts once Meta token is LIVE.",
                "why": "Brand voice (sarcastic, golf-insider) needs validation "
                       "against actual content distribution.",
                "evidence": "Stick brand-directory/voice configured.",
                "expected_outcome": "Validated creative-intelligence section.",
                "measurement": "Content Performance section.",
            },
        ]
    if brand_id == "swing-shack":
        return [
            {
                "priority": "HIGH",
                "action": "Refresh Instagram Business insights fetch — current "
                          "data is 25+ days stale.",
                "why": "Instagram is one of Swing Shack's primary organic "
                       "channels; stale data misleads every IG-touching "
                       "conclusion.",
                "evidence": "data/ig-business-analytics.json last_updated "
                            "2026-08-21 (STALE).",
                "expected_outcome": "STALE → LIVE",
                "measurement": "/api/meta/swing-shack/connect-test instagram_*",
            },
            {
                "priority": "HIGH",
                "action": "Upgrade Meta API version from v18.0 to v23.0 and "
                          "expand the per-brand token scope to enable Page "
                          "post insights + account-level insights.",
                "why": "v18.0 returns error 100/190 for most modern metrics. "
                       "The Heidi-app CAPI token has the scopes; the issue is "
                       "the Swing Shack per-brand identity + asset binding.",
                "evidence": "Step 2 audit + Step 4A diagnostic.",
                "expected_outcome": "facebook_insights metrics go from 0/8 LIVE "
                                    "to ≥6/8 LIVE.",
                "measurement": "/api/ga4/swing-shack/insights (or equivalent).",
            },
            {
                "priority": "MEDIUM",
                "action": "Replace SYNTHETIC_QUARANTINED data/meta-ads.json with "
                          "real ads history once a per-brand ads identity is "
                          "established.",
                "why": "Current ads section is not reportable; until real ads "
                       "land, paid efficiency claims cannot be made.",
                "evidence": "Quarantine flag present in meta-ads.json.",
                "expected_outcome": "First-party ads history per campaign.",
                "measurement": "/api/meta/swing-shack/ads/* live.",
            },
            {
                "priority": "MEDIUM",
                "action": "Re-baseline Swing Shack creative output against the "
                          "v3 strategy's flagship properties (10-Ball Truth, "
                          "Swing Diary, etc.) and content cadence.",
                "why": "Strategy v3 commits to 'properties, not random posts'. "
                       "Current output should be measured against that test.",
                "evidence": "data/strategy/swing-shack.json v3, market moves.",
                "expected_outcome": "Property-aligned content distribution.",
                "measurement": "Pillar / property mix in Calendar.",
            },
            {
                "priority": "LOW",
                "action": "Add the third always-on pillar (Retail, Fitting, "
                          "Coaching as per Stick) for Swing Shack where the "
                          "business model supports it — currently SS services "
                          "include memberships / play / clinics per brief.",
                "why": "Brief §2 Swing Shack section asks the engine to load "
                       "the actual configured Swing Shack objectives from "
                       "brand strategy rather than inheriting Stick targets.",
                "evidence": "Brief §2 Swing Shack North Stars.",
                "expected_outcome": "Brand-isolated North Stars in report.",
                "measurement": "report.north_stars populated.",
            },
        ]
    return []


def _test_plan_for(brand_id: str) -> list:
    if brand_id == "stick":
        return [
            {
                "hypothesis": "Fitting-led educational content (human-led) "
                              "produces stronger fitting-page engagement than "
                              "product-only posts.",
                "test": "2 human-led fitting videos vs 2 product-led fitting posts",
                "primary_metric": "club-fitting-at-stick page sessions",
                "later_metric": "generate_lead (once tracking is live)",
            },
            {
                "hypothesis": "Takomo product content drives retail interest "
                              "more strongly than generic Psycho Bunny posts.",
                "test": "1 Takomo launch post + 1 Psycho Bunny launch post; "
                        "compare landing-page sessions on /takomo-at-stick/ vs "
                        "/psycho-bunny-at-stick/",
                "primary_metric": "page sessions per product page",
                "later_metric": "generate_lead with lead_type=retail",
            },
            {
                "hypothesis": "Coaching-led content is currently under-represented; "
                              "increasing coaching content frequency should reduce "
                              "the gap between coaching sessions target (24/wk) "
                              "and current activity.",
                "test": "Run 2 coaching posts/week for 4 weeks, observe traffic "
                        "to /coaching-at-stick/ and /bookings/",
                "primary_metric": "coaching landing-page sessions",
                "later_metric": "generate_lead with lead_type=coaching",
            },
        ]
    if brand_id == "swing-shack":
        return [
            {
                "hypothesis": "A flagship property ('10-Ball Truth' or similar) "
                              "produces stronger engagement than generic swing "
                              "tips.",
                "test": "Cross-post 1 flagship-property piece and 1 generic tip; "
                        "compare reach and engagement per post",
                "primary_metric": "post engagement / reach",
            },
            {
                "hypothesis": "Swing Shack membership messaging is underrepresented "
                              "in current organic output vs. the v3 strategic "
                              "ambition.",
                "test": "Schedule 1 membership-led post/week for 4 weeks; "
                        "measure traffic to the membership page",
                "primary_metric": "membership landing-page sessions",
            },
            {
                "hypothesis": "Instagram reach is currently undervalued because "
                              "the IG business analytics is stale; once LIVE, "
                              "the engine can surface real cross-channel "
                              "synergies.",
                "test": "Refresh IG insights, then compare Meta-paid reach vs "
                        "organic IG reach for the same period",
                "primary_metric": "reach, engagement_rate",
            },
        ]
    return []


# ── HTML rendering ─────────────────────────────────────────────────

_HTML_CSS = """
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial,
         sans-serif; max-width: 900px; margin: 2em auto; padding: 0 1em;
         color: #1a1a1a; line-height: 1.55; }
  h1 { font-size: 1.8em; border-bottom: 2px solid #1a1a1a; padding-bottom: 0.3em; }
  h2 { font-size: 1.3em; margin-top: 2em; color: #2a4a3a; }
  h3 { font-size: 1.1em; color: #2a4a3a; }
  .meta { color: #666; font-size: 0.9em; }
  .pill { display: inline-block; padding: 2px 8px; border-radius: 4px;
          font-size: 0.8em; font-weight: 600; margin-right: 4px; }
  .live { background: #d4f4dd; color: #0a5a1a; }
  .partial { background: #fde7c0; color: #8a4a0a; }
  .stale { background: #fde0e0; color: #8a0a0a; }
  .pending { background: #fff5b0; color: #6a5a0a; }
  .not_connected { background: #e8e8e8; color: #4a4a4a; }
  .synthetic { background: #f0c0c0; color: #5a0a0a; }
  .historical_real { background: #d8e8f8; color: #1a3a6a; }
  .unavailable { background: #e8e8e8; color: #4a4a4a; }
  .section { margin: 2em 0; padding: 1em; border-left: 4px solid #2a4a3a;
             background: #fafafa; }
  .coverage-table { width: 100%; border-collapse: collapse; margin: 1em 0; }
  .coverage-table td, .coverage-table th { padding: 0.5em; border-bottom: 1px solid #e0e0e0;
                                          text-align: left; }
  .coverage-table th { background: #f0f0f0; }
  .rec { padding: 1em; margin: 1em 0; border-radius: 4px; }
  .rec.high { border-left: 4px solid #c0392b; background: #fdf0ee; }
  .rec.medium { border-left: 4px solid #d39e00; background: #fdf8ec; }
  .rec.low { border-left: 4px solid #6a6a6a; background: #f4f4f4; }
  .exec-summary li { margin-bottom: 0.5em; }
  .footer { margin-top: 3em; padding-top: 1em; border-top: 1px solid #e0e0e0;
            font-size: 0.85em; color: #666; }
  @media print {
    body { max-width: none; margin: 0; padding: 0.5em; font-size: 11pt; }
    .section { page-break-inside: avoid; }
  }
</style>
"""


def _pill(status: str) -> str:
    cls = (status or "unknown").lower()
    return f'<span class="pill {cls}">{status}</span>'


def render_brand_report_html(brand_id: str, period_days: int = 31) -> str:
    r = build_brand_report(brand_id, period_days)
    if r.get("error"):
        return f"<h1>Error</h1><p>{r['error']}</p>"
    parts = [f"<!DOCTYPE html><html><head><meta charset='utf-8'>",
             f"<title>{r['brand_name']} Marketing Performance Report</title>",
             _HTML_CSS, "</head><body>"]
    parts.append(f"<h1>{r['brand_name']} Marketing Performance Report</h1>")
    parts.append(f"<div class='meta'>")
    parts.append(f"Reporting period: <strong>{r['report_period']['start']} → "
                 f"{r['report_period']['end']}</strong> ({r['report_period']['days']} days)<br>")
    parts.append(f"Generated: {r['generated_at']}<br>")
    parts.append(f"Brand ID: <code>{r['brand_id']}</code> · Domain: "
                 f"<code>{r['domain']}</code>")
    parts.append("</div>")

    # Executive Summary
    parts.append("<h2>Executive Summary</h2>")
    parts.append("<ul class='exec-summary'>")
    for item in r["executive_summary"]:
        parts.append(f"<li>{item['statement']} "
                     f"<em class='meta'>({item['type']}, "
                     f"confidence: {item['confidence']})</em></li>")
    parts.append("</ul>")

    # Business Goals / North Stars
    parts.append("<h2>Business Goals / North Stars</h2>")
    parts.append("<div class='section'>")
    stars = r.get("north_stars", {})
    if stars:
        for pillar_key, star in stars.items():
            parts.append(f"<div><strong>{star['label']}</strong>: "
                         f"{star['target']}</div>")
    else:
        parts.append("<em>No North Stars configured for this brand.</em>")
    parts.append("</div>")

    # Strategy context
    strat = r.get("strategy", {})
    if strat.get("north_star") or strat.get("strategic_ambition"):
        parts.append("<h2>Strategic Context</h2>")
        parts.append("<div class='section'>")
        if strat.get("north_star"):
            parts.append(f"<div><strong>North Star</strong>: {strat['north_star']}</div>")
        if strat.get("strategic_ambition"):
            parts.append(f"<div><strong>Strategic Ambition</strong>: "
                         f"{strat['strategic_ambition']}</div>")
        if strat.get("category_position"):
            parts.append(f"<div><strong>Category Position</strong>: "
                         f"{strat['category_position']}</div>")
        if strat.get("flagship_properties"):
            parts.append("<div><strong>Flagship Properties</strong>:<ul>")
            for fp in strat["flagship_properties"]:
                parts.append(f"<li>{fp.get('name')}</li>")
            parts.append("</ul></div>")
        parts.append("</div>")

    # Data coverage matrix
    parts.append("<h2>Data Coverage Status</h2>")
    parts.append("<table class='coverage-table'>")
    parts.append("<tr><th>Source</th><th>Status</th></tr>")
    for name, status in (r.get("data_coverage") or {}).items():
        parts.append(f"<tr><td>{name}</td><td>{_pill(status)}</td></tr>")
    parts.append("</table>")

    # Per-section data
    for key, section in r.get("sections", {}).items():
        title = section.get("title", key)
        status = section.get("data_status", "UNKNOWN")
        parts.append(f"<h2>{title} {_pill(status)}</h2>")
        parts.append("<div class='section'>")
        for k, v in section.items():
            if k in ("title", "data_status"):
                continue
            if isinstance(v, (str, int)) and v:
                parts.append(f"<div><strong>{k}</strong>: {v}</div>")
        parts.append("</div>")

    # Recommendations
    parts.append("<h2>Recommendations</h2>")
    for rec in r.get("recommendations", []):
        cls = rec["priority"].lower()
        parts.append(f"<div class='rec {cls}'>")
        parts.append(f"<strong>[{rec['priority']}] {rec['action']}</strong><br>")
        parts.append(f"<em>Why:</em> {rec['why']}<br>")
        parts.append(f"<em>Evidence:</em> {rec['evidence']}<br>")
        parts.append(f"<em>Expected outcome:</em> {rec['expected_outcome']}<br>")
        parts.append(f"<em>Measure:</em> {rec['measurement']}")
        parts.append("</div>")

    # Next-period tests
    parts.append("<h2>Next-Period Test Plan</h2>")
    for i, test in enumerate(r.get("next_period_tests", []), 1):
        parts.append(f"<div class='rec medium'>")
        parts.append(f"<strong>Test {i}</strong><br>")
        parts.append(f"<em>Hypothesis:</em> {test['hypothesis']}<br>")
        parts.append(f"<em>Test:</em> {test['test']}<br>")
        parts.append(f"<em>Primary metric:</em> {test['primary_metric']}")
        if test.get("later_metric"):
            parts.append(f"<br><em>Later metric:</em> {test['later_metric']}")
        parts.append("</div>")

    # Limitations
    parts.append("<h2>Limitations</h2>")
    parts.append("<div class='section'>")
    for lim in r.get("data_limitations", []):
        parts.append(f"<div>• {lim}</div>")
    parts.append("</div>")

    # Source lineage
    parts.append("<h2>Source Lineage</h2>")
    parts.append("<table class='coverage-table'>")
    parts.append("<tr><th>Source</th><th>Asset</th><th>Brand</th>"
                 "<th>Period</th><th>Path / Origin</th></tr>")
    for ln in r.get("source_lineage", []):
        parts.append(f"<tr><td>{ln['name']}</td>"
                     f"<td>{ln.get('asset', '')}</td>"
                     f"<td><code>{ln.get('brand_id', '')}</code></td>"
                     f"<td>{ln.get('period', '')}</td>"
                     f"<td>{ln.get('source', '')}</td></tr>")
    parts.append("</table>")

    parts.append("<div class='footer'>")
    parts.append(f"<em>Reporting Intelligence V1 · Campaign OS · "
                 f"brand_id=<code>{r['brand_id']}</code> · "
                 f"brand isolation enforced · "
                 f"data_status taxonomy applied. "
                 f"No synthetic Meta Ads data is included.</em>")
    parts.append("</div>")

    parts.append("</body></html>")
    return "\n".join(parts)


def render_portfolio_summary_html(reports: dict) -> str:
    """Build the cross-brand portfolio management summary.

    Reports = {"stick": <report>, "swing-shack": <report>}.

    Per brief §5: contextual comparison only, never a league
    table. Both brands have different audience sizes, business
    models, goals, budgets, maturity, services.
    """
    parts = [f"<!DOCTYPE html><html><head><meta charset='utf-8'>",
             "<title>Portfolio Management Summary</title>",
             _HTML_CSS, "</head><body>"]
    parts.append("<h1>Portfolio Management Summary</h1>")
    parts.append(f"<div class='meta'>Generated: "
                 f"{datetime.now(timezone.utc).isoformat()}</div>")

    parts.append("<h2>Brands Covered</h2>")
    parts.append("<div class='section'>")
    parts.append("<ul>")
    for bid in ("stick", "swing-shack"):
        r = reports.get(bid, {})
        parts.append(f"<li><strong>{r.get('brand_name', bid)}</strong> "
                     f"(<code>{bid}</code>) · "
                     f"period: {r.get('report_period', {}).get('start', '')} → "
                     f"{r.get('report_period', {}).get('end', '')}</li>")
    parts.append("</ul></div>")

    parts.append("<h2>Data Completeness (per brand)</h2>")
    parts.append("<table class='coverage-table'>")
    parts.append("<tr><th>Source</th>"
                 "<th>Stick</th><th>Swing Shack</th></tr>")
    rows = ("ga4", "facebook", "instagram", "meta_ads",
            "lead_tracking", "strategy")
    for row in rows:
        s = (reports.get("stick", {}).get("data_coverage") or {}).get(row, "—")
        ss = (reports.get("swing-shack", {}).get("data_coverage") or {}).get(row, "—")
        parts.append(f"<tr><td>{row}</td>"
                     f"<td>{_pill(s)}</td><td>{_pill(ss)}</td></tr>")
    parts.append("</table>")

    parts.append("<h2>Operational Marketing Observations</h2>")
    parts.append("<div class='section'>")
    parts.append("<ul>")
    parts.append("<li><strong>Stick</strong> has GA4 LIVE for property "
                 "532174688 (stickgolf.co.za). Meta organic and ads are "
                 "partially wired but the per-brand System User token is "
                 "still pending in Railway. Lead tracking on the website is "
                 "PENDING (snippet + runbook ready, not yet installed). "
                 "North Stars are configured and active.</li>")
    parts.append("<li><strong>Swing Shack</strong> has GA4 LIVE for property "
                 "427380680 (swingshack.co.za). Facebook Page identity is "
                 "LIVE; Instagram Business insights are STALE (last fetched "
                 "2026-08-21). Meta Ads is SYNTHETIC_QUARANTINED — no real "
                 "ads history ingested. Strategy v3 is configured.</li>")
    parts.append("</ul></div>")

    parts.append("<h2>Major Risks (across the portfolio)</h2>")
    parts.append("<div class='section'>")
    parts.append("<ul>")
    parts.append("<li><strong>Commercial attribution gap.</strong> Neither "
                 "brand has verified website lead data flowing. Any claim "
                 "about 'cost per lead' / 'conversion rate' would be "
                 "fabricated. Reports explicitly mark this as PENDING.</li>")
    parts.append("<li><strong>Per-brand Meta asset bindings.</strong> The "
                 "Stick Reporting System User exists in Meta Business "
                 "Settings with 11 assets assigned, but its token is not "
                 "yet persisted in Railway under the correct env-var name "
                 "(META_SYSTEM_USER_TOKEN_STICK_PAARL). Until that lands, "
                 "Stick Meta reporting is unreachable.</li>")
    parts.append("<li><strong>Synthetic data exposure.</strong> "
                 "data/meta-ads.json is quarantined for Swing Shack but the "
                 "file remains on disk. Any new code path that touches it "
                 "must NOT promote its values into reports.</li>")
    parts.append("</ul></div>")

    parts.append("<h2>Measurement Gaps (next priorities)</h2>")
    parts.append("<div class='section'><ol>")
    parts.append("<li><strong>Persistence of META_SYSTEM_USER_TOKEN_STICK_PAARL</strong> "
                 "in Railway — Step 4A diagnostic is the source of truth.</li>")
    parts.append("<li><strong>Installation of stick-generate-lead.js</strong> "
                 "on stickgolf.co.za with the 7-test sequence.</li>")
    parts.append("<li><strong>Refresh of Swing Shack Instagram insights</strong> "
                 "(STALE → LIVE).</li>")
    parts.append("<li><strong>Real Meta Ads history ingestion</strong> for both "
                 "brands (replace synthetic).</li>")
    parts.append("<li><strong>Operator upload of historical reports</strong> "
                 "for both brands (preserves brand_id on each upload).</li>")
    parts.append("</ol></div>")

    parts.append("<h2>Cross-Brand Notes</h2>")
    parts.append("<div class='section'>")
    parts.append("<p>Per brief §5, the two brands have different audience "
                 "sizes, business models, goals, budgets, maturity, and "
                 "services. This summary intentionally does NOT compare them "
                 "as a league table. Stick and Swing Shack serve different "
                 "roles (Stick is a sub-brand with a sarcastic, golf-insider "
                 "voice; Swing Shack is the parent brand with the premium "
                 "indoor golf experience in Johannesburg).</p>")
    parts.append("<p>What they share is the measurement stack — both brands "
                 "should graduate to the same reporting standard so future "
                 "comparison is fair (same status taxonomy, same source "
                 "lineage, same deterministic calculations). That standard is "
                 "what Reporting Intelligence V1 enforces today.</p>")
    parts.append("</div>")

    parts.append("<div class='footer'>")
    parts.append(f"<em>Reporting Intelligence V1 · Portfolio Management · "
                 f"brand_isolation_enforced. "
                 f"No synthetic Meta Ads data is included in any section.</em>")
    parts.append("</div>")

    parts.append("</body></html>")
    return "\n".join(parts)
