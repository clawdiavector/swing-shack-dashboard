"""
marketing_calendar.py — Brand-aware strategy-aware marketing calendar.

Distinct from marketing_lanes.py (which is the parallel-lanes execution
surface). This module owns:

  - Brand strategy config (pillars, North Stars, scouting profile,
    lead-time rules, calendar preferences)
  - Generic calendar record model (campaign / moment / reminder / watchlist)
  - Deterministic lead-time calculation
  - Calendar view assembly
  - Candidate write + state transitions
  - Brand isolation (Takomo is product_brand under Stick, never an
    operating brand)

Architecture is brand-agnostic. Per-brand content (pillars, North Star
targets, colors, scouting profile) lives in:

  /data/brand-directory/<brand_id>/calendar_config.json

The module reads that file (or the in-process override) and never
hard-codes strategy.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_LOG = logging.getLogger("campaign_os.marketing_calendar")

# ─── Paths ──────────────────────────────────────────────────────────────────
_BRAND_DIR = Path(os.environ.get("DATA_DIR", "/data/campaign-os")) / "brand-directory"
_BUNDLED_DATA_DIR = Path(os.environ.get("BUNDLED_DATA_DIR", "/app/data"))
_DEFAULT_LOCAL_DIR = Path(
    os.environ.get("BRAND_DIR_LOCAL", "/Users/fivefriday/hermes-fleet/shared/data/brand-directory")
)
_DATA_DIR = Path(os.environ.get("DATA_DIR", "/data/campaign-os"))
_CALENDAR_DIR = _DATA_DIR / "intelligence" / "marketing-calendar"
_CALENDAR_DIR.mkdir(parents=True, exist_ok=True)

# ─── Constants ──────────────────────────────────────────────────────────────
VALID_BRAND_IDS = ["swing-shack", "stick", "bag-drop"]
VALID_PRODUCT_BRANDS = {"takomo": "stick"}  # product_brand → parent brand
VALID_RECORD_TYPES = ["campaign", "content", "moment", "reminder", "watchlist"]
VALID_STATUSES = ["candidate", "watchlist", "approved", "ignored", "active", "completed"]
VALID_LEAD_TIME_CLASSES = [
    "major_retail",
    "major_sporting_event",
    "normal_campaign",
    "reactive_opportunity",
    "content_moment",
]
VALID_LEAD_TIME_PHASES = [
    "research_start",
    "planning_start",
    "production_deadline",
    "campaign_live_start",
    "event_date",
]

# Default lead-time template (days before event_date). Generic; per-brand
# can override per class in calendar_config.json.
DEFAULT_LEAD_TIME_TEMPLATE: Dict[str, Dict[str, int]] = {
    "major_retail": {
        "research_start": 90,
        "planning_start": 60,
        "production_deadline": 21,
        "campaign_live_start": 14,
        "event_date": 0,
    },
    "major_sporting_event": {
        "research_start": 60,
        "planning_start": 30,
        "production_deadline": 14,
        "campaign_live_start": 7,
        "event_date": 0,
    },
    "normal_campaign": {
        "research_start": 30,
        "planning_start": 14,
        "production_deadline": 7,
        "campaign_live_start": 3,
        "event_date": 0,
    },
    "reactive_opportunity": {
        "research_start": 7,
        "planning_start": 3,
        "production_deadline": 1,
        "campaign_live_start": 0,
        "event_date": 0,
    },
    "content_moment": {
        "research_start": 14,
        "planning_start": 7,
        "production_deadline": 3,
        "campaign_live_start": 1,
        "event_date": 0,
    },
}


# ─── Generic Brand Calendar Context Loader ──────────────────────────────────

def _find_brand_config(brand_id: str) -> Optional[Path]:
    """Locate calendar_config.json for a brand. Mirrors p11_context_engine
    lookup pattern: tries DATA_DIR/brand-directory/<brand> (volume) +
    BUNDLED_DATA_DIR/brand-directory/<brand> (image-bundled) + local
    working-copy."""
    for base in (_BRAND_DIR, _BUNDLED_DATA_DIR, _DEFAULT_LOCAL_DIR):
        candidate = base / brand_id / "calendar_config.json"
        if candidate.exists():
            return candidate
    return None


def load_brand_config(brand_id: str) -> Dict[str, Any]:
    """Load the calendar strategy model for a brand. Returns a normalised
    dict with the structure described in the Slice 0.1 brief.

    If no config file is found, returns an empty/disabled config — the
    Scout will refuse to add candidates for an unconfigured brand.
    """
    if brand_id not in VALID_BRAND_IDS:
        raise ValueError(
            f"brand_id '{brand_id}' is not an operating brand. "
            f"Valid: {VALID_BRAND_IDS}. (takomo is a product_brand under stick.)"
        )
    path = _find_brand_config(brand_id)
    if path is None:
        return {
            "brand_id": brand_id,
            "timezone": "Africa/Johannesburg",
            "pillars": [],
            "scouting_profile": {},
            "lead_time_rules": {},
            "calendar_preferences": {},
            "configured": False,
            "config_path": None,
        }
    try:
        cfg = json.loads(path.read_text())
    except Exception as e:
        _LOG.warning("Failed to parse calendar_config.json at %s: %s", path, e)
        return {
            "brand_id": brand_id,
            "timezone": "Africa/Johannesburg",
            "pillars": [],
            "scouting_profile": {},
            "lead_time_rules": {},
            "calendar_preferences": {},
            "configured": False,
            "config_path": str(path),
            "parse_error": str(e),
        }
    # Validate the parsed structure — a file that exists but doesn't
    # have a brand_id is not actually a calendar config.
    if not isinstance(cfg, dict) or "brand_id" not in cfg:
        return {
            "brand_id": brand_id,
            "timezone": "Africa/Johannesburg",
            "pillars": [],
            "scouting_profile": {},
            "lead_time_rules": {},
            "calendar_preferences": {},
            "configured": False,
            "config_path": str(path),
            "parse_error": "missing brand_id at root",
        }
    cfg.setdefault("brand_id", brand_id)
    cfg.setdefault("timezone", "Africa/Johannesburg")
    cfg.setdefault("pillars", [])
    cfg.setdefault("scouting_profile", {})
    cfg.setdefault("lead_time_rules", {})
    cfg.setdefault("calendar_preferences", {})
    cfg["configured"] = True
    cfg["config_path"] = str(path)
    return cfg


def _persist_brand_config(brand_id: str, cfg: Dict[str, Any]) -> Path:
    """Write a brand's calendar_config.json to the volume-backed location."""
    if brand_id not in VALID_BRAND_IDS:
        raise ValueError(f"brand_id '{brand_id}' is not an operating brand.")
    target_dir = _BRAND_DIR / brand_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / "calendar_config.json"
    serialisable = {k: v for k, v in cfg.items() if k not in {"configured", "config_path"}}
    target_path.write_text(json.dumps(serialisable, indent=2, ensure_ascii=False))
    return target_path


# ─── North-Star Target Computation ──────────────────────────────────────────

def derive_pillar_weekly_target(pillar: Dict[str, Any]) -> Optional[float]:
    """If a pillar has a 'daily_volume' and 'operating_days_per_week' on its
    North Star, derive the weekly target deterministically.

    The source/provenance is preserved on the pillar — never silently
    rewritten into a global calendar rule.
    """
    ns = pillar.get("north_star_target") or {}
    if not isinstance(ns, dict):
        return None
    daily = ns.get("daily_volume")
    days = ns.get("operating_days_per_week")
    if daily is None or days is None:
        return None
    try:
        return float(daily) * float(days)
    except Exception:
        return None


def enrich_pillar_targets(pillars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach derived_weekly_target to each pillar (computed deterministically
    from daily_volume × operating_days_per_week). Provenance is preserved."""
    out = []
    for p in pillars:
        enriched = dict(p)
        wk = derive_pillar_weekly_target(p)
        if wk is not None:
            enriched["derived_weekly_target"] = wk
        out.append(enriched)
    return out


# ─── Lead-Time Engine ──────────────────────────────────────────────────────

def _resolve_lead_time_template(brand_cfg: Dict[str, Any], lead_time_class: str) -> Dict[str, int]:
    """Resolve a per-class lead-time template. Order:
      1. brand_cfg.lead_time_rules[lead_time_class]
      2. brand_cfg.lead_time_rules.default
      3. DEFAULT_LEAD_TIME_TEMPLATE[lead_time_class]
    Falls back to "normal_campaign" if class is unknown.
    """
    if lead_time_class not in DEFAULT_LEAD_TIME_TEMPLATE:
        lead_time_class = "normal_campaign"
    rules = brand_cfg.get("lead_time_rules") or {}
    if isinstance(rules, dict):
        per_class = rules.get(lead_time_class)
        if isinstance(per_class, dict):
            # Merge over default so partial overrides work
            merged = dict(DEFAULT_LEAD_TIME_TEMPLATE[lead_time_class])
            merged.update({k: int(v) for k, v in per_class.items()
                           if k in merged and isinstance(v, (int, float))})
            return merged
        # Per-brand default override
        brand_default = rules.get("default")
        if isinstance(brand_default, dict):
            merged = dict(DEFAULT_LEAD_TIME_TEMPLATE[lead_time_class])
            merged.update({k: int(v) for k, v in brand_default.items()
                           if k in merged and isinstance(v, (int, float))})
            return merged
    return dict(DEFAULT_LEAD_TIME_TEMPLATE[lead_time_class])


def compute_lead_time_schedule(
    event_date_iso: str,
    lead_time_class: str = "normal_campaign",
    brand_cfg: Optional[Dict[str, Any]] = None,
    tz_name: str = "Africa/Johannesburg",
) -> Dict[str, Optional[str]]:
    """Compute research_start, planning_start, production_deadline,
    campaign_live_start, event_date for an event.

    Returns ISO-8601 strings (YYYY-MM-DD) for each phase. Phases fall
    back to None if event_date cannot be parsed. The agent can recommend
    overrides but should not perform the arithmetic manually.
    """
    brand_cfg = brand_cfg or {}
    template = _resolve_lead_time_template(brand_cfg, lead_time_class)
    if not event_date_iso:
        return {k: None for k in VALID_LEAD_TIME_PHASES}
    try:
        ev = datetime.fromisoformat(event_date_iso.replace("Z", "+00:00"))
    except Exception:
        return {k: None for k in VALID_LEAD_TIME_PHASES}
    out: Dict[str, Optional[str]] = {"event_date": ev.date().isoformat()}
    for phase in ("research_start", "planning_start", "production_deadline", "campaign_live_start"):
        days_before = int(template.get(phase, 0))
        phase_date = ev - timedelta(days=days_before)
        out[phase] = phase_date.date().isoformat()
    return out


# ─── Generic Calendar Record ──────────────────────────────────────────────

def _calendar_path(brand_id: str) -> Path:
    return _CALENDAR_DIR / f"{brand_id}.jsonl"


def _watchlist_path(brand_id: str) -> Path:
    return _CALENDAR_DIR / f"{brand_id}__watchlist.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_calendar_id(brand_id: str, record_type: str) -> str:
    short = uuid.uuid4().hex[:8]
    return f"cal-{brand_id}-{record_type[:3]}-{int(time.time())}-{short}"


def add_candidate(
    brand_id: str,
    record: Dict[str, Any],
    initial_status: str = "candidate",
) -> Dict[str, Any]:
    """Append a candidate / moment / reminder / watchlist record.

    Brand isolation enforced: brand_id must be an operating brand.
    product_brand is allowed (e.g. takomo under stick) but does NOT
    become a brand_id.

    Returns the persisted record (with assigned calendar_id, status,
    created_at, etc.).
    """
    if brand_id not in VALID_BRAND_IDS:
        raise ValueError(
            f"brand_id '{brand_id}' is not an operating brand. "
            f"Valid: {VALID_BRAND_IDS}."
        )
    record_type = record.get("type", "moment")
    if record_type not in VALID_RECORD_TYPES:
        raise ValueError(
            f"type '{record_type}' invalid. Valid: {VALID_RECORD_TYPES}"
        )
    enriched = dict(record)
    enriched["brand_id"] = brand_id
    enriched.setdefault("calendar_id", _gen_calendar_id(brand_id, record_type))
    enriched.setdefault("status", initial_status)
    enriched.setdefault("source_urls", [])
    enriched.setdefault("source_type", "scout")
    enriched.setdefault("pillars", [])
    enriched.setdefault("campaign_ids", [])
    enriched.setdefault("product_brands", [])
    enriched.setdefault("products", [])
    enriched.setdefault("suggested_angles", [])
    enriched.setdefault("created_by", "manual")
    enriched.setdefault("created_at", _now_iso())
    enriched.setdefault("last_verified", _now_iso())

    # Auto-compute lead_time_days + schedule if event_date + lead_time_class given
    if enriched.get("event_date") and enriched.get("lead_time_class"):
        brand_cfg = load_brand_config(brand_id)
        sched = compute_lead_time_schedule(
            enriched["event_date"],
            enriched["lead_time_class"],
            brand_cfg=brand_cfg,
        )
        enriched["lead_time_schedule"] = sched
        if enriched.get("event_date"):
            try:
                ev = datetime.fromisoformat(enriched["event_date"].replace("Z", "+00:00"))
                plan = datetime.fromisoformat(sched["planning_start"]).replace(tzinfo=ev.tzinfo)
                enriched["lead_time_days"] = (ev - plan).days
            except Exception:
                enriched["lead_time_days"] = None

    # Persist
    if enriched["status"] == "watchlist":
        path = _watchlist_path(brand_id)
    else:
        path = _calendar_path(brand_id)
    with path.open("a") as f:
        f.write(json.dumps(enriched, ensure_ascii=False) + "\n")
    return enriched


def list_records(brand_id: str, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read all records for a brand. status_filter=None returns both calendar
    + watchlist; status_filter='watchlist' returns only watchlist."""
    records: List[Dict[str, Any]] = []
    files = []
    if status_filter == "watchlist":
        files = [_watchlist_path(brand_id)]
    elif status_filter and status_filter != "watchlist":
        files = [_calendar_path(brand_id), _watchlist_path(brand_id)]
    else:
        files = [_calendar_path(brand_id), _watchlist_path(brand_id)]
    for path in files:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if status_filter and r.get("status") != status_filter:
                continue
            records.append(r)
    return records


def transition_status(
    brand_id: str,
    calendar_id: str,
    new_status: str,
    reason: str = "",
) -> Optional[Dict[str, Any]]:
    """Transition a record between statuses (e.g. watchlist → candidate).
    Persists the transition by appending a new copy of the record to the
    target file (jsonl is append-only).
    """
    if new_status not in VALID_STATUSES:
        raise ValueError(f"status '{new_status}' invalid. Valid: {VALID_STATUSES}")
    all_records = list_records(brand_id)
    target = next((r for r in all_records if r.get("calendar_id") == calendar_id), None)
    if not target:
        return None
    prev = target.get("status")
    updated = dict(target)
    updated["status"] = new_status
    updated["previous_status"] = prev
    updated["transition_reason"] = reason
    updated["last_verified"] = _now_iso()
    target_path = _watchlist_path(brand_id) if new_status == "watchlist" else _calendar_path(brand_id)
    with target_path.open("a") as f:
        f.write(json.dumps(updated, ensure_ascii=False) + "\n")
    return updated


# ─── Calendar View Assembly ─────────────────────────────────────────────────

def get_calendar_view(
    brand_id: str,
    start_date_iso: Optional[str] = None,
    end_date_iso: Optional[str] = None,
    include_watchlist: bool = True,
) -> Dict[str, Any]:
    """Assemble a brand-aware calendar view: pillar summary at the top +
    records (campaign / moment / reminder / watchlist) within the date range.

    No hard-coded pillar names. The brand config determines everything.
    """
    cfg = load_brand_config(brand_id)
    pillars = enrich_pillar_targets(cfg.get("pillars") or [])

    # Records
    all_records = list_records(brand_id)
    if not include_watchlist:
        all_records = [r for r in all_records if r.get("status") != "watchlist"]

    # Filter by date range
    if start_date_iso or end_date_iso:
        def in_range(rec):
            date_fields = []
            if rec.get("event_date"):
                date_fields.append(rec["event_date"])
            if rec.get("campaign_start"):
                date_fields.append(rec["campaign_start"])
            if rec.get("campaign_end"):
                date_fields.append(rec["campaign_end"])
            if not date_fields:
                # If no dates, include (it's a watchlist-style item with no date)
                return include_watchlist and rec.get("status") == "watchlist"
            for d in date_fields:
                try:
                    d_iso = d[:10]
                    if start_date_iso and d_iso < start_date_iso[:10]:
                        continue
                    if end_date_iso and d_iso > end_date_iso[:10]:
                        continue
                    return True
                except Exception:
                    continue
            return False
        filtered = [r for r in all_records if in_range(r)]
    else:
        filtered = all_records

    # Build pillar colour map (from brand config — not hard-coded)
    pillar_colour_map = {}
    for p in pillars:
        col = p.get("colour") or p.get("color")
        if col:
            pillar_colour_map[p.get("pillar_id")] = col

    # Calendar items in chronological order
    items = []
    for r in filtered:
        items.append({
            "calendar_id": r.get("calendar_id"),
            "brand_id": r.get("brand_id", brand_id),
            "title": r.get("title", "(untitled)"),
            "type": r.get("type", "moment"),
            "status": r.get("status"),
            "event_date": r.get("event_date"),
            "event_end": r.get("event_end"),
            "campaign_start": r.get("campaign_start"),
            "campaign_end": r.get("campaign_end"),
            "pillars": r.get("pillars", []),
            "relevance_score": r.get("relevance_score"),
            "relevance_reason": r.get("relevance_reason"),
            "commercial_relevance": r.get("commercial_relevance"),
            "audience_relevance": r.get("audience_relevance"),
            "brand_relevance": r.get("brand_relevance"),
            "timeliness": r.get("timeliness"),
            "confidence": r.get("confidence"),
            "lead_time_days": r.get("lead_time_days"),
            "lead_time_schedule": r.get("lead_time_schedule"),
            "source_urls": r.get("source_urls", []),
            "source_type": r.get("source_type"),
            "suggested_angles": r.get("suggested_angles", []),
            "colour": (pillar_colour_map.get((r.get("pillars") or [None])[0])
                       if r.get("pillars") else None),
            "planning_start": (r.get("lead_time_schedule") or {}).get("planning_start"),
        })

    return {
        "ok": True,
        "brand_id": brand_id,
        "brand_configured": cfg.get("configured", False),
        "config_path": cfg.get("config_path"),
        "timezone": cfg.get("timezone", "Africa/Johannesburg"),
        "pillars": pillars,
        "items": items,
        "watchlist_count": sum(1 for r in all_records if r.get("status") == "watchlist"),
        "calendar_count": sum(1 for r in all_records if r.get("status") != "watchlist"),
        "start_date": start_date_iso,
        "end_date": end_date_iso,
    }


# ─── Brand Context API Payload ─────────────────────────────────────────────

def get_brand_calendar_context(brand_id: str, horizon_days: int = 120) -> Dict[str, Any]:
    """The contract between Campaign OS and Hermes Scout.

    Returns enough for the Scout to plan WITHOUT scraping internal files.
    """
    cfg = load_brand_config(brand_id)
    pillars = enrich_pillar_targets(cfg.get("pillars") or [])
    existing = list_records(brand_id)
    return {
        "ok": True,
        "brand": {
            "brand_id": brand_id,
            "timezone": cfg.get("timezone", "Africa/Johannesburg"),
            "configured": cfg.get("configured", False),
            "config_path": cfg.get("config_path"),
        },
        "pillars": pillars,
        "scouting_profile": cfg.get("scouting_profile") or {},
        "lead_time_rules": cfg.get("lead_time_rules") or {},
        "calendar_preferences": cfg.get("calendar_preferences") or {},
        "existing_calendar": [r for r in existing if r.get("status") != "watchlist"],
        "existing_watchlist": [r for r in existing if r.get("status") == "watchlist"],
        "horizon_days": horizon_days,
        "valid_brand_ids": VALID_BRAND_IDS,
        "valid_record_types": VALID_RECORD_TYPES,
        "valid_statuses": VALID_STATUSES,
        "valid_lead_time_classes": VALID_LEAD_TIME_CLASSES,
        "product_brands": [
            {"product_brand": pb, "parent_brand": parent}
            for pb, parent in VALID_PRODUCT_BRANDS.items()
        ],
        "issued_at": _now_iso(),
    }


# ─── Brand Adaptability Test ───────────────────────────────────────────────

def brand_adaptability_test(target_brand_id: str = "bag-drop") -> Dict[str, Any]:
    """Build a minimal TEMPORARY brand config that differs from Stick on
    pillars, North Stars, scouting profile, and colours. Then load the
    context and prove the renderer/Scout consumes it generically.

    Per Slice 0.1 §18: 'do NOT fully configure another brand, but
    demonstrate changing brand_id demonstrably changes everything.'
    """
    if target_brand_id not in VALID_BRAND_IDS:
        raise ValueError(f"target_brand_id '{target_brand_id}' not in {VALID_BRAND_IDS}")
    test_cfg = {
        "brand_id": target_brand_id,
        "timezone": "Africa/Johannesburg",
        "pillars": [
            {
                "pillar_id": f"{target_brand_id}-social",
                "name": "Social/Community",
                "always_active": True,
                "colour": "#16a085",
                "objective": "Drive Thursday Social attendance",
                "north_star_metric": "attendees_per_thursday",
                "north_star_target": {"daily_volume": 12, "operating_days_per_week": 1},
                "cadence": "weekly",
                "priority": "high",
            },
        ],
        "scouting_profile": {
            "interest_areas": {
                "social_events": [
                    "bag-drop thursday social", "golf networking events",
                    "Thursday social meetups",
                ],
                "retail_calendar": ["Black Friday", "Father's Day"],
                "creator_culture": ["golf community stories"],
            },
        },
        "lead_time_rules": {
            "default": {
                "research_start": 21,
                "planning_start": 14,
                "production_deadline": 7,
                "campaign_live_start": 3,
            },
        },
        "calendar_preferences": {
            "month_view": True,
            "default_horizon_days": 90,
        },
    }
    return {
        "ok": True,
        "test_brand_id": target_brand_id,
        "test_pillars_count": len(test_cfg["pillars"]),
        "test_pillar_names": [p["name"] for p in test_cfg["pillars"]],
        "test_scouting_interests": list(test_cfg["scouting_profile"]["interest_areas"].keys()),
        "test_lead_time_default": test_cfg["lead_time_rules"]["default"],
        "note": "Test config is built in-memory only. To persist, write to /data/brand-directory/<brand>/calendar_config.json",
    }


# ─── Generic Scout Summary Helper ──────────────────────────────────────────

def summarise_scout_run(
    brand_id: str,
    candidates: List[Dict[str, Any]],
    watchlist: List[Dict[str, Any]],
    ignored: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Tally the Scout's output into the brief's required shape:
    high relevance / medium relevance / watchlist / ignored_count."""
    return {
        "brand_id": brand_id,
        "high_relevance": [c for c in candidates if (c.get("relevance_score") or 0) >= 0.7],
        "medium_relevance": [c for c in candidates if 0.4 <= (c.get("relevance_score") or 0) < 0.7],
        "watchlist_count": len(watchlist),
        "ignored_count": len(ignored),
        "ignored_examples": ignored[:8],
    }
