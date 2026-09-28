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
    # V2.7 §4 — "foreman DOES NOT AUTOMATICALLY MEAN HUMAN"
    # Real human approvals must come from authenticated human identity
    # (actor_id starts with fp:) AND have an action-driven approval
    # transition_reason (e.g. "Lodge", "Book", "L4 approve") — NOT a
    # generation/migration/automation reason.
    if cb in ("kyle-desk",):
        # kyle-desk has historically been the human-approval actor.
        # V2.8 — the trackman-coaching-session record dedup: only the
        # variant with a meaningful transition_reason (Lodge/Book/
        # L4 approve/approve) is KEEP. The empty-tr variant is
        # REQUIRES_REAPPROVAL.
        tr_norm = tr.lower().strip() if tr else ""
        human_transition_reasons = {"lodge", "book", "l4 approve", "approve"}
        if tr_norm in human_transition_reasons:
            return "KEEP"
        return "REQUIRES_REAPPROVAL"

    if cb == "foreman":
        # Distinguish HUMAN foreman (approval/lodge transition_reason)
        # from FOREMAN-TEMPLATE-* / FOREMAN-GENERATIVE-REPLACE automation.
        tr_norm = tr.lower().strip() if tr else ""
        human_transition_reasons = {"lodge", "book", "l4 approve", "approve"}
        if tr_norm in human_transition_reasons:
            return "KEEP"
        # Empty / ambiguous / automated transition_reason — REQUIRES REAPPROVAL
        return "REQUIRES_REAPPROVAL"

    # Catch automation-by-disguise: empty created_by or ambiguous source
    # — these need human review before becoming Main Calendar events.
    if cb == "foreman-template-test":
        # Specific case for the test record's created_by (might be empty
        # but source_type=template). We classify as REMOVE_TEMPLATE_DEMO.
        if st == "operator" or tr == "ss-did-you-know template test":
            return "TEMPLATE_DEMO"
        return "TEMPLATE_DEMO"

    # V2.7 §6 — foreman-generative-replace / foreman-template-* records
    # are template/test pollution, NOT Main Calendar records. They
    # belong nowhere in production Calendar data.
    if cb in ("foreman-generative-replace", "foreman-template-test",
              "foreman-template-demo", "foreman-template-demo-v2"):
        return "TEMPLATE_DEMO"

    # V2.7 §7 — cos-reactive-watch is a discovery monitor. The records
    # it produces are intelligence, NOT Main Calendar records. They
    # go to the intake store (candidates/watchlist) only after a human
    # approves them.
    if cb == "cos-reactive-watch":
        return "SCOUT_CANDIDATE"

    # Catch automation-only `source_type` matches when created_by is
    # empty / non-canonical (e.g. legacy 2026-09-17 mass-inject).
    if st in ("scout", "template", "template-demo", "holiday", "reactive-watch"):
        return "SCOUT_CANDIDATE"

    # V2.7 §9 — records with "lodge so cooker can run" / similar
    # transition_reasons are automation-laundered approvals. They
    # are NOT human reapprovals. Treat as REQUIRES_REAPPROVAL so
    # an actual human must re-confirm before they enter the
    # Main Calendar.
    tr_norm = tr.lower().strip() if tr else ""
    tr_lower = tr_norm
    AUTOMATION_LAUNDERED_REASONS = {
        "canonical status still candidate; lodge so cooker can run",
        "lodge so cooker can run",
        "canonical status still candidate; lodge",
    }
    if tr_lower in AUTOMATION_LAUNDERED_REASONS:
        return "REQUIRES_REAPPROVAL"

    # V2.7 §6 — foreman-gen-* (variants) are template/test pollution.
    if cb and cb.startswith("foreman-gen"):
        return "TEMPLATE_DEMO"

    # V2.7 §9 — the canonical event_key "swing-shack:alfred-dunhill-
    # championship:2027" with empty creator + empty source_origin is
    # an automation-laundered version of the V2.3 alfred-dunhill
    # record. Even with status='candidate', it has no human approval
    # — route to intake / candidates.
    if (
        not cb and not so
        and ek == "swing-shack:alfred-dunhill-championship:2027"
    ):
        if status in ("candidate", "", "watchlist"):
            return "SCOUT_CANDIDATE"
        if status == "approved":
            return "REQUIRES_REAPPROVAL"

    # V2.8 §6 — Stick and Bag-Drop production stores contain
    # records with empty created_by + empty source_origin + empty
    # status. These have no human approval provenance and no
    # automation creator either. They are unknown-provenance
    # records. Route to REQUIRES_REAPPROVAL so an actual human
    # must re-confirm before they enter the Main Calendar.
    if not cb and not so and not tr:
        if status in ("candidate", "watchlist", ""):
            return "REQUIRES_REAPPROVAL"
        if status == "approved":
            return "REQUIRES_REAPPROVAL"

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
                action = "move_to_intake_as_candidate"
            elif cat == "SCOUT_WATCHLIST":
                action = "move_to_intake_as_watchlist"
            elif cat == "SCOUT_MASS_PROMOTED_CEO_DEMO":
                action = "move_to_intake_as_candidate_with_legacy_note"
            elif cat == "LEGACY_UNVERIFIED_APPROVAL":
                action = "move_to_intake_requires_reapproval"
            elif cat == "REQUIRES_REAPPROVAL":
                action = "move_to_intake_requires_reapproval"
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
    # V2.8 — plan must be 1:1 with records (NOT deduped by event_key).
    # Earlier versions deduped plans, which caused the last record's
    # plan to win — moving the FIRST (Lodge) record to intake instead
    # of keeping it. We now walk records in file order and look up
    # the plan by (line_index, event_key).
    plan_by_idx: Dict[int, Dict[str, Any]] = {
        i: p for i, p in enumerate(plan) if p.get("event_key")
    }
    # Also keep a backup by event_key for the rare case where the
    # plan is missing an event_key (e.g. records with no event_key,
    # which are still kept).
    plan_by_ek: Dict[str, Dict[str, Any]] = {}
    for p in plan:
        if p.get("event_key"):
            plan_by_ek.setdefault(p["event_key"], p)  # first wins, not last
    audit_rows: List[Dict[str, Any]] = []
    actions: Dict[str, int] = {}
    failures: List[str] = []

    # Idempotency mirror: scan the intake store for existing event_keys
    from _lib import _calendar_v27_intake as _v27
    intake_path = _v27._intake_calendar_path(brand_id)
    intake_mirror: Dict[str, Dict[str, Any]] = {}
    if intake_path.exists():
        for line in intake_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
                if r.get("event_key"):
                    intake_mirror[r["event_key"]] = r
            except Exception:
                continue

    # V2.8 dedup: track event_keys already kept, prefer the
    # variant with the strongest human action when duplicates exist.
    kept_event_keys: Dict[str, Dict[str, Any]] = {}  # ek -> rec
    removed_for_dedup: List[Dict[str, Any]] = []  # audit

    for idx, line in enumerate(raw_lines):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            kept_lines.append(line)  # preserve unparseable lines as-is
            continue
        ek = rec.get("event_key", "")
        # V2.8 — lookup plan by (idx, event_key) — 1:1 with records
        p = plan_by_idx.get(idx) or plan_by_ek.get(ek)
        if not p:
            # Unclassified or unknown — preserve as-is
            kept_lines.append(line)
            continue
        action = p["action"]
        if action == "keep":
            # V2.8 dedup: if this event_key was already kept, only one
            # survives. The variant with the strongest human-action
            # transition_reason (Lodge/Book/L4 approve/approve) wins.
            # On a tie, the LATER (newer, file-position-later) record
            # wins — the earlier one is dropped with a v28_dedup
            # audit row.
            if ek in kept_event_keys:
                existing = kept_event_keys[ek]
                HUMAN_TR = {"lodge", "book", "l4 approve", "approve"}
                existing_tr = (existing.get("transition_reason") or "").lower().strip()
                this_tr = (rec.get("transition_reason") or "").lower().strip()
                existing_score = 2 if existing_tr in HUMAN_TR else 0
                this_score = 2 if this_tr in HUMAN_TR else 0
                # Strict > means the existing wins; otherwise the
                # later (this) wins. Tie goes to the later record,
                # which is what makes V2.8 idempotent in operator
                # re-deploys.
                if existing_score > this_score:
                    # Existing wins — drop this one with audit
                    audit = _write_audit(
                        brand_id=brand_id,
                        action="v28_dedup_removed_duplicate",
                        actor=actor,
                        source_id=ek,
                        before={
                            "event_key": ek,
                            "title": rec.get("title"),
                            "transition_reason": rec.get("transition_reason"),
                            "status": rec.get("status"),
                            "created_by": rec.get("created_by"),
                        },
                        after=None,
                        extra={
                            "cleanup_reason": "v28_dedup_duplicate_event_key",
                            "kept_record": {
                                "title": existing.get("title"),
                                "transition_reason": existing.get("transition_reason"),
                            },
                            "backup_ref": backup["backup"],
                            "backup_sha256": backup["sha256"],
                        },
                    )
                    audit_rows.append(audit)
                    actions["v28_dedup_removed_duplicate"] = actions.get("v28_dedup_removed_duplicate", 0) + 1
                else:
                    # This wins (stronger OR tie → later). Drop the
                    # existing record with audit.
                    kept_lines = [
                        ln for ln in kept_lines
                        if not (ln.strip().startswith("{")
                                and ek in ln
                                and json.loads(ln).get("event_key") == ek)
                    ]
                    kept_event_keys[ek] = rec
                    kept_lines.append(line)
                    audit = _write_audit(
                        brand_id=brand_id,
                        action="v28_dedup_kept_later",
                        actor=actor,
                        source_id=ek,
                        before={
                            "event_key": ek,
                            "title": existing.get("title"),
                            "transition_reason": existing.get("transition_reason"),
                            "status": existing.get("status"),
                            "created_by": existing.get("created_by"),
                        },
                        after={
                            "event_key": ek,
                            "title": rec.get("title"),
                            "transition_reason": rec.get("transition_reason"),
                            "status": rec.get("status"),
                            "created_by": rec.get("created_by"),
                        },
                        extra={
                            "cleanup_reason": "v28_dedup_duplicate_event_key",
                            "backup_ref": backup["backup"],
                            "backup_sha256": backup["sha256"],
                        },
                    )
                    audit_rows.append(audit)
                    actions["v28_dedup_kept_later"] = actions.get("v28_dedup_kept_later", 0) + 1
            else:
                kept_event_keys[ek] = rec
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
        elif action in ("move_to_intake_as_candidate",
                        "move_to_intake_as_candidate_with_legacy_note",
                        "move_to_intake_requires_reapproval"):
            # Idempotent: if the event_key is already in the intake
            # mirror, don't re-insert.
            tag_record = dict(rec)
            tag_record["status"] = "candidate"
            tag_record["migrated_from_operator_store"] = True
            tag_record["migration_reason"] = "no_human_approval_provenance"
            tag_record["migrated_at"] = datetime.now(timezone.utc).isoformat()
            tag_record["migrated_event_key"] = ek
            if action == "move_to_intake_as_candidate_with_legacy_note":
                tag_record["legacy_provenance_note"] = (
                    "Mass-promoted during 2026-09-17 'CEO demo — land stale "
                    "calendar candidates'. Original approval is not "
                    "considered legitimate for V2.7 architecture; needs "
                    "individual re-approval by an authenticated operator."
                )
            if action == "move_to_intake_requires_reapproval":
                tag_record["provenance_status"] = "REQUIRES_REAPPROVAL"
                tag_record["requires_human_reapproval"] = True
            if ek in intake_mirror:
                actions[f"{action}_noop"] = actions.get(f"{action}_noop", 0) + 1
            else:
                _v27.write_intake_record(brand_id, tag_record)
                intake_mirror[ek] = tag_record
                actions[action] = actions.get(action, 0) + 1
            audit = _write_audit(
                brand_id=brand_id,
                action="move_to_intake",
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
                    "intake_path": str(intake_path),
                },
                extra={
                    "cleanup_step": _step_for_category(p["classification"]),
                    "classification": p["classification"],
                    "cleanup_reason": "v27_production_data_cleanup",
                    "backup_ref": backup["backup"],
                    "backup_sha256": backup["sha256"],
                },
            )
            audit_rows.append(audit)
            # do NOT append to kept_lines
        elif action == "move_to_intake_as_watchlist":
            tag_record = dict(rec)
            tag_record["status"] = "watchlist"
            tag_record["migrated_from_operator_store"] = True
            tag_record["migration_reason"] = "no_human_approval_provenance"
            tag_record["migrated_at"] = datetime.now(timezone.utc).isoformat()
            if ek in intake_mirror:
                actions["move_to_intake_as_watchlist_noop"] = actions.get(
                    "move_to_intake_as_watchlist_noop", 0
                ) + 1
            else:
                _v27.write_intake_record(brand_id, tag_record)
                intake_mirror[ek] = tag_record
                actions["move_to_intake_as_watchlist"] = actions.get(
                    "move_to_intake_as_watchlist", 0
                ) + 1
            audit = _write_audit(
                brand_id=brand_id,
                action="move_to_intake_as_watchlist",
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
                    "cleanup_reason": "v27_production_data_cleanup",
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
        "intake_path": str(intake_path),
    }, 200


def _step_for_category(cat: str) -> str:
    if cat == "TEST_ACCEPTANCE_ARTIFACT":
        return "step_3_remove_v24_acceptance_artifact"
    if cat == "TEMPLATE_DEMO":
        return "step_4_remove_template_demo"
    if cat in ("SCOUT_CANDIDATE", "SCOUT_WATCHLIST", "SCOUT_MASS_PROMOTED_CEO_DEMO"):
        return "step_5_move_scout_to_intake"
    if cat in ("LEGACY_UNVERIFIED_APPROVAL", "REQUIRES_REAPPROVAL"):
        return "step_6_move_unknown_provenance_to_reapproval"
    if cat == "DETERMINISTIC_HOLIDAY":
        return "step_7_move_holidays_to_strategic_moments"
    return "unknown"


# ─── Post-cleanup status ──────────────────────────────────────────────────

def remove_by_calendar_id(brand_id: str, calendar_id: str, actor: Dict[str, Any],
                          reason: str = "test_or_emergency_removal") -> Dict[str, Any]:
    """V2.6 — emergency-only surgical removal of a single record by
    calendar_id. Used to clean up ad-hoc test writes (e.g. a Scout
    status=candidate write that the dry-run's event_key-based cleanup
    cannot target because add_candidate doesn't always set event_key).

    Appends an immutable audit row. Does NOT modify any other records.
    """
    if brand_id not in ("swing-shack", "stick", "bag-drop"):
        raise ValueError(f"invalid brand_id: {brand_id}")
    cal_file = _calendar_path(brand_id)
    if not cal_file.exists():
        return {"ok": False, "error": f"calendar file not found: {cal_file}"}
    with open(cal_file, "r", encoding="utf-8") as f:
        raw_lines = f.readlines()
    kept_lines = []
    removed = None
    for line in raw_lines:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            kept_lines.append(line)
            continue
        if rec.get("calendar_id") == calendar_id and removed is None:
            removed = rec
            continue
        kept_lines.append(line)
    if removed is None:
        return {"ok": False, "error": f"no record found with calendar_id={calendar_id}"}
    tmp = cal_file.with_suffix(cal_file.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(kept_lines)
    tmp.replace(cal_file)
    audit_entry = _write_audit(
        brand_id=brand_id,
        action="emergency_remove_by_calendar_id",
        actor=actor,
        source_id=removed.get("event_key") or removed.get("calendar_id"),
        before={
            "calendar_id": removed.get("calendar_id"),
            "event_key": removed.get("event_key"),
            "title": removed.get("title"),
            "created_by": removed.get("created_by"),
            "status": removed.get("status"),
        },
        after=None,
        extra={
            "cleanup_reason": reason,
            "lines_before": len(raw_lines),
            "lines_after": sum(1 for ln in kept_lines if ln.strip()),
        },
    )
    return {
        "ok": True,
        "removed_calendar_id": calendar_id,
        "lines_before": len(raw_lines),
        "lines_after": sum(1 for ln in kept_lines if ln.strip()),
        "audit_entry": audit_entry,
    }


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
    # V2.8 — duplicate event_key check. The operator store must have
    # at most one active record per event_key after cleanup.
    ekey_counts: Dict[str, int] = {}
    for r in records:
        ek = r.get("event_key")
        if not ek:
            continue
        ekey_counts[ek] = ekey_counts.get(ek, 0) + 1
    duplicate_event_keys = [ek for ek, c in ekey_counts.items() if c > 1]
    return {
        "ok": True,
        "brand_id": brand_id,
        "operator_store_line_count": len(records),
        "unique_event_keys": len(ekey_counts),
        "duplicate_event_keys": duplicate_event_keys,
        "duplicate_event_key_count": len(duplicate_event_keys),
        "classification_summary": {cat: len(recs) for cat, recs in groups.items()},
        "is_clean": (
            all(
                cat == "KEEP" or len(recs) == 0
                for cat, recs in groups.items()
                if cat != "KEEP"
            )
            and len(duplicate_event_keys) == 0
        ),
    }
