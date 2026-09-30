"""
_calendar_v27_intake.py — V2.7 intake-store + write-gate closure.

Restores canonical Calendar architecture: automation writes to
intake stores, NEVER to the operator/Main Calendar store.

Architecture:
  Calendar V2.7
  ─────────────────────────────────────────────────────────────────────
  store                       writer(s)                consumer(s)
  ─────────────────────────────────────────────────────────────────────
  DATA_DIR/intelligence/      SCOUT/HEIDI/COS-         /api/planning/
  marketing-calendar/         REACTIVE-WATCH/          <brand>/candidates
  <brand>__intake.jsonl       UNFIED-INBOX             (existing static)
  = "intelligence intake"     (status=candidate,
                               watchlist, etc.)        /api/calendar/
                                                          candidates
  DATA_DIR/intelligence/      holiday_inject           Month grid
  important-dates/             (deterministic)          STRATEGIC MOMENTS
  <brand>.jsonl               (status=candidate)
  DATA_DIR/intelligence/      foreman-template-*        (test-only,
  marketing-calendar/         foreman-generative-        fixture isolated)
  <brand>__test_fixture.jsonl replace
                               (isolated DATA_DIR,
                                fixture namespace)
  DATA_DIR/intelligence/      PLANNING APPROVE          Rolling timeline
  marketing-calendar/         endpoint (HUMAN)
  <brand>.jsonl               (status=approved,
  = "operator/Main Calendar"   actor_id=fp:...,
                               transition_reason,
                               X-Actor-Display-Name)
  ─────────────────────────────────────────────────────────────────────

Per V2.7 directive:
  "automation must not be able to write ANY of these directly into
  that [operator] store: candidate, watchlist, research_lead,
  deterministic holiday, template/demo, generated replacement,
  reactive-watch discovery"
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ─── Storage paths ─────────────────────────────────────────────────────────

def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def _intelligence_root() -> Path:
    return _data_dir() / "intelligence"


def _marketing_calendar_dir() -> Path:
    return _intelligence_root() / "marketing-calendar"


def _operator_calendar_path(brand_id: str) -> Path:
    """The HUMAN-APPROVED Main Calendar. Only the planning approve
    endpoint may write here. Read-only for everything else."""
    return _marketing_calendar_dir() / f"{brand_id}.jsonl"


def _intake_calendar_path(brand_id: str) -> Path:
    """The intelligence INTAKE store. All scout / heidi / inbox /
    reactive-watch / template (in fixture) writes land here. NOT a
    Main Calendar source. Surfaced via /api/planning/<brand>/candidates."""
    return _marketing_calendar_dir() / f"{brand_id}__intake.jsonl"


def _watchlist_calendar_path(brand_id: str) -> Path:
    """Watchlist store (legacy alias kept for backwards compat)."""
    return _marketing_calendar_dir() / f"{brand_id}__watchlist.jsonl"


def _important_dates_dir() -> Path:
    return _intelligence_root() / "important-dates"


def _important_dates_path(brand_id: str) -> Path:
    """Strategic Moments / important-dates store. Holiday_inject and any
    deterministic date writer goes here. NOT a Main Calendar source."""
    return _important_dates_dir() / f"{brand_id}.jsonl"


def _audit_dir() -> Path:
    return _data_dir() / "calendar-audit"


def _audit_path(brand_id: str) -> Path:
    return _audit_dir() / f"{brand_id}-approvals.jsonl"


# ─── Writer classification ─────────────────────────────────────────────────

# These created_by values indicate AUTOMATION sources that V2.7
# forbids from writing directly to the operator-store.
AUTOMATION_SOURCES = frozenset({
    "hermes-scout",
    "heidi-ingest",
    "holiday_inject",
    "foreman-template-test",
    "foreman-template-demo",
    "foreman-template-demo-v2",
    "foreman-generative-replace",
    "cos-reactive-watch",
    "proposal_promote",
    "interpreter",
    "hermes-scout-simulation",
})

# Source types that are always automation.
AUTOMATION_SOURCE_TYPES = frozenset({
    "scout",
    "template",
    "template-demo",
    "holiday",
    "reactive-watch",
    "interpreter",
})


def is_automation_writer(record: Dict[str, Any]) -> bool:
    """Classify a record by its writer source. Returns True if the
    writer is an automation process that V2.7 forbids from touching
    the operator-store directly.
    """
    cb = (record.get("created_by") or "").strip().lower()
    if cb in AUTOMATION_SOURCES:
        return True
    st = (record.get("source_type") or "").strip().lower()
    if st in AUTOMATION_SOURCE_TYPES:
        return True
    # Empty creator + automated runner is also automation
    if not cb and st:
        return True
    return False


# ─── Intake writes ─────────────────────────────────────────────────────────

def write_intake_record(
    brand_id: str,
    record: Dict[str, Any],
) -> Dict[str, Any]:
    """Append a record to the intelligence intake store.

    Used by: scout, heidi-ingest, reactive-watch, inbox intake.
    NEVER the operator/Main Calendar.

    Idempotent: same event_key is deduplicated by checking the latest
    revision; the new record's revision is bumped.
    """
    if brand_id not in ("swing-shack", "stick", "bag-drop"):
        raise ValueError(f"invalid brand_id: {brand_id}")

    intake_path = _intake_calendar_path(brand_id)
    intake_path.parent.mkdir(parents=True, exist_ok=True)

    rec = dict(record)
    rec.setdefault("brand_id", brand_id)
    rec.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    rec.setdefault("last_checked_at", rec["created_at"])
    # Tag — this record lives in the INTAKE store
    rec.setdefault("intake_store", True)
    rec.setdefault("intake_promoted_to_main", False)

    # Idempotency: scan existing intake for matching event_key
    event_key = rec.get("event_key")
    if event_key:
        latest_rev = 0
        if intake_path.exists():
            for line in intake_path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("event_key") == event_key:
                    latest_rev = max(latest_rev, r.get("revision") or 1)
        rec["revision"] = latest_rev + 1
        rec["change_type"] = "updated" if latest_rev else "new_event"
    else:
        rec.setdefault("revision", 1)
        rec.setdefault("change_type", "new_event")

    with open(intake_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def write_important_dates(
    brand_id: str,
    record: Dict[str, Any],
) -> Dict[str, Any]:
    """Append a record to the important-dates store. Used by:
    holiday_inject and any deterministic-date writer.

    NOT a Main Calendar source. The month grid's STRATEGIC MOMENT
    layer reads from <DATA_DIR>/important-dates/<brand>.jsonl.
    """
    if brand_id not in ("swing-shack", "stick", "bag-drop"):
        raise ValueError(f"invalid brand_id: {brand_id}")

    imp_path = _important_dates_path(brand_id)
    imp_path.parent.mkdir(parents=True, exist_ok=True)

    rec = dict(record)
    rec.setdefault("brand_id", brand_id)
    rec.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    rec.setdefault("source_type", "deterministic")
    rec.setdefault("source_origin", "deterministic_calendar")
    rec.setdefault("layer", "strategic_moment")

    # Dedupe by event_key
    event_key = rec.get("event_key")
    if event_key and imp_path.exists():
        for line in imp_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("event_key") == event_key:
                # Already present — idempotent noop
                return {"ok": True, "action": "noop", "record": r}

    with open(imp_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"ok": True, "action": "created", "record": rec}


# ─── Store-ownership gates ────────────────────────────────────────────────

def assert_automation_uses_intake_or_important_dates(
    record: Dict[str, Any],
    target_store: str,
) -> None:
    """Enforce V2.7 store ownership:
      - AUTOMATION writers MUST target "intake" or "important_dates",
        NEVER "operator".
      - HUMAN APPROVAL writers MAY target "operator".

    Raises PermissionError on violation.
    """
    is_auto = is_automation_writer(record)
    if is_auto and target_store == "operator":
        raise PermissionError(
            f"V2.7 store-ownership: automation writer "
            f"created_by={record.get('created_by')!r} "
            f"source_type={record.get('source_type')!r} "
            f"cannot write to the operator/Main Calendar store. "
            f"Use the intake store (candidates/watchlist) or the "
            f"important-dates store (Strategic Moments)."
        )


# ─── Records counter ─────────────────────────────────────────────────────

def intake_count(brand_id: str) -> int:
    p = _intake_calendar_path(brand_id)
    if not p.exists():
        return 0
    n = 0
    for line in p.read_text().splitlines():
        if line.strip():
            n += 1
    return n


def important_dates_count(brand_id: str) -> int:
    p = _important_dates_path(brand_id)
    if not p.exists():
        return 0
    n = 0
    for line in p.read_text().splitlines():
        if line.strip():
            n += 1
    return n


def operator_count(brand_id: str) -> int:
    p = _operator_calendar_path(brand_id)
    if not p.exists():
        return 0
    n = 0
    for line in p.read_text().splitlines():
        if line.strip():
            n += 1
    return n


def store_snapshot(brand_id: str) -> Dict[str, Any]:
    return {
        "ok": True,
        "brand_id": brand_id,
        "operator_main_calendar": operator_count(brand_id),
        "intake": intake_count(brand_id),
        "important_dates": important_dates_count(brand_id),
        "watchlist": sum(
            1 for line in _watchlist_calendar_path(brand_id).read_text().splitlines()
            if line.strip()
        ) if _watchlist_calendar_path(brand_id).exists() else 0,
    }
