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
