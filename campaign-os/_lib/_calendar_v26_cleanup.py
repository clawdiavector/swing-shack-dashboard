"""
_calendar_v26_cleanup.py — V2.6 production store cleanup.

Restores the intended Calendar architecture:

  intelligence / candidates
  → HUMAN APPROVAL
  → Main Strategic Calendar (operator-store, status=approved only)

Finds and remediates pollution in the operator-store (marketing-calendar/<brand>.jsonl):

  1. Test / acceptance artifacts           → REMOVE (audit row)
  2. Template / demo records               → REMOVE (audit row, NOT promoted to candidates)
  3. Scout / ingest direct-writes          → MOVE TO CANDIDATES (idempotent upsert)
  4. Unknown-provenance (2026-09-17 mass-inject) → MOVE TO CANDIDATES (requires_human_reapproval)
  5. Deterministic public holidays         → REMOVE FROM OPERATOR STORE (still appear via
                                            baked data/important-dates/ as STRATEGIC MOMENTS)
  6. Genuine operator approvals (kyle-desk etc.) → KEEP

The module NEVER mutates audit history. It ONLY appends new audit rows
for every action taken. The original approval rows are preserved.

Defence-in-depth write gates (separately enforced in app.py):
  - Planning timeline merge filters operator-store records by
    status == "approved". Records with status=candidate or status=watchlist
    are surfaced via the candidates endpoint, NOT the Main Calendar.
  - The marketing-calendar.jsonl append path requires an explicit
    approval action. Scout/template/ingest bypasses are blocked at
    the marketing_calendar._persist() level.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ─── Storage paths ─────────────────────────────────────────────────────────

def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/data/campaign-os"))


def _calendar_dir() -> Path:
    """The marketing-calendar jsonl directory. Same path the marketing_calendar
    module uses.
    """
    return _data_dir() / "intelligence" / "marketing-calendar"


def _calendar_path(brand_id: str) -> Path:
    return _calendar_dir() / f"{brand_id}.jsonl"


def _watchlist_path(brand_id: str) -> Path:
    return _calendar_dir() / f"{brand_id}__watchlist.jsonl"


def _audit_dir() -> Path:
    return _data_dir() / "calendar-audit"


def _audit_path(brand_id: str) -> Path:
    return _audit_dir() / f"{brand_id}-approvals.jsonl"


def _backup_dir() -> Path:
    return _data_dir() / "calendar-audit-backups"


# ─── Backup ───────────────────────────────────────────────────────────────

def backup_calendar(brand_id: str) -> Dict[str, Any]:
    """Write a timestamped, sha256-verified copy of the marketing-calendar
    jsonl to calendar-audit-backups/. The backup is a plain jsonl with
    one record per line (the same as the source).
    """
    if brand_id not in ("swing-shack", "stick", "bag-drop"):
        raise ValueError(f"invalid brand_id: {brand_id}")
    src = _calendar_path(brand_id)
    backup_root = _backup_dir()
    backup_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = backup_root / f"{brand_id}__backup__{ts}.jsonl"
    lines = 0
    if src.exists():
        with open(src, "r", encoding="utf-8") as f:
            content = f.read()
        lines = sum(1 for ln in content.splitlines() if ln.strip())
        # Atomic write: write to a tmp file, then rename
        tmp = dst.with_suffix(dst.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        tmp.replace(dst)
    sha = hashlib.sha256()
    if dst.exists():
        with open(dst, "rb") as f:
            sha.update(f.read())
    return {
        "ok": True,
        "brand_id": brand_id,
        "source": str(src),
        "source_exists": src.exists(),
        "backup": str(dst),
        "backup_lines": lines,
        "sha256": sha.hexdigest(),
        "ts": ts,
    }


# ─── Classifier ────────────────────────────────────────────────────────────

def classify_record(rec: Dict[str, Any]) -> str:
    """V2.5/V2.6 classification — the category that drives cleanup action.

    Returns one of:
      KEEP                                 — operator-approved with real provenance
      TEST_ACCEPTANCE_ARTIFACT             — the V2.4 acceptance approve (event_key known)
      TEMPLATE_DEMO                        — foreman-template-* or tpl-demo-* or tpl-v2-*
      SCOUT_CANDIDATE                      — hermes-scout / heidi-ingest with status=candidate
      SCOUT_WATCHLIST                      — hermes-scout / heidi-ingest with status=watchlist
      SCOUT_MASS_PROMOTED_CEO_DEMO         — scout records mass-promoted in 2026-09-17 demo
      LEGACY_UNVERIFIED_APPROVAL           — 2026-09-17 mass-inject with empty created_by
      DETERMINISTIC_HOLIDAY                — holiday_inject + source_origin=deterministic_calendar
    """
    cb = (rec.get("created_by") or "").strip()
    so = (rec.get("source_origin") or "").strip()
    st = (rec.get("source_type") or "").strip()
    status = (rec.get("status") or "").strip()
    tr = (rec.get("transition_reason") or "").strip()
    ek = (rec.get("event_key") or "").strip()

    # 1. The known V2.4 acceptance test artifact
    if ek == "swing-shack:alfred-dunhill-championship-2027:2027-02-25":
        return "TEST_ACCEPTANCE_ARTIFACT"

    # 2. Template / demo / test pollution
    if cb.startswith("foreman-template"):
        return "TEMPLATE_DEMO"
    if "tpl-demo" in ek or "tpl-v2" in ek:
        return "TEMPLATE_DEMO"

    # 3. Scout / ingest records
    if cb == "hermes-scout" or cb == "heidi-ingest":
        if status == "watchlist":
            return "SCOUT_WATCHLIST"
        if tr == "CEO demo — land stale calendar candidates":
            return "SCOUT_MASS_PROMOTED_CEO_DEMO"
        # status=candidate is the default — but some show status=approved
        # without a legitimate transition_reason. Treat them as candidate.
        return "SCOUT_CANDIDATE"

    # 4. Unknown provenance 2026-09-17 mass-inject
    if cb == "" and tr == "CEO demo — land stale calendar candidates":
        return "LEGACY_UNVERIFIED_APPROVAL"
    if cb == "" and tr == "" and so in ("external", "internal_strategy"):
        return "LEGACY_UNVERIFIED_APPROVAL"

    # 5. Deterministic holidays
    if cb == "holiday_inject" and so == "deterministic_calendar":
        return "DETERMINISTIC_HOLIDAY"

    # 6. Genuine operator approvals
    if cb in ("kyle-desk", "foreman") or (cb and tr and tr != "CEO demo — land stale calendar candidates" and st != "scout"):
        return "KEEP"

    # Fall-through — anything not classified is flagged for human review
    return "UNCLASSIFIED"


def classify_all(records: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group records by classification category."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        cat = classify_record(r)
        groups.setdefault(cat, []).append(r)
    return groups


def dry_run_cleanup(brand_id: str) -> Dict[str, Any]:
    """Read the marketing-calendar jsonl, classify each record, return the
    planned cleanup action. No writes.
    """
    if brand_id not in ("swing-shack", "stick", "bag-drop"):
        raise ValueError(f"invalid brand_id: {brand_id}")
    src = _calendar_path(brand_id)
    records: List[Dict[str, Any]] = []
    if src.exists():
        with open(src, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
    groups = classify_all(records)

    # Build the plan
    plan: List[Dict[str, Any]] = []
    for cat, recs in groups.items():
        for r in recs:
            ek = r.get("event_key")
            title = r.get("title") or ""
            if cat == "KEEP":
                action = "keep"
            elif cat in ("TEST_ACCEPTANCE_ARTIFACT", "TEMPLATE_DEMO", "DETERMINISTIC_HOLIDAY"):
                action = "remove_from_operator_store"
            elif cat == "SCOUT_CANDIDATE":
                action = "move_to_candidates"
            elif cat == "SCOUT_WATCHLIST":
                action = "move_to_watchlist"
            elif cat == "SCOUT_MASS_PROMOTED_CEO_DEMO":
                action = "move_to_candidates_with_legacy_note"
            elif cat == "LEGACY_UNVERIFIED_APPROVAL":
                action = "move_to_candidates_requires_reapproval"
            else:
                action = "halt_unclassified"
            plan.append({
                "event_key": ek,
                "title": title[:80],
                "created_by": r.get("created_by") or "",
                "source_origin": r.get("source_origin") or "",
                "status": r.get("status") or "",
                "transition_reason": r.get("transition_reason") or "",
                "classification": cat,
                "action": action,
            })

    # Signature: hash of the plan (used as a confirm guard on execute)
    plan_json = json.dumps(plan, sort_keys=True, ensure_ascii=False)
    sig = hashlib.sha256(plan_json.encode("utf-8")).hexdigest()

    return {
        "ok": True,
        "brand_id": brand_id,
        "source": str(src),
        "source_line_count": len(records),
        "classification_summary": {cat: len(recs) for cat, recs in groups.items()},
        "plan": plan,
        "plan_signature": sig,
    }


# ─── Audit helper ──────────────────────────────────────────────────────────

def _write_audit(brand_id: str, action: str, actor: Dict[str, Any],
                 source_id: str, before: Optional[Dict[str, Any]],
                 after: Optional[Dict[str, Any]], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Append an immutable audit row."""
    audit_dir = _audit_dir()
    audit_dir.mkdir(parents=True, exist_ok=True)
    entry: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "brand_id": brand_id,
        "action": action,
        "actor": actor,
        "source_id": source_id,
        "before": before,
        "after": after,
    }
    if extra:
        entry.update(extra)
    audit_file = audit_dir / f"{brand_id}-approvals.jsonl"
    with open(audit_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


# ─── Execute cleanup ──────────────────────────────────────────────────────

def execute_cleanup(brand_id: str, plan_signature: str, actor: Dict[str, Any],
                    confirm: bool = False) -> Tuple[Dict[str, Any], int]:
    """Execute the V2.6 cleanup. Requires:
      - confirm: True (else rejected)
      - plan_signature: matches a fresh dry_run_cleanup signature
                         (operator must read the dry-run and pass its sig)
    """
    if not confirm:
        return {"ok": False, "error": "confirm=True required"}, 400
    if brand_id not in ("swing-shack", "stick", "bag-drop"):
        return {"ok": False, "error": f"invalid brand_id: {brand_id}"}, 400

    # Re-run dry-run to get current state and compare signature
    dry = dry_run_cleanup(brand_id)
    if dry["plan_signature"] != plan_signature:
        return {
            "ok": False,
            "error": "plan_signature does not match current state. Re-run dry_run_cleanup and use the latest plan_signature.",
            "current_signature": dry["plan_signature"],
            "supplied_signature": plan_signature,
        }, 400

    plan = dry["plan"]

    # Mandatory: backup first
    backup = backup_calendar(brand_id)

    # Execute
    cal_file = _calendar_path(brand_id)
    if not cal_file.exists():
        return {"ok": False, "error": f"calendar file not found: {cal_file}"}, 404

    # Read all records
    with open(cal_file, "r", encoding="utf-8") as f:
        raw_lines = f.readlines()
    kept_lines: List[str] = []
    plan_by_ek = {p["event_key"]: p for p in plan if p["event_key"]}
    audit_rows: List[Dict[str, Any]] = []
    actions: Dict[str, int] = {}
    failures: List[str] = []

    # Watchlist and candidates files (created on demand)
    watchlist_file = _watchlist_path(brand_id)
    candidates_mirror: Dict[str, Dict[str, Any]] = {}  # in-memory idempotency guard
    if watchlist_file.exists():
        with open(watchlist_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    candidates_mirror[r.get("event_key", "")] = r
                except Exception:
                    continue

    for line in raw_lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            kept_lines.append(line)  # preserve unparseable lines as-is
            continue
        ek = rec.get("event_key", "")
        p = plan_by_ek.get(ek)
        if not p:
            # Unclassified or unknown — preserve as-is
            kept_lines.append(line)
            continue
        action = p["action"]
        if action == "keep":
            kept_lines.append(line)
            actions["keep"] = actions.get("keep", 0) + 1
        elif action == "remove_from_operator_store":
            # Drop from operator store; audit
            audit = _write_audit(
                brand_id=brand_id,
                action="remove_from_operator_store",
                actor=actor,
                source_id=ek,
                before={
                    "event_key": ek,
                    "title": rec.get("title"),
                    "status": rec.get("status"),
                    "created_by": rec.get("created_by"),
                    "source_origin": rec.get("source_origin"),
                    "transition_reason": rec.get("transition_reason"),
                },
                after=None,
                extra={
                    "cleanup_step": _step_for_category(p["classification"]),
                    "classification": p["classification"],
                    "cleanup_reason": "v26_production_data_cleanup",
                    "backup_ref": backup["backup"],
                    "backup_sha256": backup["sha256"],
                },
            )
            audit_rows.append(audit)
            actions[action] = actions.get(action, 0) + 1
            # do NOT append to kept_lines
        elif action in ("move_to_candidates", "move_to_candidates_with_legacy_note",
                        "move_to_candidates_requires_reapproval"):
            # Idempotent: if the event_key is already in the candidates mirror,
            # don't re-insert. Otherwise tag the record and append to a
            # candidates mirror file.
            tag_record = dict(rec)
            tag_record["status"] = "candidate"
            tag_record["migrated_from_operator_store"] = True
            tag_record["migration_reason"] = "no_human_approval_provenance"
            tag_record["migrated_at"] = datetime.now(timezone.utc).isoformat()
            tag_record["migrated_event_key"] = ek
            if action == "move_to_candidates_with_legacy_note":
                tag_record["legacy_provenance_note"] = (
                    "Mass-promoted during 2026-09-17 'CEO demo — land stale "
                    "calendar candidates'. Original approval is not "
                    "considered legitimate for V2.6 architecture; needs "
                    "individual re-approval by an authenticated operator."
                )
            if action == "move_to_candidates_requires_reapproval":
                tag_record["provenance_status"] = "LEGACY_UNVERIFIED_APPROVAL"
                tag_record["requires_human_reapproval"] = True
            # Append to candidates mirror jsonl
            mirror_path = _calendar_dir() / f"{brand_id}__candidates_mirror.jsonl"
            _calendar_dir().mkdir(parents=True, exist_ok=True)
            if ek in candidates_mirror:
                # Idempotent noop
                actions[f"{action}_noop"] = actions.get(f"{action}_noop", 0) + 1
            else:
                with open(mirror_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(tag_record, ensure_ascii=False) + "\n")
                candidates_mirror[ek] = tag_record
                actions[action] = actions.get(action, 0) + 1
            # Drop from operator store
            audit = _write_audit(
                brand_id=brand_id,
                action="move_to_candidates",
                actor=actor,
                source_id=ek,
                before={
                    "event_key": ek,
                    "title": rec.get("title"),
                    "status": rec.get("status"),
                    "created_by": rec.get("created_by"),
                    "source_origin": rec.get("source_origin"),
                    "transition_reason": rec.get("transition_reason"),
                },
                after={
                    "event_key": ek,
                    "new_status": "candidate",
                    "mirror": str(mirror_path),
                },
                extra={
                    "cleanup_step": _step_for_category(p["classification"]),
                    "classification": p["classification"],
                    "cleanup_reason": "v26_production_data_cleanup",
                    "backup_ref": backup["backup"],
                    "backup_sha256": backup["sha256"],
                },
            )
            audit_rows.append(audit)
            # do NOT append to kept_lines
        elif action == "move_to_watchlist":
            tag_record = dict(rec)
            tag_record["status"] = "watchlist"
            tag_record["migrated_from_operator_store"] = True
            tag_record["migration_reason"] = "scout_watchlist_relocation"
            tag_record["migrated_at"] = datetime.now(timezone.utc).isoformat()
            watchlist_file.parent.mkdir(parents=True, exist_ok=True)
            if ek in candidates_mirror:
                actions[f"{action}_noop"] = actions.get(f"{action}_noop", 0) + 1
            else:
                with open(watchlist_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(tag_record, ensure_ascii=False) + "\n")
                candidates_mirror[ek] = tag_record
                actions[action] = actions.get(action, 0) + 1
            audit = _write_audit(
                brand_id=brand_id,
                action="move_to_watchlist",
                actor=actor,
                source_id=ek,
                before={
                    "event_key": ek,
                    "title": rec.get("title"),
                    "status": rec.get("status"),
                },
                after={"event_key": ek, "new_status": "watchlist"},
                extra={
                    "cleanup_step": _step_for_category(p["classification"]),
                    "classification": p["classification"],
                    "cleanup_reason": "v26_production_data_cleanup",
                    "backup_ref": backup["backup"],
                    "backup_sha256": backup["sha256"],
                },
            )
            audit_rows.append(audit)
        else:
            # Halt unclassified
            kept_lines.append(line)
            failures.append(f"halt_unclassified: {ek}")
            actions["halt_unclassified"] = actions.get("halt_unclassified", 0) + 1

    # Atomic write of the cleaned operator store
    tmp = cal_file.with_suffix(cal_file.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(kept_lines)
    tmp.replace(cal_file)

    return {
        "ok": True,
        "brand_id": brand_id,
        "backup": backup,
        "actions": actions,
        "failures": failures,
        "audit_rows_written": len(audit_rows),
        "operator_store_lines_before": len(raw_lines),
        "operator_store_lines_after": sum(1 for ln in kept_lines if ln.strip()),
        "candidates_mirror_path": str(_calendar_dir() / f"{brand_id}__candidates_mirror.jsonl"),
        "watchlist_path": str(watchlist_file),
    }, 200


def _step_for_category(cat: str) -> str:
    if cat == "TEST_ACCEPTANCE_ARTIFACT":
        return "step_3_remove_v24_acceptance_artifact"
    if cat == "TEMPLATE_DEMO":
        return "step_4_remove_template_demo"
    if cat in ("SCOUT_CANDIDATE", "SCOUT_WATCHLIST", "SCOUT_MASS_PROMOTED_CEO_DEMO"):
        return "step_5_move_scout_to_candidates"
    if cat == "LEGACY_UNVERIFIED_APPROVAL":
        return "step_6_move_unknown_provenance_to_reapproval"
    if cat == "DETERMINISTIC_HOLIDAY":
        return "step_7_move_holidays_to_strategic_moments"
    return "unknown"


# ─── Post-cleanup status ──────────────────────────────────────────────────

def cleanup_status(brand_id: str) -> Dict[str, Any]:
    """After the cleanup, return the post-state. Independent of dry-run.
    Used to verify the operator-store now contains only genuine records.
    """
    if brand_id not in ("swing-shack", "stick", "bag-drop"):
        raise ValueError(f"invalid brand_id: {brand_id}")
    cal_file = _calendar_path(brand_id)
    records: List[Dict[str, Any]] = []
    if cal_file.exists():
        with open(cal_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
    groups = classify_all(records)
    return {
        "ok": True,
        "brand_id": brand_id,
        "operator_store_line_count": len(records),
        "classification_summary": {cat: len(recs) for cat, recs in groups.items()},
        "is_clean": all(
            cat == "KEEP" or len(recs) == 0
            for cat, recs in groups.items()
            if cat != "KEEP"
        ),
    }
