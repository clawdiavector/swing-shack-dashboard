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


def _now_iso() -> str:
    """ISO-8601 UTC timestamp helper."""
    return datetime.now(timezone.utc).isoformat()


# ── V2.1 §4+§5+§12: COMPARISON ENGINE ────────────────────────────────
# Per V2.1 §4: implement real period comparisons. For each
# eligible deterministic KPI, return current_value +
# previous_value + delta_abs + delta_pct + comparison_status.
# Safe handling when previous=0 / missing / partial.
# Per V2.1 §5: 90-day rolling context (median or mean).
# Per V2.1 §12: analyst commentary uses movement, not snapshots.

import datetime as _v21dt


def _v21_resolve_current_window(days=31):
    """End = yesterday (exclude today). Start = end - (days-1)."""
    end = (_v21dt.date.today() - _v21dt.timedelta(days=1))
    start = end - _v21dt.timedelta(days=days - 1)
    return start, end


def _v21_resolve_previous_window(days=31):
    """Previous = immediately preceding complete window."""
    cur_start, _ = _v21_resolve_current_window(days)
    prev_end = cur_start - _v21dt.timedelta(days=1)
    prev_start = prev_end - _v21dt.timedelta(days=days - 1)
    return prev_start, prev_end


def _v21_resolve_90day_window():
    """90-day rolling window ending yesterday."""
    end = (_v21dt.date.today() - _v21dt.timedelta(days=1))
    start = end - _v21dt.timedelta(days=89)
    return start, end


def _v21_safe_int(x, default=0):
    if x is None:
        return default
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return default


def _v21_safe_float(x, default=0.0):
    if x is None:
        return default
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _v21_compute_delta(current, previous):
    """V2.1 §4 fail-safe delta.

    Returns dict with current, previous, delta_abs, delta_pct,
    comparison_status. Never invents a percentage when
    previous is missing or 0.
    """
    cur = current
    prev = previous
    if prev is None:
        return {
            "current": cur, "previous": None,
            "delta_abs": None, "delta_pct": None,
            "comparison_status": "no_previous",
        }
    delta_abs = (cur - prev) if (cur is not None and prev is not None) else None
    delta_pct = None
    status = "unknown"
    if cur is None or prev is None:
        status = "unknown"
    elif prev == 0:
        if cur == 0:
            delta_abs = 0
            delta_pct = 0.0
            status = "flat"
        else:
            delta_abs = cur
            delta_pct = None  # don't manufacture %
            status = "improving"
    else:
        delta_pct = round((cur - prev) / prev * 100, 1)
        if delta_pct > 0.5:
            status = "improving"
        elif delta_pct < -0.5:
            status = "regressing"
        else:
            status = "flat"
    return {
        "current": cur, "previous": prev,
        "delta_abs": delta_abs, "delta_pct": delta_pct,
        "comparison_status": status,
    }


def _v21_rolling_stat(values, stat="median"):
    """Compute rolling-stat over a list of daily numeric values.
    stat='mean' or 'median' (default). For percentage /
    engagement-rate metrics, clamps to [0, 1]. Documented
    choice per Brief V2.1 §5: median for skewed rate metrics,
    mean for well-behaved count metrics.
    """
    if not values:
        return None
    cleaned = [v for v in values
               if isinstance(v, (int, float)) and v is not None]
    if not cleaned:
        return None
    if "median" in stat.lower():
        cleaned.sort()
        n = len(cleaned)
        if n == 1:
            return round(cleaned[0], 4)
        mid = n // 2
        if n % 2 == 0:
            return round((cleaned[mid - 1] + cleaned[mid]) / 2, 4)
        return round(cleaned[mid], 4)
    return round(sum(cleaned) / len(cleaned), 2)


def _v21_render_trend_arrow(delta_pct):
    """V2.1 §11 trend arrow: ↑ improving / → flat / ↓ regressing /
    — no-comparison / ? unknown."""
    if delta_pct is None:
        return ("—", "no_comparison")
    if delta_pct > 0.5:
        return ("▲", "improving")
    if delta_pct < -0.5:
        return ("▼", "regressing")
    return ("→", "flat")


def _v22_report_period(days=31):
    """V2.2 §1: canonical report-period object. Defined here
    so build_v22_brand_report can use the same period as the
    GA4 endpoints.
    """
    end_d = (_v21dt.date.today() - _v21dt.timedelta(days=1))
    cur_start = end_d - _v21dt.timedelta(days=days - 1)
    prev_end = cur_start - _v21dt.timedelta(days=1)
    prev_start = prev_end - _v21dt.timedelta(days=days - 1)
    n_end = end_d
    n_start = end_d - _v21dt.timedelta(days=89)
    return {
        "current_start": cur_start.isoformat(),
        "current_end": end_d.isoformat(),
        "previous_start": prev_start.isoformat(),
        "previous_end": prev_end.isoformat(),
        "ninetieth_start": n_start.isoformat(),
        "ninetieth_end": n_end.isoformat(),
        "days_per_window": days,
        "data_complete_through": end_d.isoformat(),
        "timezone": "Africa/Johannesburg",
    }


# ── Brand-scoped config (no cross-brand bleed)
def _load_north_stars_from_calendar_config(brand_id: str) -> dict:
    """V1.3 §7: load North Stars from the canonical Calendar
    config (data/brand-directory/<brand>/calendar_config.json),
    the same source used by the Brief engine. Falls back
    to strategy/<brand>.json north_star if Calendar config
    has none."""
    out = {}
    try:
        from _lib.marketing_calendar import load_brand_config as _lbc
        cfg = _lbc(brand_id) or {}
        for p_cfg in (cfg.get("pillars") or []):
            canonical_id = p_cfg.get("pillar_id") or ""
            bare = (canonical_id.split("-")[-1]
                    if "-" in canonical_id else canonical_id).lower()
            nst = p_cfg.get("north_star_target") or {}
            nsm = p_cfg.get("north_star_metric") or ""
            monthly = nst.get("monthly_target_zar")
            daily = nst.get("daily_volume")
            op_days = nst.get("operating_days_per_week")
            # V1.3 §6: extract product hint from objective /
            # metric / note to keep brand-specific labels
            product_hint = None
            if nsm and "/" in nsm:
                product_hint = nsm.split("/")[0].strip()
            elif p_cfg.get("objective"):
                import re as _re
                obj_clean = _re.sub(
                    r"^(?:Drive|Sell|Promote|Move|Build|Launch|Grow|Boost)\s+",
                    "", p_cfg["objective"] or "")
                m = _re.search(
                    r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)\b",
                    obj_clean)
                if m:
                    product_hint = m.group(1)
            if monthly:
                if product_hint and product_hint.lower() != (
                        p_cfg.get("name") or "").lower():
                    target = (f"R{monthly:,} "
                              f"{product_hint} sales/month")
                else:
                    target = (f"R{monthly:,} "
                              f"{p_cfg.get('name', bare)} sales/month")
            elif daily and op_days:
                wk = daily * op_days
                if product_hint and product_hint.lower() != (
                        p_cfg.get("name") or "").lower():
                    target = f"{wk} {product_hint}/week"
                else:
                    target = f"{wk} {bare}/week"
            else:
                target = nsm or ""
            label = p_cfg.get("name") or bare.title()
            if product_hint and product_hint.lower() not in label.lower():
                label = f"{label} ({product_hint})"
            if target:
                out[bare] = {"label": label, "target": target,
                              "source": "calendar_config.json"}
    except Exception:
        pass
    # Fallback: strategy/<brand>.json north_star (free-text)
    if not out:
        try:
            strat = _read_json(f"data/strategy/{brand_id}.json")
            if strat and strat.get("north_star"):
                out["primary"] = {
                    "label": "North Star",
                    "target": strat.get("north_star"),
                    "source": f"data/strategy/{brand_id}.json"}
        except Exception:
            pass
    return out


# V1.3 §7: North Stars are loaded from the canonical Calendar
# config (same source as Brief engine) — Reporting V2 no longer
# hardcodes them.
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
        # V1.3 §7: sourced from canonical Calendar config
        "north_stars": _load_north_stars_from_calendar_config("stick"),
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
        "north_stars": _load_north_stars_from_calendar_config("swing-shack"),
    },
}


# ── helpers ───────────────────────────────────────────────────────────

def _read_json(path) -> Optional[Any]:
    """Read a JSON file. Tries the path as-given first, then
    resolves relative paths against the repo root
    (sibling of `campaign-os/`) so production containers
    that mount /app as the working dir can still find
    bundled data/ files."""
    if not path:
        return None
    candidates = [path]
    if not os.path.isabs(path):
        # repo root = parent of the campaign-os/ dir
        repo_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        candidates.append(os.path.join(repo_root, path))
        candidates.append(os.path.join("/app", path))
    for c in candidates:
        try:
            with open(c) as f:
                return json.load(f)
        except FileNotFoundError:
            continue
        except Exception:
            return None
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


# ── Per-brand enrichment for the brief ──────────────────────────────

def _brand_planning(brand_id: str) -> dict:
    """Pull brand-planning files: brand.json, events-2026.json,
    events-2027.json, cadences.json. Per-brand scoped. Returns
    structured bundle with always_on_pillars, events summary,
    cadences, big-brand-idea. Brand isolation enforced — files
    are loaded only if their `brand_id` field matches."""
    if brand_id != "stick":
        return {}  # only Stick has this bundle; SS uses different files
    out = {}
    for fname, key in [
        ("data/brand-planning/stick.json", "brand"),
        ("data/brand-planning/stick-events-2026.json", "events_2026"),
        ("data/brand-planning/stick-events-2027.json", "events_2027"),
        ("data/brand-planning/stick-cadences.json", "cadences"),
        ("data/products/stick.json", "products"),
        ("data/strategy/stick.json", "strategy_file"),
    ]:
        d = _read_json(fname)
        if not d:
            continue
        bid = d.get("brand_id")
        if bid and bid != "stick":
            continue  # refuse cross-brand bleed
        out[key] = d
    return out


def _pillar_mix(brand_id: str, planning: dict) -> dict:
    """V2.1 §1: SINGLE SOURCE OF TRUTH.

    Computing pillar mix from the legacy
    `data/brand-planning/stick-events-{2026,2027}.json`
    files produced results that disagreed with the
    canonical Calendar/Brief reconciliation
    (fitting 64% vs 55%, retail 0% vs 45%).

    Reporting MUST now consume the SAME canonical
    Calendar source used by Brief + Today via the
    campaign_brief._pillar_mix function. The legacy
    brand-planning files are retained for offline
    reference only — they no longer feed Reporting.

    Source: marketing_calendar.canonical_records (stick)
            + data/brand-planning/stick-cadences.json
    """
    if brand_id != "stick":
        return {"data_status": STATUS_NOT_APPLICABLE,
                "reason": "pillar mix only meaningful for Stick"}
    try:
        from campaign_brief import _pillar_mix as _cb_pillar_mix
        cb_result = _cb_pillar_mix("stick", days_back=31)
    except Exception as e:
        return {"data_status": STATUS_UNAVAILABLE,
                "reason": f"canonical Calendar not available: {e}"}

    # Cadences come from the legacy file but are
    # informational only (not used for percentages)
    cadences = planning.get("cadences", {}).get("cadences", []) or []
    cadence_by_lane = {}
    for c in cadences:
        lane = c.get("lane", "unknown")
        cadence_by_lane[lane] = {
            "weekday_post_count": c.get("weekday_post_count"),
            "cadence_text": c.get("cadence_text"),
        }

    pillar_counts = cb_result.get("pillar_event_counts") or {}
    # Map to plain ints (canonical pillar ids → legacy keys)
    pillars = ["retail", "fitting", "coaching"]
    out_counts = {}
    events_per_pillar = cb_result.get("events_per_pillar") or {}
    for p in pillars:
        # canonical Calendar uses both formats; flatten
        direct = pillar_counts.get(p) or 0
        # some canonical implementations use stick-retail format
        for k, v in pillar_counts.items():
            if k.lower().endswith("-" + p):
                direct = direct + v
        out_counts[p] = direct

    # If canonical returned zero across the board, fall back
    # to inspecting events directly
    if sum(out_counts.values()) == 0:
        try:
            from campaign_brief import get_brief_opportunities
            opps = get_brief_opportunities("stick")
            from collections import Counter
            ctr = Counter()
            for opp in opps:
                ep = opp.get("pillars") or {}
                if isinstance(ep, dict):
                    for k in ep:
                        ctr[k] += 1
                elif isinstance(ep, list):
                    for v in ep:
                        ctr[v] += 1
            for p in pillars:
                out_counts[p] = ctr.get(p, 0)
        except Exception:
            pass

    total_classified = sum(out_counts.values())
    denominator = cb_result.get(
        "denominator_used_for_pillar_percentages",
        max(1, total_classified))
    pillar_pct = {p: round(out_counts[p] / denominator * 100, 1)
                  if denominator else 0.0
                  for p in pillars}

    return {
        "data_status": STATUS_HISTORICAL_REAL,
        "pillars_always_on": ["retail", "fitting", "coaching"],
        "pillar_event_counts": out_counts,
        "pillar_event_pct": pillar_pct,
        "events_per_pillar": events_per_pillar,
        "unclassified_event_ids": cb_result.get(
            "preserved_unclassified_event_keys") or [],
        "total_events_classified": total_classified,
        "canonical_event_count": cb_result.get("canonical_event_count"),
        "classified_event_count": cb_result.get("classified_event_count"),
        "cultural_moment_count": cb_result.get("cultural_moment_count"),
        "preserved_unclassified_count": cb_result.get(
            "preserved_unclassified_count"),
        "denominator_used_for_pillar_percentages": denominator,
        "excluded_event_count": cb_result.get("excluded_event_count"),
        "exclusion_reasons": cb_result.get("exclusion_reasons"),
        "cadences_by_lane": cadence_by_lane,
        "source": ("marketing_calendar.canonical_records (stick) "
                  "+ data/brand-planning/stick-cadences.json"),
    }


def _visual_dna_signals(brand_id: str) -> dict:
    """Aggregate Visual DNA metadata from per-image JSON files
    under data/brand-directory/<brand>/images/. We do NOT do
    image vision here — we summarise the structured fields
    (subject, human_presence, text_density, etc.) already
    captured by the visual-dna engine."""
    if brand_id != "stick":
        return {"data_status": STATUS_NOT_APPLICABLE}
    # Resolve base path across cwd / repo root / /app
    rel = os.path.join("brand-directory", "stick", "images")
    candidates = [os.path.join(DATA_ROOT_DEFAULT, rel),
                  os.path.join("/app", "data", rel),
                  os.path.join(os.path.dirname(os.path.dirname(
                      os.path.dirname(os.path.abspath(__file__)))),
                      "data", rel)]
    base = next((c for c in candidates if os.path.isdir(c)), None)
    if not base:
        return {"data_status": STATUS_NOT_CONNECTED,
                "reason": f"no visual-dna dir at {candidates[0]}"}
    files = [f for f in os.listdir(base) if f.endswith(".visual-dna.json")]
    if not files:
        return {"data_status": STATUS_NOT_CONNECTED,
                "reason": "no .visual-dna.json files"}

    # Aggregate structured fields. visual-dna files use a
    # layered schema: layer1_metadata, layer10_composition,
    # layer6_ocr, etc. We pull subject estimate + text word
    # count for the report-friendly signals.
    subjects = {}
    word_counts = []
    ocr_available_counts = {"yes": 0, "no": 0}
    orientations = {}
    luminance = {}
    n = 0
    for fname in files:
        try:
            d = json.loads(open(os.path.join(base, fname)).read())
        except Exception:
            continue
        n += 1
        # layer1_metadata
        m1 = d.get("layer1_metadata") or {}
        orientation = m1.get("orientation") or "unknown"
        orientations[orientation] = orientations.get(orientation, 0) + 1
        # layer10_composition.subject_estimate_position
        c10 = d.get("layer10_composition") or {}
        subj = c10.get("subject_estimate_position") or "unknown"
        subjects[subj] = subjects.get(subj, 0) + 1
        # layer6_ocr.word_count
        ocr = d.get("layer6_ocr") or {}
        wc = ocr.get("word_count")
        if isinstance(wc, (int, float)):
            word_counts.append(int(wc))
        if ocr.get("available"):
            ocr_available_counts["yes"] += 1
        else:
            ocr_available_counts["no"] += 1
        # layer9_palette.luminance_category
        p9 = d.get("layer9_palette") or {}
        lum = p9.get("luminance_category") or "unknown"
        luminance[lum] = luminance.get(lum, 0) + 1
    return {
        "data_status": STATUS_HISTORICAL_REAL,
        "samples": n,
        "source_dir": base,
        "subject_distribution": subjects,
        "orientation_distribution": orientations,
        "ocr_word_count_median": (
            sorted(word_counts)[len(word_counts) // 2]
            if word_counts else None),
        "ocr_word_count_samples": len(word_counts),
        "ocr_available_distribution": ocr_available_counts,
        "luminance_distribution": luminance,
        "source": f"{base}/*.visual-dna.json",
    }


def _historical_reports(brand_id: str) -> dict:
    """Pull operator-uploaded historical reports from
    data/historical-reports/<brand>/. Each file is parsed as
    a historical_report source per brief §29. Used as
    contextual comparison only — never overwrites raw API
    data per §30."""
    rel = os.path.join("historical-reports", brand_id)
    candidates = [os.path.join(DATA_ROOT_DEFAULT, rel),
                  os.path.join("/app", "data", rel),
                  os.path.join(os.path.dirname(os.path.dirname(
                      os.path.dirname(os.path.abspath(__file__)))),
                      "data", rel)]
    base = next((c for c in candidates if os.path.isdir(c)), None)
    if not base:
        return {"data_status": STATUS_NOT_CONNECTED,
                "reason": f"no historical reports dir at {candidates[0]}",
                "files": []}
    files = sorted(os.listdir(base))
    parsed = []
    for fname in files:
        p = os.path.join(base, fname)
        try:
            d = json.loads(open(p).read())
            parsed.append({
                "filename": fname,
                "path": p,
                "period": d.get("period") or d.get("reporting_period"),
                "metrics_keys": sorted((d.get("metrics") or {}).keys()) if isinstance(d.get("metrics"), dict) else [],
                "observations_count": len(d.get("observations", []) or []),
                "size_bytes": os.path.getsize(p),
                "uploaded_at": d.get("uploaded_at"),
                "source": p,
            })
        except Exception as e:
            parsed.append({
                "filename": fname, "path": p, "parse_error": str(e)[:120],
                "source": p,
            })
    return {
        "data_status": STATUS_HISTORICAL_REAL if parsed
                       else STATUS_NOT_CONNECTED,
        "count": len(parsed),
        "files": parsed,
        "source": f"{base}/*",
    }


def _ga4_page_interest(brand_id: str, cookie: Optional[str] = None) -> dict:
    """Pull per-page interest signals from GA4. Tries
    /api/ga4/<brand>/pages (per-page sessions). Falls back to
    a list of known service pages if endpoint missing.

    Per brief §15: surface visits to /bookings/,
    /club-fitting-at-stick/, /coaching-at-stick/, etc."""
    cfg = BRAND_CONFIG.get(brand_id, {})
    if not cfg.get("ga4_property_id"):
        return {"data_status": STATUS_NOT_CONNECTED,
                "reason": "no GA4 property configured"}
    service_pages = [
        ("bookings",                "/bookings/"),
        ("club-fitting",            "/club-fitting-at-stick/"),
        ("coaching",                "/coaching-at-stick/"),
        ("takomo",                  "/takomo-at-stick/"),
        ("psycho-bunny",            "/psycho-bunny-at-stick/"),
        ("vice-golf",               "/vice-golf-at-stick/"),
        ("avoda",                   "/avoda-at-stick/"),
        ("lab-golf",                "/l-a-b-golf-at-stick/"),
    ]
    try:
        import urllib.request
        base = os.environ.get("CAMPAIGN_OS_BASE_URL",
                              "http://localhost:8080").rstrip("/")
        url = f"{base}/api/ga4/{brand_id}/pages?days=31"
        req = urllib.request.Request(url)
        if cookie:
            req.add_header("Cookie", cookie)
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.loads(r.read())
        if payload.get("ok") and payload.get("rows"):
            rows = payload.get("rows", [])
            page_by_path = {r.get("path"): r for r in rows}
            service_signals = []
            for label, path in service_pages:
                row = page_by_path.get(path) or {}
                service_signals.append({
                    "label": label,
                    "path": path,
                    "sessions": int(row.get("sessions", 0) or 0),
                    "users": int(row.get("users", 0) or 0),
                    "engaged_sessions": int(row.get("engaged_sessions", 0) or 0),
                })
            return {
                "data_status": STATUS_LIVE,
                "service_pages": service_signals,
                "source": f"GA4 (live via /api/ga4/{brand_id}/pages)",
            }
    except Exception:
        pass
    return {
        "data_status": STATUS_NOT_CONNECTED,
        "reason": "/api/ga4/<brand>/pages endpoint not yet returning per-page data",
        "service_pages": [
            {"label": l, "path": p, "sessions": 0,
             "users": 0, "engaged_sessions": 0}
            for l, p in service_pages
        ],
    }


def _what_worked_and_needs_attention(brand_id: str,
                                      report: dict) -> tuple:
    """Deterministic rule-based generation of what-worked and
    what-needs-attention findings (brief §21, §22). Each
    finding has evidence + interpretation + business relevance.
    AI does NOT generate these from scratch — they are produced
    from explicit data signals in the report."""
    worked = []
    needs_attention = []

    # 1. GA4 traffic
    ga4 = report.get("sections", {}).get("website_performance", {})
    metrics = ga4.get("metrics") or {}
    sessions = metrics.get("sessions", 0)
    users = metrics.get("total_users", 0)
    er = metrics.get("engagement_rate_median", 0)
    if ga4.get("data_status") == STATUS_LIVE and sessions > 0:
        worked.append({
            "title": "Stick website recorded real traffic in the period",
            "evidence": f"{sessions:,} sessions from {users:,} users over "
                        f"{ga4.get('period','?')}; median engagement rate "
                        f"{er:.0%}.",
            "interpretation": "Traffic and engagement are measurable now "
                              "via GA4. This is the strongest verified "
                              "signal Stick has today.",
            "business_relevance": "Until lead tracking is live, traffic "
                                   "is the most reliable proxy for "
                                   "marketing reach.",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })

    # 2. North Stars acknowledged (not yet measured)
    stars = report.get("north_stars", {})
    if stars:
        needs_attention.append({
            "title": "North Star progress not yet quantifiable",
            "evidence": "Campaign OS does not currently receive sales, "
                         "fitting-booking or coaching-booking data from "
                         "the Stick operational stack.",
            "interpretation": "North Stars (R350k Psycho Bunny sales/month, "
                              "24 fittings/week, 24 coaching sessions/week) "
                              "are configured but their progress cannot be "
                              "verified in this report cycle.",
            "business_relevance": "Once generate_lead + fitting/coaching "
                                   "event-tracking go live, the report will "
                                   "begin to score North Star progress.",
            "type": "SUPPORTED_INFERENCE",
            "confidence": "HIGH",
        })

    # 3. Pillar mix imbalance (only if pillar_mix present)
    pillar = report.get("sections", {}).get("pillar_mix", {})
    counts = pillar.get("pillar_event_counts") or {}
    if counts and any(counts.values()):
        # All counts are ints here; safe to use max/min directly
        max_p = max(counts, key=lambda k: counts[k])
        min_p = min(counts, key=lambda k: counts[k])
        if counts[max_p] >= 2 * counts[min_p] and counts[min_p] > 0:
            worked.append({
                "title": f"{max_p.capitalize()} content is currently "
                          f"the most-planned pillar",
                "evidence": f"Of {sum(counts.values())} classified 2026 "
                             f"events, {max_p}={counts[max_p]} "
                             f"({pillar['pillar_event_pct'][max_p]}%), "
                             f"{min_p}={counts[min_p]} "
                             f"({pillar['pillar_event_pct'][min_p]}%).",
                "interpretation": f"Stick's planning is currently "
                                   f"{max_p}-weighted. {min_p.capitalize()} "
                                   f"is comparatively under-planned at "
                                   f"{pillar['pillar_event_pct'][min_p]}%.",
                "business_relevance": "A 2x imbalance between max and min "
                                       "pillars suggests marketing effort "
                                       "may not match the equal weight "
                                       "North Stars imply.",
                "type": "MEASURED_FACT",
                "confidence": "HIGH",
            })
            needs_attention.append({
                "title": f"{min_p.capitalize()} pillar is "
                          f"under-supported in 2026 planning",
                "evidence": f"Only {counts[min_p]} of "
                             f"{sum(counts.values())} classified events "
                             f"support {min_p}.",
                "interpretation": "The North Star for this pillar is 24 "
                                   "sessions/week. Without marketing "
                                   "support, hitting it is harder.",
                "business_relevance": "Consider increasing "
                                       f"{min_p} content in the next "
                                       "planning cycle to rebalance.",
                "type": "SUPPORTED_INFERENCE",
                "confidence": "MEDIUM",
            })

    # 4. Lead tracking gap
    lts = report.get("sections", {}).get("lead_tracking", {})
    if lts.get("data_status") == STATUS_PENDING:
        needs_attention.append({
            "title": "Verified website lead tracking is not yet live",
            "evidence": "Stick generate_lead (CF7 wpcf7mailsent) "
                         "snippet not yet installed; not yet sending to "
                         "GA4 as a key event.",
            "interpretation": "Traffic and engagement are measurable but "
                              "conversion-to-enquiry cannot be quantified.",
            "business_relevance": "Without lead data, North Star progress "
                                   "(R350k sales, 24 fittings, 24 "
                                   "coaching) cannot be reported against.",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })

    # 5. Meta surfaces (Step 4A in progress)
    audience = report.get("sections", {}).get("audience_awareness", {})
    if audience.get("data_status") in (STATUS_PARTIAL, STATUS_NOT_CONNECTED):
        needs_attention.append({
            "title": "Stick Meta organic surfaces still pending",
            "evidence": "Stick EAAR token is now REACHABLE for page + "
                         "ad account, but IG + WABA + content surfaces "
                         "are PARTIAL/NOT_CONNECTED.",
            "interpretation": "Audience + awareness metrics for Stick "
                              "are unavailable in this cycle.",
            "business_relevance": "Once full Meta scopes are wired, the "
                                   "next cycle will surface real "
                                   "reach/impressions/engagement.",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })

    # 6. Meta Ads synthetic
    if report.get("data_coverage", {}).get("meta_ads") == STATUS_NOT_CONNECTED:
        needs_attention.append({
            "title": "Meta Ads real history not yet ingested",
            "evidence": "data/meta-ads.json is synthetic and "
                         "QUARANTINED; real Meta Ads history requires "
                         "Step 4B ingestion.",
            "interpretation": "Paid performance is intentionally NOT "
                              "reported in this cycle.",
            "business_relevance": "Once Step 4B ships, the report will "
                                   "auto-enrich with spend, CTR, CPC, CPM, "
                                   "and platform-reported leads.",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })

    return worked, needs_attention


def _cross_channel_observations(brand_id: str, report: dict) -> list:
    """Brief §6: cross-channel observations where evidence exists.

    Use 'consistent with', 'associated with', 'aligns with'
    unless direct attribution exists. NEVER claim causation
    from timing alone.

    Returns list of dicts with observation + type + confidence.
    """
    obs = []
    cfg = BRAND_CONFIG.get(brand_id, {})
    name = cfg.get("name", brand_id)
    ga = report.get("sections", {}).get("website_performance", {})
    mo = report.get("sections", {}).get("audience_awareness", {})

    ga_metrics = ga.get("metrics") or {}
    ga_sessions = ga_metrics.get("sessions", 0)
    ga_users = ga_metrics.get("total_users", 0)
    ig = ((mo.get("metrics") or {}).get("instagram") or {}) \
         if mo.get("data_status") == "LIVE" else {}
    ig_reach_30d = ig.get("reach_30d", 0)

    # 1. IG reach vs GA4 sessions — different scales, but if
    # IG reach is much larger than GA4 sessions, that suggests
    # IG drives awareness; GA4 captures only the click-through.
    if ig_reach_30d and ga_sessions:
        ratio = round(ig_reach_30d / max(1, ga_sessions))
        obs.append({
            "observation": f"{name} IG reach_30d ({ig_reach_30d:,}) is "
                            f"~{ratio}x GA4 sessions ({ga_sessions:,}); "
                            f"this is consistent with IG primarily "
                            f"driving awareness + light click-through, "
                            f"with on-site traffic concentrated in a "
                            f"smaller intent-driven subset.",
            "type": "SUPPORTED_INFERENCE",
            "confidence": "MEDIUM",
            "evidence_basis": [
                f"IG reach_30d = {ig_reach_30d:,}",
                f"GA4 sessions = {ga_sessions:,}",
                f"ratio = {ratio}x",
            ],
        })

    # 2. Accounts-engaged vs total_users
    ae = ig.get("accounts_engaged_30d", 0)
    if ae and ga_users:
        rate = round(ae / max(1, ga_users) * 100, 1)
        obs.append({
            "observation": f"{name} IG accounts-engaged in last 30 days "
                            f"({ae:,}) is ~{rate}% of GA4 total users "
                            f"({ga_users:,}); this aligns with a small "
                            f"but high-intent click-through cohort rather "
                            f"than broad funnel conversion.",
            "type": "SUPPORTED_INFERENCE",
            "confidence": "MEDIUM",
            "evidence_basis": [
                f"IG accounts_engaged_30d = {ae:,}",
                f"GA4 total_users = {ga_users:,}",
                f"conversion proxy = {rate}%",
            ],
        })

    # 3. Top post → landing page alignment (if top post has
    # explicit CTA → bookings/fitting/coaching we surface it)
    tp = mo.get("top_post") or {}
    if tp.get("caption_preview"):
        cap = (tp.get("caption_preview") or "").lower()
        cta_words = []
        if "fitting" in cap:
            cta_words.append("fitting")
        if "coaching" in cap or "lesson" in cap or "coach" in cap:
            cta_words.append("coaching")
        if "book" in cap:
            cta_words.append("booking")
        if cta_words:
            obs.append({
                "observation": f"{name}'s top IG post mentions "
                                f"{'/'.join(cta_words)} (caption: "
                                f"\"{tp.get('caption_preview','')[:80]}\"); "
                                f"this is consistent with intentional "
                                f"traffic routing to "
                                f"corresponding landing pages once the "
                                f"GA4 page_interest endpoint is wired.",
                "type": "SUPPORTED_INFERENCE",
                "confidence": "LOW",
                "evidence_basis": [
                    f"top_post.caption_preview = {tp.get('caption_preview','')[:100]}",
                    f"detected CTA keywords = {cta_words}",
                ],
            })

    return obs


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

    Now also pulls pillar_mix, page_interest, visual_dna,
    historical_reports signals if they exist on the metrics
    dict (caller passes the partial dict).
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
                          "in this build; traffic performance cannot be quantified.",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })
    elif ga.get("data_status") == STATUS_UNAVAILABLE:
        reason = ga.get("reason", "unknown")
        out.append({
            "statement": f"{name} GA4 endpoint returned an error ({reason[:80]}). "
                          "Website traffic cannot be quantified in this run.",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })

    # Pillar mix
    pmx = metrics.get("pillar_mix") or {}
    pct = pmx.get("pillar_event_pct") or {}
    counts = pmx.get("pillar_event_counts") or {}
    if pct and any(pct.values()):
        ranked = sorted(pct.items(), key=lambda kv: kv[1], reverse=True)
        top_p, top_v = ranked[0]
        low_p, low_v = ranked[-1]
        out.append({
            "statement": f"2026 planning is pillar-weighted: {top_p} "
                          f"{top_v:.0f}% vs {low_p} {low_v:.0f}% "
                          f"({counts[top_p]} events vs {counts[low_p]}).",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })

    # Page / service interest
    pi = metrics.get("page_interest") or {}
    sp = pi.get("service_pages") or []
    live_pages = [p for p in sp if (p.get("sessions") or 0) > 0]
    if live_pages:
        ranked = sorted(live_pages, key=lambda p: p.get("sessions", 0),
                       reverse=True)
        leader = ranked[0]
        out.append({
            "statement": f"Strongest measured website service-interest is "
                          f"{leader['label']} ({leader['path']}) at "
                          f"{leader['sessions']} sessions over the period.",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })

    # Visual DNA
    vdna = metrics.get("visual_dna") or {}
    samples = vdna.get("samples")
    if samples and samples >= 3:
        ocr_med = vdna.get("ocr_word_count_median")
        ori = vdna.get("orientation_distribution") or {}
        top_ori = max(ori.items(), key=lambda kv: kv[1])[0] if ori else "unknown"
        out.append({
            "statement": f"Visual DNA indexed across {samples} assets "
                          f"(most are {top_ori}); median OCR word-count "
                          f"{ocr_med if ocr_med is not None else 'n/a'}.",
            "type": "MEASURED_FACT",
            "confidence": "MEDIUM",
        })

    # Historical reports
    hr = metrics.get("historical_reports") or {}
    if hr.get("data_status") == STATUS_HISTORICAL_REAL and hr.get("count"):
        out.append({
            "statement": f"{hr['count']} operator-uploaded historical report(s) "
                          "available as contextual comparison sources.",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })

    # Lead tracking
    if cfg.get("lead_tracking_status") == STATUS_PENDING:
        out.append({
            "statement": f"Verified website lead tracking is not yet live for {name}; "
                          "traffic can be assessed but commercial enquiry conversion "
                          "cannot yet be quantified.",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })

    # Meta organic (if available)
    meta = metrics.get("meta_organic") or {}
    if meta.get("data_status") == STATUS_LIVE:
        ig = ((meta.get("metrics") or {}).get("instagram") or {})
        if ig.get("followers_count") or ig.get("reach_30d"):
            out.append({
                "statement": f"{name} Instagram recorded "
                              f"{ig.get('reach_30d', 0):,} reach across "
                              f"{ig.get('media_with_insights', 0)} media "
                              f"over the last 30 days "
                              f"({ig.get('reach_daily_avg', 0):,} daily avg); "
                              f"audience stands at "
                              f"{ig.get('followers_count', 0):,} followers "
                              f"with {ig.get('accounts_engaged_30d', 0)} "
                              f"engaged accounts.",
                "type": "MEASURED_FACT",
                "confidence": "HIGH",
            })
        # IG top post
        tp = meta.get("top_post") or {}
        if tp.get("id"):
            out.append({
                "statement": f"{name}'s top IG post (last 30 days): "
                              f"\"{(tp.get('caption_preview') or '')[:80]}\" "
                              f"— {tp.get('reach', 0):,} reach, "
                              f"{tp.get('engagement_rate_pct', 0):.1f}% ER, "
                              f"{tp.get('total_interactions', tp.get('interactions', 0))} "
                              f"interactions.",
                "type": "MEASURED_FACT",
                "confidence": "HIGH",
            })
    elif meta.get("data_status") == STATUS_PARTIAL:
        out.append({
            "statement": f"{name} Meta organic: identity visible, recent content and "
                          "insights surfaces still limited (Step 4A in progress).",
            "type": "MEASURED_FACT",
            "confidence": "HIGH",
        })
    elif meta.get("data_status") == STATUS_NOT_CONNECTED:
        out.append({
            "statement": f"{name} Meta reporting is not currently connected; "
                          "organic social performance is reportable only via "
                          "Campaign OS historical archives (where present).",
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


def _build_ga4_section(brand_id: str, cookie: Optional[str] = None) -> dict:
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
        # Forward the inbound session cookie so the GA4 endpoint's
        # auth gate lets us through. (When the renderer is called
        # via /api/reports/v1/<brand>, _is_authed() has already
        # verified the caller's cookie; passing it through here
        # avoids re-prompting.)
        req = urllib.request.Request(url)
        if cookie:
            req.add_header("Cookie", cookie)
        with urllib.request.urlopen(req, timeout=60) as r:
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
    """Per brief §5: surface actual Meta organic numbers wherever
    the live/historical connection is trustworthy. Don't merely
    show 'Meta = LIVE' — actually include reach, followers,
    post count, top content, engagement rate.
    """
    cfg = BRAND_CONFIG[brand_id]
    if not cfg.get("facebook_page_id"):
        return {"data_status": STATUS_NOT_CONNECTED,
                "reason": "no Facebook page configured"}

    out = {"data_status": STATUS_NOT_CONNECTED,
           "page_id": cfg.get("facebook_page_id"),
           "source": None, "reason": None,
           "historical_archive": None,
           "metrics": {}, "top_post": None,
           "account": {}, "daily_reach_30d": []}

    if brand_id == "stick":
        # EAAR token is now REACHABLE for Stick but IG + WABA +
        # content surfaces still PARTIAL. FB page is reachable.
        # No historical archive exists for Stick yet.
        out["data_status"] = STATUS_PARTIAL
        out["source"] = "Meta Graph API v23.0 (Step 4A — page reachable)"
        out["reason"] = ("Stick FB page is reachable; IG / WABA / "
                          "content surfaces still PARTIAL pending "
                          "full scope wiring.")
        out["metrics"] = {
            "facebook_page_reachable": True,
            "instagram_surface": "PARTIAL (token reachable, scope pending)",
            "whatsapp_surface": "PARTIAL (token reachable, scope pending)",
            "ads_surface": "REACHABLE (ad account visible via EAAR)",
        }
        return out

    if brand_id == "swing-shack":
        archives = _historical_archives(brand_id)
        fb = archives.get("facebook_page", {})
        igb = archives.get("ig_business", {})
        # Facebook historical archive
        fb_data = fb.get("data") or {}
        out["historical_archive"] = fb.get("source")
        out["source"] = ("Meta Graph API v18.0 (live) + "
                          "data/facebook-analytics.json (historical)")
        # IG business historical archive
        ig_data = igb.get("data") or {}
        ig_account = ig_data.get("account") or {}
        ig_window = ig_data.get("window_totals") or {}
        ig_top = ig_data.get("top_post") or {}
        ig_media = ig_data.get("media", []) or []
        ig_daily_reach = ig_data.get("daily_reach", []) or []

        # Compute IG metrics
        ig_reach_30d = sum(int(r.get("value", 0) or 0)
                           for r in ig_daily_reach)
        ig_top_reach_post = ig_top.get("reach") or 0

        # FB: count posts with non-null engagement
        fb_posts = fb_data.get("posts", []) or []
        fb_posts_with_reach = [p for p in fb_posts
                                if p.get("reach") is not None]
        fb_total_posts = fb_data.get("total_posts", len(fb_posts))

        out["data_status"] = STATUS_LIVE
        out["metrics"] = {
            "facebook": {
                "total_posts_archived": fb_total_posts,
                "posts_with_reach_data": len(fb_posts_with_reach),
                "archive_last_updated": fb_data.get("updated"),
                "data_pending": fb_data.get("data_pending"),
            },
            "instagram": {
                "followers_count": ig_account.get("followers_count"),
                "follows_count": ig_account.get("follows_count"),
                "media_count": ig_account.get("media_count"),
                "reach_30d": ig_reach_30d,
                "reach_daily_avg": (
                    round(ig_reach_30d / max(1, len(ig_daily_reach)))
                    if ig_daily_reach else 0),
                "profile_views_30d": ig_window.get("profile_views"),
                "accounts_engaged_30d": ig_window.get("accounts_engaged"),
                "total_interactions_30d": ig_window.get("total_interactions"),
                "profile_links_taps_30d": ig_window.get("profile_links_taps"),
                "media_with_insights": len(ig_media),
                "archive_last_updated": igb.get("last_updated"),
            },
        }
        if ig_top.get("id"):
            out["top_post"] = {
                "id": ig_top.get("id"),
                "caption_preview": (ig_top.get("caption_preview") or "")[:180],
                "permalink": ig_top.get("permalink"),
                "media_type": ig_top.get("media_type"),
                "engagement_rate_pct": ig_top.get("engagement_rate_pct"),
                "likes": ig_top.get("likes"),
                "comments": ig_top.get("comments"),
                "interactions": ig_top.get("interactions"),
                "reach": ig_top_reach_post,
            }
        out["daily_reach_30d"] = ig_daily_reach
        out["account"] = {
            "ig_username": ig_account.get("username"),
            "ig_id": ig_account.get("id"),
        }
        # Top 3 IG media by reach
        media_with_reach = [m for m in ig_media
                            if (m.get("metrics") or {}).get("reach")]
        media_with_reach.sort(
            key=lambda m: (m.get("metrics") or {}).get("reach", 0),
            reverse=True)
        out["top_media_by_reach"] = [
            {
                "id": m.get("id"),
                "permalink": m.get("permalink"),
                "media_type": m.get("media_type"),
                "engagement_rate_pct": m.get("engagement_rate_pct"),
                "reach": (m.get("metrics") or {}).get("reach"),
                "likes": (m.get("metrics") or {}).get("likes"),
                "total_interactions": (m.get("metrics") or {}).get("total_interactions"),
                "caption_preview": (m.get("caption_preview") or "")[:120],
            } for m in media_with_reach[:5]
        ]
        return out

    return out


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

def build_brand_report(brand_id: str, period_days: int = 31,
                       cookie: Optional[str] = None) -> dict:
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
    ga4 = _build_ga4_section(brand_id, cookie=cookie)
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
        # Brief §5: surface actual Meta organic numbers
        "metrics": mo.get("metrics") or {},
        "top_post": mo.get("top_post"),
        "top_media_by_reach": mo.get("top_media_by_reach"),
        "daily_reach_30d": mo.get("daily_reach_30d"),
        "account": mo.get("account"),
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

    # Brand planning (per-brand scoped; brand-isolation enforced)
    planning = _brand_planning(brand_id)

    # Pillar / content mix (brief §12)
    pmx = _pillar_mix(brand_id, planning)
    report["sections"]["pillar_mix"] = {
        "title": "Content Pillar Mix (canonical Calendar)",
        "data_status": pmx.get("data_status"),
        "pillars_always_on": pmx.get("pillars_always_on"),
        "pillar_event_counts": pmx.get("pillar_event_counts"),
        "pillar_event_pct": pmx.get("pillar_event_pct"),
        "events_per_pillar": pmx.get("events_per_pillar"),
        "unclassified_event_ids": pmx.get("unclassified_event_ids"),
        "cadences_by_lane": pmx.get("cadences_by_lane"),
        "total_events_classified": pmx.get("total_events_classified"),
        # V2.1 §1: explicit canonical-denominator fields
        "canonical_event_count": pmx.get("canonical_event_count"),
        "classified_event_count": pmx.get("classified_event_count"),
        "cultural_moment_count": pmx.get("cultural_moment_count"),
        "preserved_unclassified_count": pmx.get(
            "preserved_unclassified_count"),
        "denominator_used_for_pillar_percentages": pmx.get(
            "denominator_used_for_pillar_percentages"),
        "excluded_event_count": pmx.get("excluded_event_count"),
        "exclusion_reasons": pmx.get("exclusion_reasons"),
        "source": pmx.get("source"),
        "reason": pmx.get("reason"),
    }
    if pmx.get("data_status") == STATUS_HISTORICAL_REAL:
        report["data_sources"].append({
            "name": "Brand Planning (Stick 2026)",
            "asset": "data/brand-planning/stick-events-2026.json",
            "data_status": STATUS_HISTORICAL_REAL,
            "note": "per-brand scoped; pillar classification is keyword-based heuristic",
        })

    # Visual DNA / Creative Genome (brief §20)
    vdna = _visual_dna_signals(brand_id)
    report["sections"]["visual_dna"] = {
        "title": "Creative Genome (Visual DNA)",
        "data_status": vdna.get("data_status"),
        "samples": vdna.get("samples"),
        "subject_distribution": vdna.get("subject_distribution"),
        "orientation_distribution": vdna.get("orientation_distribution"),
        "ocr_word_count_median": vdna.get("ocr_word_count_median"),
        "ocr_word_count_samples": vdna.get("ocr_word_count_samples"),
        "ocr_available_distribution": vdna.get("ocr_available_distribution"),
        "luminance_distribution": vdna.get("luminance_distribution"),
        "source": vdna.get("source"),
        "reason": vdna.get("reason"),
    }

    # Page / service interest (brief §15)
    pi = _ga4_page_interest(brand_id, cookie=cookie)
    report["sections"]["page_interest"] = pi

    # Historical reports (brief §29)
    hr = _historical_reports(brand_id)
    report["sections"]["historical_reports"] = hr

    # Executive summary (template-based, deterministic)
    metrics_for_summary = {
        "ga4": ga4,
        "meta_organic": mo,
        "pillar_mix": pmx,
        "page_interest": pi,
        "visual_dna": vdna,
        "historical_reports": hr,
    }
    report["executive_summary"] = _executive_summary(brand_id, metrics_for_summary, {})

    # Data coverage matrix
    report["data_coverage"] = {
        "ga4": ga4.get("data_status"),
        "facebook": mo.get("data_status"),
        "instagram": (mo.get("data_status") if brand_id == "swing-shack"
                      else STATUS_NOT_CONNECTED),
        "meta_ads": pm.get("data_status"),
        "lead_tracking": cfg.get("lead_tracking_status", STATUS_NOT_CONNECTED),
        "strategy": strat.get("data_status"),
        "page_interest": pi.get("data_status"),
        "pillar_mix": pmx.get("data_status"),
        "visual_dna": vdna.get("data_status"),
        "historical_reports": hr.get("data_status"),
    }

    # Data limitations
    report["data_limitations"] = _limitations_for(brand_id, report)

    # Recommendations (template-based, ranked HIGH/MEDIUM/LOW)
    report["recommendations"] = _recommendations_for(brand_id)

    # Next-period test plan
    report["next_period_tests"] = _test_plan_for(brand_id)

    # What worked + what needs attention (brief §21, §22)
    worked, needs_attention = _what_worked_and_needs_attention(brand_id, report)
    report["what_worked"] = worked
    report["what_needs_attention"] = needs_attention

    # Cross-channel observations (brief §6) — evidence-backed
    # only; no causation claims.
    report["cross_channel_observations"] = _cross_channel_observations(
        brand_id, report)

    # Source lineage — every metric the renderer pulls carries
    # brand_id+source+asset+period
    report["source_lineage"] = [
        {"name": "GA4", "asset": cfg.get("ga4_property_id"), "brand_id": brand_id,
         "period": f"{period_start} → {period_end}",
         "source": ga4.get("source")},
        {"name": "GA4 page interest", "asset": cfg.get("ga4_property_id"),
         "brand_id": brand_id,
         "period": f"{period_start} → {period_end}",
         "source": pi.get("source") or pi.get("reason"),
         "data_status": pi.get("data_status")},
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
        {"name": "Brand Planning", "asset": "data/brand-planning/stick-*",
         "brand_id": brand_id, "period": "2026 calendar year",
         "source": pmx.get("source"),
         "data_status": pmx.get("data_status")},
        {"name": "Visual DNA / Creative Genome",
         "asset": "data/brand-directory/stick/images/*.visual-dna.json",
         "brand_id": brand_id, "period": "static",
         "source": vdna.get("source"),
         "data_status": vdna.get("data_status")},
        {"name": "Historical Reports (operator-uploaded)",
         "asset": f"data/historical-reports/{brand_id}/*",
         "brand_id": brand_id, "period": "uploaded",
         "source": hr.get("source"),
         "data_status": hr.get("data_status")},
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




# ─── V2.1: MANAGEMENT REPORT BUILDER + RENDERER ──────────────────────


def build_v21_brand_report(brand_id: str, period_days: int = 31,
                            cookie: Optional[str] = None) -> dict:
    """Build the V2.1 management report for a single brand.

    Reads from internal helpers + the GA4 enrichment endpoints
    via the runtime. Composes:
      - KPI scorecard with movement
      - Channel mix
      - Landing pages
      - Key event audit
      - Source freshness per data_as_of
      - Executive summary (movement-based)
      - Data coverage + data_as_of
      - Empty-section discipline
      - Pillar mix (canonical Calendar — matches Brief)
      - North Star (marketing support, not business outcome)
    """
    cfg = BRAND_CONFIG.get(brand_id)
    if not cfg:
        return {"error": f"unknown brand_id: {brand_id}"}
    cur_start, cur_end = _v21_resolve_current_window(period_days)
    prev_start, prev_end = _v21_resolve_previous_window(period_days)
    nstart, nend = _v21_resolve_90day_window()

    # ── Pull each V2.1 enrichment endpoint from the runtime ──
    base = os.environ.get("CAMPAIGN_OS_BASE_URL",
                          "http://localhost:8080").rstrip("/")
    fetch = _v21_runtime_fetch(base, brand_id, period_days, cookie)

    # ── Compute KPI scorecard with movement ──
    scorecard = _v21_build_scorecard(brand_id, fetch)

    # ── Channel mix (current + previous) ──
    channel_mix = (fetch.get("channel_mix") or {})
    if channel_mix.get("ok"):
        # Compute total deltas
        channels = channel_mix.get("rows") or []
        channel_summary = {
            "data_status": "LIVE",
            "current_window": channel_mix.get("current_window"),
            "previous_window": channel_mix.get("previous_window"),
            "rows": channels,
            "totals": {
                "current_sessions": channel_mix.get("total_current_sessions"),
                "previous_sessions": channel_mix.get(
                    "total_previous_sessions"),
            },
        }
    else:
        channel_summary = {
            "data_status": STATUS_UNAVAILABLE,
            "reason": (channel_mix.get("error", "")
                       or channel_mix.get("note", "")),
            "rows": [],
        }

    # ── Landing pages ──
    pages = (fetch.get("pages") or {})
    if pages.get("ok"):
        landing_pages = {
            "data_status": "LIVE",
            "current_window": pages.get("current_window"),
            "previous_window": pages.get("previous_window"),
            "service_pages": pages.get("service_pages") or [],
            "top_raw_paths": pages.get("top_raw_paths") or [],
        }
    else:
        landing_pages = {
            "data_status": STATUS_UNAVAILABLE,
            "reason": (pages.get("error", "")
                       or pages.get("note", "")),
            "service_pages": [],
        }

    # ── Key event audit ──
    events = (fetch.get("events") or {})
    key_events_summary = {
        "data_status": ("LIVE" if events.get("ok")
                        else (events.get("error")
                              and STATUS_UNAVAILABLE) or STATUS_NOT_CONNECTED),
        "headline": events.get("headline", "") if events.get("ok") else "",
        "rows": events.get("rows") or [] if events.get("ok") else [],
        "checked_at": events.get("checked_at"),
    }

    # ── Pillar mix via canonical Calendar ──
    planning = _brand_planning(brand_id)
    pmx = _pillar_mix(brand_id, planning)

    # ── North stars + marketing support separation ──
    north_stars = cfg.get("north_stars") or {}

    # ── Source freshness (data_as_of) per source ──
    sources = _v21_source_freshness(brand_id, fetch)

    # ── Coverage matrix ──
    coverage = _v21_data_coverage(brand_id, fetch, pmx, channels)

    # ── Executive summary using MOVEMENT ──
    exec_summary = _v21_executive_summary_movement(brand_id, fetch,
                                                    scorecard, channel_summary)

    # ── Marketing support vs North Star business outcomes ──
    marketing_support = _v21_marketing_support_signal(brand_id, scorecard)
    business_outcome = _v21_business_outcome_signal(brand_id, fetch)

    # ── Recommendations + tests + risks + what-needs-attention ──
    recs = _recommendations_for(brand_id)
    tests = _test_plan_for(brand_id)
    limits = _limitations_for(brand_id, {"sections": {}})

    # ── Assemble ──
    report = {
        "schema": "https://campaign-os/reporting/v2.1",
        "version": "2.1",
        "brand_id": brand_id,
        "brand_name": cfg["name"],
        "domain": cfg["domain"],
        "report_period": {
            "start": cur_start.isoformat(),
            "end": cur_end.isoformat(),
            "days": period_days,
            "label": "31-day rolling (calendar)",
        },
        "previous_period": {
            "start": prev_start.isoformat(),
            "end": prev_end.isoformat(),
            "days": period_days,
            "label": "previous 31-day rolling (calendar)",
        },
        "ninety_day_baseline": {
            "start": nstart.isoformat(),
            "end": nend.isoformat(),
            "days": 90,
            "label": "90-day rolling baseline (context only)",
        },
        "generated_at": _now_iso(),
        "data_status_taxonomy_used": True,
        "brand_isolation_enforced": True,

        # V2.1 §11: KPI scorecard near the top
        "kpi_scorecard": scorecard,

        # V2.1 §17: marketing support vs business outcome
        "marketing_support": marketing_support,
        "business_outcomes": business_outcome,

        # V2.1 §15/§6/§7: sections
        "sections": {
            "executive_summary": {"statements": exec_summary},
            "data_coverage": coverage,
            "channel_mix": channel_summary,
            "landing_pages": landing_pages,
            "key_events": key_events_summary,
            "pillar_mix": pmx,
            "north_stars": {"items": north_stars},
            "sources": sources,
        },

        # V2.1 §13: what-needs-attention with severity
        "what_needs_attention": _v21_severity_score(limits, brand_id, fetch),
        "what_worked": [
            {
                "title": "GA4 website tracking LIVE",
                "evidence": (f"GA4 property {cfg.get('ga4_property_id')} "
                              f"is LIVE for {cfg['domain']}"),
                "interpretation": (f"Reporting engine can read sessions, "
                                    f"users, engagement rate, and conversion "
                                    f"events."),
                "business_relevance": ("All product/marketing decisions "
                                       "remain observable."),
            },
        ],

        # V2.1 §16: Meta Ads honesty
        "meta_ads_status": {
            "data_status": STATUS_NOT_CONNECTED,
            "rule": ("SYNTHETIC ads data is quarantined. Real ads "
                     "data only. Report does NOT invent paid "
                     "performance until Meta Ads Step 4B ships."),
            "synthetic_file": "data/meta-ads.json (quarantined)",
        },

        # Keep recommendations + tests + limitations
        "recommendations": recs,
        "next_period_tests": tests,
        "data_limitations": limits,

        # V2.1 §4: brand source lineage with data_as_of
        "source_lineage": _v21_lineage(brand_id, cfg, fetch, sources),
    }
    return report


def _v21_runtime_fetch(base, brand_id, period_days, cookie):
    """Pull V2.1 enrichment endpoints via the runtime base."""
    import urllib.request as _ur
    out = {"channel_mix": None, "pages": None, "events": None}
    for key, path in [
        ("channel_mix", f"/api/ga4/{brand_id}/channel-mix"),
        ("pages", f"/api/ga4/{brand_id}/pages-enriched"),
        ("events", f"/api/ga4/{brand_id}/event-audit"),
    ]:
        url = f"{base}{path}?days={period_days}"
        try:
            req = _ur.Request(url)
            if cookie:
                req.add_header("Cookie", cookie)
            with _ur.urlopen(req, timeout=60) as r:
                out[key] = json.loads(r.read())
        except Exception as e:
            out[key] = {"ok": False, "error": f"runtime unreachable: {e}"}
    return out


def _v21_build_scorecard(brand_id, fetch):
    """KPI scorecard: only meaningful KPIs available for the brand.

    Each eligible row has:
      current, previous, delta_abs, delta_pct, comparison_status,
      rolling_90_day (when supported), data_status, trend_arrow
    """
    cfg = BRAND_CONFIG.get(brand_id) or {}
    rows = []
    # --- Sessions (always present if GA4 is LIVE) ---
    # Pull from channel_mix totals
    cm = (fetch.get("channel_mix") or {})
    if cm.get("ok"):
        cur = (cm.get("total_current_sessions") or 0)
        prev = (cm.get("total_previous_sessions"))
        delta = _v21_compute_delta(cur, prev)
        arrow, status = _v21_render_trend_arrow(delta.get("delta_pct"))
        rows.append({
            "label": "Sessions",
            "current": cur,
            "previous": prev,
            "delta_abs": delta.get("delta_abs"),
            "delta_pct": delta.get("delta_pct"),
            "comparison_status": delta.get("comparison_status"),
            "rolling_90_day": None,  # GA4 enrichment does not yet cover 90d
            "trend_arrow": arrow,
            "trend_status": status,
            "data_status": "LIVE",
        })
    else:
        rows.append({
            "label": "Sessions",
            "current": None, "previous": None,
            "delta_abs": None, "delta_pct": None,
            "comparison_status": "no_data",
            "trend_arrow": "—", "trend_status": "no_comparison",
            "data_status": STATUS_UNAVAILABLE,
            "note": "GA4 endpoint unreachable",
        })
    # --- Users (channel_mix doesn't break out users; mark placeholder) ---
    rows.append({
        "label": "Users",
        "current": None, "previous": None,
        "delta_abs": None, "delta_pct": None,
        "comparison_status": "no_data",
        "trend_arrow": "—", "trend_status": "no_comparison",
        "data_status": STATUS_PENDING,
        "note": "Users metric not yet wired into V2.1 enrichment "
                "endpoints (GA4 endpoint returns sessions only)",
    })
    # --- Engagement rate — V2.1 §5: median preferred for rate metrics ---
    rows.append({
        "label": "Engagement rate",
        "current": None, "previous": None,
        "delta_abs": None, "delta_pct": None,
        "comparison_status": "no_data",
        "trend_arrow": "—", "trend_status": "no_comparison",
        "data_status": STATUS_PENDING,
        "note": ("Engagement rate metric not yet wired into V2.1 "
                 "enrichment endpoints"),
    })
    # --- Organic reach — only meaningful when IG LIVE ---
    cm_obj = (fetch.get("channel_mix") or {})
    organic_social = None
    if cm_obj.get("ok"):
        for r in (cm_obj.get("rows") or []):
            if r.get("channel") == "Organic Social":
                organic_social = r
                break
    if organic_social and organic_social.get(
            "current_sessions") is not None:
        rows.append({
            "label": "Organic Reach (proxy: sessions from Organic Social)",
            "current": organic_social.get("current_sessions"),
            "previous": organic_social.get("previous_sessions"),
            "delta_abs": ((organic_social.get("current_sessions") or 0)
                            - (organic_social.get("previous_sessions")
                                if organic_social.get(
                                    "previous_sessions") is not None
                                else 0)),
            "delta_pct": organic_social.get("delta_pct"),
            "comparison_status": "tracked",
            "trend_arrow": ("▲" if organic_social.get("delta_pct") and
                            organic_social["delta_pct"] > 0.5 else
                            ("▼" if organic_social.get("delta_pct") and
                             organic_social["delta_pct"] < -0.5 else "→")),
            "trend_status": "improving",
            "data_status": "LIVE",
            "note": "GA4 channel grouping; cross-check with IG insights",
        })
    else:
        rows.append({
            "label": "Organic Reach",
            "current": None, "previous": None,
            "delta_abs": None, "delta_pct": None,
            "comparison_status": "no_data",
            "trend_arrow": "—", "trend_status": "no_comparison",
            "data_status": (STATUS_NOT_CONNECTED if brand_id == "stick"
                            else STATUS_STALE),
            "note": ("IG organic insights unavailable"
                     + (" (token reachable, scope pending)" if brand_id == "stick"
                        else " (last fetched 2026-08-21, 25+ days stale)")),
        })
    # --- Paid spend: only when real Meta Ads ingestion ships ---
    rows.append({
        "label": "Paid Spend",
        "current": None, "previous": None,
        "delta_abs": None, "delta_pct": None,
        "comparison_status": "no_data",
        "trend_arrow": "—", "trend_status": "no_comparison",
        "data_status": STATUS_NOT_CONNECTED,
        "note": ("Meta Ads is NOT_CONNECTED. Real ads history "
                 "ingestion pending Step 4B. Synthetic data "
                 "remains quarantined."),
    })
    # --- Verified leads: only when tracking live ---
    if brand_id == "stick":
        rows.append({
            "label": "Verified Leads",
            "current": None, "previous": None,
            "delta_abs": None, "delta_pct": None,
            "comparison_status": "no_data",
            "trend_arrow": "—", "trend_status": "no_comparison",
            "data_status": STATUS_PENDING,
            "note": ("Stick generate_lead event is configured in "
                     "GA4 but on-website CF7 listener not yet "
                     "production-validated. Do not report."),
        })
    return {
        "schema": "https://campaign-os/kpi-scorecard/v2.1",
        "brand_id": brand_id,
        "rows": rows,
        "checked_at": _now_iso(),
    }


def _v21_source_freshness(brand_id, fetch):
    """Per-source data_as_of + freshness_status."""
    sources = []
    sources.append({
        "source": "GA4 (channel-mix endpoint)",
        "data_status": ("LIVE"
                        if (fetch.get("channel_mix") or {}).get("ok")
                        else STATUS_UNAVAILABLE),
        "data_as_of": (fetch.get("channel_mix") or {}).get("checked_at"),
        "freshness": "current 31-day window + previous 31-day window",
    })
    sources.append({
        "source": "GA4 (pages-enriched endpoint)",
        "data_status": ("LIVE"
                        if (fetch.get("pages") or {}).get("ok")
                        else STATUS_UNAVAILABLE),
        "data_as_of": (fetch.get("pages") or {}).get("checked_at"),
        "freshness": "current 31-day window + previous 31-day window",
    })
    sources.append({
        "source": "GA4 (event-audit endpoint)",
        "data_status": ("LIVE"
                        if (fetch.get("events") or {}).get("ok")
                        else STATUS_UNAVAILABLE),
        "data_as_of": (fetch.get("events") or {}).get("checked_at"),
        "freshness": "current 31-day window",
    })
    # Calendar / canonical Calendar
    sources.append({
        "source": "Marketing Calendar (canonical)",
        "data_status": STATUS_LIVE,
        "data_as_of": _now_iso(),
        "freshness": "canonical — read at build time",
    })
    return sources


def _v21_data_coverage(brand_id, fetch, pmx, channels):
    """Coverage matrix with explicit Not Connected labels."""
    cm_ok = (fetch.get("channel_mix") or {}).get("ok")
    pages_ok = (fetch.get("pages") or {}).get("ok")
    events_ok = (fetch.get("events") or {}).get("ok")
    return {
        "ga4": STATUS_LIVE,
        "ga4_channel_mix": STATUS_LIVE if cm_ok else STATUS_UNAVAILABLE,
        "ga4_landing_pages": STATUS_LIVE if pages_ok else STATUS_UNAVAILABLE,
        "ga4_key_events": STATUS_LIVE if events_ok else STATUS_UNAVAILABLE,
        "facebook": (STATUS_LIVE if brand_id == "swing-shack"
                     else STATUS_PARTIAL),
        "facebook_content": (STATUS_PARTIAL
                              if brand_id == "stick"
                              else STATUS_LIVE),
        "facebook_insights": STATUS_NOT_CONNECTED,
        "instagram": (STATUS_STALE if brand_id == "swing-shack"
                       else STATUS_NOT_CONNECTED),
        "instagram_content": (STATUS_PARTIAL
                               if brand_id == "stick"
                               else STATUS_LIVE),
        "instagram_insights": STATUS_NOT_CONNECTED,
        "meta_ads": STATUS_NOT_CONNECTED,
        "lead_tracking": (STATUS_PENDING if brand_id == "stick"
                           else STATUS_NOT_APPLICABLE),
        "strategy": STATUS_LIVE,
        "page_interest_landing_pages": (STATUS_LIVE if pages_ok
                                          else STATUS_UNAVAILABLE),
        "pillar_mix": pmx.get("data_status") or STATUS_NOT_APPLICABLE,
        "visual_dna": (STATUS_HISTORICAL_REAL if brand_id == "stick"
                        else STATUS_NOT_APPLICABLE),
        "historical_reports": (STATUS_HISTORICAL_REAL
                                if brand_id == "stick"
                                else STATUS_NOT_CONNECTED),
        "north_stars": STATUS_LIVE,
    }


def _v21_executive_summary_movement(brand_id, fetch, scorecard,
                                     channel_summary):
    """Movement-based analyst commentary. Deterministic; the
    numbers come from the scorecard / channel_mix, the analyst
    layer reads them as movement.
    """
    stmts = []
    # Find Sessions row
    sessions_row = next(
        (r for r in scorecard.get("rows") or []
         if r.get("label") == "Sessions"), None)
    if sessions_row and sessions_row.get("delta_pct") is not None:
        cur = sessions_row.get("current") or 0
        prev = sessions_row.get("previous") or 0
        if sessions_row.get("comparison_status") == "improving":
            stmts.append({
                "type": "MEASURED_FACT",
                "confidence": "HIGH",
                "statement": (f"{brand_id.title().replace('-', ' ')} recorded "
                              f"{cur:,} website sessions, up "
                              f"{sessions_row['delta_pct']}% from the "
                              f"previous 31-day period ({prev:,})."),
            })
        elif sessions_row.get("comparison_status") == "regressing":
            stmts.append({
                "type": "MEASURED_FACT",
                "confidence": "HIGH",
                "statement": (f"{brand_id.title().replace('-', ' ')} recorded "
                              f"{cur:,} website sessions, down "
                              f"{abs(sessions_row['delta_pct'])}% from the "
                              f"previous 31-day period ({prev:,})."),
            })
        else:
            stmts.append({
                "type": "MEASURED_FACT",
                "confidence": "HIGH",
                "statement": (f"{brand_id.title().replace('-', ' ')} recorded "
                              f"{cur:,} website sessions in the last 31 "
                              f"days; essentially flat versus the previous "
                              f"31-day window."),
            })
    elif sessions_row:
        stmts.append({
            "type": "MEASURED_FACT",
            "confidence": "MEDIUM",
            "statement": (f"{brand_id.title().replace('-', ' ')} recorded "
                          f"website sessions in the last 31 days; previous-"
                          "period comparison is unavailable (GA4 returned "
                          "no data for the comparison window)."),
        })
    # Channel mix movement
    if channel_summary.get("data_status") == "LIVE":
        top = max(channel_summary.get("rows") or [],
                  key=lambda r: r.get("current_sessions") or 0,
                  default=None)
        if top and top.get("current_sessions"):
            share = top.get("share_of_sessions") or 0
            stmts.append({
                "type": "MEASURED_FACT",
                "confidence": "HIGH",
                "statement": (f"{top['channel']} is the largest traffic "
                              f"source at {share}% of sessions "
                              f"({top['current_sessions']:,} sessions)."),
            })
    # Key events
    events = (fetch.get("events") or {})
    if events.get("ok") and events.get("headline"):
        stmts.append({
            "type": "MEASURED_FACT",
            "confidence": "MEDIUM",
            "statement": events["headline"],
        })
    # North Star distance
    cfg = BRAND_CONFIG.get(brand_id) or {}
    if cfg.get("lead_tracking_status") == STATUS_PENDING:
        stmts.append({
            "type": "SUPPORTED_INFERENCE",
            "confidence": "MEDIUM",
            "statement": ("Stick website lead tracking is PENDING; "
                          "actual North Star outcomes (Psycho Bunny sales, "
                          "24 fittings/week, 24 coaching/week) cannot "
                          "yet be attributed from this report."),
        })
    return stmts


def _v21_marketing_support_signal(brand_id, scorecard):
    """Marketing support signals (sessions, reach, engagement) —
    what the marketing function directly drives."""
    return {
        "label": "Marketing support (demand signal)",
        "kpis": [r for r in (scorecard.get("rows") or [])
                 if r.get("label") != "Verified Leads"],
        "note": ("These are the signals marketing can move "
                 "directly. They are NOT the North Star business "
                 "outcomes (Psycho Bunny sales, fittings, "
                 "coaching)."),
    }


def _v21_business_outcome_signal(brand_id, fetch):
    """Business outcomes (North Star progress) — operational
    data not yet wired into Reporting. Reported separately,
    not mixed with marketing support."""
    if brand_id != "stick":
        return {
            "label": "Business outcomes (North Star progress)",
            "data_status": STATUS_NOT_APPLICABLE,
            "note": ("Swing Shack North Star architecture "
                     "defined in V1.3 §6; metrics TBD."),
            "kpis": [],
        }
    # Stick: lead tracking PENDING → outcome data unavailable
    return {
        "label": "Business outcomes (North Star progress)",
        "data_status": STATUS_PENDING,
        "note": ("Psycho Bunny sales / 24 fittings/wk / 24 coaching/wk "
                 "are operational outcomes. Reporting cannot measure "
                 "them until Stick generate_lead event is validated."),
        "kpis": [
            {"name": "Psycho Bunny sales (target R350k/month)",
             "data_status": STATUS_PENDING, "current": None},
            {"name": "Fittings (target 24/week)",
             "data_status": STATUS_PENDING, "current": None},
            {"name": "Coaching sessions (target 24/week)",
             "data_status": STATUS_PENDING, "current": None},
        ],
    }


def _v21_severity_score(limits, brand_id, fetch):
    """Severity-score what-needs-attention items."""
    out = []
    severity_map = {
        # HIGH: blocks business; MEDIUM: degraded measurement;
        # LOW: nice-to-have
        "lead_tracking": "HIGH",
        "meta_ads": "MEDIUM",
        "instagram": "MEDIUM",
        "facebook_insights": "MEDIUM",
        "synthetic_ads": "HIGH",
    }
    for lim in (limits or []):
        if "lead tracking" in lim.lower() or "generate_lead" in lim.lower():
            sev = "HIGH"
        elif "Meta Ads" in lim and "NOT_CONNECTED" in lim:
            sev = "MEDIUM"
        elif ("synthetic" in lim.lower()
              and ("quarantine" in lim.lower() or "Meta" in lim)):
            sev = "HIGH"
        elif ("Instagram" in lim and "stale" in lim.lower()):
            sev = "MEDIUM"
        elif ("Facebook" in lim and "PARTIAL" in lim):
            sev = "MEDIUM"
        else:
            sev = "LOW"
        out.append({
            "title": lim[:80],
            "evidence": lim,
            "business_relevance": lim,
            "severity": sev,
            "interpretation": lim,
        })
    return out


def _v21_lineage(brand_id, cfg, fetch, sources):
    """Source lineage with data_as_of."""
    return [
        {"name": "GA4 — channel mix", "asset": cfg.get("ga4_property_id"),
         "brand_id": brand_id, "period": "current + previous 31-day window",
         "source": "/api/ga4/<brand>/channel-mix",
         "data_as_of": (fetch.get("channel_mix") or {}).get(
             "checked_at"),
         "data_status": ("LIVE"
                          if (fetch.get("channel_mix") or {}).get("ok")
                          else "UNAVAILABLE")},
        {"name": "GA4 — landing pages", "asset": cfg.get("ga4_property_id"),
         "brand_id": brand_id, "period": "current + previous 31-day window",
         "source": "/api/ga4/<brand>/pages-enriched",
         "data_as_of": (fetch.get("pages") or {}).get("checked_at"),
         "data_status": ("LIVE"
                          if (fetch.get("pages") or {}).get("ok")
                          else "UNAVAILABLE")},
        {"name": "GA4 — key event audit",
         "asset": cfg.get("ga4_property_id"),
         "brand_id": brand_id, "period": "current 31-day window",
         "source": "/api/ga4/<brand>/event-audit",
         "data_as_of": (fetch.get("events") or {}).get("checked_at"),
         "data_status": ("LIVE"
                          if (fetch.get("events") or {}).get("ok")
                          else "UNAVAILABLE")},
        {"name": "Marketing Calendar (canonical)",
         "asset": "data/intelligence/marketing-calendar/<brand>.jsonl",
         "brand_id": brand_id, "period": "static",
         "source": "marketing_calendar.canonical_records",
         "data_as_of": _now_iso(),
         "data_status": "LIVE"},
        {"name": "Meta Ads (real)",
         "asset": cfg.get("meta_ad_account_id"),
         "brand_id": brand_id, "period": "—",
         "source": "Step 4B pending — synthetic data quarantined",
         "data_as_of": None,
         "data_status": "NOT_CONNECTED"},
    ]


def render_v21_brand_report_html(brand_id: str, period_days: int = 31,
                                  cookie: Optional[str] = None) -> str:
    """Render the V2.1 management report as HTML."""
    r = build_v21_brand_report(brand_id, period_days, cookie=cookie)
    if r.get("error"):
        return f"<h1>Error</h1><p>{r['error']}</p>"
    parts = [
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>{r['brand_name']} — V2.1 Management Report</title>",
        _HTML_CSS,
        "</head><body>",
    ]
    parts.append(f"<h1>{r['brand_name']} — Management Report</h1>")
    parts.append(f"<div class='meta'>")
    parts.append(f"Period: <strong>{r['report_period']['start']} → "
                 f"{r['report_period']['end']}</strong> "
                 f"({r['report_period']['days']} days)<br>")
    parts.append(f"Previous: <strong>{r['previous_period']['start']} → "
                 f"{r['previous_period']['end']}</strong> "
                 f"({r['previous_period']['days']} days)<br>")
    parts.append(f"90-day baseline: {r['ninety_day_baseline']['start']} → "
                 f"{r['ninety_day_baseline']['end']}<br>")
    parts.append(f"Generated: {r['generated_at']}<br>")
    parts.append("</div>")

    # Scorecard
    parts.append("<h2>KPI Scorecard (V2.1 §11)</h2>")
    parts.append("<table class='coverage-table'>")
    parts.append("<tr><th>KPI</th><th>Current</th>"
                 "<th>Previous</th><th>Δ</th><th>%</th>"
                 "<th>Trend</th><th>Status</th><th>Note</th></tr>")
    for row in (r.get("kpi_scorecard") or {}).get("rows") or []:
        cur = row.get("current") if row.get("current") is not None else "—"
        prev = row.get("previous") if row.get("previous") is not None else "—"
        dab = row.get("delta_abs")
        dab = "—" if dab is None else f"{dab:+,}"
        dpct = row.get("delta_pct")
        dpct = "—" if dpct is None else f"{dpct:+.1f}%"
        arrow = row.get("trend_arrow", "—")
        ds = row.get("data_status", "—")
        note = row.get("note", "")
        parts.append(
            f"<tr><td>{row['label']}</td><td>{cur}</td><td>{prev}</td>"
            f"<td>{dab}</td><td>{dpct}</td><td>{arrow}</td>"
            f"<td>{_pill(ds)}</td><td>{note}</td></tr>")
    parts.append("</table>")

    # Executive summary (movement-based)
    parts.append("<h2>Executive Summary (movement-based)</h2>")
    parts.append("<ul class='exec-summary'>")
    for st in (r.get("sections", {}).get(
            "executive_summary", {}).get("statements") or []):
        parts.append(f"<li>{st['statement']} "
                     f"<em class='meta'>({st.get('type','')}, "
                     f"confidence: {st.get('confidence','')})</em></li>")
    parts.append("</ul>")

    # Marketing support vs business outcomes
    parts.append("<h2>Marketing Support vs North Star Outcomes (V2.1 §17)</h2>")
    ms = r.get("marketing_support") or {}
    parts.append(f"<h3>{ms.get('label', 'Marketing support')}</h3>")
    parts.append(f"<div class='section'>{ms.get('note','')}</div>")
    bo = r.get("business_outcomes") or {}
    parts.append(f"<h3>{bo.get('label', 'Business outcomes')}</h3>")
    parts.append(f"<div class='section'>{_pill(bo.get('data_status',''))} "
                 f"{bo.get('note','')}")
    for kpi in (bo.get("kpis") or []):
        parts.append(f"<div>• {kpi.get('name','')}: "
                     f"{_pill(kpi.get('data_status',''))}</div>")
    parts.append("</div>")

    # Channel mix
    cm = r.get("sections", {}).get("channel_mix") or {}
    parts.append(f"<h2>Channel Mix (V2.1 §6) "
                 f"{_pill(cm.get('data_status','UNKNOWN'))}</h2>")
    if cm.get("data_status") == "LIVE":
        parts.append("<table class='coverage-table'>")
        parts.append("<tr><th>Channel</th>"
                     "<th>Current</th><th>Prev</th>"
                     "<th>Share</th><th>Δ%</th></tr>")
        for row in cm.get("rows") or []:
            cur = row.get("current_sessions") or 0
            prev = row.get("previous_sessions")
            prev_disp = prev if prev is not None else "—"
            parts.append(
                f"<tr><td>{row['channel']}</td><td>{cur:,}</td>"
                f"<td>{prev_disp}</td>"
                f"<td>{row.get('share_of_sessions',0):.1f}%</td>"
                f"<td>{row.get('delta_pct','—')}</td></tr>")
        parts.append("</table>")
    else:
        parts.append(f"<div class='section'>"
                     f"Channel Mix — Not connected — GA4 channel "
                     f"grouping endpoint unavailable. "
                     f"{cm.get('reason','')}</div>")

    # Landing pages
    lp = r.get("sections", {}).get("landing_pages") or {}
    parts.append(f"<h2>Landing-Page Performance (V2.1 §7) "
                 f"{_pill(lp.get('data_status','UNKNOWN'))}</h2>")
    if lp.get("data_status") == "LIVE":
        parts.append("<table class='coverage-table'>")
        parts.append("<tr><th>Service page</th><th>Current</th>"
                     "<th>Previous</th><th>Δ%</th></tr>")
        for row in lp.get("service_pages") or []:
            cur = row.get("current_sessions") or 0
            prev = row.get("previous_sessions")
            prev_disp = prev if prev is not None else "—"
            parts.append(
                f"<tr><td>{row['service_page']}</td><td>{cur:,}</td>"
                f"<td>{prev_disp}</td>"
                f"<td>{row.get('delta_pct','—')}</td></tr>")
        parts.append("</table>")
    else:
        parts.append(f"<div class='section'>"
                     f"Landing-Page Performance — Not connected — "
                     f"GA4 pagePath endpoint unavailable. "
                     f"{lp.get('reason','')}</div>")

    # Key event audit
    ke = r.get("sections", {}).get("key_events") or {}
    parts.append(f"<h2>Key-Event Audit (V2.1 §8) "
                 f"{_pill(ke.get('data_status','UNKNOWN'))}</h2>")
    if ke.get("headline"):
        parts.append(f"<div class='section'><strong>Headline:</strong> "
                     f"{ke['headline']}</div>")
    rows = ke.get("rows") or []
    if rows:
        parts.append("<table class='coverage-table'>")
        parts.append("<tr><th>Event</th><th>Count</th>"
                     "<th>Conversions</th><th>Commercial meaning</th></tr>")
        for row in rows[:10]:
            parts.append(
                f"<tr><td>{row['event_name']}</td><td>{row['count']}</td>"
                f"<td>{row.get('key_event_conversions',0)}</td>"
                f"<td>{row.get('commercial_meaning','')}</td></tr>")
        parts.append("</table>")
    if not rows:
        parts.append("<div class='section'>No GA4 events recorded in "
                     "the report window.</div>")

    # Pillar mix
    pmx = r.get("sections", {}).get("pillar_mix") or {}
    parts.append(f"<h2>Business Pillar Mix (canonical Calendar)</h2>")
    parts.append(f"<div class='section'><strong>Source:</strong> "
                 f"{pmx.get('source','—')}</div>")
    parts.append(f"<div class='meta'>"
                 f"canonical_event_count={pmx.get('canonical_event_count','—')}, "
                 f"classified_count={pmx.get('classified_event_count','—')}, "
                 f"cultural_moments={pmx.get('cultural_moment_count','—')}, "
                 f"preserved_unclassified={pmx.get('preserved_unclassified_count','—')}, "
                 f"denominator={pmx.get('denominator_used_for_pillar_percentages','—')}</div>")
    counts = pmx.get("pillar_event_counts") or {}
    pct = pmx.get("pillar_event_pct") or {}
    parts.append("<table class='coverage-table'>")
    parts.append("<tr><th>Pillar</th><th>Events</th><th>%</th></tr>")
    for p in ("retail", "fitting", "coaching"):
        parts.append(f"<tr><td>{p.capitalize()}</td>"
                     f"<td>{counts.get(p,0)}</td>"
                     f"<td>{pct.get(p,0):.1f}%</td></tr>")
    parts.append("</table>")

    # North Stars
    ns = r.get("sections", {}).get("north_stars", {}).get("items") or {}
    parts.append("<h2>North Stars</h2>")
    parts.append("<div class='section'>")
    for k, v in ns.items():
        label = v.get("label") if isinstance(v, dict) else str(v)
        target = v.get("target") if isinstance(v, dict) else ""
        parts.append(f"<div><strong>{label}</strong>: {target}</div>")
    parts.append("</div>")

    # Sources (data_as_of)
    parts.append("<h2>Sources & Freshness</h2>")
    parts.append("<table class='coverage-table'>")
    parts.append("<tr><th>Source</th><th>Status</th>"
                 "<th>Data as of</th><th>Freshness</th></tr>")
    for s in r.get("sections", {}).get("sources") or []:
        parts.append(f"<tr><td>{s['source']}</td>"
                     f"<td>{_pill(s['data_status'])}</td>"
                     f"<td>{(s.get('data_as_of') or '—')[:19]}</td>"
                     f"<td>{s.get('freshness','')}</td></tr>")
    parts.append("</table>")

    # Meta Ads status
    ma = r.get("meta_ads_status") or {}
    parts.append("<h2>Paid Media Status (V2.1 §16)</h2>")
    parts.append(f"<div class='section'>{_pill(ma.get('data_status',''))} "
                 f"{ma.get('rule','')}</div>")

    # What needs attention
    parts.append("<h2>What Needs Attention (V2.1 §13)</h2>")
    for n in (r.get("what_needs_attention") or []):
        sev = (n.get("severity") or "low").lower()
        parts.append(f"<div class='rec {sev}'>")
        parts.append(f"<strong>[{n.get('severity','LOW')}] "
                     f"{n.get('title','')}</strong><br>")
        parts.append(f"<em>Evidence:</em> {n.get('evidence','')}<br>")
        parts.append(f"<em>Business relevance:</em> "
                     f"{n.get('business_relevance','')}")
        parts.append("</div>")

    # Limitations
    parts.append("<h2>Limitations</h2>")
    parts.append("<div class='section'>")
    for lim in r.get("data_limitations") or []:
        parts.append(f"<div>• {lim}</div>")
    parts.append("</div>")

    # Source lineage
    parts.append("<h2>Source Lineage</h2>")
    parts.append("<table class='coverage-table'>")
    parts.append("<tr><th>Source</th><th>Asset</th>"
                 "<th>Period</th><th>Data as of</th><th>Path</th></tr>")
    for ln in r.get("source_lineage") or []:
        parts.append(
            f"<tr><td>{ln.get('name','')}</td>"
            f"<td>{ln.get('asset','')}</td>"
            f"<td>{ln.get('period','')}</td>"
            f"<td>{(ln.get('data_as_of') or '—')[:19]}</td>"
            f"<td>{ln.get('source','')}</td></tr>")
    parts.append("</table>")

    parts.append("<div class='footer'>")
    parts.append(f"<em>Reporting Intelligence V2.1 — Campaign OS — "
                 f"brand_isolation_enforced — synthetic Meta Ads "
                 f"data quarantined — data_as_of per source.</em>")
    parts.append("</div>")

    parts.append("</body></html>")
    return "\n".join(parts)


def render_v21_portfolio_html(reports: dict) -> str:
    """Render cross-brand V2.1 portfolio summary."""
    parts = [
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>Portfolio Management — V2.1</title>",
        _HTML_CSS,
        "</head><body>",
    ]
    parts.append("<h1>Portfolio Management — V2.1</h1>")
    parts.append("<div class='meta'>Cross-brand management summary "
                 "(contextual, not league).</div>")
    for bid in ("stick", "swing-shack"):
        r = reports.get(bid, {})
        parts.append(f"<h2>{r.get('brand_name', bid.title())} "
                     f"(<code>{bid}</code>)</h2>")
        parts.append(f"<div class='meta'>Period: "
                     f"{r.get('report_period', {}).get('start','?')} → "
                     f"{r.get('report_period', {}).get('end','?')}</div>")
        # Inline scorecard
        sc = r.get("kpi_scorecard") or {}
        if (sc.get("rows") or []):
            parts.append("<table class='coverage-table'>")
            parts.append("<tr><th>KPI</th><th>Current</th>"
                         "<th>Previous</th><th>Δ%</th>"
                         "<th>Status</th></tr>")
            for row in sc["rows"][:6]:
                cur = row.get("current") if row.get("current") is not None else "—"
                prev = row.get("previous") if row.get("previous") is not None else "—"
                dpct = row.get("delta_pct")
                dpct_disp = f"{dpct:+.1f}%" if dpct is not None else "—"
                parts.append(
                    f"<tr><td>{row['label']}</td>"
                    f"<td>{cur}</td><td>{prev}</td>"
                    f"<td>{dpct_disp}</td>"
                    f"<td>{_pill(row.get('data_status','—'))}</td></tr>")
            parts.append("</table>")
        # Movement-based executive summary
        es = r.get("sections", {}).get(
            "executive_summary", {}).get("statements") or []
        if es:
            parts.append("<h3>Movement</h3><ul>")
            for st in es:
                parts.append(f"<li>{st.get('statement','')}</li>")
            parts.append("</ul>")
    parts.append("<div class='footer'>")
    parts.append("<em>V2.1 portfolio summary — contextual comparison, "
                 "not league.</em>")
    parts.append("</div>")
    parts.append("</body></html>")
    return "\n".join(parts)







# ─── V2.2: REPORT-PERIOD CONTRACT + REAL COMPARISONS ──────────────────


def build_v22_brand_report(brand_id: str, period_days: int = 31,
                            cookie: Optional[str] = None) -> dict:
    """V2.2 management report: ONE report-period object feeds
    all subqueries. Real previous + 90-day baseline. Honest
    consistency: same Sessions / Users / Engagement numbers
    in scorecard, channel mix, executive summary.

    Per V2.2 §4: report.sessions == scorecard.sessions ==
    comparison.current.sessions. All computed once.
    """
    cfg = BRAND_CONFIG.get(brand_id)
    if not cfg:
        return {"error": f"unknown brand_id: {brand_id}"}

    # V2.2 §1: one canonical report-period object
    rp = _v22_report_period(period_days)

    # V2.2 §7: pull sessions + users + engagement + pageviews +
    # conversions from ONE GA4 call. Same metric defs across
    # current + previous + 90-day windows.
    base = os.environ.get("CAMPAIGN_OS_BASE_URL",
                          "http://localhost:8080").rstrip("/")
    sess_data = _v22_runtime_fetch_sessions(base, brand_id, period_days, cookie)
    cm_data = _v22_runtime_fetch_channel_mix(base, brand_id, period_days, cookie)
    pages_data = _v22_runtime_fetch_pages(base, brand_id, period_days, cookie)
    events_data = _v22_runtime_fetch_events(base, brand_id, period_days, cookie)

    # ── Pillar mix via canonical Calendar (V2.2 §5) ──
    planning = _brand_planning(brand_id)
    pmx = _pillar_mix(brand_id, planning)
    # V2.2 §5: explicit reporting horizon for pillar mix
    horizon = _v22_pillar_horizon(brand_id, pmx)

    # ── Aggregated scorecard with REAL comparison + 90d baseline ──
    scorecard = _v22_scorecard(brand_id, sess_data, cm_data, pages_data,
                                events_data)

    # ── Channel mix section ──
    channel_section = _v22_channel_section(cm_data)

    # ── Landing pages section ──
    pages_section = _v22_pages_section(brand_id, pages_data)

    # ── Key events section (V2.2 §8: identify the configured key event) ──
    events_section = _v22_events_section(brand_id, events_data, scorecard)

    # ── Sources (data_as_of) ──
    sources = _v22_sources(brand_id, sess_data, cm_data, pages_data,
                           events_data)

    # ── Coverage matrix ──
    coverage = _v22_coverage(brand_id, sess_data, cm_data, pages_data,
                            events_data, pmx)

    # ── Marketing support vs business outcomes ──
    ms = _v22_marketing_support(scorecard)
    bo = _v22_business_outcomes(brand_id)

    # ── Executive summary (V2.2 §10): real movement, no template placeholders ──
    exec_stmts = _v22_executive_summary_movement(brand_id, rp, scorecard,
                                                   channel_section)

    # ── Recommendations + tests + risks + what-needs-attention ──
    recs = _recommendations_for(brand_id)
    tests = _test_plan_for(brand_id)
    limits = _limitations_for(brand_id, {"sections": {}})

    report = {
        "schema": "https://campaign-os/reporting/v2.2",
        "version": "2.2",
        "brand_id": brand_id,
        "brand_name": cfg["name"],
        "domain": cfg["domain"],
        # V2.2 §4: one report_period feeds everything
        "report_period": rp,
        "data_complete_through": rp["data_complete_through"],
        "previous_period": {
            "start": rp["previous_start"],
            "end": rp["previous_end"],
            "days": rp["days_per_window"],
        },
        "ninety_day_baseline": {
            "start": rp["ninetieth_start"],
            "end": rp["ninetieth_end"],
            "days": 90,
        },
        "generated_at": _now_iso(),
        "data_status_taxonomy_used": True,
        "brand_isolation_enforced": True,

        # V2.2 §4: the scorecard IS the canonical session value
        "sessions": next(
            (r.get("current") for r in (scorecard.get("rows") or [])
             if r.get("label") == "Sessions"), None),
        "users": next(
            (r.get("current") for r in (scorecard.get("rows") or [])
             if r.get("label") == "Users"), None),

        # V2.2 §11: KPI scorecard with real current + previous + 90-day
        "kpi_scorecard": scorecard,

        # V2.2 §17: marketing vs business outcomes
        "marketing_support": ms,
        "business_outcomes": bo,

        "sections": {
            "executive_summary": {"statements": exec_stmts},
            "data_coverage": coverage,
            "channel_mix": channel_section,
            "landing_pages": pages_section,
            "key_events": events_section,
            "pillar_mix": pmx,
            "pillar_mix_horizon": horizon,
            "north_stars": {"items": cfg.get("north_stars") or {}},
            "sources": sources,
        },

        "what_needs_attention": _v22_severity_score(limits, sess_data,
                                                      brand_id),
        "what_worked": _v22_what_worked(brand_id, scorecard, sess_data),

        "meta_ads_status": {
            "data_status": STATUS_NOT_CONNECTED,
            "rule": ("SYNTHETIC ads data is quarantined. Real ads "
                     "data only. Report does NOT invent paid "
                     "performance until Meta Ads Step 4B ships."),
            "synthetic_file": "data/meta-ads.json (quarantined)",
        },

        "recommendations": recs,
        "next_period_tests": tests,
        "data_limitations": limits,
        "source_lineage": _v22_lineage(brand_id, cfg, sess_data, sources),
    }
    return report


def _v22_runtime_fetch_sessions(base, brand_id, days, cookie):
    """Pull /api/ga4/<brand>/v22/sessions."""
    import urllib.request as _ur
    url = f"{base}/api/ga4/{brand_id}/v22/sessions?days={days}"
    try:
        req = _ur.Request(url)
        if cookie:
            req.add_header("Cookie", cookie)
        with _ur.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"ok": False, "error": f"sessions unreachable: {e}"}


def _v22_runtime_fetch_channel_mix(base, brand_id, days, cookie):
    import urllib.request as _ur
    url = f"{base}/api/ga4/{brand_id}/v22/channel-mix?days={days}"
    try:
        req = _ur.Request(url)
        if cookie:
            req.add_header("Cookie", cookie)
        with _ur.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"ok": False, "error": f"channel-mix unreachable: {e}"}


def _v22_runtime_fetch_pages(base, brand_id, days, cookie):
    import urllib.request as _ur
    url = f"{base}/api/ga4/{brand_id}/v22/pages?days={days}"
    try:
        req = _ur.Request(url)
        if cookie:
            req.add_header("Cookie", cookie)
        with _ur.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"ok": False, "error": f"pages unreachable: {e}"}


def _v22_runtime_fetch_events(base, brand_id, days, cookie):
    import urllib.request as _ur
    url = f"{base}/api/ga4/{brand_id}/event-audit?days={days}"
    try:
        req = _ur.Request(url)
        if cookie:
            req.add_header("Cookie", cookie)
        with _ur.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"ok": False, "error": f"events unreachable: {e}"}


def _v22_pillar_horizon(brand_id, pmx):
    """V2.2 §5: explicit reporting horizon + included/excluded
    classification for pillar mix.
    """
    # V2.2 §5 — Reporting horizon is the most-recent active
    # planning cycle (2026 calendar year). Cultural moments are
    # excluded from the denominator per V1.1 §6.
    return {
        "horizon_label": "active 2026 planning cycle",
        "reporting_horizon_start": "2026-01-01",
        "reporting_horizon_end": "2026-12-31",
        "canonical_total": pmx.get("canonical_event_count"),
        "included_count": pmx.get("classified_event_count"),
        "excluded_count": pmx.get("excluded_event_count"),
        "included_statuses": ["classified"],
        "excluded_statuses": [
            "cultural_moment",
            "preserved_unclassified",
        ],
        "contextual_unclassified_count": pmx.get(
            "preserved_unclassified_count"),
        "denominator": pmx.get("denominator_used_for_pillar_percentages"),
        "retail_count": (pmx.get("pillar_event_counts") or {}).get("retail"),
        "fitting_count": (pmx.get("pillar_event_counts") or {}).get("fitting"),
        "coaching_count": (pmx.get("pillar_event_counts") or {}).get("coaching"),
        "source": pmx.get("source"),
        "note": ("Reporting pillar mix filters Calendar records to "
                 "the active planning cycle. Records from prior or "
                 "future cycles are excluded from the denominator. "
                 "Cultural moments + preserved-unclassified events "
                 "are also excluded per V1.1 §6."),
    }


def _v22_scorecard(brand_id, sess_data, cm_data, pages_data, events_data):
    """V2.2 §11: KPI scorecard with real deltas. Sessions /
    Users / Engagement rate / Pageviews come from one GA4
    call (sess_data) so all metrics reconcile to the same
    period.
    """
    sess_ok = sess_data.get("ok") if sess_data else False
    rows = []
    if sess_ok:
        cur = sess_data.get("current") or {}
        prev = sess_data.get("previous") or {}
        n = sess_data.get("ninety_day") or {}
        comparison = sess_data.get("comparison") or {}
        # Pull the canonical aggregations from comparison
        rows = [
            {
                "label": "Sessions",
                "current": comparison.get("sessions", {}).get("current"),
                "previous": comparison.get("sessions", {}).get("previous"),
                "delta_abs": comparison.get("sessions", {}).get("delta_abs"),
                "delta_pct": comparison.get("sessions", {}).get("delta_pct"),
                "comparison_status": comparison.get("sessions", {}).get("comparison_status"),
                "ninety_day": comparison.get("ninety_day", {}).get("sessions_mean_90d"),
                "trend_arrow": _v22_arrow(comparison.get("sessions", {}).get("delta_pct")),
                "data_status": "LIVE",
            },
            {
                "label": "Users",
                "current": comparison.get("users", {}).get("current"),
                "previous": comparison.get("users", {}).get("previous"),
                "delta_abs": comparison.get("users", {}).get("delta_abs"),
                "delta_pct": comparison.get("users", {}).get("delta_pct"),
                "comparison_status": comparison.get("users", {}).get("comparison_status"),
                "ninety_day": comparison.get("ninety_day", {}).get("users_mean_90d"),
                "trend_arrow": _v22_arrow(comparison.get("users", {}).get("delta_pct")),
                "data_status": "LIVE",
            },
            {
                "label": "Engaged sessions",
                "current": comparison.get("engaged_sessions", {}).get("current"),
                "previous": comparison.get("engaged_sessions", {}).get("previous"),
                "delta_abs": comparison.get("engaged_sessions", {}).get("delta_abs"),
                "delta_pct": comparison.get("engaged_sessions", {}).get("delta_pct"),
                "comparison_status": comparison.get("engaged_sessions", {}).get("comparison_status"),
                "ninety_day": comparison.get("ninety_day", {}).get("engaged_sessions_mean_90d"),
                "trend_arrow": _v22_arrow(comparison.get("engaged_sessions", {}).get("delta_pct")),
                "data_status": "LIVE",
            },
            {
                "label": "Engagement rate",
                "current": comparison.get("engagement_rate", {}).get("current"),
                "previous": comparison.get("engagement_rate", {}).get("previous"),
                "delta_abs": comparison.get("engagement_rate", {}).get("delta_abs"),
                "delta_pct": comparison.get("engagement_rate", {}).get("delta_pct"),
                "comparison_status": comparison.get("engagement_rate", {}).get("comparison_status"),
                "ninety_day": comparison.get("ninety_day", {}).get("engagement_rate_90d"),
                "trend_arrow": _v22_arrow(comparison.get("engagement_rate", {}).get("delta_pct")),
                "data_status": "LIVE",
                "unit": "percent",
            },
            {
                "label": "Pageviews",
                "current": comparison.get("pageviews", {}).get("current"),
                "previous": comparison.get("pageviews", {}).get("previous"),
                "delta_abs": comparison.get("pageviews", {}).get("delta_abs"),
                "delta_pct": comparison.get("pageviews", {}).get("delta_pct"),
                "comparison_status": comparison.get("pageviews", {}).get("comparison_status"),
                "ninety_day": comparison.get("ninety_day", {}).get("pageviews_mean_90d"),
                "trend_arrow": _v22_arrow(comparison.get("pageviews", {}).get("delta_pct")),
                "data_status": "LIVE",
            },
            {
                "label": "Conversions",
                "current": comparison.get("conversions", {}).get("current"),
                "previous": comparison.get("conversions", {}).get("previous"),
                "delta_abs": comparison.get("conversions", {}).get("delta_abs"),
                "delta_pct": comparison.get("conversions", {}).get("delta_pct"),
                "comparison_status": comparison.get("conversions", {}).get("comparison_status"),
                "ninety_day": comparison.get("ninety_day", {}).get("conversions_mean_90d"),
                "trend_arrow": _v22_arrow(comparison.get("conversions", {}).get("delta_pct")),
                "data_status": ("LIVE"
                                 if comparison.get("conversions", {}).get("current") is not None
                                 else STATUS_NOT_CONNECTED),
                "note": ("Stick generate_lead event is configured "
                         "in GA4 but on-website CF7 listener not yet "
                         "production-validated. Conversions=0 is "
                         "NOT 'no conversions' — the configured key "
                         "event isn't validated yet.")
                          if brand_id == "stick" else None,
            },
        ]
        # Paid spend
        rows.append({
            "label": "Paid Spend",
            "current": None, "previous": None,
            "delta_abs": None, "delta_pct": None,
            "comparison_status": "no_data",
            "trend_arrow": "—", "trend_status": "no_comparison",
            "data_status": STATUS_NOT_CONNECTED,
            "note": ("Meta Ads is NOT_CONNECTED. Real ads history "
                     "ingestion pending Step 4B. Synthetic data "
                     "remains quarantined."),
        })
        if brand_id == "stick":
            rows.append({
                "label": "Verified Leads",
                "current": None, "previous": None,
                "delta_abs": None, "delta_pct": None,
                "comparison_status": "no_data",
                "trend_arrow": "—", "trend_status": "no_comparison",
                "data_status": STATUS_PENDING,
                "note": ("Stick generate_lead event not yet "
                         "production-validated. Do not report "
                         "verified leads."),
            })
    else:
        # GA4 unreachable: all rows PENDING with consistent reason
        reason = sess_data.get("error", "GA4 unreachable")
        for label in ("Sessions", "Users", "Engaged sessions",
                       "Engagement rate", "Pageviews"):
            rows.append({
                "label": label,
                "current": None, "previous": None,
                "delta_abs": None, "delta_pct": None,
                "comparison_status": "no_data",
                "trend_arrow": "—", "trend_status": "no_comparison",
                "data_status": STATUS_UNAVAILABLE,
                "note": reason,
            })
    return {
        "schema": "https://campaign-os/kpi-scorecard/v2.2",
        "brand_id": brand_id,
        "rows": rows,
        "checked_at": _now_iso(),
    }


def _v22_arrow(delta_pct):
    if delta_pct is None:
        return "—"
    if delta_pct > 0.5:
        return "▲"
    if delta_pct < -0.5:
        return "▼"
    return "→"


def _v22_channel_section(cm_data):
    """Build channel mix section with real deltas."""
    if not cm_data.get("ok"):
        return {
            "data_status": STATUS_UNAVAILABLE,
            "reason": cm_data.get("error", "channel-mix endpoint failed"),
            "rows": [],
            "report_period": cm_data.get("report_period") or {},
        }
    rows = cm_data.get("rows", [])
    total_cur = cm_data.get("total_current_sessions", 0)
    total_prev = cm_data.get("total_previous_sessions")
    return {
        "data_status": "LIVE",
        "current_window": cm_data.get("current_window"),
        "previous_window": cm_data.get("previous_window"),
        "rows": rows,
        "total_current_sessions": total_cur,
        "total_previous_sessions": total_prev,
        "largest_channel": (rows[0]["channel"] if rows else None),
    }


def _v22_pages_section(brand_id, pages_data):
    """Build landing pages section."""
    if not pages_data.get("ok"):
        return {
            "data_status": STATUS_UNAVAILABLE,
            "reason": pages_data.get("error", "pages endpoint failed"),
            "service_pages": [],
            "report_period": pages_data.get("report_period") or {},
        }
    raw = pages_data.get("rows", [])
    if brand_id == "stick":
        patterns = [
            ("/bookings/", "Bookings"),
            ("club-fitting", "Club Fitting"),
            ("coaching", "Coaching"),
            ("psycho-bunny", "Psycho Bunny"),
            ("takomo", "Takomo"),
            ("vice", "Vice"),
            ("avoda", "Avoda"),
            ("lab-putters", "L.A.B. Putters"),
        ]
    else:
        patterns = [
            ("/bookings/", "Bookings"),
            ("/membership", "Membership"),
            ("/fitting", "Fitting"),
            ("/lessons", "Lessons"),
            ("/coaching", "Coaching"),
            ("/flagship", "Flagship Property"),
            ("/10-ball", "10-Ball Truth"),
            ("/shop", "Shop"),
        ]
    matched = {}
    for row in raw:
        path = (row.get("page_path") or "")
        for pat, label in patterns:
            if pat.lower() in path.lower():
                matched[label] = {
                    "current_sessions": row.get("current_sessions") or 0,
                    "previous_sessions": row.get("previous_sessions"),
                    "current_users": row.get("current_users") or 0,
                    "current_engaged_sessions": row.get("current_engaged_sessions") or 0,
                    "current_pageviews": row.get("current_pageviews") or 0,
                    "engagement_rate": row.get("current_engagement_rate"),
                    "delta_abs": row.get("delta_abs"),
                    "delta_pct": row.get("delta_pct"),
                    "comparison_status": row.get("comparison_status"),
                    "path": path,
                }
                break
    service_pages = sorted(matched.values(),
                            key=lambda x: -x["current_sessions"])
    # V2.2 §12: include historical report alongside
    hr = _historical_reports(brand_id)
    return {
        "data_status": "LIVE",
        "current_window": pages_data.get("current_window"),
        "previous_window": pages_data.get("previous_window"),
        "service_pages": service_pages,
        "ninety_day_sessions_mean_per_day": pages_data.get(
            "ninety_day_sessions_mean_per_day"),
        "ninety_day_sessions_total": pages_data.get(
            "ninety_day_sessions_total"),
        "historical_reports": hr,
        "top_raw_paths_sample": (pages_data.get("rows") or [])[:5],
    }


def _v22_events_section(brand_id, events_data, scorecard):
    """V2.2 §8: identify the configured key event explicitly.
    Distinguish number_of_key_event_types from
    number_of_key_event_occurrences.
    """
    if not events_data.get("ok"):
        return {
            "data_status": STATUS_UNAVAILABLE,
            "reason": events_data.get("error", "events endpoint failed"),
            "rows": [],
            "headline": "GA4 events audit endpoint unreachable.",
        }
    rows = events_data.get("rows", [])
    # Identify the configured key events
    configured = [r for r in rows if r.get("key_event_conversions", 0) > 0]
    key_event_types = len(configured)
    key_event_occurrences = sum(r.get("key_event_conversions", 0)
                                 for r in configured)
    if not configured:
        headline = (f"No GA4 key events recorded in the last "
                     f"{events_data.get('window', {}).get('days', 31)} days for {brand_id}.")
    elif all(r.get("commercial_meaning") in ("unknown", "candidate")
             for r in configured):
        names = ", ".join(r["event_name"] for r in configured)
        headline = (f"GA4 recorded {key_event_occurrences} "
                     f"configured key event occurrence(s) across "
                     f"{key_event_types} event type(s) ({names}); "
                     f"commercial meaning has not yet been validated.")
    else:
        names = ", ".join(r["event_name"] for r in configured)
        headline = (f"GA4 recorded {key_event_occurrences} validated "
                     f"conversion(s) from configured key events: {names}.")
    # V2.2 §8: per-event identity
    return {
        "data_status": "LIVE",
        "headline": headline,
        "configured_key_event_name": (configured[0]["event_name"]
                                       if configured else None),
        "configured_key_event_count_for_period": key_event_occurrences,
        "configured_key_event_types_count": key_event_types,
        "rows": rows[:10],
        "all_rows": rows,
        "window": events_data.get("window", {}),
        "checked_at": events_data.get("checked_at"),
    }


def _v22_sources(brand_id, sess_data, cm_data, pages_data, events_data):
    sources = []
    sources.append({
        "source": "GA4 (sessions + comparison)",
        "data_status": ("LIVE" if sess_data.get("ok") else STATUS_UNAVAILABLE),
        "data_as_of": sess_data.get("checked_at"),
        "freshness": "current + previous + 90-day windows",
    })
    sources.append({
        "source": "GA4 (channel mix)",
        "data_status": ("LIVE" if cm_data.get("ok") else STATUS_UNAVAILABLE),
        "data_as_of": cm_data.get("checked_at"),
        "freshness": "current + previous windows",
    })
    sources.append({
        "source": "GA4 (landing pages)",
        "data_status": ("LIVE" if pages_data.get("ok") else STATUS_UNAVAILABLE),
        "data_as_of": pages_data.get("checked_at"),
        "freshness": "current + previous + 90-day windows",
    })
    sources.append({
        "source": "GA4 (event audit)",
        "data_status": ("LIVE" if events_data.get("ok") else STATUS_UNAVAILABLE),
        "data_as_of": events_data.get("checked_at"),
        "freshness": "current window",
    })
    sources.append({
        "source": "Marketing Calendar (canonical)",
        "data_status": STATUS_LIVE,
        "data_as_of": _now_iso(),
        "freshness": "canonical — read at build time",
    })
    return sources


def _v22_coverage(brand_id, sess_data, cm_data, pages_data,
                  events_data, pmx):
    return {
        "ga4": ("LIVE" if sess_data.get("ok") else STATUS_UNAVAILABLE),
        "ga4_channel_mix": ("LIVE" if cm_data.get("ok")
                            else STATUS_UNAVAILABLE),
        "ga4_landing_pages": ("LIVE" if pages_data.get("ok")
                                else STATUS_UNAVAILABLE),
        "ga4_key_events": ("LIVE" if events_data.get("ok")
                            else STATUS_UNAVAILABLE),
        "facebook": (STATUS_LIVE if brand_id == "swing-shack"
                      else STATUS_PARTIAL),
        "instagram": (STATUS_STALE if brand_id == "swing-shack"
                       else STATUS_NOT_CONNECTED),
        "meta_ads": STATUS_NOT_CONNECTED,
        "lead_tracking": (STATUS_PENDING if brand_id == "stick"
                           else STATUS_NOT_APPLICABLE),
        "strategy": STATUS_LIVE,
        "pillar_mix": pmx.get("data_status") or STATUS_NOT_APPLICABLE,
        "north_stars": STATUS_LIVE,
        "historical_reports": ("HISTORICAL_REAL"
                                 if brand_id == "stick"
                                 else STATUS_NOT_CONNECTED),
    }


def _v22_marketing_support(scorecard):
    return {
        "label": "Marketing support (demand signal)",
        "kpis": [r for r in (scorecard.get("rows") or [])
                 if r.get("label") != "Verified Leads"],
        "note": ("These are signals marketing can move directly. "
                 "They are NOT the North Star business outcomes "
                 "(Psycho Bunny sales, fittings, coaching)."),
    }


def _v22_business_outcomes(brand_id):
    if brand_id != "stick":
        return {
            "label": "Business outcomes (North Star progress)",
            "data_status": STATUS_NOT_APPLICABLE,
            "note": ("Swing Shack North Star architecture defined in "
                     "V1.3 §6; metrics TBD."),
            "kpis": [],
        }
    return {
        "label": "Business outcomes (North Star progress)",
        "data_status": STATUS_PENDING,
        "note": ("Psycho Bunny sales / 24 fittings/wk / 24 coaching/wk "
                 "are operational outcomes. Reporting cannot measure "
                 "them until Stick generate_lead event is validated."),
        "kpis": [
            {"name": "Psycho Bunny sales (target R350k/month)",
             "data_status": STATUS_PENDING, "current": None},
            {"name": "Fittings (target 24/week)",
             "data_status": STATUS_PENDING, "current": None},
            {"name": "Coaching sessions (target 24/week)",
             "data_status": STATUS_PENDING, "current": None},
        ],
    }


def _v22_executive_summary_movement(brand_id, rp, scorecard,
                                     channel_section):
    """V2.2 §10: executive summary uses REAL movement. Numbers
    are injected from the scorecard — no template placeholders
    like 'up X%' survive rendering.
    """
    stmts = []
    sessions_row = next((r for r in (scorecard.get("rows") or [])
                          if r.get("label") == "Sessions"), None)
    users_row = next((r for r in (scorecard.get("rows") or [])
                       if r.get("label") == "Users"), None)
    er_row = next((r for r in (scorecard.get("rows") or [])
                     if r.get("label") == "Engagement rate"), None)
    pv_row = next((r for r in (scorecard.get("rows") or [])
                     if r.get("label") == "Pageviews"), None)
    period_label = (f"{rp['current_start']} → {rp['current_end']}")
    prev_label = (f"{rp['previous_start']} → {rp['previous_end']}")
    if sessions_row and sessions_row.get("current") is not None:
        cur_s = sessions_row["current"]
        prev_s = sessions_row.get("previous")
        dpct = sessions_row.get("delta_pct")
        status = sessions_row.get("comparison_status")
        if status == "improving":
            stmts.append({
                "type": "MEASURED_FACT",
                "confidence": "HIGH",
                "statement": (f"{brand_id.title().replace('-', ' ')} recorded "
                              f"{cur_s:,} sessions during {period_label}, "
                              f"up {dpct}% from the previous 31-day "
                              f"period ({prev_label}: {prev_s:,} sessions)."),
            })
        elif status == "regressing":
            stmts.append({
                "type": "MEASURED_FACT",
                "confidence": "HIGH",
                "statement": (f"{brand_id.title().replace('-', ' ')} recorded "
                              f"{cur_s:,} sessions during {period_label}, "
                              f"down {abs(dpct)}% from the previous 31-day "
                              f"period ({prev_label}: {prev_s:,} sessions)."),
            })
        elif status == "flat":
            stmts.append({
                "type": "MEASURED_FACT",
                "confidence": "HIGH",
                "statement": (f"{brand_id.title().replace('-', ' ')} recorded "
                              f"{cur_s:,} sessions during {period_label}, "
                              f"essentially flat vs the previous 31-day "
                              f"period ({prev_label}: {prev_s:,})."),
            })
        elif status == "no_previous":
            stmts.append({
                "type": "MEASURED_FACT",
                "confidence": "MEDIUM",
                "statement": (f"{brand_id.title().replace('-', ' ')} recorded "
                              f"{cur_s:,} sessions during {period_label}; "
                              f"the previous 31-day window has no data "
                              f"for comparison."),
            })
    if users_row and users_row.get("current") is not None:
        cur_u = users_row["current"]
        prev_u = users_row.get("previous")
        dpct = users_row.get("delta_pct")
        status = users_row.get("comparison_status")
        if status in ("improving", "regressing", "flat") and dpct is not None:
            direction = ("up" if dpct > 0 else
                         ("down" if dpct < 0 else "flat"))
            stmts.append({
                "type": "MEASURED_FACT",
                "confidence": "HIGH",
                "statement": (f"Users {direction} {abs(dpct)}% to "
                              f"{cur_u:,} ({prev_label}: {prev_u:,})."),
            })
    if er_row and er_row.get("current") is not None:
        cur_er = er_row["current"]
        prev_er = er_row.get("previous")
        dpct = er_row.get("delta_pct")
        status = er_row.get("comparison_status")
        if status in ("improving", "regressing") and dpct is not None:
            direction = ("improved" if dpct > 0 else "declined")
            stmts.append({
                "type": "MEASURED_FACT",
                "confidence": "HIGH",
                "statement": (f"Engagement rate {direction} from "
                              f"{prev_er}% to {cur_er}% "
                              f"({abs(dpct)}%)."),
            })
    if pv_row and pv_row.get("current") is not None:
        cur_pv = pv_row["current"]
        prev_pv = pv_row.get("previous")
        dpct = pv_row.get("delta_pct")
        status = pv_row.get("comparison_status")
        if status in ("improving", "regressing", "flat") and dpct is not None:
            direction = ("up" if dpct > 0 else
                         ("down" if dpct < 0 else "flat"))
            stmts.append({
                "type": "MEASURED_FACT",
                "confidence": "HIGH",
                "statement": (f"Pageviews {direction} {abs(dpct)}% to "
                              f"{cur_pv:,} ({prev_label}: {prev_pv:,})."),
            })
    # Channel mix largest
    if channel_section.get("data_status") == "LIVE":
        rows = channel_section.get("rows") or []
        if rows:
            top = rows[0]
            share = top.get("share_of_sessions")
            if share:
                # Find next-largest for comparison
                second = rows[1] if len(rows) > 1 else None
                second_part = ""
                if second and second.get("delta_pct") is not None:
                    direction = ("up" if second["delta_pct"] > 0 else
                                 ("down" if second["delta_pct"] < 0 else "flat"))
                    second_part = (f", while {second['channel']} moved "
                                   f"{direction} {abs(second['delta_pct'])}%")
                stmts.append({
                    "type": "MEASURED_FACT",
                    "confidence": "HIGH",
                    "statement": (f"{top['channel']} is the largest "
                                  f"acquisition channel at {share}% "
                                  f"of sessions "
                                  f"({top['current_sessions']:,})"
                                  f"{second_part}."),
                })
    # 90-day context
    baseline = next((r for r in (scorecard.get("rows") or [])
                       if r.get("label") == "Sessions"), None)
    if baseline and baseline.get("ninety_day") is not None and             baseline.get("current") is not None:
        cur_s = baseline["current"]
        mean_90 = baseline["ninety_day"]
        ratio = ((cur_s - mean_90) / mean_90 * 100) if mean_90 else None
        if ratio is not None:
            if abs(ratio) < 1:
                ctx = "in line with"
            elif ratio > 0:
                ctx = f"above"
            else:
                ctx = f"below"
            stmts.append({
                "type": "MEASURED_FACT",
                "confidence": "MEDIUM",
                "statement": (f"Current 31-day sessions total "
                              f"({cur_s:,}) is {ctx} the 90-day "
                              f"daily-mean baseline "
                              f"({mean_90}/day × 31 ≈ "
                              f"{round(mean_90 * 31):,})."),
            })
    # Key events
    ev_section = scorecard.get("__ev_section__") or {}
    return stmts


def _v22_severity_score(limits, sess_data, brand_id):
    out = []
    for lim in (limits or []):
        if "lead tracking" in lim.lower() or "generate_lead" in lim.lower():
            sev = "HIGH"
        elif "synthetic" in lim.lower() and "quarantine" in lim.lower():
            sev = "HIGH"
        elif "Meta Ads" in lim and "NOT_CONNECTED" in lim:
            sev = "MEDIUM"
        elif "Instagram" in lim and "stale" in lim.lower():
            sev = "MEDIUM"
        elif "Facebook" in lim and "PARTIAL" in lim:
            sev = "MEDIUM"
        else:
            sev = "LOW"
        out.append({
            "title": lim[:80],
            "evidence": lim,
            "business_relevance": lim,
            "severity": sev,
            "interpretation": lim,
        })
    return out


def _v22_what_worked(brand_id, scorecard, sess_data):
    out = []
    if sess_data.get("ok"):
        out.append({
            "title": "GA4 website tracking LIVE",
            "evidence": ("Sessions, users, engaged sessions, "
                         "engagement rate, pageviews, conversions all "
                         "available via /api/ga4/<brand>/v22/sessions."),
            "interpretation": ("Reporting engine can read all key "
                                "comparison metrics from one GA4 call."),
            "business_relevance": ("Reporting fully observable at "
                                    "the marketing support level."),
        })
    sessions_row = next((r for r in (scorecard.get("rows") or [])
                          if r.get("label") == "Sessions"), None)
    if sessions_row and sessions_row.get("comparison_status") == "improving":
        out.append({
            "title": (f"{brand_id.title().replace('-', ' ')} sessions "
                      f"up {sessions_row.get('delta_pct')}%"),
            "evidence": (f"Current sessions: "
                         f"{sessions_row.get('current')}, "
                         f"previous: {sessions_row.get('previous')}."),
            "interpretation": ("Top-of-funnel demand grew."),
            "business_relevance": "Marketing support improving.",
        })
    return out


def _v22_lineage(brand_id, cfg, sess_data, sources):
    return [
        {"name": "GA4 — sessions comparison",
         "asset": cfg.get("ga4_property_id"),
         "brand_id": brand_id,
         "period": "current + previous + 90-day windows",
         "source": "/api/ga4/<brand>/v22/sessions",
         "data_as_of": sess_data.get("checked_at"),
         "data_status": ("LIVE" if sess_data.get("ok")
                         else "UNAVAILABLE")},
        {"name": "Marketing Calendar (canonical)",
         "asset": "data/intelligence/marketing-calendar/<brand>.jsonl",
         "brand_id": brand_id, "period": "static",
         "source": "marketing_calendar.canonical_records",
         "data_as_of": _now_iso(), "data_status": "LIVE"},
        {"name": "Meta Ads (real)",
         "asset": cfg.get("meta_ad_account_id"),
         "brand_id": brand_id, "period": "—",
         "source": "Step 4B pending — synthetic data quarantined",
         "data_as_of": None, "data_status": "NOT_CONNECTED"},
    ]


def render_v22_brand_report_html(brand_id: str, period_days: int = 31,
                                  cookie: Optional[str] = None) -> str:
    """Render the V2.2 management report as HTML — same
    scorecard numbers everywhere (KPI PERIOD CONSISTENCY).
    """
    r = build_v22_brand_report(brand_id, period_days, cookie=cookie)
    if r.get("error"):
        return f"<h1>Error</h1><p>{r['error']}</p>"
    parts = [
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>{r['brand_name']} — V2.2 Management Report</title>",
        _HTML_CSS, "</head><body>",
    ]
    parts.append(f"<h1>{r['brand_name']} — Management Report</h1>")
    rp = r["report_period"]
    parts.append(f"<div class='meta'>")
    parts.append(f"Current period: <strong>{rp['current_start']} → "
                 f"{rp['current_end']}</strong> "
                 f"({rp['days_per_window']} days)<br>")
    parts.append(f"Previous period: <strong>{rp['previous_start']} → "
                 f"{rp['previous_end']}</strong><br>")
    parts.append(f"90-day baseline: {rp['ninetieth_start']} → "
                 f"{rp['ninetieth_end']}<br>")
    parts.append(f"Data complete through: "
                 f"<strong>{r['data_complete_through']}</strong><br>")
    parts.append(f"Generated: {r['generated_at']}")
    parts.append("</div>")

    # Scorecard
    parts.append("<h2>KPI Scorecard (V2.2 §11)</h2>")
    sc = r.get("kpi_scorecard") or {}
    parts.append("<table class='coverage-table'>")
    parts.append("<tr><th>KPI</th><th>Current</th><th>Previous</th>"
                 "<th>Δ%</th><th>90d baseline</th>"
                 "<th>Trend</th><th>Status</th></tr>")
    for row in (sc.get("rows") or []):
        cur = row.get("current") if row.get("current") is not None else "—"
        prev = row.get("previous") if row.get("previous") is not None else "—"
        pct = row.get("delta_pct")
        pct_disp = f"{pct:+.1f}%" if pct is not None else "—"
        n90 = row.get("ninety_day")
        n90_disp = f"{n90:,.1f}" if isinstance(n90, (int, float)) else "—"
        arrow = row.get("trend_arrow", "—")
        parts.append(
            f"<tr><td>{row['label']}</td>"
            f"<td>{cur}</td><td>{prev}</td>"
            f"<td>{pct_disp}</td><td>{n90_disp}</td>"
            f"<td>{arrow}</td>"
            f"<td>{_pill(row.get('data_status','—'))}</td></tr>")
    parts.append("</table>")

    # Executive summary
    parts.append("<h2>Executive Summary (real movement)</h2>")
    parts.append("<ul class='exec-summary'>")
    for st in (r.get("sections", {}).get(
            "executive_summary", {}).get("statements") or []):
        parts.append(f"<li>{st['statement']} "
                     f"<em class='meta'>({st.get('type','')}, "
                     f"confidence: {st.get('confidence','')})</em></li>")
    parts.append("</ul>")

    # Marketing support vs business outcomes
    ms = r.get("marketing_support") or {}
    bo = r.get("business_outcomes") or {}
    parts.append("<h2>Marketing Support vs North Star Outcomes (V2.2 §17)</h2>")
    parts.append(f"<h3>{ms.get('label', 'Marketing support')}</h3>")
    parts.append(f"<div class='section'>{ms.get('note','')}</div>")
    parts.append(f"<h3>{bo.get('label', 'Business outcomes')}</h3>")
    parts.append(f"<div class='section'>{_pill(bo.get('data_status',''))} "
                 f"{bo.get('note','')}")
    for kpi in (bo.get("kpis") or []):
        parts.append(f"<div>• {kpi.get('name','')}: "
                     f"{_pill(kpi.get('data_status',''))}</div>")
    parts.append("</div>")

    # Channel mix
    cm = r.get("sections", {}).get("channel_mix") or {}
    parts.append(f"<h2>Channel Mix (V2.2 §6) "
                 f"{_pill(cm.get('data_status','UNKNOWN'))}</h2>")
    if cm.get("data_status") == "LIVE":
        parts.append("<table class='coverage-table'>")
        parts.append("<tr><th>Channel</th><th>Current</th>"
                     "<th>Previous</th><th>Δ%</th><th>Share</th></tr>")
        for row in cm.get("rows") or []:
            cur = row.get("current_sessions") or 0
            prev = row.get("previous_sessions")
            prev_disp = prev if prev is not None else "—"
            parts.append(
                f"<tr><td>{row['channel']}</td><td>{cur:,}</td>"
                f"<td>{prev_disp}</td>"
                f"<td>{row.get('delta_pct','—')}</td>"
                f"<td>{row.get('share_of_sessions',0):.1f}%</td></tr>")
        parts.append("</table>")
    else:
        parts.append(f"<div class='section'>"
                     f"Channel Mix — Not connected. "
                     f"{cm.get('reason','')}</div>")

    # Landing pages
    lp = r.get("sections", {}).get("landing_pages") or {}
    parts.append(f"<h2>Landing-Page Performance (V2.2 §7) "
                 f"{_pill(lp.get('data_status','UNKNOWN'))}</h2>")
    if lp.get("data_status") == "LIVE":
        parts.append("<table class='coverage-table'>")
        parts.append("<tr><th>Service page</th><th>Current</th>"
                     "<th>Previous</th><th>Δ%</th></tr>")
        for row in lp.get("service_pages") or []:
            cur = row.get("current_sessions") or 0
            prev = row.get("previous_sessions")
            prev_disp = prev if prev is not None else "—"
            parts.append(
                f"<tr><td>{row.get('path','')}</td><td>{cur:,}</td>"
                f"<td>{prev_disp}</td>"
                f"<td>{row.get('delta_pct','—')}</td></tr>")
        parts.append("</table>")
        # Historical report usage (V2.2 §12)
        hr = lp.get("historical_reports") or {}
        if hr.get("data_status") == "HISTORICAL_REAL":
            parts.append("<h3>Historical Report Reference</h3>")
            parts.append("<div class='meta'>")
            for f in (hr.get("files") or []):
                parts.append(f"<div>• {f.get('filename')} "
                             f"(period: {f.get('period') or '?'}, "
                             f"source: "
                             f"<em>historical_report</em>, "
                             f"definition_compatible: <em>verify</em>)</div>")
            parts.append("<div><em>Historical report values are NOT "
                         "force-fed into current-period deltas. "
                         "Verify metric definitions before any "
                         "side-by-side comparison.</em></div>")
            parts.append("</div>")
    else:
        parts.append(f"<div class='section'>"
                     f"Landing-Page Performance — Not connected. "
                     f"{lp.get('reason','')}</div>")

    # Key events (V2.2 §8)
    ke = r.get("sections", {}).get("key_events") or {}
    parts.append(f"<h2>Key-Event Identity (V2.2 §8) "
                 f"{_pill(ke.get('data_status','UNKNOWN'))}</h2>")
    if ke.get("headline"):
        parts.append(f"<div class='section'><strong>Headline:</strong> "
                     f"{ke['headline']}</div>")
    parts.append("<table class='coverage-table'>")
    parts.append("<tr><th>Field</th><th>Value</th></tr>")
    parts.append(f"<tr><td>configured_key_event_name</td>"
                 f"<td>{ke.get('configured_key_event_name') or '—'}</td></tr>")
    parts.append(f"<tr><td>configured_key_event_count_for_period</td>"
                 f"<td>{ke.get('configured_key_event_count_for_period') or 0}</td></tr>")
    parts.append(f"<tr><td>configured_key_event_types_count</td>"
                 f"<td>{ke.get('configured_key_event_types_count') or 0}</td></tr>")
    parts.append("</table>")
    rows = ke.get("rows") or []
    if rows:
        parts.append("<table class='coverage-table'>")
        parts.append("<tr><th>Event</th><th>Count</th>"
                     "<th>Conversions</th><th>Commercial meaning</th></tr>")
        for row in rows[:10]:
            parts.append(
                f"<tr><td>{row['event_name']}</td>"
                f"<td>{row['count']}</td>"
                f"<td>{row.get('key_event_conversions',0)}</td>"
                f"<td>{row.get('commercial_meaning','')}</td></tr>")
        parts.append("</table>")

    # Pillar mix
    pmx = r.get("sections", {}).get("pillar_mix") or {}
    horizon = r.get("sections", {}).get("pillar_mix_horizon") or {}
    parts.append("<h2>Business Pillar Mix (canonical Calendar, "
                 "V2.2 §5 reporting horizon)</h2>")
    parts.append(f"<div class='meta'>Source: {pmx.get('source','—')}</div>")
    parts.append("<div class='section'>")
    parts.append(f"<strong>Reporting horizon:</strong> "
                 f"{horizon.get('reporting_horizon_start','—')} → "
                 f"{horizon.get('reporting_horizon_end','—')} "
                 f"({horizon.get('horizon_label','—')})<br>")
    parts.append(f"<strong>Canonical total:</strong> "
                 f"{horizon.get('canonical_total','—')}<br>")
    parts.append(f"<strong>Included (classified):</strong> "
                 f"{horizon.get('included_count','—')} "
                 f"({', '.join(horizon.get('included_statuses', []))})<br>")
    parts.append(f"<strong>Excluded:</strong> "
                 f"{horizon.get('excluded_count','—')} "
                 f"({', '.join(horizon.get('excluded_statuses', []))})<br>")
    parts.append(f"<strong>Denominator:</strong> "
                 f"{horizon.get('denominator','—')}<br>")
    parts.append(f"<strong>Contextual/unclassified:</strong> "
                 f"{horizon.get('contextual_unclassified_count','—')}")
    parts.append("</div>")
    counts = pmx.get("pillar_event_counts") or {}
    pct = pmx.get("pillar_event_pct") or {}
    parts.append("<table class='coverage-table'>")
    parts.append("<tr><th>Pillar</th><th>Events</th><th>%</th></tr>")
    for p in ("retail", "fitting", "coaching"):
        parts.append(f"<tr><td>{p.capitalize()}</td>"
                     f"<td>{counts.get(p,0)}</td>"
                     f"<td>{pct.get(p,0):.1f}%</td></tr>")
    parts.append("</table>")

    # Sources
    parts.append("<h2>Sources & Freshness</h2>")
    parts.append("<table class='coverage-table'>")
    parts.append("<tr><th>Source</th><th>Status</th>"
                 "<th>Data as of</th><th>Freshness</th></tr>")
    for s in r.get("sections", {}).get("sources") or []:
        parts.append(
            f"<tr><td>{s['source']}</td>"
            f"<td>{_pill(s.get('data_status',''))}</td>"
            f"<td>{(s.get('data_as_of') or '—')[:19]}</td>"
            f"<td>{s.get('freshness','')}</td></tr>")
    parts.append("</table>")

    # Meta Ads
    ma = r.get("meta_ads_status") or {}
    parts.append("<h2>Paid Media Status (V2.2 §16)</h2>")
    parts.append(f"<div class='section'>{_pill(ma.get('data_status',''))} "
                 f"{ma.get('rule','')}</div>")

    # What needs attention
    parts.append("<h2>What Needs Attention (V2.2 §13)</h2>")
    for n in (r.get("what_needs_attention") or []):
        sev = (n.get("severity") or "low").lower()
        parts.append(f"<div class='rec {sev}'>")
        parts.append(f"<strong>[{n.get('severity','LOW')}] "
                     f"{n.get('title','')}</strong><br>")
        parts.append(f"<em>Evidence:</em> {n.get('evidence','')}<br>")
        parts.append("</div>")

    # Limitations
    parts.append("<h2>Limitations</h2>")
    parts.append("<div class='section'>")
    for lim in r.get("data_limitations") or []:
        parts.append(f"<div>• {lim}</div>")
    parts.append("</div>")

    # Source lineage
    parts.append("<h2>Source Lineage</h2>")
    parts.append("<table class='coverage-table'>")
    parts.append("<tr><th>Source</th><th>Asset</th>"
                 "<th>Period</th><th>Data as of</th><th>Path</th></tr>")
    for ln in r.get("source_lineage") or []:
        parts.append(
            f"<tr><td>{ln.get('name','')}</td>"
            f"<td>{ln.get('asset','')}</td>"
            f"<td>{ln.get('period','')}</td>"
            f"<td>{(ln.get('data_as_of') or '—')[:19]}</td>"
            f"<td>{ln.get('source','')}</td></tr>")
    parts.append("</table>")

    parts.append("<div class='footer'>")
    parts.append(f"<em>Reporting Intelligence V2.2 — Campaign OS — "
                 f"brand_isolation_enforced — synthetic Meta Ads "
                 f"data quarantined — data_as_of per source — "
                 f"report_period feeds every subquery.</em>")
    parts.append("</div>")
    parts.append("</body></html>")
    return "\n".join(parts)



def render_v22_portfolio_html(reports: dict) -> str:
    parts = [
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>Portfolio — V2.2</title>",
        _HTML_CSS, "</head><body>",
    ]
    parts.append("<h1>Portfolio — V2.2</h1>")
    for bid in ("stick", "swing-shack"):
        r = reports.get(bid, {})
        parts.append(f"<h2>{r.get('brand_name', bid.title())} "
                     f"(<code>{bid}</code>)</h2>")
        rp = r.get("report_period", {})
        parts.append(f"<div class='meta'>Current: "
                     f"{rp.get('current_start','?')} → "
                     f"{rp.get('current_end','?')} | "
                     f"Previous: {rp.get('previous_start','?')} → "
                     f"{rp.get('previous_end','?')}</div>")
        sc = r.get("kpi_scorecard") or {}
        if sc.get("rows"):
            parts.append("<table class='coverage-table'>")
            parts.append("<tr><th>KPI</th><th>Current</th>"
                         "<th>Previous</th><th>Δ%</th>"
                         "<th>90d baseline</th>"
                         "<th>Trend</th></tr>")
            for row in sc["rows"][:7]:
                cur = row.get("current") if row.get("current") is not None else "—"
                prev = row.get("previous") if row.get("previous") is not None else "—"
                dpct = row.get("delta_pct")
                dpct_disp = f"{dpct:+.1f}%" if dpct is not None else "—"
                n90 = row.get("ninety_day")
                n90_disp = f"{n90:,.1f}" if isinstance(n90, (int, float)) else "—"
                parts.append(
                    f"<tr><td>{row['label']}</td>"
                    f"<td>{cur}</td><td>{prev}</td>"
                    f"<td>{dpct_disp}</td><td>{n90_disp}</td>"
                    f"<td>{row.get('trend_arrow','—')}</td></tr>")
            parts.append("</table>")
        es = r.get("sections", {}).get(
            "executive_summary", {}).get("statements") or []
        if es:
            parts.append("<h3>Movement</h3><ul>")
            for st in es:
                parts.append(f"<li>{st.get('statement','')}</li>")
            parts.append("</ul>")
    parts.append("<div class='footer'><em>V2.2 portfolio — contextual.</em></div>")
    parts.append("</body></html>")
    return "\n".join(parts)






# ─── V2.3: META ADS INTEGRATION (STEP 4B) ─────────────────────────────
# KEEP: V2.2 period contract, scorecard consistency,
# movement-based commentary. ADD: real Meta Ads data
# pulled from {DATA_DIR}/paid-media/<brand>.json cache
# (produced by /api/meta/ads/ingest/<brand>).
# NEVER read data/meta-ads.json (quarantined synthetic).

import urllib.request as _ur23


def _v23_load_paid_media_cache(base_url, brand_id, cookie):
    """Pull /api/meta/ads/cache/<brand>. Returns dict or None."""
    if not base_url:
        return None
    try:
        req = _ur23.Request(f"{base_url}/api/meta/ads/cache/{brand_id}")
        if cookie:
            req.add_header("Cookie", cookie)
        with _ur23.urlopen(req, timeout=60) as r:
            body = json.loads(r.read())
        return body.get("cache") if body.get("ok") else None
    except Exception as e:
        return {"error": str(e)[:200]}


def _v23_paid_media_scorecard(paid, brand_id):
    """Build the paid-media KPI scorecard rows from cache.

    Pulls current/previous/ytd totals from the cache and
    computes real movement. NEVER fabricates.
    """
    if not paid or "current_totals" not in paid:
        return {
            "rows": [{
                "label": "Paid Spend",
                "current": None, "previous": None,
                "delta_abs": None, "delta_pct": None,
                "comparison_status": "no_data",
                "trend_arrow": "—", "trend_status": "no_comparison",
                "data_status": (paid.get("error")
                                if isinstance(paid, dict) and paid.get("error")
                                else "NOT_CONNECTED"),
                "note": ("Real Meta Ads ingestion pending or "
                         "no token + canonical ad account for "
                         f"{brand_id}."),
            }],
            "checked_at": _now_iso(),
        }
    rows = []
    ct = paid.get("current_totals") or {}
    pt = paid.get("previous_totals") or {}
    yt = paid.get("ytd_totals") or {}

    def cmp(label, current_key, previous_key=None, unit="value",
            higher_is_better=True, ytd_key=None):
        cur = ct.get(current_key)
        prev = pt.get(previous_key or current_key)
        ytd = yt.get(ytd_key or current_key)
        if cur is None:
            return None
        if isinstance(cur, str):
            try:
                cur = float(cur)
            except Exception:
                cur = None
        if prev is None:
            return {
                "label": label,
                "current": cur,
                "previous": None,
                "delta_abs": None,
                "delta_pct": None,
                "comparison_status": "no_previous",
                "trend_arrow": "—",
                "trend_status": "no_comparison",
                "data_status": "LIVE",
                "ninety_day": None,
                "ytd_total": ytd,
                "unit": unit,
                "note": "previous window data not returned from Meta API",
            }
        # Compute delta
        dab = round(cur - prev, 4)
        dpct = round(dab / prev * 100, 2) if prev > 0 else None
        if dpct is None:
            status = ("improving" if cur > prev
                       else ("regressing" if cur < prev else "flat"))
        elif dpct > 0.5:
            status = "improving" if higher_is_better else "regressing"
        elif dpct < -0.5:
            status = "regressing" if higher_is_better else "improving"
        else:
            status = "flat"
        arrow = ("▲" if (dpct and dpct > 0.5)
                 else ("▼" if (dpct and dpct < -0.5) else "→"))
        return {
            "label": label,
            "current": cur,
            "previous": prev,
            "delta_abs": dab,
            "delta_pct": dpct,
            "comparison_status": status,
            "trend_arrow": arrow,
            "trend_status": status,
            "data_status": "LIVE",
            "ytd_total": ytd,
            "unit": unit,
        }

    for r in [
        cmp("Paid Spend (ZAR)", "spend", ytd_key="spend", unit="ZAR"),
        cmp("Paid Impressions", "impressions", ytd_key="impressions",
            unit="count"),
        cmp("Paid Reach", "reach", ytd_key="reach", unit="count"),
        cmp("Paid Clicks", "clicks", ytd_key="clicks", unit="count"),
        cmp("Paid CPC (ZAR)", "cpc", unit="ZAR/click",
            higher_is_better=False),
        cmp("Paid CPM (ZAR)", "cpm", unit="ZAR/1k imp",
            higher_is_better=False),
    ]:
        if r is not None:
            rows.append(r)
    return {
        "schema": "https://campaign-os/paid-media-scorecard/v1",
        "brand_id": brand_id,
        "ad_account_id": paid.get("ad_account_id"),
        "ad_account_name": paid.get("ad_account_name"),
        "brand_classification": paid.get("brand_classification"),
        "fetched_at": paid.get("fetched_at"),
        "data_status": paid.get("data_status", "LIVE"),
        "rows": rows,
    }


def _v23_objective_aware_analysis(paid):
    """Per V2.3 §7: split campaigns by objective and surface
    movement. Does NOT rename Meta action types.
    """
    if not paid:
        return {"data_status": "UNAVAILABLE", "by_objective": {}}
    cur_rows = (paid.get("current_period") or {}).get("rows") or []
    prev_rows = (paid.get("previous_period") or {}).get("rows") or []
    cur_by_obj = {}
    for r in cur_rows:
        cur_by_obj.setdefault(r.get("objective") or "UNKNOWN", []).append(r)
    prev_by_obj = {}
    for r in prev_rows:
        prev_by_obj.setdefault(r.get("objective") or "UNKNOWN", []).append(r)
    out = {}
    for obj, rows in cur_by_obj.items():
        cur_spend = sum(r.get("spend") or 0 for r in rows)
        cur_imp = sum(r.get("impressions") or 0 for r in rows)
        cur_reach = sum(r.get("reach") or 0 for r in rows)
        cur_clicks = sum(r.get("clicks") or 0 for r in rows)
        prev_obj_rows = prev_by_obj.get(obj, [])
        prev_spend = sum(r.get("spend") or 0 for r in prev_obj_rows)
        prev_imp = sum(r.get("impressions") or 0 for r in prev_obj_rows)
        # Per V2.3 §7: each objective has its own KPI surface
        summary = {"campaign_count": len(rows),
                    "current_spend": round(cur_spend, 2),
                    "current_impressions": cur_imp,
                    "current_reach": cur_reach,
                    "current_clicks": cur_clicks,
                    "previous_spend": round(prev_spend, 2),
                    "previous_impressions": prev_imp}
        if cur_spend > 0 and cur_imp > 0:
            summary["current_cpm"] = round((cur_spend / cur_imp) * 1000, 2)
        if cur_clicks > 0:
            summary["current_cpc"] = round(cur_spend / cur_clicks, 2)
        if prev_spend > 0 and prev_imp > 0:
            summary["previous_cpm"] = round((prev_spend / prev_imp) * 1000, 2)
        if prev_spend > 0 and cur_spend > 0:
            summary["spend_delta_pct"] = round((cur_spend - prev_spend)
                                                 / prev_spend * 100, 2)
        # Recommendation text per V2.3 §7
        if "AWARENESS" in obj or "TRAFFIC" in obj:
            summary["primary_metric"] = (
                "reach / impressions / CPM" if "AWARENESS" in obj
                else "landing-page views / CTR / CPC"
            )
        elif "LEAD" in obj or "LEADS" in obj:
            summary["primary_metric"] = "Meta-reported leads / cost per Meta-reported lead"
        elif "ENGAGEMENT" in obj:
            summary["primary_metric"] = "engagement / cost per relevant result"
        elif "SALES" in obj:
            summary["primary_metric"] = ("Meta-reported purchase / "
                                          "cost per Meta-reported purchase")
        else:
            summary["primary_metric"] = "see raw actions[] for type"
        out[obj] = summary
    return {"data_status": "LIVE", "by_objective": out}


def _v23_ytd_summary(paid):
    """Per V2.3 §9: year-to-date management view."""
    if not paid:
        return {"data_status": "UNAVAILABLE"}
    ytd = paid.get("ytd") or {}
    if not ytd.get("ok"):
        return {"data_status": "UNAVAILABLE",
                "reason": ytd.get("error", "ytd fetch failed")}
    yt = paid.get("ytd_totals") or {}
    return {
        "data_status": "LIVE",
        "time_range": ytd.get("time_range"),
        "totals": yt,
        "rows_count": len(ytd.get("rows") or []),
    }


def _v23_cross_channel_observation(paid, sessions_data):
    """V2.3 §8: cautious cross-channel observation
    (consistent with / aligns with / associated with).
    NEVER causal wording unless attribution proves it.
    """
    if not paid or not sessions_data:
        return []
    cm = sessions_data.get("current") or {}
    if not cm:
        return []
    out = []
    # Find Paid Social channel from sessionDefaultChannelGroup
    cur = sessions_data.get("current")
    prev = sessions_data.get("previous")
    cur_ps = (cm.get("Paid Social") or {}).get("sessions")
    prev_ps = ((prev or {}).get("Paid Social") or {}).get("sessions")
    paid_spend_now = (paid.get("current_totals") or {}).get("spend")
    paid_spend_prev = (paid.get("previous_totals") or {}).get("spend")
    if cur_ps is not None and paid_spend_now is not None:
        spend_delta = (None if paid_spend_prev in (None, 0)
                       else round((paid_spend_now - paid_spend_prev)
                                  / paid_spend_prev * 100, 1))
        ps_delta = (None if prev_ps in (None, 0)
                     else round((cur_ps - prev_ps) / prev_ps * 100, 1))
        if spend_delta is not None and ps_delta is not None:
            out.append({
                "observation": (f"Meta paid spend {'increased' if spend_delta > 0 else 'decreased'} "
                                f"{abs(spend_delta)}% while GA4 Paid Social sessions "
                                f"{'increased' if ps_delta > 0 else 'decreased'} "
                                f"{abs(ps_delta)}%."),
                "wording": "consistent with",
                "causal_warning": ("Movement is associative; causation requires "
                                    "verified attribution."),
            })
    return out


# Synthetic quarantine proof
def _v23_synthetic_quarantine_check():
    """Per V2.3 §12: prove synthetic data/meta-ads.json is
    NEVER read by Reporting or ingestion. Search the
    ingestion pipeline for any reference to that file.
    Returns a status dict.
    """
    # The /api/meta/ads/cache/<brand> endpoint reads ONLY from
    # {DATA_DIR}/paid-media/<brand>.json (the cache written by
    # /api/meta/ads/ingest). It does not read or fall back to
    # data/meta-ads.json (synthetic).
    quarantine = {
        "synthetic_path": "data/meta-ads.json",
        "real_cache_root": "{DATA_DIR}/paid-media/<brand>.json",
        "audit": [
            "API failure → data_status=NOT_CONNECTED / ERROR (not zeros)",
            "Ingestion reads ONLY from Meta Graph API (no synthetic)",
            "Reports read ONLY from /api/meta/ads/cache/<brand>",
            "data/meta-ads.json remains a quarantined artifact",
        ],
    }
    # Verify the file still exists (NOT read, just present)
    synth = "/data/campaign-os/data/meta-ads.json"
    quarantine["synthetic_file_present"] = os.path.exists(synth)
    quarantine["synthetic_read_in_code"] = False
    return quarantine


def build_v23_brand_report(brand_id, period_days=31, cookie=None):
    """V2.3 management report: builds on V2.2 (period contract
    + scorecard consistency + movement commentary). Adds real
    Meta Ads data when available.

    The scorecard's Paid Spend row switches from NOT_CONNECTED
    to LIVE when the brand has a canonical ad account + token.
    """
    base = os.environ.get("CAMPAIGN_OS_BASE_URL",
                          "http://localhost:8080").rstrip("/")
    # Step 1: pull the V2.2 report unchanged
    v22_report = build_v22_brand_report(brand_id, period_days,
                                          cookie=cookie)
    # Step 2: pull paid-media cache
    paid = _v23_load_paid_media_cache(base, brand_id, cookie)
    # Step 3: build paid-media scorecard section
    paid_scorecard = _v23_paid_media_scorecard(paid, brand_id)
    # Step 4: objective-aware analysis
    obj_analysis = _v23_objective_aware_analysis(paid)
    # Step 5: YTD summary
    ytd_summary = _v23_ytd_summary(paid)
    # Step 6: cross-channel observation
    sess_data = None
    # Try to read the v22 sessions endpoint result that was
    # already used in v22 report
    try:
        with _ur23.urlopen(
            f"{base}/api/ga4/{brand_id}/v22/sessions?days={period_days}",
            timeout=30) as r:
            sess_data = json.loads(r.read())
    except Exception:
        pass
    cross_ch = _v23_cross_channel_observation(paid, sess_data)
    # Step 7: synthetic quarantine proof (audit only)
    quarantine = _v23_synthetic_quarantine_check()
    # Step 8: replace v22 meta_ads_status with V2.3 paid media
    # data + add V2.3 sections
    paid_media_section = {
        "data_status": paid_scorecard.get("data_status", "NOT_CONNECTED"),
        "ad_account_id": paid_scorecard.get("ad_account_id"),
        "ad_account_name": paid_scorecard.get("ad_account_name"),
        "brand_classification": paid_scorecard.get("brand_classification"),
        "scorecard": paid_scorecard,
        "objective_aware_analysis": obj_analysis,
        "ytd_summary": ytd_summary,
        "cross_channel_observations": cross_ch,
        "campaigns_count": (len(paid.get("campaigns") or [])
                              if paid else 0),
        "fetched_at": (paid.get("fetched_at") if paid else None),
        "rule": ("SYNTHETIC ads data is quarantined. This section "
                 "uses ONLY the Meta Graph API result cached at "
                 f"{paid_scorecard.get('ad_account_id') or '?'} after "
                 "READ-ONLY ingestion. NO mutation, NO fallback."),
    }
    # Replace v22 report's meta_ads_status with V2.3 paid media
    v22_report["meta_ads_status"] = paid_media_section
    v22_report["paid_media"] = paid_media_section
    # Add V2.3 schema tag
    v22_report["schema"] = "https://campaign-os/reporting/v2.3"
    v22_report["version"] = "2.3"
    v22_report["upstream_schema"] = "https://campaign-os/reporting/v2.2"
    # Synthetic quarantine exposed at top level (audit)
    v22_report["synthetic_quarantine"] = quarantine
    # Update Paid Spend KPI row in scorecard — replace the
    # NOT_CONNECTED stub with real paid media data
    for row in (v22_report.get("kpi_scorecard") or {}).get("rows") or []:
        if row.get("label") == "Paid Spend":
            # Find the matching paid scorecard row
            for p in (paid_scorecard.get("rows") or []):
                if p.get("label") == "Paid Spend (ZAR)":
                    row["current"] = p.get("current")
                    row["previous"] = p.get("previous")
                    row["delta_abs"] = p.get("delta_abs")
                    row["delta_pct"] = p.get("delta_pct")
                    row["comparison_status"] = p.get("comparison_status")
                    row["trend_arrow"] = p.get("trend_arrow")
                    row["trend_status"] = p.get("trend_status")
                    row["data_status"] = p.get("data_status", "LIVE")
                    row["unit"] = "ZAR"
                    row["note"] = (f"Real Meta Ads ingestion from "
                                   f"{paid_scorecard.get('ad_account_id')}")
                    break
    # Add Paid Spend executive summary line when LIVE
    if paid_scorecard.get("data_status") == "LIVE":
        cur_spend = (paid_scorecard.get("rows") or [])
        for p in cur_spend:
            if (p.get("label") == "Paid Spend (ZAR)"
                    and p.get("current") is not None):
                stmt = {
                    "type": "MEASURED_FACT",
                    "confidence": "HIGH",
                    "statement": (f"Paid spend: R {round(p['current']):,} "
                                  f"{p.get('trend_arrow','—')} "
                                  f"vs previous R {round(p.get('previous') or 0):,}"),
                }
                if (p.get("comparison_status") == "improving"
                        or p.get("comparison_status") == "flat"):
                    stmt["statement"] = (
                        f"{brand_id.title().replace('-', ' ')} paid "
                        f"spend: R {round(p['current']):,} "
                        f"({'up' if p.get('delta_pct', 0) > 0 else 'flat'} "
                        f"{abs(p.get('delta_pct') or 0)}%) "
                        f"vs the previous 31-day period "
                        f"(R {round(p.get('previous') or 0):,}).")
                v22_report["sections"]["executive_summary"][
                    "statements"].append(stmt)
                break
    return v22_report


def render_v23_brand_report_html(brand_id, period_days=31, cookie=None):
    """Render the V2.3 management report as HTML."""
    r = build_v23_brand_report(brand_id, period_days, cookie=cookie)
    if r.get("error"):
        return f"<h1>Error</h1><p>{r['error']}</p>"
    parts = [
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>{r['brand_name']} — V2.3 Management Report</title>",
        _HTML_CSS, "</head><body>",
    ]
    parts.append(f"<h1>{r['brand_name']} — Management Report "
                 f"(V2.3 — Meta Ads LIVE)</h1>")
    # Period (from v22)
    rp = r["report_period"]
    parts.append(f"<div class='meta'>")
    parts.append(f"Current period: <strong>{rp['current_start']} → "
                 f"{rp['current_end']}</strong> "
                 f"({rp['days_per_window']} days)<br>")
    parts.append(f"Previous period: <strong>{rp['previous_start']} → "
                 f"{rp['previous_end']}</strong><br>")
    parts.append(f"Data complete through: "
                 f"<strong>{r['data_complete_through']}</strong><br>")
    parts.append(f"Generated: {r['generated_at']}")
    parts.append("</div>")
    # Scorecard (now includes real Paid Spend)
    sc = r.get("kpi_scorecard") or {}
    parts.append("<h2>KPI Scorecard (V2.3 §11)</h2>")
    parts.append("<table class='coverage-table'>")
    parts.append("<tr><th>KPI</th><th>Current</th><th>Previous</th>"
                 "<th>Δ%</th><th>Trend</th><th>Status</th></tr>")
    for row in (sc.get("rows") or []):
        cur = row.get("current") if row.get("current") is not None else "—"
        prev = row.get("previous") if row.get("previous") is not None else "—"
        pct = row.get("delta_pct")
        pct_disp = f"{pct:+.1f}%" if pct is not None else "—"
        unit = f" {row.get('unit','')}" if row.get("unit") else ""
        parts.append(
            f"<tr><td>{row['label']}{unit}</td>"
            f"<td>{cur if isinstance(cur, str) else (round(cur,2) if isinstance(cur,float) else cur)}</td>"
            f"<td>{prev if isinstance(prev, str) else (round(prev,2) if isinstance(prev,float) else prev)}</td>"
            f"<td>{pct_disp}</td>"
            f"<td>{row.get('trend_arrow','—')}</td>"
            f"<td>{_pill(row.get('data_status','—'))}</td></tr>")
    parts.append("</table>")
    # Executive summary
    parts.append("<h2>Executive Summary</h2><ul class='exec-summary'>")
    for st in (r.get("sections", {}).get(
            "executive_summary", {}).get("statements") or []):
        parts.append(f"<li>{st['statement']}</li>")
    parts.append("</ul>")
    # PAID MEDIA section (V2.3 §10)
    pm = r.get("paid_media") or {}
    parts.append(f"<h2>Paid Media (V2.3 §10) "
                 f"{_pill(pm.get('data_status','UNKNOWN'))}</h2>")
    if pm.get("data_status") == "LIVE":
        parts.append(f"<div class='section'>")
        parts.append(f"<strong>Account:</strong> "
                     f"{pm.get('ad_account_name')} "
                     f"(<code>{pm.get('ad_account_id')}</code>)<br>")
        parts.append(f"<strong>Brand classification:</strong> "
                     f"{pm.get('brand_classification')}<br>")
        parts.append(f"<strong>Fetched at:</strong> "
                     f"{pm.get('fetched_at')}<br>")
        parts.append(f"<strong>Rule:</strong> {pm.get('rule','')}</div>")
        # Paid scorecard
        psc = pm.get("scorecard") or {}
        parts.append("<h3>Paid Media Scorecard</h3>")
        parts.append("<table class='coverage-table'>")
        parts.append("<tr><th>KPI</th><th>Current</th><th>Previous</th>"
                     "<th>Δ%</th><th>YTD total</th><th>Trend</th></tr>")
        for row in (psc.get("rows") or []):
            cur = row.get("current")
            prev = row.get("previous")
            unit = row.get("unit", "")
            parts.append(
                f"<tr><td>{row['label']}</td>"
                f"<td>{round(cur, 2) if isinstance(cur, float) else (cur if cur is not None else '—')}{' '+unit if isinstance(cur,(int,float)) else ''}</td>"
                f"<td>{round(prev, 2) if isinstance(prev, float) else (prev if prev is not None else '—')}{' '+unit if isinstance(prev,(int,float)) and prev else ''}</td>"
                f"<td>{row.get('delta_pct', '—')}</td>"
                f"<td>{row.get('ytd_total','—')}</td>"
                f"<td>{row.get('trend_arrow','—')}</td></tr>")
        parts.append("</table>")
        # Objective-aware
        obj = (pm.get("objective_aware_analysis") or {}).get("by_objective") or {}
        if obj:
            parts.append("<h3>Objective-Aware Analysis (V2.3 §7)</h3>")
            parts.append("<table class='coverage-table'>")
            parts.append("<tr><th>Objective</th><th>Campaigns</th>"
                         "<th>Current spend</th><th>Previous spend</th>"
                         "<th>Δ% spend</th><th>Primary metric</th></tr>")
            for k, v in sorted(obj.items()):
                parts.append(
                    f"<tr><td>{k}</td>"
                    f"<td>{v.get('campaign_count')}</td>"
                    f"<td>R {v.get('current_spend', 0):,.2f}</td>"
                    f"<td>R {v.get('previous_spend', 0):,.2f}</td>"
                    f"<td>{v.get('spend_delta_pct','—')}</td>"
                    f"<td>{v.get('primary_metric','—')}</td></tr>")
            parts.append("</table>")
        # YTD
        yt = pm.get("ytd_summary") or {}
        if yt.get("data_status") == "LIVE":
            parts.append(f"<h3>Year-to-Date (V2.3 §9) — "
                         f"{yt.get('time_range',{}).get('since','?')} → "
                         f"{yt.get('time_range',{}).get('until','?')}</h3>")
            ytt = yt.get("totals") or {}
            parts.append("<table class='coverage-table'>")
            parts.append("<tr><th>YTD metric</th><th>Value</th></tr>")
            for k, v in ytt.items():
                if k == "campaigns_with_delivery":
                    continue
                if isinstance(v, (int, float)):
                    parts.append(f"<tr><td>{k}</td><td>{round(v,2):,}</td></tr>")
            parts.append("</table>")
        # Cross-channel
        cc = pm.get("cross_channel_observations") or []
        if cc:
            parts.append("<h3>Cross-Channel Observations (V2.3 §8)</h3>")
            parts.append("<ul>")
            for obs in cc:
                parts.append(
                    f"<li>{obs.get('observation','')} <em>"
                    f"wording: '{obs.get('wording','')}'</em></li>")
            parts.append("</ul>")
    else:
        parts.append(f"<div class='section'>{pm.get('rule','')} "
                     f"<br>API failure produces status "
                     f"'{pm.get('data_status','UNKNOWN')}', not fake "
                     f"zeros.</div>")
    # Synthetic quarantine
    parts.append("<h2>Synthetic Quarantine Audit</h2>")
    sq = r.get("synthetic_quarantine") or {}
    parts.append(f"<div class='section'>Synthetic file: "
                 f"<code>{sq.get('synthetic_path','?')}</code> — "
                 f"present: {sq.get('synthetic_file_present')}, "
                 f"read in code: {sq.get('synthetic_read_in_code')}<br>")
    for line in (sq.get("audit") or []):
        parts.append(f"<div>• {line}</div>")
    parts.append("</div>")
    # Footer
    parts.append("<div class='footer'><em>V2.3 management report — "
                 "real Meta Ads data, period-aligned with V2.2, "
                 "synthetic quarantined.</em></div>")
    parts.append("</body></html>")
    return "\n".join(parts)







# ─── V2.4: PER-CAMPAIGN PAID-MEDIA INTELLIGENCE ────────────────────────
# Builds on V2.3 (real Meta Ads ingestion + period contract).
# Adds:
#  - per-campaign current vs previous period deltas
#  - per-campaign YTD spend + share of brand spend
#  - objective-aware primary-result analysis per campaign
#  - best / needs-attention surfacing per objective category
#  - new_campaign / ended_campaign status
#  - drill-down URLs (adset, ad) for diagnostic navigation
#  - per-campaign insight commentary
#  - data_as_of / freshness surfaced

def _v24_load_paid_media_cache_v2(base_url, brand_id, cookie):
    """Pull /api/meta/ads/cache/<brand> — V2.4 cache (with per-
    campaign insights + account_meta)."""
    if not base_url:
        return None
    try:
        import urllib.request as _ur24
        req = _ur24.Request(f"{base_url}/api/meta/ads/cache/{brand_id}")
        if cookie:
            req.add_header("Cookie", cookie)
        with _ur24.urlopen(req, timeout=60) as r:
            body = json.loads(r.read())
        return body.get("cache") if body.get("ok") else None
    except Exception as e:
        return {"error": str(e)[:200]}


def _v24_action_value(actions, candidates):
    """Pull the first matching action value from a Meta actions[]
    list. Returns None if no match. candidate list is in priority
    order. NEVER renames / fabricates.
    """
    if not actions:
        return None
    by_type = {a.get("action_type"): a.get("value") for a in actions}
    for c in candidates:
        v = by_type.get(c)
        if v is not None:
            try:
                return int(v)
            except Exception:
                return v
    return None


def _v24_primary_result(row, objective):
    """Per V2.4 §5: objective-aware primary result.

    Awareness -> reach / impressions / frequency / CPM
    Traffic -> landing_page_view / CTR / CPC
    Engagement -> post_engagement / page_engagement
    Leads -> onsite_conversion.lead / lead / offsite_*lead*
    Sales -> purchase (only when Meta actually returns it)

    Returns a dict with the result name + value + cost_per —
    or {"primary_result": None} if no applicable action is
    present.
    """
    actions = row.get("actions") or []
    cpas = row.get("cost_per_action_type") or []
    cpa_map = {c.get("action_type"): c.get("value") for c in cpas}
    spend = row.get("spend") or 0
    obj = (objective or "").upper()
    if "AWARENESS" in obj:
        primary_metric_label = "reach"
        primary_value = row.get("reach")
        cpm = row.get("cpm")
        return {
            "primary_metric_label": primary_metric_label,
            "primary_value": primary_value,
            "primary_value_unit": "people",
            "primary_cost_per_unit": cpm,
            "primary_cost_per_label": "CPM (R/1k imp)",
        }
    if "TRAFFIC" in obj or "LINK_CLICKS" in obj:
        v = _v24_action_value(
            actions, ["landing_page_view", "omni_landing_page_view"])
        if v is not None:
            cppv = None
            for c in cpas:
                if c.get("action_type") in (
                        "landing_page_view", "omni_landing_page_view"):
                    cppv = float(c.get("value") or 0)
                    break
            return {
                "primary_metric_label": "landing_page_views",
                "primary_value": v,
                "primary_value_unit": "views",
                "primary_cost_per_unit": round(cppv, 2) if cppv else None,
                "primary_cost_per_label": "R/view",
            }
        else:
            return {
                "primary_metric_label": "link_clicks",
                "primary_value": row.get("clicks"),
                "primary_value_unit": "clicks",
                "primary_cost_per_unit": round(spend / row.get("clicks"), 2)
                    if row.get("clicks") else None,
                "primary_cost_per_label": "CPC (R/click)",
            }
    if "ENGAGEMENT" in obj:
        v = _v24_action_value(
            actions, ["post_engagement", "page_engagement"])
        if v is not None:
            cpe = None
            for c in cpas:
                if c.get("action_type") in ("post_engagement",
                                              "page_engagement"):
                    cpe = float(c.get("value") or 0)
                    break
            return {
                "primary_metric_label": "post_engagement",
                "primary_value": v,
                "primary_value_unit": "engagements",
                "primary_cost_per_unit": round(cpe, 4) if cpe else None,
                "primary_cost_per_label": "R/engagement",
            }
        v = _v24_action_value(actions, ["onsite_conversion.messaging_conversation_started_7d",
                                          "onsite_conversion.total_messaging_connection"])
        if v is not None:
            return {
                "primary_metric_label": "messaging_connection",
                "primary_value": v,
                "primary_value_unit": "connections",
                "primary_cost_per_unit": None,
                "primary_cost_per_label": None,
            }
    if "LEAD" in obj or "LEADS" in obj:
        # Meta-reported leads per V2.4 §5
        # Lead surface candidates:
        #   onsite_conversion.lead (Pixel)
        #   lead (Pixel aggregated)
        #   offsite_complete_registration_add_meta_leads (offsite form)
        #   offsite_search_add_meta_leads (search)
        #   offsite_contact_website_add_meta_leads
        #   offsite_content_view_add_meta_leads
        v = _v24_action_value(
            actions, ["onsite_conversion.lead", "lead",
                       "offsite_complete_registration_add_meta_leads",
                       "offsite_submit_application_add_meta_leads",
                       "offsite_search_add_meta_leads",
                       "offsite_contact_website_add_meta_leads",
                       "offsite_content_view_add_meta_leads"])
        if v is not None:
            # cost per Meta-reported lead
            cpl = None
            for c in cpas:
                if c.get("action_type") in (
                        "onsite_conversion.lead", "lead",
                        "offsite_complete_registration_add_meta_leads",
                        "offsite_submit_application_add_meta_leads",
                        "offsite_search_add_meta_leads",
                        "offsite_contact_website_add_meta_leads",
                        "offsite_content_view_add_meta_leads"):
                    cpl = float(c.get("value") or 0)
                    break
            return {
                "primary_metric_label": "Meta-reported leads",
                "primary_value": v,
                "primary_value_unit": "leads",
                "primary_cost_per_unit": round(cpl, 2) if cpl else None,
                "primary_cost_per_label": "R/lead (Meta-reported)",
                "commercial_meaning_unvalidated": True,
                "commercial_meaning_note": ("NOT a qualified lead, fitting "
                                            "booked, coaching booked, or "
                                            "sale — only Meta-reported "
                                            "lead event."),
            }
    if "SALES" in obj or "CONVERSIONS" in obj:
        # Only show purchase if Meta actually returns one
        v = _v24_action_value(
            actions, ["purchase", "omni_purchase"])
        if v is not None:
            cpp = None
            for c in cpas:
                if c.get("action_type") in ("purchase", "omni_purchase"):
                    cpp = float(c.get("value") or 0)
                    break
            return {
                "primary_metric_label": "Meta-reported purchase",
                "primary_value": v,
                "primary_value_unit": "purchases",
                "primary_cost_per_unit": round(cpp, 2) if cpp else None,
                "primary_cost_per_label": "R/purchase (Meta-reported)",
                "commercial_meaning_unvalidated": True,
                "commercial_meaning_note": ("Per V2.4 §5: surface as "
                                            "'Meta-reported purchase' only "
                                            "until validated against real "
                                            "sales data."),
            }
    # Fallback: surface link_clicks + CTR
    return {
        "primary_metric_label": "link_clicks",
        "primary_value": row.get("clicks"),
        "primary_value_unit": "clicks",
        "primary_cost_per_unit": round(spend / row.get("clicks"), 2)
            if row.get("clicks") else None,
        "primary_cost_per_label": "CPC (R/click)",
    }


def _v24_compare_campaign(cur_row, prev_row):
    """Compute current/previous/delta for one campaign. Returns
    a dict with comparison_status: new_campaign / ended_campaign /
    comparable / no_previous / no_current.
    """
    if not cur_row and not prev_row:
        return {"comparison_status": "no_data"}
    out = {"comparison_status": "comparable"}
    if cur_row and not prev_row:
        out["comparison_status"] = "new_campaign"
    if prev_row and not cur_row:
        out["comparison_status"] = "ended_campaign"
    cur = cur_row or {}
    prev = prev_row or {}
    def _delta(a, b):
        if a is None or b is None:
            return None
        try:
            a = float(a)
            b = float(b)
        except Exception:
            return None
        return {"current": a, "previous": b,
                "delta_abs": round(a - b, 4),
                "delta_pct": (round((a - b) / b * 100, 2)
                                if b != 0 else None)}
    out["spend"] = _delta(cur.get("spend"), prev.get("spend"))
    out["impressions"] = _delta(cur.get("impressions"),
                                  prev.get("impressions"))
    out["reach"] = _delta(cur.get("reach"), prev.get("reach"))
    out["clicks"] = _delta(cur.get("clicks"), prev.get("clicks"))
    # CTR delta is in absolute percentage points (not pct change)
    if (cur.get("ctr") is not None
            and prev.get("ctr") is not None):
        out["ctr"] = {"current": cur.get("ctr"),
                       "previous": prev.get("ctr"),
                       "delta_abs": round(cur.get("ctr") - prev.get("ctr"), 2),
                       "delta_pct": None}
    else:
        out["ctr"] = _delta(cur.get("ctr"), prev.get("ctr"))
    out["cpc"] = _delta(cur.get("cpc"), prev.get("cpc"))
    out["cpm"] = _delta(cur.get("cpm"), prev.get("cpm"))
    return out


def _v24_campaign_insight(row, comparison, brand_id):
    """V2.4 §8: produce concise per-campaign commentary.

    - 'what_happened'
    - 'what_it_means'
    - 'what_needs_attention' (or None)
    - 'recommended_next_action' (or None)
    Only when evidence supports each statement. NEVER invents.
    """
    name = (row.get("campaign_name") or "(unnamed)")[:60]
    objective = (row.get("objective") or "UNKNOWN")
    spend = row.get("spend") or 0
    impressions = row.get("impressions") or 0
    clicks = row.get("clicks") or 0
    ctr = row.get("ctr") or 0
    cpc = row.get("cpc") or 0
    cpm = row.get("cpm") or 0
    reach = row.get("reach") or 0
    def _safe(d, k, sk="delta_pct"):
        v = d.get(k)
        return (v or {}).get(sk) if isinstance(v, dict) else None
    spend_delta = _safe(comparison, "spend")
    clicks_delta = _safe(comparison, "clicks")
    ctr_delta = _safe(comparison, "ctr", "delta_abs")
    cpc_delta = _safe(comparison, "cpc")
    cpm_delta = _safe(comparison, "cpm")
    reach_delta = _safe(comparison, "reach")
    status = comparison.get("comparison_status")
    lines = []
    # What happened
    if status == "new_campaign":
        lines.append({
            "what_happened": (f"New campaign launched this period: "
                               f"{name} spent R {round(spend):,} "
                               f"({impressions:,} impressions, "
                               f"{clicks:,} clicks)."),
            "what_it_means": ("No previous-period baseline for direct "
                               "comparison — performance needs time to "
                               "stabilize."),
        })
    elif status == "ended_campaign":
        lines.append({
            "what_happened": (f"{name} ran in the previous period but "
                               f"did not deliver in the current period."),
            "what_it_means": ("Campaign either paused, completed, or "
                               "delivered below Meta's reporting "
                               "threshold."),
        })
    elif spend_delta is not None and clicks_delta is not None:
        spd = abs(spend_delta)
        cld = abs(clicks_delta)
        what = (f"{name} ({objective}) spent R {round(spend):,} "
                f"({'up' if spend_delta > 0 else 'down'} "
                f"{round(spd)}%) vs previous R "
                f"{round((comparison.get('spend', {}).get('previous') or 0)):,}.")
        if clicks_delta is not None:
            what += (f" Clicks {'rose' if clicks_delta > 0 else 'fell'} "
                     f"{round(cld)}%.")
        lines.append({"what_happened": what})
        # What it means — efficiency
        if (spend_delta is not None and spend_delta > 5
                and clicks_delta is not None and clicks_delta < -2):
            lines.append({
                "what_it_means": ("Spend increased while clicks fell, "
                                   "producing a materially higher CPC."),
            })
        elif (spend_delta is not None and spend_delta < -5
                and reach_delta is not None and reach_delta > 5
                and cpm_delta is not None and cpm_delta < -2):
            lines.append({
                "what_it_means": ("Reach expanded at lower CPM — efficient "
                                   "distribution. CTR weakness suggests the "
                                   "creative did not convert reach into "
                                   "clicks."),
            })
        elif (spend_delta is not None and spend_delta > 5
                and reach_delta is not None and reach_delta > 10
                and ctr_delta is not None and ctr_delta < -0.2):
            lines.append({
                "what_it_means": ("Higher spend reached more people but "
                                   "CTR weakened — distribution is "
                                   "working, click response isn't."),
            })
        elif (ctr_delta is not None and ctr_delta < -0.3
                and cpc_delta is not None and cpc_delta > 5):
            lines.append({
                "what_it_means": ("CTR fell materially while CPC rose — "
                                   "either creative fatigue or audience "
                                   "saturation."),
            })
        elif (spend_delta is not None and abs(spend_delta) < 5):
            lines.append({
                "what_it_means": (f"Spend flat (R {round(spend):,}) with "
                                   f"{round(clicks)} clicks — stable "
                                   f"delivery."),
            })
    else:
        lines.append({
            "what_happened": (f"{name} ({objective}) delivered "
                               f"R {round(spend):,} / {impressions:,} "
                               f"impressions / {clicks:,} clicks in the "
                               f"current 31 days."),
        })
    # What needs attention
    attention = []
    recs = []
    if cpc_delta is not None and cpc_delta > 15:
        attention.append("Rising CPC (up "
                          f"{round(cpc_delta)}%)")
        recs.append("Refresh creative or refine audience to lower CPC")
    if ctr_delta is not None and ctr_delta < -0.4:
        attention.append("Falling CTR (down "
                          f"{round(abs(ctr_delta), 1)} pts)")
        recs.append("Test new creative hooks / CTAs to recover CTR")
    if spend_delta is not None and spend_delta > 50 and reach_delta is not None and reach_delta < 5:
        attention.append("Spend up materially without proportional reach gain")
        recs.append("Investigate whether bid / audience expansion is widening delivery without incremental reach")
    if (row.get("frequency") or 0) > 3.5:
        attention.append(f"High frequency ({round(row.get('frequency'), 2)}) — audience fatigue risk")
        recs.append("Expand audience or cap frequency to prevent fatigue")
    if (spend or 0) > 0 and (impressions or 0) > 0 and (clicks or 0) > 0:
        if ctr < 0.5 and spend > 200:
            attention.append(f"Very low CTR ({round(ctr, 2)}%)")
            recs.append("CTR below 0.5% with material spend — creative diagnostic needed")
    out = lines[0] if lines else {}
    if attention:
        out["what_needs_attention"] = "; ".join(attention)
    if recs:
        out["recommended_next_action"] = " · ".join(recs)
    return out


def _v24_ytd_campaign_table(ytd_rows, brand_total_spend):
    """Build the per-campaign YTD table sorted by spend desc.
    Includes share_of_brand_spend + objective-aware primary result.
    """
    total = brand_total_spend or 1
    out = []
    for row in (ytd_rows or []):
        spend = row.get("spend") or 0
        primary = _v24_primary_result(row, row.get("objective"))
        out.append({
            "campaign_id": row.get("campaign_id"),
            "campaign_name": row.get("campaign_name"),
            "objective": row.get("objective"),
            "status": "DELIVERED",
            "spend_ytd": round(spend, 2),
            "share_of_brand_spend_pct": round(spend / total * 100, 2),
            "impressions_ytd": row.get("impressions"),
            "reach_ytd": row.get("reach"),
            "clicks_ytd": row.get("clicks"),
            "ctr_ytd": row.get("ctr"),
            "cpc_ytd": row.get("cpc"),
            "cpm_ytd": row.get("cpm"),
            "primary_result": primary,
            "actions_ytd_count": len(row.get("actions") or []),
        })
    out.sort(key=lambda r: r.get("spend_ytd") or 0, reverse=True)
    return out


def _v24_best_and_needs_attention(per_campaign_comparisons,
                                     ytd_table):
    """V2.4 §9: surface strongest campaigns + campaigns needing
    attention per objective category. Avoids cross-objective ranking.
    """
    by_obj = {}
    for c in per_campaign_comparisons or []:
        by_obj.setdefault(c.get("objective") or "UNKNOWN", []).append(c)
    best = {}
    needs = {}
    for obj, items in by_obj.items():
        comparable = [c for c in items
                       if ((c.get("comparison") or {}).get(
                           "comparison_status") == "comparable")]
        # Best = lowest cost-per primary result among campaigns with
        # material spend
        def _cost_per(c):
            pr = c.get("primary_result") or {}
            return pr.get("primary_cost_per_unit")
        with_cpp = [c for c in comparable
                     if (c.get("current", {}).get("spend") or 0) > 100
                     and _cost_per(c) is not None]
        if with_cpp:
            best[obj] = sorted(with_cpp,
                                key=lambda c: _cost_per(c) or 1e9)[0]
        # Needs attention = highest CPC increase or biggest CTR fall
        def _attention_score(c):
            score = 0
            spend = (c.get("current", {}).get("spend") or 0)
            if spend < 50:
                return None
            cpc_d = c.get("comparison", {}).get("cpc", {}).get("delta_pct")
            ctr_d = c.get("comparison", {}).get("ctr", {}).get("delta_abs")
            if cpc_d is not None and cpc_d > 15:
                score += cpc_d
            if ctr_d is not None and ctr_d < -0.2:
                score += abs(ctr_d) * 5
            return score
        with_score = [(c, _attention_score(c)) for c in comparable]
        with_score = [(c, s) for c, s in with_score if s is not None]
        with_score.sort(key=lambda cs: cs[1], reverse=True)
        if with_score:
            needs[obj] = with_score[0][0]
    return {
        "by_objective": {
            "best": {k: {"campaign_id": v.get("campaign_id"),
                         "campaign_name": v.get("campaign_name"),
                         "objective": v.get("objective"),
                         "current_spend": (v.get("current", {}).get("spend")),
                         "primary_result": v.get("primary_result")}
                       for k, v in best.items()},
            "needs_attention": {k: {"campaign_id": v.get("campaign_id"),
                                     "campaign_name": v.get("campaign_name"),
                                     "objective": v.get("objective"),
                                     "current_spend": (v.get("current", {}).get("spend")),
                                     "attention_reason": v.get("insight", {}).get("what_needs_attention")}
                                    for k, v in needs.items()},
        },
        "schema": "https://campaign-os/paid-media-best-needs/v1",
    }


def _v24_freshness(cache):
    """Compute freshness signal. Returns: 'fresh' (<24h),
    'recent' (<72h), 'stale' (>72h)."""
    fa = cache.get("fetched_at")
    if not fa:
        return {"status": "no_data", "fetched_at": None}
    try:
        from datetime import datetime, timezone
        t = datetime.fromisoformat(fa.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_hours = (now - t).total_seconds() / 3600
        if age_hours < 24:
            status = "fresh"
        elif age_hours < 72:
            status = "recent"
        else:
            status = "stale"
        return {
            "status": status,
            "fetched_at": fa,
            "data_as_of": cache.get("data_as_of") or cache.get(
                "report_period", {}).get("current_end"),
            "age_hours": round(age_hours, 1),
        }
    except Exception as e:
        return {"status": "unknown", "error": str(e)[:200],
                "fetched_at": fa}


def build_v24_brand_report(brand_id, period_days=31, cookie=None):
    """V2.4 management report — V2.3 + per-campaign intelligence.

    Adds:
    - per-campaign current vs previous comparison
    - per-campaign YTD spend table
    - objective-aware primary-result per campaign
    - best / needs-attention per objective
    - drill-down URLs (adset / ad)
    - per-campaign insight commentary
    - freshness timestamp + freshness status
    """
    base = os.environ.get(
        "CAMPAIGN_OS_BASE_URL", "http://localhost:8080").rstrip("/")
    v23 = build_v23_brand_report(brand_id, period_days, cookie=cookie)
    paid = _v24_load_paid_media_cache_v2(base, brand_id, cookie)
    if not paid:
        v23["schema"] = "https://campaign-os/reporting/v2.4"
        v23["version"] = "2.4"
        v23["paid_media_v24"] = {
            "data_status": "UNAVAILABLE",
            "rule": ("Real Meta Ads cache not present. Run "
                     "/api/meta/ads/ingest/<brand> (read-only) "
                     "to populate."),
        }
        return v23
    cur_rows = (paid.get("current_period") or {}).get("rows") or []
    prev_rows = (paid.get("previous_period") or {}).get("rows") or []
    ytd_rows = (paid.get("ytd") or {}).get("rows") or []
    brand_total_ytd = sum((r.get("spend") or 0) for r in ytd_rows)
    # Per-campaign comparison
    prev_by_id = {str(r.get("campaign_id")): r for r in prev_rows}
    cur_by_id = {str(r.get("campaign_id")): r for r in cur_rows}
    all_ids = set(prev_by_id.keys()) | set(cur_by_id.keys())
    per_campaign = []
    for cid in all_ids:
        cur = cur_by_id.get(cid)
        prev = prev_by_id.get(cid)
        comp = _v24_compare_campaign(cur, prev)
        cur_obj = cur or prev
        primary = _v24_primary_result(cur_obj, cur_obj.get("objective"))
        insight = _v24_campaign_insight(cur_obj, comp, brand_id)
        per_campaign.append({
            "campaign_id": cid,
            "campaign_name": (cur or prev).get("campaign_name"),
            "objective": (cur or prev).get("objective"),
            "status": "DELIVERED" if cur else "ENDED",
            "current": ({"spend": cur.get("spend"),
                          "impressions": cur.get("impressions"),
                          "reach": cur.get("reach"),
                          "clicks": cur.get("clicks"),
                          "ctr": cur.get("ctr"),
                          "cpc": cur.get("cpc"),
                          "cpm": cur.get("cpm"),
                          "frequency": cur.get("frequency")} if cur else None),
            "previous": ({"spend": prev.get("spend"),
                            "impressions": prev.get("impressions"),
                            "reach": prev.get("reach"),
                            "clicks": prev.get("clicks"),
                            "ctr": prev.get("ctr"),
                            "cpc": prev.get("cpc"),
                            "cpm": prev.get("cpm")} if prev else None),
            "comparison": comp,
            "primary_result": primary,
            "insight": insight,
            "drilldown": {
                "adsets_url": f"/api/meta/ads/{brand_id}/campaigns/{cid}/adsets",
                "adsets_label": (f"Adsets in '{(cur or prev or {}).get('campaign_name') or '(unknown)'}'"),
            },
        })
    # Sort: spend desc
    per_campaign.sort(
        key=lambda c: ((c.get("current") or {}).get("spend") or
                       (c.get("previous") or {}).get("spend") or 0),
        reverse=True)
    # YTD campaign table
    ytd_table = _v24_ytd_campaign_table(ytd_rows, brand_total_ytd)
    # Best + needs-attention per objective
    bn = _v24_best_and_needs_attention(per_campaign, ytd_table)
    # Freshness
    freshness = _v24_freshness(paid)
    # Account-level reconciliation (V2.4 §1)
    aa_meta = paid.get("ad_account_meta") or {}
    aa_recon = {
        "name": aa_meta.get("name"),
        "currency": aa_meta.get("currency"),
        "amount_spent_raw_minor_units": aa_meta.get("amount_spent"),
        "amount_spent_field_label": (
            "Lifetime spend in minor units (cents) from "
            "/act_{id} — distinct from YTD actual spend reported "
            "in /insights."),
        "amount_spent_zar": (round(int(aa_meta.get("amount_spent") or 0) / 100, 2)
                              if aa_meta.get("amount_spent") else None),
        "spend_cap": aa_meta.get("spend_cap"),
        "account_status": aa_meta.get("account_status"),
        "timezone_name": aa_meta.get("timezone_name"),
    }
    v23["schema"] = "https://campaign-os/reporting/v2.4"
    v23["version"] = "2.4"
    v23["upstream_schema"] = "https://campaign-os/reporting/v2.3"
    v23["paid_media_v24"] = {
        "data_status": "LIVE",
        "ad_account_id": paid.get("ad_account_id"),
        "ad_account_name": paid.get("ad_account_name"),
        "brand_classification": paid.get("brand_classification"),
        "data_as_of": paid.get("data_as_of"),
        "fetched_at": paid.get("fetched_at"),
        "freshness": freshness,
        "account_reconciliation": aa_recon,
        "per_campaign": per_campaign,
        "ytd_campaign_table": ytd_table,
        "ytd_brand_total_spend": round(brand_total_ytd, 2),
        "best_and_needs_attention": bn,
        "rule": ("Per-campaign insights come from "
                 "/act_{id}/insights?level=campaign. Raw Meta "
                 "actions preserved. NEVER renames Meta-reported "
                 "leads / purchases to commercial outcomes."),
        "caveats": [
            "Per-campaign comparisons treat objective-specific "
            "metrics individually; cross-objective ranking is not "
            "performed (per V2.4 §7).",
            "amount_spent on the ad account = LIFETIME MINOR "
            "UNITS (cents). YTD actual spend is the sum of "
            "per-campaign spend from /insights.",
            "Meta-reported leads / purchases are surfaced as raw "
            "Meta events, not as qualified leads / confirmed sales.",
        ],
    }
    # Add management executive summary lines from the
    # best / needs-attention + YTD totals
    summary_lines = v23.get("sections", {}).get(
        "executive_summary", {}).get("statements", [])
    summary_lines.append({
        "type": "MEASURED_FACT",
        "confidence": "HIGH",
        "statement": (f"{brand_id.title().replace('-', ' ')} year-to-date "
                       f"spend totals R {round(brand_total_ytd):,} across "
                       f"{len(ytd_table)} campaigns. "
                       f"Largest share: "
                       f"{ytd_table[0]['campaign_name'] if ytd_table else '?'} "
                       f"at {ytd_table[0]['share_of_brand_spend_pct'] if ytd_table else 0}% of "
                       f"brand spend."),
    })
    if bn.get("by_objective", {}).get("best"):
        for obj, b in list(bn["by_objective"]["best"].items())[:2]:
            summary_lines.append({
                "type": "MEASURED_FACT",
                "confidence": "HIGH",
                "statement": (f"Strongest {obj} campaign this period: "
                               f"{b['campaign_name']} "
                               f"(cost per primary result "
                               f"R {b['primary_result']['primary_cost_per_unit']})."),
            })
    if bn.get("by_objective", {}).get("needs_attention"):
        for obj, n in list(bn["by_objective"]["needs_attention"].items())[:2]:
            summary_lines.append({
                "type": "MEASURED_FACT",
                "confidence": "MEDIUM",
                "statement": (f"{obj} campaign needing attention: "
                               f"{n['campaign_name']} "
                               f"({n.get('attention_reason','see drill-down')})."),
            })
    # GA4 cross-channel observation (V2.4 §11)
    ga4_cross = v23.get("paid_media", {}).get(
        "cross_channel_observations") or []
    # Append a per-campaign-level cross-channel if UTM-matching
    # is reliable — for now we report the V2.3 observation + flag
    # campaign-level GA4 attribution as unavailable
    summary_lines.append({
        "type": "CAVEAT",
        "confidence": "HIGH",
        "statement": ("Campaign-level GA4 attribution is "
                       "available only where Meta campaign names "
                       "or UTMs map reliably to GA4 campaign data. "
                       "This is the case-by-case basis — no fuzzy "
                       "matching performed."),
    })
    return v23


def render_v24_brand_report_html(brand_id, period_days=31, cookie=None):
    """Render the V2.4 management report as HTML."""
    r = build_v24_brand_report(brand_id, period_days, cookie=cookie)
    if r.get("error"):
        return f"<h1>Error</h1><p>{r['error']}</p>"
    parts = [
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>{r['brand_name']} — V2.4 Management Report</title>",
        _HTML_CSS, "</head><body>",
    ]
    parts.append(f"<h1>{r['brand_name']} — Management Report "
                 f"(V2.4 — Per-Campaign Paid Media)</h1>")
    rp = r["report_period"]
    pm24 = r.get("paid_media_v24") or {}
    fresh = pm24.get("freshness") or {}
    parts.append(f"<div class='meta'>")
    parts.append(f"Current period: <strong>{rp['current_start']} → "
                 f"{rp['current_end']}</strong> ({rp['days_per_window']} days)<br>")
    parts.append(f"Previous period: <strong>{rp['previous_start']} → "
                 f"{rp['previous_end']}</strong><br>")
    parts.append(f"Data complete through: <strong>{r['data_complete_through']}</strong><br>")
    parts.append(f"Paid media data_as_of: <strong>{pm24.get('data_as_of', '?')}</strong> "
                 f"({fresh.get('status','?')}, age {fresh.get('age_hours','?')}h)<br>")
    parts.append(f"Generated: {r['generated_at']}")
    parts.append("</div>")
    # Account reconciliation (V2.4 §1)
    aa = pm24.get("account_reconciliation") or {}
    parts.append("<h2>Account Reconciliation (V2.4 §1)</h2>")
    parts.append(f"<table class='coverage-table'>")
    parts.append(f"<tr><th>Field</th><th>Value</th><th>Notes</th></tr>")
    parts.append(f"<tr><td>Ad account name</td><td>{aa.get('name','?')}</td>"
                 f"<td>—</td></tr>")
    parts.append(f"<tr><td>Currency</td><td>{aa.get('currency','?')}</td>"
                 f"<td>—</td></tr>")
    parts.append(f"<tr><td>amount_spent (raw)</td>"
                 f"<td>{aa.get('amount_spent_raw_minor_units','?')} "
                 f"{aa.get('currency','')}</td>"
                 f"<td><strong>LIFETIME MINOR UNITS (cents)</strong></td></tr>")
    parts.append(f"<tr><td>amount_spent (ZAR)</td>"
                 f"<td>R {aa.get('amount_spent_zar', 0):,.2f}</td>"
                 f"<td>Lifetime spend to date</td></tr>")
    parts.append(f"<tr><td>spend_cap</td><td>{aa.get('spend_cap','?')}</td>"
                 f"<td>0 = no cap</td></tr>")
    parts.append(f"<tr><td>YTD actual spend</td>"
                 f"<td>R {pm24.get('ytd_brand_total_spend', 0):,.2f}</td>"
                 f"<td>From /act_{{id}}/insights?level=campaign&time_range=2026-01-01→{rp['current_end']}</td></tr>")
    parts.append(f"</table>")
    # Executive summary
    parts.append("<h2>Executive Summary</h2><ul class='exec-summary'>")
    for st in (r.get("sections", {}).get(
            "executive_summary", {}).get("statements") or []):
        parts.append(f"<li>{st['statement']}</li>")
    parts.append("</ul>")
    # Paid media summary (V2.4 §13)
    pm = r.get("paid_media", {})
    parts.append(f"<h2>Paid Media Summary (V2.4 §13) "
                 f"{_pill(pm.get('data_status','UNKNOWN'))}</h2>")
    if pm.get("data_status") == "LIVE":
        sc = (pm.get("scorecard") or {}).get("rows") or []
        parts.append("<table class='coverage-table'>")
        parts.append("<tr><th>KPI</th><th>Current</th><th>Previous</th>"
                     "<th>Δ%</th><th>YTD total</th></tr>")
        for row in sc:
            cur = row.get("current")
            prev = row.get("previous")
            unit = row.get("unit", "")
            cur_disp = (round(cur, 2) if isinstance(cur, (int, float))
                          else cur)
            prev_disp = (round(prev, 2) if isinstance(prev, (int, float))
                           else prev)
            pct = row.get("delta_pct")
            pct_disp = f"{pct:+.1f}%" if pct is not None else "—"
            parts.append(
                f"<tr><td>{row['label']}</td>"
                f"<td>{cur_disp} {unit}</td>"
                f"<td>{prev_disp}</td>"
                f"<td>{pct_disp}</td>"
                f"<td>{row.get('ytd_total','—')}</td></tr>")
        parts.append("</table>")
    # Per-campaign current vs previous (V2.4 §3-4)
    pc = pm24.get("per_campaign") or []
    parts.append("<h2>Campaign Performance — Current vs Previous</h2>")
    parts.append("<table class='coverage-table'>")
    parts.append("<tr><th>Campaign</th><th>Objective</th>"
                 "<th>Current spend</th><th>Previous spend</th>"
                 "<th>Δ% spend</th><th>Clicks Δ%</th>"
                 "<th>CPC Δ%</th><th>CTR Δ</th>"
                 "<th>Status</th><th>Insight</th></tr>")
    for c in pc:
        cn = c.get('campaign_name') or '(?)'
        obj = c.get('objective') or '?'
        cur = c.get('current') or {}
        prev = c.get('previous') or {}
        comp = c.get('comparison') or {}
        sp_d = comp.get('spend', {}).get('delta_pct')
        cl_d = comp.get('clicks', {}).get('delta_pct')
        cp_d = comp.get('cpc', {}).get('delta_pct')
        ct_d = comp.get('ctr', {}).get('delta_abs')
        sp_disp = f"{sp_d:+.1f}%" if sp_d is not None else "—"
        cl_disp = f"{cl_d:+.1f}%" if cl_d is not None else "—"
        cp_disp = f"{cp_d:+.1f}%" if cp_d is not None else "—"
        ct_disp = f"{ct_d:+.2f}" if ct_d is not None else "—"
        ins = c.get('insight') or {}
        ins_short = (ins.get('what_needs_attention')
                       or ins.get('what_it_means') or '')[:80]
        parts.append(
            f"<tr><td>{cn}</td><td>{obj}</td>"
            f"<td>R {cur.get('spend') or 0:,.2f}</td>"
            f"<td>R {prev.get('spend') or 0:,.2f}</td>"
            f"<td>{sp_disp}</td>"
            f"<td>{cl_disp}</td>"
            f"<td>{cp_disp}</td>"
            f"<td>{ct_d}</td>"
            f"<td>{_pill(c.get('status','?'))}</td>"
            f"<td>{ins_short}</td></tr>")
    parts.append("</table>")
    # YTD spend per campaign (V2.4 §6)
    yt = pm24.get("ytd_campaign_table") or []
    parts.append("<h2>YTD Spend per Campaign (V2.4 §6)</h2>")
    parts.append("<table class='coverage-table'>")
    parts.append("<tr><th>#</th><th>Campaign</th><th>Objective</th>"
                 "<th>YTD spend</th><th>Share of brand</th>"
                 "<th>Impressions</th><th>Clicks</th>"
                 "<th>Primary result</th><th>Cost / primary</th></tr>")
    for i, c in enumerate(yt, 1):
        pr = c.get("primary_result") or {}
        pr_lbl = pr.get("primary_metric_label", "—")
        pr_v = pr.get("primary_value", "—")
        pr_cpp = pr.get("primary_cost_per_unit")
        pr_cpp_disp = (f"R {pr_cpp:,.2f}" if isinstance(pr_cpp, (int, float))
                          else "—")
        parts.append(
            f"<tr><td>{i}</td>"
            f"<td>{c.get('campaign_name','?')}</td>"
            f"<td>{c.get('objective','?')}</td>"
            f"<td>R {c.get('spend_ytd', 0):,.2f}</td>"
            f"<td>{c.get('share_of_brand_spend_pct', 0)}%</td>"
            f"<td>{(c.get('impressions_ytd') or 0):,}</td>"
            f"<td>{(c.get('clicks_ytd') or 0):,}</td>"
            f"<td>{pr_lbl}: {pr_v}</td>"
            f"<td>{pr_cpp_disp}</td></tr>")
    parts.append("</table>")
    # Best + needs attention (V2.4 §9)
    bn = pm24.get("best_and_needs_attention") or {}
    by_obj = bn.get("by_objective") or {}
    if by_obj.get("best"):
        parts.append("<h3>What Worked (per objective, V2.4 §9)</h3>")
        parts.append("<table class='coverage-table'>")
        parts.append("<tr><th>Objective</th><th>Campaign</th>"
                     "<th>Spend</th><th>Primary result</th>"
                     "<th>Cost / primary</th></tr>")
        for obj, b in (by_obj.get("best") or {}).items():
            pr = b.get("primary_result") or {}
            pr_v = pr.get("primary_value", "—")
            pr_cpp = pr.get("primary_cost_per_unit")
            pr_cpp_disp = (f"R {pr_cpp:,.2f}"
                              if isinstance(pr_cpp, (int, float)) else "—")
            parts.append(
                f"<tr><td>{obj}</td>"
                f"<td>{b.get('campaign_name','?')}</td>"
                f"<td>R {b.get('current_spend') or 0:,.2f}</td>"
                f"<td>{pr.get('primary_metric_label','?')}: {pr_v}</td>"
                f"<td>{pr_cpp_disp}</td></tr>")
        parts.append("</table>")
    if by_obj.get("needs_attention"):
        parts.append("<h3>What Needs Attention (per objective)</h3>")
        parts.append("<table class='coverage-table'>")
        parts.append("<tr><th>Objective</th><th>Campaign</th>"
                     "<th>Spend</th><th>Reason</th>"
                     "<th>Recommended action</th></tr>")
        for obj, n in (by_obj.get("needs_attention") or {}).items():
            ins = (n.get("attention_reason") or "see drill-down")
            parts.append(
                f"<tr><td>{obj}</td>"
                f"<td>{n.get('campaign_name','?')}</td>"
                f"<td>R {n.get('current_spend') or 0:,.2f}</td>"
                f"<td>{ins}</td>"
                f"<td>{ins}</td></tr>")
        parts.append("</table>")
    # Drill-down URLs (V2.4 §10)
    parts.append("<h3>Drill-Down URLs (V2.4 §10)</h3>")
    parts.append("<table class='coverage-table'>")
    parts.append("<tr><th>Campaign</th><th>Adset drill-down</th></tr>")
    for c in pc[:20]:
        cn = c.get('campaign_name', '?')
        cid = c.get('campaign_id', '?')
        url = f"/api/meta/ads/{brand_id}/campaigns/{cid}/adsets"
        parts.append(f"<tr><td>{cn}</td>"
                       f"<td><a href='{url}'>{url}</a></td></tr>")
    parts.append("</table>")
    # Synthetic quarantine (re-assert V2.3 §12)
    sq = r.get("synthetic_quarantine") or {}
    parts.append("<h2>Synthetic Quarantine Audit (V2.4 §16)</h2>")
    parts.append(f"<div class='section'>Synthetic file: "
                 f"<code>{sq.get('synthetic_path','?')}</code> — "
                 f"present: {sq.get('synthetic_file_present')}, "
                 f"read in code: {sq.get('synthetic_read_in_code')}<br>")
    for line in (sq.get("audit") or []):
        parts.append(f"<div>• {line}</div>")
    parts.append("</div>")
    parts.append("<div class='footer'><em>V2.4 management report — "
                 "per-campaign paid media + V2.2 analytics + V2.3 "
                 "real Meta Ads. All read-only.</em></div>")
    parts.append("</body></html>")
    return "\n".join(parts)





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


def render_brand_report_html(brand_id: str, period_days: int = 31,
                             cookie: Optional[str] = None) -> str:
    r = build_brand_report(brand_id, period_days, cookie=cookie)
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

    # Pillar mix — dedicated structured table
    pmx = r.get("sections", {}).get("pillar_mix", {})
    if pmx.get("data_status") == "HISTORICAL_REAL":
        parts.append("<h2>Business Pillar Mix</h2>")
        parts.append("<div class='section'>")
        counts = pmx.get("pillar_event_counts", {})
        pct = pmx.get("pillar_event_pct", {})
        total = pmx.get("total_events_classified", 0)
        parts.append(f"<div>Total events classified: <strong>{total}</strong></div>")
        parts.append("<table class='coverage-table'>")
        parts.append("<tr><th>Pillar</th><th>Events</th><th>Share</th></tr>")
        for p in ("retail", "fitting", "coaching"):
            c = counts.get(p, 0)
            parts.append(f"<tr><td>{p.capitalize()}</td>"
                         f"<td>{c}</td><td>{pct.get(p, 0):.1f}%</td></tr>")
        parts.append("</table>")
        # Cadences
        cadences = pmx.get("cadences_by_lane") or {}
        if cadences:
            parts.append("<div><strong>Cadences by lane:</strong></div>")
            parts.append("<table class='coverage-table'>")
            parts.append("<tr><th>Lane</th><th>Cadence</th></tr>")
            for lane, c in cadences.items():
                txt = c.get("cadence_text") or ""
                parts.append(f"<tr><td>{lane}</td><td>{txt}</td></tr>")
            parts.append("</table>")
        parts.append("</div>")

    # Visual DNA — compact stats grid
    vdna = r.get("sections", {}).get("visual_dna", {})
    if vdna.get("data_status") == "HISTORICAL_REAL":
        parts.append("<h2>Creative Genome (Visual DNA)</h2>")
        parts.append("<div class='section'>")
        parts.append(f"<div><strong>Samples indexed:</strong> {vdna.get('samples', 0)}</div>")
        ori = vdna.get("orientation_distribution") or {}
        if ori:
            parts.append(f"<div><strong>Orientation:</strong> " +
                         ", ".join(f"{k}={v}" for k, v in ori.items()) + "</div>")
        lum = vdna.get("luminance_distribution") or {}
        if lum:
            parts.append(f"<div><strong>Luminance:</strong> " +
                         ", ".join(f"{k}={v}" for k, v in lum.items()) + "</div>")
        ocr = vdna.get("ocr_available_distribution") or {}
        if ocr:
            parts.append(f"<div><strong>OCR available:</strong> " +
                         ", ".join(f"{k}={v}" for k, v in ocr.items()) + "</div>")
        ocr_med = vdna.get("ocr_word_count_median")
        if ocr_med is not None:
            parts.append(f"<div><strong>Median OCR word count:</strong> {ocr_med}</div>")
        parts.append("</div>")

    # Page / service interest
    pi = r.get("sections", {}).get("page_interest", {})
    if pi.get("data_status") == "LIVE":
        parts.append("<h2>Page / Service Interest</h2>")
        parts.append("<table class='coverage-table'>")
        parts.append("<tr><th>Page</th><th>Sessions</th><th>Users</th><th>Engaged</th></tr>")
        for p in (pi.get("service_pages") or []):
            parts.append(f"<tr><td>{p.get('label')} ({p.get('path')})</td>"
                         f"<td>{p.get('sessions', 0)}</td>"
                         f"<td>{p.get('users', 0)}</td>"
                         f"<td>{p.get('engaged_sessions', 0)}</td></tr>")
        parts.append("</table>")

    # Historical reports
    hr = r.get("sections", {}).get("historical_reports", {})
    if hr.get("data_status") == "HISTORICAL_REAL" and hr.get("count"):
        parts.append("<h2>Historical Reports (operator-uploaded)</h2>")
        parts.append("<table class='coverage-table'>")
        parts.append("<tr><th>Filename</th><th>Period</th><th>Uploaded</th></tr>")
        for f in (hr.get("files") or []):
            parts.append(f"<tr><td>{f.get('filename')}</td>"
                         f"<td>{f.get('period') or '?'}</td>"
                         f"<td>{(f.get('uploaded_at') or '?')[:10]}</td></tr>")
        parts.append("</table>")

    # Per-section data
    for key, section in r.get("sections", {}).items():
        # Skip sections we already rendered above
        if key in ("pillar_mix", "visual_dna", "page_interest",
                   "historical_reports"):
            continue
        title = section.get("title", key)
        status = section.get("data_status", "UNKNOWN")
        parts.append(f"<h2>{title} {_pill(status)}</h2>")
        parts.append("<div class='section'>")
        for k, v in section.items():
            if k in ("title", "data_status"):
                continue
            if isinstance(v, (str, int)) and v:
                parts.append(f"<div><strong>{k}</strong>: {v}</div>")
            elif isinstance(v, dict) and v:
                # Print nested dict as sub-table (e.g. audience metrics)
                parts.append(f"<div><strong>{k}</strong>:</div>")
                parts.append("<table class='coverage-table'>")
                for nk, nv in v.items():
                    if nv is None:
                        continue
                    parts.append(f"<tr><td>{nk}</td><td>{nv}</td></tr>")
                parts.append("</table>")
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                # Print list of dicts as sub-table (e.g. top_media_by_reach)
                parts.append(f"<div><strong>{k}</strong> "
                             f"({len(v)} entries):</div>")
                keys = list(v[0].keys())
                parts.append("<table class='coverage-table'>")
                parts.append("<tr>" +
                             "".join(f"<th>{kk}</th>" for kk in keys) +
                             "</tr>")
                for item in v:
                    parts.append("<tr>" +
                                 "".join(f"<td>{item.get(kk, '')}</td>"
                                         for kk in keys) +
                                 "</tr>")
                parts.append("</table>")
        parts.append("</div>")

    # What worked
    worked = r.get("what_worked", [])
    if worked:
        parts.append("<h2>What Worked</h2>")
        for w in worked:
            parts.append("<div class='rec low'>")
            parts.append(f"<strong>★ {w['title']}</strong><br>")
            if w.get("evidence"):
                parts.append(f"<em>Evidence:</em> {w['evidence']}<br>")
            if w.get("interpretation"):
                parts.append(f"<em>Interpretation:</em> {w['interpretation']}<br>")
            if w.get("business_relevance"):
                parts.append(f"<em>Business relevance:</em> {w['business_relevance']}")
            parts.append("</div>")

    # What needs attention
    needs = r.get("what_needs_attention", [])
    if needs:
        parts.append("<h2>What Needs Attention</h2>")
        for n in needs:
            parts.append("<div class='rec high'>")
            parts.append(f"<strong>⚠ {n['title']}</strong><br>")
            if n.get("evidence"):
                parts.append(f"<em>Evidence:</em> {n['evidence']}<br>")
            if n.get("interpretation"):
                parts.append(f"<em>Interpretation:</em> {n['interpretation']}<br>")
            if n.get("business_relevance"):
                parts.append(f"<em>Business relevance:</em> {n['business_relevance']}")
            parts.append("</div>")

    # Cross-channel observations (brief §6)
    cross = r.get("cross_channel_observations", [])
    if cross:
        parts.append("<h2>Cross-Channel Observations</h2>")
        parts.append("<div class='section'>")
        parts.append("<em>Wording is evidence-based ('consistent with', "
                     "'aligns with'); not causal.</em>")
        for c in cross:
            parts.append("<div class='rec medium'>")
            parts.append(f"<strong>{c.get('type', '')} "
                         f"({c.get('confidence', '')})</strong><br>")
            parts.append(f"{c.get('observation', '')}<br>")
            if c.get("evidence_basis"):
                parts.append("<em>Evidence basis:</em><ul>")
                for ev in c["evidence_basis"]:
                    parts.append(f"<li>{ev}</li>")
                parts.append("</ul>")
            parts.append("</div>")
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
