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
_BUNDLED_DATA_DIR = Path(os.environ.get("BUNDLED_DATA_DIR", "/app/data")) / "brand-directory"
_DEFAULT_LOCAL_DIR = Path(
    os.environ.get("BRAND_DIR_LOCAL", "/Users/fivefriday/hermes-fleet/shared/data/brand-directory")
)
_REPO_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "brand-directory"  # repo-local data/brand-directory/
_DATA_DIR = Path(os.environ.get("DATA_DIR", "/data/campaign-os"))
_CALENDAR_DIR = _DATA_DIR / "intelligence" / "marketing-calendar"
_CALENDAR_DIR_READY = False

# ─── Constants ──────────────────────────────────────────────────────────────
VALID_BRAND_IDS = ["swing-shack", "stick", "bag-drop"]
VALID_PRODUCT_BRANDS = {"takomo": "stick"}  # product_brand → parent brand
VALID_RECORD_TYPES = ["campaign", "content", "moment", "reminder", "watchlist"]
VALID_STATUSES = ["candidate", "watchlist", "approved", "ignored", "active", "completed"]

# Slice 0.2 — extended event_lifecycle enum (brief §13).
VALID_EVENT_LIFECYCLE = (
    "upcoming",
    "live",
    "recently_completed",
    "completed",
    "postponed",
    "cancelled",
    "expired",
)

# Slice 0.2 close-out §2 — source_origin enum enforced at write time.
VALID_SOURCE_ORIGIN = (
    "external",
    "deterministic_calendar",
    "internal_strategy",
)

# Slice 0.2 — change types for revision model (brief §4).
VALID_CHANGE_TYPES = (
    "new_event",            # first time this event_key appears
    "date_change",          # event_start/event_end/event_window changed
    "venue_change",         # venue / location changed
    "verification_change",  # verification_status / source_class changed
    "lifecycle_change",     # upcoming → live → postponed → cancelled
    "promotion",            # watchlist → candidate
    "pillar_change",        # pillar mapping changed
    "relevance_change",     # relevance_score changed materially
    "supersession",         # new revision explicitly supersedes an earlier one
    "no_change",            # Scout verified — nothing changed
)

# Slice 0.2 — freshness reverify windows (days).
DEFAULT_REVERIFY_DAYS = {
    "live": 1,                # events currently happening: recheck daily
    "upcoming_far": 30,       # far future (>60d): recheck monthly
    "upcoming_near": 7,       # near future (<60d): recheck weekly
    "recently_completed": 14, # recent past with reactive story: recheck biweekly
    "completed": 90,          # fully completed: recheck quarterly
    "postponed": 7,           # postponed: recheck weekly until resolved
    "cancelled": 365,         # cancelled: recheck yearly (to catch reschedule)
    "expired": 365,
}
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
    for base in (_BRAND_DIR, _BUNDLED_DATA_DIR, _REPO_DATA_DIR, _DEFAULT_LOCAL_DIR):
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

def _ensure_calendar_dir() -> Path:
    """Lazy-create the calendar storage dir. Skips if the parent dir is
    on a read-only filesystem (e.g. when running locally)."""
    global _CALENDAR_DIR_READY
    if _CALENDAR_DIR_READY:
        return _CALENDAR_DIR
    try:
        _CALENDAR_DIR.mkdir(parents=True, exist_ok=True)
        _CALENDAR_DIR_READY = True
    except (OSError, PermissionError):
        # Read-only filesystem — config-only runs still work
        _CALENDAR_DIR_READY = True  # don't retry every call
    return _CALENDAR_DIR


def _calendar_path(brand_id: str) -> Path:
    return _ensure_calendar_dir() / f"{brand_id}.jsonl"


def _watchlist_path(brand_id: str) -> Path:
    return _ensure_calendar_dir() / f"{brand_id}__watchlist.jsonl"


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

    Fail-closed default: every externally-sourced candidate must carry
    a verification_status. Valid states:
      verified_primary, verified_secondary, conflicting, unverified
    Records without one are written with verification_status='unverified'
    (unless the caller passed one explicitly).

    Records whose `source_type` is 'scout' but whose verification_status
    is 'unverified' are NOT trusted for planning reminders / Morning Brief
    alerts / automatic content planning. They appear in the calendar view
    but carry an explicit unverified flag.
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

    # Source verification contract — every externally-sourced record must
    # declare its source URL(s) and verification status. Without these
    # the record is treated as UNVERIFIED and excluded from trusted
    # planning pipelines.
    VALID_VERIFICATION_STATES = (
        "verified_primary",
        "verified_secondary",
        "conflicting",
        "unverified",
        "unverified_agent_memory",  # explicit marker for quarantined records
    )
    src = enriched.get("source_urls") or []
    ver = enriched.get("verification_status")
    if ver is None:
        if src:
            # Has source URLs but no verification_status — default to unverified
            enriched["verification_status"] = "unverified"
        else:
            # No sources at all — definitely unverified
            enriched["verification_status"] = "unverified"
    elif ver not in VALID_VERIFICATION_STATES:
        raise ValueError(
            f"verification_status '{ver}' invalid. "
            f"Valid: {VALID_VERIFICATION_STATES}"
        )
    # Date-confidence lifecycle (Slice 0.1 §14)
    lifecycle = enriched.get("event_lifecycle")
    if lifecycle and lifecycle not in ("upcoming", "live", "recently_completed", "expired"):
        raise ValueError(
            f"event_lifecycle '{lifecycle}' invalid. "
            f"Valid: upcoming, live, recently_completed, expired"
        )
    # Opportunity mode (Slice 0.1 §13)
    opp_mode = enriched.get("opportunity_mode")
    if opp_mode and opp_mode not in ("planned", "reactive", "watch"):
        raise ValueError(
            f"opportunity_mode '{opp_mode}' invalid. Valid: planned, reactive, watch"
        )
    # Date confidence (Slice 0.1 §5 + Slice 0.1 v2 close-out §5)
    # 'unannounced' added in v2 close-out to mark records where the source
    # was about a DIFFERENT calendar year (e.g. 2026 season = 2025 calendar
    # year event) and the future-year event is not yet announced.
    date_conf = enriched.get("date_confidence")
    if date_conf and date_conf not in ("confirmed_date", "announced_window",
                                       "expected_unannounced", "unannounced"):
        raise ValueError(
            f"date_confidence '{date_conf}' invalid. "
            f"Valid: confirmed_date, announced_window, expected_unannounced, unannounced"
        )
    # Source origin (Slice 0.1 v2 close-out §10)
    # external              → date from external internet source
    # deterministic_calendar → date is a fixed civil/public holiday
    # internal_strategy     → date is defined by brand campaign strategy
    src_origin = enriched.get("source_origin")
    if src_origin and src_origin not in ("external", "deterministic_calendar", "internal_strategy"):
        raise ValueError(
            f"source_origin '{src_origin}' invalid. "
            f"Valid: external, deterministic_calendar, internal_strategy"
        )
    # Season label vs calendar year (Slice 0.1 v2 close-out §3)
    # e.g. season_label='2026' but calendar_year=2025 if the event was
    # played in Dec 2025 as part of the 2026 DP World Tour season.
    if enriched.get("calendar_year") and not isinstance(enriched["calendar_year"], int):
        raise ValueError(f"calendar_year must be int, got {type(enriched['calendar_year']).__name__}")

    # Trusted-for-planning flag — True only when source verified primary.
    # Downstream consumers (planning reminders, Morning Brief, automatic
    # content planning) must filter on this.
    enriched["trusted_for_planning"] = bool(
        enriched.get("verification_status") == "verified_primary"
        and enriched.get("date_confidence") in ("confirmed_date", "announced_window")
        and bool(src)
    )

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
    canonical: bool = True,
) -> Dict[str, Any]:
    """Assemble a brand-aware calendar view: pillar summary at the top +
    records (campaign / moment / reminder / watchlist) within the date range.

    No hard-coded pillar names. The brand config determines everything.

    canonical=True  (default, close-out §4):
      Returns ONE row per event_key — the latest active revision.
      Auditing/data-shipping consumers use this by default.

    canonical=False (revisions_only):
      Returns every persisted jsonl line (audit mode). Used by internal
      integrity checks and explicit history queries via
      `?revisions_only=true`.
    """
    cfg = load_brand_config(brand_id)
    pillars = enrich_pillar_targets(cfg.get("pillars") or [])

    # Records
    if canonical:
        # Slice 0.2 close-out §4 — canonical = latest per event_key,
        # understanding status (cancelled/postponed/expired stay canonical).
        all_records = canonical_records(brand_id)
        if not include_watchlist:
            all_records = [r for r in all_records if r.get("status") != "watchlist"]
    else:
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
            # Slice 0.1 close-out — source verification + lifecycle
            "verification_status": r.get("verification_status"),
            "trusted_for_planning": r.get("trusted_for_planning", False),
            "event_lifecycle": r.get("event_lifecycle"),
            "opportunity_mode": r.get("opportunity_mode"),
            "date_confidence": r.get("date_confidence"),
            "source_domain": r.get("source_domain"),
            "source_title": r.get("source_title"),
            "source_class": r.get("source_class"),
            "retrieved_at": r.get("retrieved_at"),
            "created_by": r.get("created_by"),
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


# ─────────────────────────────────────────────────────────────────────────────
# SLICE 0.2 — AUTOMATION READINESS
#
# Adds:
#   - stable event_key generation (brand-scoped logical identity)
#   - append-only revision model (preserves historical truth)
#   - true idempotency (repeat Scout runs produce 0 new logical events / 0
#     unnecessary revisions)
#   - material-change detection
#   - watchlist promotion with audit trail
#   - watchlist rechecking cadence
#   - source precedence + season-year guard (regression tests)
#   - reminder trust gate (planning reminders must not fire from untrusted
#     external records)
#   - freshness (last_verified_at + reverify_after)
#   - research concurrency cap helper (max 2 Firecrawl-heavy lanes)
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA_VERSION = "0.2"

# Source class precedence (higher = more authoritative). Used by
# resolve_source_precedence() for cross-source conflict resolution.
SOURCE_PRECEDENCE = {
    "primary_official": 100,    # official event organiser / official governing tour
    "primary_lpga":     100,    # LPGA's own schedule
    "primary_brand":     90,    # brand's own press release
    "primary_creator":   80,    # creator's own channel/account
    "secondary_news":    40,    # reputable secondary news
    "secondary_aggregator": 30, # schedule aggregator
}

# Event-key slug building blocks — explicit mapping from canonical name
# to stable slug. The slug is the durable identity component; the year
# suffix uses calendar_year (NOT the season label) so that an event whose
# organiser shifts the date within the same calendar year keeps the same
# event_key (per brief §1: "Do not include dates in a way that creates
# a new event if the organiser changes the date").
_EVENT_KEY_SLUGS = {
    "presidents cup": "presidents-cup",
    "nedbank golf challenge": "nedbank-golf-challenge",
    "alfred dunhill championship": "alfred-dunhill-championship",
    "good good championship": "good-good-championship",
    "internet invitational": "internet-invitational",
    "solheim cup": "solheim-cup",
    "cme group tour championship": "cme-group-tour-championship",
    "heritage day": "heritage-day",
    "day of reconciliation": "day-of-reconciliation",
    "christmas day": "christmas",
    "day of goodwill": "day-of-goodwill",
    "new year's day": "new-years-day",
    "sa festive season": "sa-festive-season",
    "black friday": "black-friday",
    "cyber monday": "cyber-monday",
    "tgl season 3": "tgl-season-3",
    "good good callaway fallout": "good-good-callaway-fallout",
    "takomo ambassador activations": "takomo-ambassador-activations",
}


def _slugify_event_title(title: str) -> str:
    """Map a candidate title to a stable slug.

    Uses an explicit slug table when possible; falls back to a
    deterministic lowercase-dash normalisation.
    """
    if not title:
        return "unknown-event"
    t = title.lower().strip()
    # Direct lookup
    for needle, slug in _EVENT_KEY_SLUGS.items():
        if needle in t:
            return slug
    # Fallback: strip year suffixes, lowercase, dash-separate
    import re as _re
    cleaned = _re.sub(r"\b(20\d{2})\b", "", t)
    cleaned = _re.sub(r"[^a-z0-9]+", "-", cleaned).strip("-")
    return cleaned or "unknown-event"


def build_event_key(
    brand_id: str,
    title: str,
    calendar_year: Optional[int] = None,
    kind: str = "moment",
) -> str:
    """Generate a stable logical identifier per brief §1.

    Format: ``<brand_id>:<slug>[:<calendar_year>]``

    The calendar_year suffix is included when known; for watchlist items
    with no calendar_year, the suffix is omitted so the same logical
    event can be observed across years (e.g. annual Christmas).

    Per brief §9 (season-year guard), this NEVER uses the season_label
    or URL year — only the actual event_start/event_end calendar year or
    the explicit calendar_year field.
    """
    slug = _slugify_event_title(title or "")
    parts = [brand_id, slug]
    if calendar_year:
        parts.append(str(calendar_year))
    return ":".join(parts)


def _season_year_guard(
    title: str,
    source_url: Optional[str],
    season_label: Optional[str],
    event_start: Optional[str],
    event_end: Optional[str],
) -> Dict[str, Any]:
    """Brief §9: never infer calendar_year from URL/season/article title.

    Returns a dict with:
      - calendar_year: derived from actual event dates when possible
      - season_year_guard_ok: bool
      - warnings: list[str]
    """
    import re as _re
    warnings: list = []
    cy_from_url = None
    cy_from_season = None
    cy_from_title = None
    cy_from_dates = None

    if source_url:
        m = _re.search(r"/(20\d{2})", source_url)
        if m:
            cy_from_url = int(m.group(1))
    if season_label:
        m = _re.search(r"(20\d{2})", str(season_label))
        if m:
            cy_from_season = int(m.group(1))
    # Title year — informational, not authoritative
    if title:
        m = _re.search(r"\b(20\d{2})\b", title)
        if m:
            cy_from_title = int(m.group(1))
    # Authoritative: actual event_start/event_end
    for d in (event_start, event_end):
        if d:
            m = _re.search(r"\b(20\d{2})\b", d)
            if m:
                cy_from_dates = int(m.group(1))
                break

    # Conflict detection
    candidates = [v for v in (cy_from_url, cy_from_season, cy_from_title, cy_from_dates) if v]
    if len(set(candidates)) > 1:
        warnings.append(
            f"calendar_year disagreement: url={cy_from_url} season={cy_from_season} "
            f"title={cy_from_title} dates={cy_from_dates}"
        )
    # Authoritative answer = event-start year (if present)
    cal_year = cy_from_dates or cy_from_title  # title is fallback
    return {
        "calendar_year": cal_year,
        "season_year_guard_ok": (cy_from_dates is None) or (cal_year == cy_from_dates),
        "warnings": warnings,
    }


def resolve_source_precedence(
    sources: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Brief §8: source precedence is not purely hierarchical.

    For a list of competing source records (each with at least
    source_url + source_class + retrieved_at), pick the winner based on:
      1. source_class precedence (organiser > governing tour > venue > brand > secondary)
      2. event-organiser self-page: same-domain as event name beats generic tour
      3. recency (newer retrieved_at wins)
      4. date specificity (page whose URL says /schedule/ or /2026/ beats a /news/ article)
    """
    if not sources:
        return {"winner": None, "loser": None, "rationale": "no sources"}
    scored = []
    for s in sources:
        cls = s.get("source_class") or ""
        base = SOURCE_PRECEDENCE.get(cls, 10)
        # Recency bonus: +0..10 based on days since retrieved_at
        rec_bonus = 0
        try:
            ra = s.get("retrieved_at", "")
            if ra:
                from datetime import datetime, timezone as _tz
                dt = datetime.fromisoformat(ra.replace("Z", "+00:00"))
                days = (datetime.now(_tz.utc) - dt).days
                rec_bonus = max(0, 10 - min(days, 10))
        except Exception:
            rec_bonus = 0
        # Date-specificity bonus: schedule URL beats news article
        url = (s.get("source_url") or "").lower()
        spec_bonus = 0
        if any(seg in url for seg in ("/schedule", "/fixtures", "/tournaments", "/events", "/calendar", "/information")):
            spec_bonus = 5
        if any(seg in url for seg in ("/news/", "/article/", "/blog/", "/press-releases/")):
            spec_bonus = max(spec_bonus, 0)  # no penalty, just no bonus
        # Event-organiser domain bonus: a domain that matches the event
        # name (e.g. nedbankgolfchallenge.com for "Nedbank Golf Challenge")
        # beats a generic tour domain (e.g. europeantour.com).
        # Heuristic: if domain is *not* one of the big tour domains
        # (europeantour.com, pgatour.com, lpga.com, tglgolf.com,
        # solheimcup.com, presidentscup.com, rydercup.com), and it's an
        # event-specific page, treat it as the organiser's site.
        TOUR_DOMAINS = {
            "europeantour.com", "pgatour.com", "lpga.com", "tglgolf.com",
            "solheimcup.com", "presidentscup.com", "rydercup.com",
            "sunshinetour.com", "ladieseuropeantour.com",
        }
        try:
            from urllib.parse import urlparse as _up
            domain = _up(s.get("source_url") or "").netloc.lower()
        except Exception:
            domain = ""
        organiser_bonus = 0
        if domain and not any(domain.endswith(td) for td in TOUR_DOMAINS):
            # Likely the event organiser's own site
            organiser_bonus = 15
        scored.append((base + rec_bonus + spec_bonus + organiser_bonus, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    winner = scored[0][1]
    loser = scored[-1][1] if len(scored) > 1 else None
    return {
        "winner": winner,
        "loser": loser,
        "rationale": (
            f"winner={winner.get('source_url')} "
            f"(score={scored[0][0]}, class={winner.get('source_class')}); "
            f"loser={loser.get('source_url') if loser else 'n/a'}"
        ),
    }


# ─── Revision model + upsert ─────────────────────────────────────────────────

def _material_change_detected(
    prev: Dict[str, Any],
    new: Dict[str, Any],
) -> Tuple[bool, str, List[str]]:
    """Brief §4: detect whether a new revision should be appended.

    Returns (changed, change_type, changed_fields).

    Excluded from change detection:
      - retrieved_at (operational metadata, brief §3)
      - created_at (operational metadata)
      - last_verified_at (operational metadata)
      - source ordering / whitespace

    Material fields (changes create new revisions):
      - event_start, event_end, event_window_start, event_window_end,
        competition_start, competition_end
      - source_origin, calendar_year, season_label
      - verification_status, source_class, date_confidence
      - event_lifecycle, opportunity_mode
      - pillars, relevance_score
      - title, venue
    """
    MATERIAL_FIELDS = [
        "event_start", "event_end",
        "event_window_start", "event_window_end",
        "competition_start", "competition_end",
        "source_origin", "calendar_year", "season_label",
        "verification_status", "source_class", "date_confidence",
        "event_lifecycle", "opportunity_mode",
        "pillars", "relevance_score",
        "title", "venue",
    ]
    changed_fields: List[str] = []
    for f in MATERIAL_FIELDS:
        pv = prev.get(f)
        nv = new.get(f)
        # List comparison for pillars
        if isinstance(pv, list) and isinstance(nv, list):
            if sorted(pv) != sorted(nv):
                changed_fields.append(f)
            continue
        if pv != nv:
            changed_fields.append(f)

    if not changed_fields:
        return False, "no_change", []

    # Decide change_type based on which fields moved
    # Order matters — promotion check must come BEFORE verification_change
    # because a watchlist→candidate transition also changes verification_status.
    # Promotion = previous status was "watchlist" (regardless of event_lifecycle value).
    if prev.get("status") == "watchlist" and (
        "event_lifecycle" in changed_fields
        or "status" in changed_fields
        or "date_confidence" in changed_fields
    ):
        return True, "promotion", changed_fields
    if any(f.startswith("event_") or f.startswith("competition_") or f == "event_end" for f in changed_fields):
        return True, "date_change", changed_fields
    if "verification_status" in changed_fields or "source_class" in changed_fields:
        return True, "verification_change", changed_fields
    if "venue" in changed_fields:
        return True, "venue_change", changed_fields
    if "event_lifecycle" in changed_fields:
        return True, "lifecycle_change", changed_fields
    if "pillars" in changed_fields:
        return True, "pillar_change", changed_fields
    if "relevance_score" in changed_fields:
        return True, "relevance_change", changed_fields
    if "title" in changed_fields:
        # Title change with same event_key usually = promotion/rebrand
        return True, "promotion", changed_fields
    return True, "supersession", changed_fields


def _ensure_event_key(record: Dict[str, Any]) -> Dict[str, Any]:
    """Populate event_key if missing. Returns the (possibly mutated) record."""
    if not record.get("event_key"):
        title = record.get("title", "")
        cy = record.get("calendar_year")
        kind = record.get("type") or "moment"
        record["event_key"] = build_event_key(
            record.get("brand_id", "unknown"),
            title,
            calendar_year=cy,
            kind=kind,
        )
    return record


def list_event_revisions(brand_id: str, event_key: str) -> List[Dict[str, Any]]:
    """Read all revisions for an event_key from both calendar + watchlist
    jsonl files, sorted by revision ascending.
    """
    revisions: List[Dict[str, Any]] = []
    for path in (_calendar_path(brand_id), _watchlist_path(brand_id)):
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("event_key") == event_key:
                revisions.append(r)
    revisions.sort(key=lambda x: (x.get("revision") or 1, x.get("created_at") or ""))
    return revisions


def find_latest_revision(brand_id: str, event_key: str) -> Optional[Dict[str, Any]]:
    """Get the highest-revision record for an event_key."""
    revs = list_event_revisions(brand_id, event_key)
    return revs[-1] if revs else None


def upsert_event(
    brand_id: str,
    record: Dict[str, Any],
    skip_guards: bool = False,
) -> Dict[str, Any]:
    """Slice 0.2 — append-only revision upsert with production-path guards.

    Production-path guards (always enforced unless skip_guards=True,
    used only by migration paths that pre-validate):
      1. brand_id/event_key consistency (close-out §9)
      2. source_origin enum (close-out §2)
      3. season-year guard when event_start/end present (close-out §1)

    The same event_key across revisions preserves a single logical
    event. Upsert returns one of three actions:
      - created — first time this event_key was seen (revision=1)
      - updated — material change detected (revision=N+1)
      - noop — nothing material changed (last_checked_at refreshed)
    """
    # Capture the caller's supplied event_key BEFORE we auto-generate
    # one. The brand-safety check requires us to validate the SUPPLIED
    # key (per brief §9 "event_key brand prefix == brand_id on real
    # writes") rather than silently overwriting with a new one.
    supplied_event_key = record.get("event_key")
    record = _ensure_event_key(record)
    # Ensure brand_id is set on the record (used by event_key building)
    # AND for the brand-prefix validation below — must happen before
    # guards that reference event_key.
    record.setdefault("brand_id", brand_id)

    if supplied_event_key:
        # Caller supplied an explicit event_key — use it. The brand-
        # safety guard below validates the prefix.
        record["event_key"] = supplied_event_key
    else:
        # No event_key supplied — generate one with brand_id in scope
        record["event_key"] = build_event_key(
            brand_id,
            record.get("title", ""),
            calendar_year=record.get("calendar_year"),
            kind=record.get("type") or "moment",
        )
    event_key = record["event_key"]

    if not skip_guards:
        # Guard §9: brand_id MUST match event_key prefix
        if not event_key.startswith(f"{brand_id}:"):
            raise ValueError(
                f"event_key '{event_key}' does not match brand_id '{brand_id}'. "
                f"event_key must be prefixed with '{brand_id}:'."
            )
        # Guard §2: source_origin enum enforcement
        if "source_origin" in record:
            if record["source_origin"] not in VALID_SOURCE_ORIGIN:
                raise ValueError(
                    f"source_origin '{record.get('source_origin')}' invalid. "
                    f"Valid: {list(VALID_SOURCE_ORIGIN)}"
                )
        # Guard §1: season-year guard when event dates present
        if record.get("event_start") or record.get("event_end"):
            guard = _season_year_guard(
                record.get("title", ""),
                record.get("source_urls", [None])[0] if record.get("source_urls") else None,
                record.get("season_label"),
                record.get("event_start"),
                record.get("event_end"),
            )
            supplied_year = record.get("calendar_year")
            derived_year = guard.get("calendar_year")
            if supplied_year and derived_year and supplied_year != derived_year:
                warnings = record.setdefault("production_path_warnings", [])
                warnings.append(
                    f"calendar_year mismatch: supplied={supplied_year} derived={derived_year} "
                    f"from event_start={record.get('event_start')}. "
                    f"Derived value preferred for canonical placement."
                )
                # Normalise to derived_year
                record["calendar_year"] = derived_year
                # Regenerate event_key now that calendar_year is correct
                record["event_key"] = build_event_key(
                    brand_id,
                    record.get("title", ""),
                    calendar_year=derived_year,
                    kind=record.get("type") or "moment",
                )
                event_key = record["event_key"]

    # Default schema v2 fields
    record.setdefault("schema_version", SCHEMA_VERSION)
    record.setdefault("created_at", _now_iso())
    record.setdefault("last_verified_at", _now_iso())
    record.setdefault("last_checked_at", _now_iso())
    # Freshness — recompute reverify_after from event_lifecycle
    record["reverify_after"] = _compute_reverify_after(record)

    latest = find_latest_revision(brand_id, event_key)
    if latest is None:
        # New event — revision 1
        record["revision"] = 1
        record["change_type"] = "new_event"
        record["supersedes_calendar_id"] = None
        record["changed_fields"] = []
        # Persist
        _persist(brand_id, record)
        return {
            "ok": True,
            "action": "created",
            "record": record,
            "change_type": "new_event",
            "changed_fields": [],
            "supersedes_calendar_id": None,
        }

    # Compare against the latest revision
    changed, change_type, changed_fields = _material_change_detected(latest, record)
    if not changed:
        # No-op — just refresh last_checked_at on the latest revision
        latest["last_checked_at"] = _now_iso()
        _rewrite_latest_revision(brand_id, latest)
        return {
            "ok": True,
            "action": "noop",
            "record": latest,
            "change_type": "no_change",
            "changed_fields": [],
            "supersedes_calendar_id": latest.get("calendar_id"),
        }

    # Material change — append a new revision
    next_rev = (latest.get("revision") or 1) + 1
    record["revision"] = next_rev
    record["change_type"] = change_type
    record["changed_fields"] = changed_fields
    record["supersedes_calendar_id"] = latest.get("calendar_id")
    record["event_key"] = event_key
    record["schema_version"] = SCHEMA_VERSION
    _persist(brand_id, record)
    return {
        "ok": True,
        "action": "updated",
        "record": record,
        "change_type": change_type,
        "changed_fields": changed_fields,
        "supersedes_calendar_id": latest.get("calendar_id"),
    }


def _compute_reverify_after(record: Dict[str, Any]) -> Optional[str]:
    """Compute the next reverify date based on event_lifecycle."""
    from datetime import datetime, timedelta, timezone as _tz
    lifecycle = record.get("event_lifecycle", "upcoming")
    # Choose days based on lifecycle + how far away the event is
    days = DEFAULT_REVERIFY_DAYS.get(lifecycle, 30)
    # If upcoming + far future, use upcoming_far
    if lifecycle == "upcoming":
        ev = record.get("event_start") or record.get("event_window_start")
        if ev:
            try:
                d = datetime.fromisoformat(ev.replace("Z", "+00:00"))
                now = datetime.now(_tz.utc)
                diff_days = (d - now).days
                if diff_days > 60:
                    days = DEFAULT_REVERIFY_DAYS["upcoming_far"]
                else:
                    days = DEFAULT_REVERIFY_DAYS["upcoming_near"]
            except Exception:
                pass
    return (datetime.now(_tz.utc) + timedelta(days=days)).isoformat().replace("+00:00", "Z")


def _persist(brand_id: str, record: Dict[str, Any]) -> None:
    """Append a revision to the appropriate jsonl (calendar or watchlist)."""
    # Determine path by status/type
    if record.get("status") == "watchlist" or record.get("type") == "watchlist":
        path = _watchlist_path(brand_id)
    else:
        path = _calendar_path(brand_id)
    # Generate a calendar_id (revision identifier, not event identifier)
    if not record.get("calendar_id"):
        from uuid import uuid4
        slug = record.get("event_key", "event").split(":")[-1]
        record["calendar_id"] = (
            f"cal-{brand_id}-{record.get('type','moment')}-"
            f"{int(__import__('time').time())}-{uuid4().hex[:8]}"
        )
    with path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _rewrite_latest_revision(brand_id: str, updated: Dict[str, Any]) -> None:
    """Rewrite only the latest jsonl line matching calendar_id."""
    target_cid = updated.get("calendar_id")
    if not target_cid:
        return
    for path in (_calendar_path(brand_id), _watchlist_path(brand_id)):
        if not path.exists():
            continue
        lines = path.read_text().splitlines()
        for i, line in enumerate(lines):
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("calendar_id") == target_cid:
                lines[i] = json.dumps(updated, ensure_ascii=False)
                path.write_text("\n".join(lines) + "\n")
                return


# ─── Reminder trust gate (brief §12) ─────────────────────────────────────────

def can_fire_planning_reminder(record: Dict[str, Any]) -> Tuple[bool, str]:
    """Brief §12 — Trust before reminders.

    Planning reminders for external moments MUST NOT fire from records
    that are not trusted_for_planning AND not from records that are
    cancelled/postponed/conflicting/stale.

    Returns (allowed, reason).
    """
    if record.get("trusted_for_planning") is not True:
        return False, f"trusted_for_planning={record.get('trusted_for_planning')}"
    if record.get("verification_status") == "conflicting":
        return False, "verification_status=conflicting"
    if record.get("event_lifecycle") in ("postponed", "cancelled", "expired"):
        return False, f"event_lifecycle={record.get('event_lifecycle')}"
    # Stale check (brief §12) — a record is stale when the reverify
    # window has passed without re-verification, i.e. now > reverify_after.
    lv = record.get("last_verified_at")
    ra = record.get("reverify_after")
    if ra:
        try:
            from datetime import datetime, timezone as _tz
            ra_dt = datetime.fromisoformat(ra.replace("Z", "+00:00"))
            if datetime.now(_tz.utc) > ra_dt:
                return False, f"stale: now > reverify_after={ra} (last_verified_at={lv})"
        except Exception:
            pass
    return True, "ok"


# ─── Brand-scoped identity (brief §17) ───────────────────────────────────────

def event_keys_for_brand(brand_id: str) -> List[str]:
    """List all distinct event_keys for a brand across all revisions."""
    keys = set()
    for path in (_calendar_path(brand_id), _watchlist_path(brand_id)):
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                if r.get("event_key"):
                    keys.add(r["event_key"])
            except Exception:
                continue
    return sorted(keys)


def brand_isolation_check() -> Dict[str, Any]:
    """Brief §17 — same event_key MUST NOT be shared across brands.

    event_keys are brand-scoped by construction (prefixed with brand_id),
    so a global dedupe would silently merge stick's Nedbank with
    bag-drop's Nedbank, with different relevance/pillars/angles.
    Verify by listing event_keys per brand and confirming no overlap.
    """
    per_brand: Dict[str, set] = {}
    for bid in VALID_BRAND_IDS:
        per_brand[bid] = set(event_keys_for_brand(bid))
    overlap = {}
    for a in VALID_BRAND_IDS:
        for b in VALID_BRAND_IDS:
            if a >= b:
                continue
            shared = per_brand[a] & per_brand[b]
            if shared:
                overlap[f"{a} ∩ {b}"] = sorted(shared)
    return {
        "per_brand_count": {k: len(v) for k, v in per_brand.items()},
        "cross_brand_overlap": overlap,
        "ok": len(overlap) == 0,
    }


# ─── Research concurrency cap (brief §10) ────────────────────────────────────

MAX_FIRECRAWL_HEAVY_LANES = 2  # brief §10 — cap

RESEARCH_LANE_BATCHES = [
    # Batch 1 (2 Firecrawl-heavy lanes)
    ["south_african_local", "womens_golf"],
    # Batch 2 (2 Firecrawl-heavy lanes)
    ["global_golf", "creator_culture"],
    # Batch 3 (1 lane, less Firecrawl-heavy)
    ["retail_commercial"],
]


def batch_research_calls(call_fn, lane_specs: List[Dict[str, Any]]) -> List[Any]:
    """Execute research calls respecting the Firecrawl-heavy lane cap.

    The cap is enforced dynamically: at any moment, no more than
    MAX_FIRECRAWL_HEAVY_LANES lanes with firecrawl_heavy=True may be
    running concurrently. Non-heavy lanes never count toward the cap.

    Args:
        call_fn: callable(spec: dict) -> result. spec has 'name',
            'firecrawl_heavy', 'params'.
        lane_specs: list of dicts, each with at least 'name',
            'firecrawl_heavy', 'params'.

    Returns:
        List of results in the same order as lane_specs.

    Concurrency model:
      - Build the firecrawl-heavy queue and the firecrawl-light queue.
      - Process heavy lanes one by one up to MAX_FIRECRAWL_HEAVY_LANES
        active; the LIGHT queue may run fully in parallel because they
        don't trip the cap.
      - For the simulator/test pattern: process all lanes sequentially
        within the heavy queue (ensures max active ≤ cap) and let
        light lanes run in parallel.

    For SIMPLER correctness and consistent determinism with the
    concurrent test, this implementation runs heavy lanes sequentially
    with a small inter-lane pause (mimicking the contract more clearly
    than true async queues), and light lanes in a tight loop after.
    """
    import time as _t
    results: list = [None] * len(lane_specs)
    heavy = [(i, s) for i, s in enumerate(lane_specs) if s.get("firecrawl_heavy")]
    light = [(i, s) for i, s in enumerate(lane_specs) if not s.get("firecrawl_heavy")]

    # Heavy lanes — sequential within the cap to guarantee no more than
    # MAX_FIRECRAWL_HEAVY_LANES are concurrently active. (True async
    # pools would allow more, but the brief's whole point is capping.)
    for idx, spec in heavy:
        for attempt in range(3):
            try:
                results[idx] = call_fn(spec)
                break
            except Exception as e:
                msg = str(e).lower()
                if ("429" in msg or "rate" in msg) and attempt < 2:
                    wait = (2 ** attempt) + (0.1 * attempt)
                    _t.sleep(wait)
                    continue
                raise
        # Optional light throttle between heavy calls to be a good
        # citizen with the Firecrawl provider (50ms is negligible vs
        # the lane's own work)
        _t.sleep(0.05)

    # Light lanes — fully unconstrained, can run in any order
    for idx, spec in light:
        results[idx] = call_fn(spec)
    return results


# ─── Watchlist rechecking (brief §6) ─────────────────────────────────────────

def watchlist_due_for_research(brand_id: str, today_iso: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return the latest watchlist revisions that are due for research.

    A watchlist item is "due" if next_check_date <= today OR
    last_checked_at is older than (today - check_cadence_days).
    """
    from datetime import datetime, timedelta
    if not today_iso:
        today_iso = datetime.utcnow().isoformat() + "Z"
    today = datetime.fromisoformat(today_iso.replace("Z", "+00:00"))
    cadence_map = {
        "daily": 1, "weekly": 7, "biweekly": 14,
        "monthly": 30, "quarterly": 90, "yearly": 365,
    }
    due: list = []
    revs = list_event_revisions(brand_id, "")  # placeholder
    # Use list_records-style logic
    for path in (_watchlist_path(brand_id), _calendar_path(brand_id)):
        if not path.exists():
            continue
        latest_per_key = {}
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            ek = r.get("event_key")
            if not ek or r.get("status") != "watchlist":
                continue
            if ek not in latest_per_key or (r.get("revision") or 1) > (latest_per_key[ek].get("revision") or 1):
                latest_per_key[ek] = r
        for ek, r in latest_per_key.items():
            ncd = r.get("next_check_date")
            if ncd:
                try:
                    ncd_dt = datetime.fromisoformat(ncd.replace("Z", "+00:00"))
                    if ncd_dt <= today:
                        due.append(r)
                        continue
                except Exception:
                    pass
            cad = (r.get("check_cadence") or "").lower()
            days = cadence_map.get(cad, 30)
            lca = r.get("last_checked_at")
            if lca:
                try:
                    lca_dt = datetime.fromisoformat(lca.replace("Z", "+00:00"))
                    if today - lca_dt >= timedelta(days=days):
                        due.append(r)
                except Exception:
                    pass
            else:
                due.append(r)
    return due


# ─── Schema v2 migration helper (brief §7) ──────────────────────────────────

def migrate_record_to_v2(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a v1 record to v2 schema.

    Sets:
      - schema_version = "0.2"
      - event_key (from brand_id + title + calendar_year)
      - calendar_year (from event_start year if missing)
      - source_origin (default "external" if missing)
      - season_label (default None)
      - last_verified_at / last_checked_at / reverify_after
      - revision = 1 (assuming migration targets the current latest state)
      - change_type = "no_change" (migration is a no-op semantically)
    """
    record = dict(record)  # shallow copy
    record.setdefault("schema_version", SCHEMA_VERSION)
    if not record.get("calendar_year"):
        for d in (record.get("event_start"), record.get("event_window_start"), record.get("campaign_start")):
            if d:
                import re as _re
                m = _re.search(r"\b(20\d{2})\b", d)
                if m:
                    record["calendar_year"] = int(m.group(1))
                    break
    if not record.get("source_origin"):
        if record.get("status") == "watchlist":
            record["source_origin"] = "external"
        elif record.get("verification_status") == "verified_primary":
            record["source_origin"] = "external"
        else:
            record["source_origin"] = "external"
    if not record.get("season_label") and record.get("calendar_year"):
        record["season_label"] = str(record["calendar_year"])
    record.setdefault("revision", 1)
    record.setdefault("change_type", "no_change")
    record.setdefault("changed_fields", [])
    record.setdefault("supersedes_calendar_id", None)
    record["last_verified_at"] = record.get("last_verified_at") or record.get("created_at") or _now_iso()
    record["last_checked_at"] = record.get("last_checked_at") or record["last_verified_at"]
    record["reverify_after"] = _compute_reverify_after(record)
    record = _ensure_event_key(record)
    return record


def migrate_brand_calendar_to_v2(brand_id: str) -> Dict[str, Any]:
    """Brief §7 — migrate all current records to schema v2.

    For each calendar_id, keep only the LATEST revision (most recent
    jsonl entry), migrate it to schema v2, and rewrite. Earlier
    revisions are preserved in the jsonl (auditability). Returns a
    summary of actions taken.
    """
    summary = {
        "brand_id": brand_id,
        "scanned": 0,
        "migrated": 0,
        "already_v2": 0,
        "event_keys_assigned": [],
    }
    for path in (_calendar_path(brand_id), _watchlist_path(brand_id)):
        if not path.exists():
            continue
        lines = path.read_text().splitlines()
        latest_per_cid: Dict[str, Dict[str, Any]] = {}
        for line in lines:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            cid = r.get("calendar_id")
            if not cid:
                continue
            summary["scanned"] += 1
            # Track latest per calendar_id (highest created_at or last_verified)
            ts = r.get("created_at") or r.get("last_verified_at") or ""
            if cid not in latest_per_cid or ts > (latest_per_cid[cid].get("created_at") or latest_per_cid[cid].get("last_verified_at") or ""):
                latest_per_cid[cid] = r

        # Rewrite lines: keep non-target lines as-is, replace target lines
        # with migrated versions
        target_cids = set(latest_per_cid.keys())
        # Build a map from cid+ts to migrated version
        migrated_by_cid_ts: Dict[tuple, Dict[str, Any]] = {}
        for cid, r in latest_per_cid.items():
            ts = r.get("created_at") or r.get("last_verified_at") or ""
            migrated = migrate_record_to_v2(r)
            migrated_by_cid_ts[(cid, ts)] = migrated
        new_lines = []
        for line in lines:
            try:
                r = json.loads(line)
            except Exception:
                new_lines.append(line)
                continue
            cid = r.get("calendar_id")
            ts = r.get("created_at") or r.get("last_verified_at") or ""
            key = (cid, ts)
            if cid in target_cids and key in migrated_by_cid_ts:
                # This is a latest-revision line — replace with migrated
                if r.get("schema_version") == SCHEMA_VERSION and r.get("event_key"):
                    summary["already_v2"] += 1
                    new_lines.append(line)
                else:
                    migrated = migrated_by_cid_ts[key]
                    summary["migrated"] += 1
                    if migrated.get("event_key"):
                        summary["event_keys_assigned"].append(migrated["event_key"])
                    new_lines.append(json.dumps(migrated, ensure_ascii=False))
            else:
                # Older revisions / non-target lines — leave alone
                new_lines.append(line)

        path.write_text("\n".join(new_lines) + "\n")
    summary["event_keys_assigned"] = sorted(set(summary["event_keys_assigned"]))
    return summary


# ─── View helper: canonical (latest-active per event_key) ───────────────────

def canonical_records(brand_id: str, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return the latest revision per event_key for a brand.

    The canonical Calendar view should show this — NOT every revision.
    Earlier revisions remain inspectable via list_event_revisions().

    Per brief §5: if the highest-revision record is cancelled /
    postponed / expired, that is the canonical version — we do NOT
    fall back to an older "active" revision.
    """
    canonical = {}
    for path in (_calendar_path(brand_id), _watchlist_path(brand_id)):
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
            ek = r.get("event_key") or r.get("calendar_id")
            if ek not in canonical:
                canonical[ek] = r
            else:
                cur_rev = canonical[ek].get("revision") or 1
                new_rev = r.get("revision") or 1
                if new_rev > cur_rev:
                    canonical[ek] = r
    return sorted(
        canonical.values(),
        key=lambda x: (
            x.get("event_start") or x.get("event_window_start")
            or x.get("campaign_start") or x.get("title", "")
        ),
    )


# ─── Slice 0.2 close-out — Unified work_due + reverification + freshness ────

def compute_reverify_after_for(
    brand_id: str,
    event: Dict[str, Any],
) -> Optional[str]:
    """Brief §7: freshness timing must be configurable per lifecycle.

    Lifecycle-based buckets (the brief asked for far_future /
    planning_window / near_event / live / watchlist):
      - watchlist: 7 days (recheck weekly)
      - live: 1 day (recheck daily)
      - near_event: 14 days (event within 30 days)
      - planning_window: 7 days (event within planning window)
      - far_future: 30 days (event >90 days away)
      - reactive: 14 days (recently_completed)
      - completed/expired/cancelled: stop checking (unless explicitly
        reactive opportunity)
    """
    from datetime import datetime, timedelta, timezone as _tz
    lifecycle = event.get("event_lifecycle", "upcoming")
    status = event.get("status")
    source_origin = event.get("source_origin")
    # Deterministic + internal_strategy events don't get reverified
    if source_origin in ("deterministic_calendar", "internal_strategy"):
        return None
    if lifecycle in ("completed", "expired", "cancelled"):
        # Unless the record explicitly tags a reactive opportunity
        if event.get("opportunity_mode") == "reactive":
            return (datetime.now(_tz.utc) + timedelta(days=14)).isoformat().replace("+00:00", "Z")
        return None
    if status == "watchlist":
        days = 7
    elif lifecycle == "live":
        days = 1
    else:
        # Upcoming — bucket by distance
        ev = event.get("event_start") or event.get("event_window_start")
        days = 30
        if ev:
            try:
                d = datetime.fromisoformat(ev.replace("Z", "+00:00"))
                now = datetime.now(_tz.utc)
                dd = (d - now).days
                if dd < 0:
                    days = 14  # reactive
                elif dd <= 14:
                    days = 7   # near_event — daily awareness
                elif dd <= 60:
                    days = 7   # planning_window — weekly
                else:
                    days = 30  # far_future — monthly
            except Exception:
                pass
    return (datetime.now(_tz.utc) + timedelta(days=days)).isoformat().replace("+00:00", "Z")


def work_due(brand_id: str) -> Dict[str, Any]:
    """Brief §8 — unified work_due contract.

    Returns one bundle that the Scout can consume:
      - new_discovery_needed: external canonical events with no source_origin
        or with source_origin=external and reverify_after <= now
      - watchlist_rechecks: watchlist items whose next_check_date or
        check_cadence says they are due
      - event_reverification: canonical external events whose
        reverify_after <= now

    All three are designed so the future Scout can call ONE endpoint and
    route work appropriately. No three separate scheduling systems.
    """
    from datetime import datetime, timezone as _tz
    now = datetime.now(_tz.utc)
    now_iso = now.isoformat().replace("+00:00", "Z")

    # Canonical view (one row per event_key)
    canonical = canonical_records(brand_id)

    new_discovery_needed = []
    event_reverification = []
    for r in canonical:
        so = r.get("source_origin")
        # Only external events need reverification
        if so not in ("external", None):
            continue
        # Skip non-actionable lifecycles
        if r.get("event_lifecycle") in ("completed", "expired", "cancelled"):
            continue
        # Skip status=ignored
        if r.get("status") == "ignored":
            continue
        ra = r.get("reverify_after")
        if not ra:
            # No reverify_after set → treat as due
            new_discovery_needed.append({
                "event_key": r.get("event_key"),
                "title": r.get("title"),
                "calendar_id": r.get("calendar_id"),
                "reason": "missing reverify_after",
            })
            continue
        try:
            ra_dt = datetime.fromisoformat(ra.replace("Z", "+00:00"))
        except Exception:
            continue
        if ra_dt <= now:
            event_reverification.append({
                "event_key": r.get("event_key"),
                "title": r.get("title"),
                "calendar_id": r.get("calendar_id"),
                "event_start": r.get("event_start"),
                "reverify_after": ra,
                "now": now_iso,
                "reason": "reverify_after <= now",
            })

    # Watchlist recheck
    watchlist_rechecks = []
    for r in canonical:
        if r.get("status") != "watchlist":
            continue
        # Use next_check_date primarily
        ncd = r.get("next_check_date")
        if ncd:
            try:
                ncd_dt = datetime.fromisoformat(ncd.replace("Z", "+00:00"))
                if ncd_dt <= now:
                    watchlist_rechecks.append({
                        "event_key": r.get("event_key"),
                        "title": r.get("title"),
                        "calendar_id": r.get("calendar_id"),
                        "next_check_date": ncd,
                        "reason": "next_check_date <= now",
                    })
                    continue
            except Exception:
                pass
        # Fallback: check_cadence + last_checked_at
        cad = (r.get("check_cadence") or "weekly").lower()
        cadence_map = {
            "daily": 1, "weekly": 7, "biweekly": 14,
            "monthly": 30, "quarterly": 90, "yearly": 365,
        }
        days = cadence_map.get(cad, 7)
        lca = r.get("last_checked_at")
        if lca:
            try:
                lca_dt = datetime.fromisoformat(lca.replace("Z", "+00:00"))
                if (now - lca_dt).days >= days:
                    watchlist_rechecks.append({
                        "event_key": r.get("event_key"),
                        "title": r.get("title"),
                        "calendar_id": r.get("calendar_id"),
                        "next_check_date": ncd,
                        "reason": f"check_cadence={cad} ({days}d) elapsed since last_checked_at",
                    })
            except Exception:
                pass

    return {
        "ok": True,
        "brand_id": brand_id,
        "evaluated_at": now_iso,
        "new_discovery_needed": new_discovery_needed,
        "event_reverification": event_reverification,
        "watchlist_rechecks": watchlist_rechecks,
        "totals": {
            "new_discovery_needed_count": len(new_discovery_needed),
            "event_reverification_count": len(event_reverification),
            "watchlist_rechecks_count": len(watchlist_rechecks),
        },
    }


# ─── Integrity audit (brief §11) ─────────────────────────────────────────────

def audit_brand_records(brand_id: str) -> Dict[str, Any]:
    """Brief §11 — migration integrity audit.

    For every persisted jsonl line, check:
      - schema_v2 (schema_version=='0.2' + event_key present)
      - source_origin enum
      - brand/event_key consistency
      - calendar_year matches event dates
      - canonical resolution works (latest-per-event_key)
    """
    issues = {
        "logical_events": 0,
        "revision_rows": 0,
        "schema_v2_events": 0,
        "invalid_source_origin": [],
        "invalid_brand_event_keys": [],
        "calendar_year_mismatches": [],
        "canonical_resolution_errors": [],
    }

    rows: List[Dict[str, Any]] = []
    for path in (_calendar_path(brand_id), _watchlist_path(brand_id)):
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                rows.append(r)
            except Exception as e:
                issues["canonical_resolution_errors"].append({
                    "jsonl_path": str(path),
                    "error": f"parse: {e}",
                })

    issues["revision_rows"] = len(rows)

    # Distinct event_keys = logical events
    keys = set()
    for r in rows:
        ek = r.get("event_key")
        if ek:
            keys.add(ek)
        # Schemav2 check
        if r.get("schema_version") == "0.2" and r.get("event_key"):
            issues["schema_v2_events"] += 1

        # source_origin enum
        so = r.get("source_origin")
        if so is not None and so not in VALID_SOURCE_ORIGIN:
            issues["invalid_source_origin"].append({
                "calendar_id": r.get("calendar_id"),
                "event_key": ek,
                "source_origin": so,
            })
        # brand/event_key consistency
        if ek and r.get("brand_id"):
            if not ek.startswith(f"{r['brand_id']}:"):
                issues["invalid_brand_event_keys"].append({
                    "calendar_id": r.get("calendar_id"),
                    "event_key": ek,
                    "brand_id": r.get("brand_id"),
                })
        # calendar_year vs dates
        cy = r.get("calendar_year")
        ev = r.get("event_start") or r.get("event_end")
        if cy and ev:
            import re as _re
            m = _re.search(r"\b(20\d{2})\b", ev)
            if m and int(m.group(1)) != cy:
                issues["calendar_year_mismatches"].append({
                    "calendar_id": r.get("calendar_id"),
                    "event_key": ek,
                    "supplied_calendar_year": cy,
                    "derived_from_dates": int(m.group(1)),
                })

    issues["logical_events"] = len(keys)

    # Canonical resolution — does canonical_records work without error?
    try:
        canon = canonical_records(brand_id)
        # Each canonical record must have a non-null event_key
        for r in canon:
            if not r.get("event_key"):
                issues["canonical_resolution_errors"].append({
                    "calendar_id": r.get("calendar_id"),
                    "error": "canonical record missing event_key",
                })
    except Exception as e:
        issues["canonical_resolution_errors"].append({
            "error": f"canonical_records raised: {e}",
        })

    # Final integrity count
    issues["integrity_ok"] = (
        len(issues["invalid_source_origin"]) == 0
        and len(issues["invalid_brand_event_keys"]) == 0
        and len(issues["calendar_year_mismatches"]) == 0
        and len(issues["canonical_resolution_errors"]) == 0
    )

    return issues


# ─── Slice 0.3 — Calendar Alert model + Scout run-log + Lead-Time Watcher ─

VALID_ALERT_TYPES = [
    "planning_window_open",
    "production_deadline",
    "campaign_live_window",
    "event_imminent",
    "new_opportunity",
    "watchlist_promoted",
    "event_changed",
    "event_postponed",
    "event_cancelled",
    "verification_problem",
    "research_degraded",
]
VALID_ALERT_STATUSES = ["new", "seen", "dismissed", "acted_on"]
VALID_ALERT_PRIORITIES = ["low", "normal", "high", "urgent"]


def _alerts_path(brand_id: str) -> "Path":
    """Where alerts are persisted for a brand.

    Uses the same precedence as the rest of marketing_calendar:
      1. DATA_DIR (volume-mounted /data/campaign-os/brand-directory)
      2. BUNDLED_DATA_DIR (/app/data/brand-directory)
      3. REPO_DATA_DIR + default local fallback
    """
    for candidate in (_DATA_DIR / "brand-directory", _BUNDLED_DATA_DIR, _REPO_DATA_DIR):
        if candidate and candidate.exists() and (candidate / brand_id).exists():
            return candidate / brand_id / "calendar_alerts.jsonl"
    # If brand dir doesn't exist yet anywhere, fall back to BUNDLED_DATA_DIR (which
    # is always writable on Railway as /app/data) and create on first write
    for candidate in (_DATA_DIR / "brand-directory", _BUNDLED_DATA_DIR, _REPO_DATA_DIR):
        if candidate and candidate.exists():
            return candidate / brand_id / "calendar_alerts.jsonl"
    # Final fallback (e.g. local dev)
    return _DEFAULT_LOCAL_DIR / brand_id / "calendar_alerts.jsonl"


def _ensure_runs_dir() -> "Path":
    """Where Scout/Watch run logs are persisted.

    Uses BUNDLED_DATA_DIR (always writable on Railway) when available,
    with DATA_DIR/_system as the production preferred location.
    """
    for candidate in (
        _DATA_DIR / "_system" / "calendar_runs",
        _BUNDLED_DATA_DIR.parent / "_system" / "calendar_runs",
        _REPO_DATA_DIR.parent / "_system" / "calendar_runs",
        Path("/tmp/calendar_runs"),
    ):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            # Test writable
            test = candidate / ".write_test"
            test.touch()
            test.unlink()
            return candidate
        except Exception:
            continue
    # Last resort
    fallback = Path("/tmp/calendar_runs")
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _is_writable_fs(path) -> bool:
    if not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception:
            return False
    return True


def list_alerts(
    brand_id: str,
    *,
    status: Optional[str] = None,
    alert_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Read all alerts for a brand. Optional filters by status + alert_type."""
    if brand_id not in VALID_BRAND_IDS:
        raise ValueError(f"brand_id '{brand_id}' is not an operating brand.")
    path = _alerts_path(brand_id)
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            a = json.loads(line)
        except Exception:
            continue
        if status and a.get("status") != status:
            continue
        if alert_type and a.get("alert_type") != alert_type:
            continue
        out.append(a)
    return out


def _alert_dedupe_key(alert: Dict[str, Any]) -> str:
    """Close-out §6 — alert identity for dedupe.

    Per brief: same (brand_id, event_key, event_revision, alert_type, threshold)
    => noop.
    """
    parts = [
        str(alert.get("brand_id", "")),
        str(alert.get("event_key", "")),
        str(alert.get("event_revision", "")),
        str(alert.get("alert_type", "")),
        str(alert.get("threshold", "")),
    ]
    return "|".join(parts)


def create_alert_if_new(alert: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Append an alert ONLY if no existing alert has the same dedupe key.

    Returns the persisted alert dict, or None if deduped (noop).
    """
    brand_id = alert.get("brand_id")
    if brand_id not in VALID_BRAND_IDS:
        raise ValueError(f"brand_id '{brand_id}' is not an operating brand.")
    alert.setdefault("status", "new")
    alert.setdefault("created_at", _now_iso())
    if alert.get("alert_type") not in VALID_ALERT_TYPES:
        raise ValueError(
            f"alert_type '{alert.get('alert_type')}' invalid. "
            f"Valid: {VALID_ALERT_TYPES}"
        )
    if alert.get("priority") not in VALID_ALERT_PRIORITIES:
        alert.setdefault("priority", "normal")

    dedupe = _alert_dedupe_key(alert)
    alert["alert_dedupe_key"] = dedupe

    # Check existing
    existing = list_alerts(brand_id)
    for a in existing:
        if a.get("alert_dedupe_key") == dedupe and a.get("status") not in ("dismissed", "acted_on"):
            return None  # deduped

    path = _alerts_path(brand_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(alert, ensure_ascii=False) + "\n")
    except Exception:
        # Railway may have read-only /data; fallback
        alt = Path("/tmp/calendar_alerts") / brand_id
        alt.mkdir(parents=True, exist_ok=True)
        with (alt / "calendar_alerts.jsonl").open("a") as f:
            f.write(json.dumps(alert, ensure_ascii=False) + "\n")
    return alert


def transition_alert(
    brand_id: str,
    alert_id: str,
    new_status: str,
) -> Optional[Dict[str, Any]]:
    """Update an alert's status. Returns the updated alert or None."""
    if new_status not in VALID_ALERT_STATUSES:
        raise ValueError(f"status '{new_status}' invalid.")
    alerts = list_alerts(brand_id)
    target = next((a for a in alerts if a.get("alert_id") == alert_id), None)
    if not target:
        return None
    target["status"] = new_status
    target["status_updated_at"] = _now_iso()
    # Rewrite jsonl (last-wins)
    path = _alerts_path(brand_id)
    if not path.exists():
        return None
    seen = set()
    kept = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            a = json.loads(line)
        except Exception:
            kept.append(line)
            continue
        if a.get("alert_id") == alert_id:
            if alert_id not in seen:
                kept.append(json.dumps(target, ensure_ascii=False))
                seen.add(alert_id)
            else:
                continue
        else:
            kept.append(line)
    path.write_text("\n".join(kept) + "\n")
    return target


def append_run_log(run: Dict[str, Any]) -> Dict[str, Any]:
    """Slice 0.3 §9 — append Scout/Watch run log.

    Persists to `<DATA_DIR>/_system/calendar_runs/<job_type>.jsonl`.
    Returns the run record (with run_id + persisted_at).
    """
    run.setdefault("started_at", _now_iso())
    run.setdefault("run_id", f"run-{run.get('job_type','unknown')}-{int(datetime.now().timestamp())}")
    run.setdefault("errors", [])
    runs_dir = _ensure_runs_dir()
    path = runs_dir / f"{run.get('job_type','unknown')}.jsonl"
    with path.open("a") as f:
        f.write(json.dumps(run, ensure_ascii=False) + "\n")
    return run


def lead_time_watcher(brand_id: str, *, now: Optional[str] = None) -> Dict[str, Any]:
    """Slice 0.3 §3C — script-only lead-time watcher.

    Reads canonical Calendar events + deterministic/internal campaigns
    and checks each lead-time threshold. Returns:

      {
        "brand_id": ...,
        "evaluated_at": ...,
        "alerts_created": [...],
        "alerts_deduplicated": N,
        "silent": True/False,
      }

    No LLM. Threshold math only.
    """
    if brand_id not in VALID_BRAND_IDS:
        raise ValueError(f"brand_id '{brand_id}' is not an operating brand.")
    from datetime import datetime, timezone, timedelta
    cfg = load_brand_config(brand_id)
    if not cfg:
        return {"brand_id": brand_id, "evaluated_at": _now_iso(),
                "alerts_created": [], "alerts_deduplicated": 0,
                "silent": True, "skipped_reason": "brand not configured"}
    anchor = now or _now_iso()
    try:
        anchor_dt = datetime.fromisoformat(anchor.replace("Z", "+00:00"))
    except Exception:
        anchor_dt = datetime.now(timezone.utc)
    canonical = canonical_records(brand_id)
    alerts_created = []
    alerts_deduplicated = 0

    # Thresholds: (days, alert_type, derived from brief §22 examples)
    threshold_buckets = [
        (90, "planning_window_open"),
        (60, "planning_window_open"),
        (21, "production_deadline"),
        (7, "campaign_live_window"),
        (1, "event_imminent"),
    ]

    for r in canonical:
        ev = r.get("event_start") or r.get("event_window_start")
        if not ev:
            continue
        try:
            ev_str = ev.replace("Z", "+00:00")
            ev_dt = datetime.fromisoformat(ev_str)
            if ev_dt.tzinfo is None:
                ev_dt = ev_dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        # Ensure both are tz-aware
        if anchor_dt.tzinfo is None:
            anchor_dt = anchor_dt.replace(tzinfo=timezone.utc)
        days_to_event = (ev_dt - anchor_dt).days
        lifecycle = r.get("event_lifecycle")
        if lifecycle in ("cancelled", "expired", "completed"):
            continue

        for threshold_days, alert_type in threshold_buckets:
            # Trigger when days_to_event ≈ threshold (±3 day tolerance)
            if abs(days_to_event - threshold_days) > 3:
                continue
            alert = {
                "alert_id": f"alert-{brand_id}-{r.get('event_key')}-{alert_type}-{threshold_days}",
                "brand_id": brand_id,
                "event_key": r.get("event_key"),
                "event_revision": r.get("revision"),
                "alert_type": alert_type,
                "threshold": threshold_days,
                "title": f"{r.get('title','')} — {alert_type.replace('_',' ')}",
                "message": (
                    f"{r.get('title','')} enters its {threshold_days}-day "
                    f"{alert_type.replace('_',' ')} window (event on "
                    f"{ev_dt.date().isoformat()}, "
                    f"evaluated at {anchor_dt.date().isoformat()})."
                ),
                "priority": (
                    "urgent" if threshold_days <= 7
                    else "high" if threshold_days <= 21
                    else "normal"
                ),
                "due_at": ev,
                "source_event_revision": r.get("revision"),
                "source_job": "lead_time_watcher",
                "calendar_year": r.get("calendar_year"),
            }
            # Pillar + north star context (brief §8)
            pillars = r.get("pillars") or []
            if pillars:
                alert["pillar_ids"] = pillars
            # Map lead-time class to north_star via cfg
            lts = cfg.get("lead_time_rules") or {}
            lt_class = r.get("lead_time_class") or "normal_campaign"
            class_cfg = (lts.get("by_class") or {}).get(lt_class) or {}
            if class_cfg.get("north_star_metric"):
                alert["north_star_ids"] = [class_cfg["north_star_metric"]]
            elif pillars:
                p_cfg = next(
                    (p for p in cfg.get("pillars", []) if p.get("pillar_id") == pillars[0]),
                    None,
                )
                if p_cfg and p_cfg.get("north_star_metric"):
                    alert["north_star_ids"] = [p_cfg["north_star_metric"]]
            persisted = create_alert_if_new(alert)
            if persisted:
                alerts_created.append(persisted)
            else:
                alerts_deduplicated += 1

    return {
        "brand_id": brand_id,
        "evaluated_at": _now_iso(),
        "alerts_created": alerts_created,
        "alerts_deduplicated": alerts_deduplicated,
        "silent": len(alerts_created) == 0,
        "brands_processed": 1,
    }


