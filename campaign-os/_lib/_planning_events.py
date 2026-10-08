"""
_planning_events.py — Friendly wrapper around marketing_calendar.upsert_event.

Used by the Calendar V1 SPA buttons:

  POST /api/planning/v1/<brand>/add-event
  POST /api/planning/v1/<brand>/apply-shopping-moment

Both endpoints translate a friendly front-end payload (date +
type + title + pillar) into a proper records/upsert_event payload
that passes the production-path guards (brand-prefix, source_origin,
season-year). They NEVER bypass guards.

All writes carry:
- event_key  : <brand>:<slug>-<YYYY-MM-DD>  (brand-prefix enforced)
- source_origin : "internal_strategy"  (the only valid enum for
                                          human-initiated writes)
- trusted_for_planning : True  (the human review is the gate)
- calendar_year derived from date
- type       : "moment" | "content" | "campaign" | "reminder" | "watchlist"
"""
from __future__ import annotations

import json
import re
from datetime import date as _date, datetime as _datetime, timedelta as _timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple


# Brand prefix guard — must match _is_authed BANNED list in app.py.
_VALID_BRANDS = ("stick", "swing-shack", "bag-drop")

# Reused for slug building. Only ASCII-safe chars survive.
_SLUG_RE = re.compile(r"[^a-z0-9-]+")
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _validate_brand(brand_id: str) -> None:
    if brand_id not in _VALID_BRANDS:
        raise ValueError(
            f"brand_id '{brand_id}' invalid. Valid: {list(_VALID_BRANDS)}"
        )


def _slugify(s: str, max_len: int = 48) -> str:
    s = (s or "").lower().strip()
    s = _SLUG_RE.sub("-", s).strip("-")
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s or "event"


def _date_iso(d: str) -> _date:
    m = _DATE_RE.match((d or "").strip())
    if not m:
        raise ValueError(f"date '{d}' must be YYYY-MM-DD")
    y, mo, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return _date(y, mo, day)


def _build_event_key(brand_id: str, title: str, day: _date) -> str:
    return f"{brand_id}:{_slugify(title)}-{day.isoformat()}"


def _safe_get(d: Dict[str, Any], *path: str, default=None):
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


# ─────────────────────────────────────────────────────────────────────
# add-event  — used by day-detail popup "+ Add to calendar"
# ─────────────────────────────────────────────────────────────────────

def build_event_record(
    brand_id: str,
    title: str,
    date: str,
    type_: str = "content",
    pillar: Optional[str] = None,
    channel: Optional[str] = None,
    purpose: Optional[str] = None,
    notes: Optional[str] = None,
    added_by: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Translate friendly input → proper calendar record. Pure data — no I/O.

    Enforces:
      - brand prefix on event_key
      - source_origin = "internal_strategy"
      - calendar_year derived from date
      - type in VALID_RECORD_TYPES
      - record passes the season-year guard (callers must supply event_start
        that matches the inferred year)
    """
    _validate_brand(brand_id)
    if not title or not title.strip():
        raise ValueError("title required")
    if type_ not in ("campaign", "content", "moment", "reminder", "watchlist"):
        raise ValueError(f"type '{type_}' invalid")
    day = _date_iso(date)

    record: Dict[str, Any] = {
        "event_key": _build_event_key(brand_id, title, day),
        "brand_id": brand_id,
        "title": title.strip(),
        "type": type_,
        "event_start": day.isoformat(),
        "event_end": day.isoformat(),
        "calendar_year": day.year,
        "season_label": _infer_season(day),
        "source_origin": "internal_strategy",
        "trusted_for_planning": True,
        "verification_status": "verified_primary",
        "tier": "C-PIN",
        "production_path_warnings": [],
        "production_path_notes": [
            f"Added from Calendar V1 SPA by '{added_by or 'operator'}' "
            f"at {_datetime.utcnow().isoformat()}Z."
        ],
    }
    if pillar:
        record["pillar"] = pillar
        # `pillars` (a list) is the canonical field: the calendar view and
        # the Brief engine read it. `pillar` alone is invisible to both.
        record["pillars"] = [pillar]
    if channel:
        record["channel"] = channel
    if purpose:
        record["purpose"] = purpose
    if notes:
        record["notes"] = notes
    if added_by:
        record["added_by"] = added_by
    if extra:
        # Only allow pass-through of safe, recognised fields.
        for k in ("category", "lanes", "deadlines", "phases", "tags"):
            if k in extra and k not in record:
                record[k] = extra[k]
    return record


def _infer_season(d: _date) -> str:
    m = d.month
    if m in (12, 1, 2):
        return "Summer-SA"
    if m in (3, 4, 5):
        return "Autumn-SA"
    if m in (6, 7, 8):
        return "Winter-SA"
    return "Spring-SA"


# ──────────────────────────────────────────────────────────────────────
# Calendar V2.2 — Slice 3: Approve candidate → spine.
# Takes a candidate entry from data/brand-planning/<brand>-candidates-*.json
# and translates it to a marketing_calendar.upsert_event-ready record.
# Preserves brand + title + dates + sources/evidence + confidence + tier +
# runway recommendation. Marks source_origin = internal_strategy. Writes a
# parallel audit record to data/calendar-audit/<brand>-approvals.jsonl.
# ──────────────────────────────────────────────────────────────────────


def _slugify_event_key(s: str, max_len: int = 96) -> str:
    """Slug for a canonical event key. Preserves meaningful words (no truncation
    chops). ASCII-safe, hyphens only, lowercased. Length capped at max_len.

    V2.3 rule (operator directive): do NOT chop meaningful words. The full
    slug is used in the event_key path; trailing overflow beyond max_len
    is replaced with a stable short hash so distinct candidates cannot
    collide on long names.
    """
    s = (s or "").lower().strip()
    if not s:
        return "event"
    # Replace any non-alphanum chunk with a single hyphen; trim hyphens.
    cleaned = _SLUG_RE.sub("-", s).strip("-")
    if len(cleaned) <= max_len:
        return cleaned or "event"
    # Long slug: keep the meaningful head, append a stable short hash from
    # the original raw title so two truncated names are still distinguishable.
    head = cleaned[:max_len].rstrip("-")
    import hashlib as _hl
    tail = _hl.sha1(s.encode("utf-8")).hexdigest()[:8]
    return f"{head}-{tail}"


def _slug_from_candidate_id(cid: str) -> str:
    """Extract a stable slug from a candidate id like 'candidate-alfred-…'.

    V2.3: candidate ids are typically the canonical candidate name already
    (e.g. 'candidate-alfred-dunhill-championship-2027'), so the 'candidate-'
    prefix is the only thing stripped. No middle-of-word truncation.
    """
    if not cid:
        return "event"
    raw = cid.replace("candidate-", "", 1).replace("candidate_", "", 1)
    return _slugify_event_key(raw, max_len=48)


def write_audit_entry(
    brand_id: str,
    action: str,
    actor: Optional[Any] = None,
    source_id: Optional[str] = None,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    audit_dir: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append a single immutable audit row. Returns the entry written.

    Default audit_dir is <DATA_DIR or .>/calendar-audit/. Each row is
    append-only JSONL — never overwritten, never truncated. The audit
    log is the ground truth for human-initiated Calendar state changes.

    V2.3 actor: actor may be a string (legacy "operator") OR a structured
    dict produced by _resolve_v23_actor() in app.py. Structured actors
    are stored verbatim under "actor": {actor_id, actor_id_method,
    actor_display_name, actor_display_name_source, actor_ip_prefix,
    actor_session_cookie_digest_prefix, actor_user_agent_marker,
    actor_authenticated}. No fake reviewer names ever appear.

    V2.3 `extra`: optional dict of additional structured fields (e.g.
    {"revert": True, "revert_reason": "...", "previous_event_key": "..."}).
    Useful for the revert-test-approval admin endpoint.
    """
    if audit_dir is None:
        import os as _os
        base = _os.environ.get("DATA_DIR") or _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            "data",
        )
        audit_dir = _os.path.join(base, "calendar-audit")

    import os as _os
    _os.makedirs(audit_dir, exist_ok=True)

    entry: Dict[str, Any] = {
        "ts": _datetime.utcnow().isoformat() + "Z",
        "brand_id": brand_id,
        "action": action,
        "actor": _serialize_actor_for_audit(actor),
        "source_id": source_id or None,
        "before": before or None,
        "after": after or None,
    }
    if extra:
        entry.update(extra)

    audit_file = _os.path.join(audit_dir, f"{brand_id}-approvals.jsonl")
    with open(audit_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def _marketing_calendar_storage_paths(
    brand_id: str,
) -> List[Any]:
    """V2.3 — locate the marketing_calendar jsonl file across the
    proper path candidates.

    The marketing_calendar module writes to:
      DATA_DIR/intelligence/marketing-calendar/<brand>.jsonl        (canonical)
      /app/data/intelligence/marketing-calendar/<brand>.jsonl        (baked fallback)
      <repo>/data/intelligence/marketing-calendar/<brand>.jsonl      (local dev fallback)
    """
    import os as _os
    candidates = []
    data_dir = _os.environ.get("DATA_DIR") or "/data/campaign-os"
    candidates.append(_os.path.join(data_dir, "intelligence", "marketing-calendar", f"{brand_id}.jsonl"))
    candidates.append(_os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
        "data", "intelligence", "marketing-calendar", f"{brand_id}.jsonl",
    ))
    return candidates


def revert_event_approval(
    brand_id: str,
    event_key: str,
    actor: Optional[Any] = None,
    reason: str = "test_approval_reverted",
) -> Dict[str, Any]:
    """V2.3 — remove an operator-approved candidate from the canonical
    spine and log the revert.

    Scans the marketing_calendar jsonl + the audit log. If a record with
    matching event_key is found, removes it from the jsonl. Appends a
    revert entry to the audit log.

    Used by the admin endpoint POST /api/planning/<brand>/_internal/
    revert-test-approval?event_key=... OR by the multi-key reset path.

    Returns a small dict with ok + before/after counts.
    """
    import os as _os
    base = _os.environ.get("DATA_DIR") or _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
        "data",
    )
    audit_dir = _os.path.join(base, "calendar-audit")

    cal_files = _marketing_calendar_storage_paths(brand_id)

    before_count = 0
    after_count = 0
    audit_before: Optional[Dict[str, Any]] = None
    audit_after: Optional[Dict[str, Any]] = None
    removed = False
    cal_file_used: Optional[str] = None

    for cal_file in cal_files:
        if not _os.path.exists(cal_file):
            continue
        try:
            with open(cal_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            kept_lines = []
            for line in lines:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    kept_lines.append(line)
                    continue
                if rec.get("event_key") == event_key:
                    if not removed:
                        audit_before = {
                            "event_key": rec.get("event_key"),
                            "title": rec.get("title"),
                            "tier": rec.get("tier"),
                            "event_start": rec.get("event_start"),
                            "event_end": rec.get("event_end"),
                            "revision": rec.get("revision"),
                        }
                        removed = True
                    # Drop this record.
                    continue
                kept_lines.append(line)
            with open(cal_file, "w", encoding="utf-8") as f:
                f.writelines(kept_lines)
            before_count = len(lines)
            after_count = len(kept_lines)
            cal_file_used = cal_file
            break
        except Exception as e:
            return {"ok": False, "error": f"failed to clean jsonl: {e}"}

    # Always log the revert, even if there was nothing to remove (so the
    # audit shows a NOOP revert was attempted and explained why).
    audit_entry = write_audit_entry(
        brand_id=brand_id,
        action="revert_test_approval",
        actor=actor,
        source_id=event_key,
        before=audit_before,
        after=audit_after,
        audit_dir=audit_dir,
        extra={
            "revert_reason": reason,
            "removed_record": removed,
            "jsonl_before_lines": before_count,
            "jsonl_after_lines": after_count,
            "cal_file_used": cal_file_used,
        },
    )
    return {
        "ok": True,
        "removed_record": removed,
        "jsonl_before_lines": before_count,
        "jsonl_after_lines": after_count,
        "cal_file_used": cal_file_used,
        "audit_entry": audit_entry,
    }


def bulk_revert_event_approvals(
    brand_id: str,
    actor: Optional[Any] = None,
    since_iso: Optional[str] = None,
    match_event_keys: Optional[List[str]] = None,
    reason: str = "bulk_revert",
) -> Dict[str, Any]:
    """V2.3 — bulk wrapper for the admin endpoint that wipes test pollution.

    Either `since_iso` filters audit entries older than the boundary
    (revert the matching event_keys) OR `match_event_keys` is supplied
    directly. Whitelist narrowing only — never blindly wipes everything.
    """
    import os as _os
    base = _os.environ.get("DATA_DIR") or _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
        "data",
    )
    audit_dir = _os.path.join(base, "calendar-audit")
    audit_file = _os.path.join(audit_dir, f"{brand_id}-approvals.jsonl")

    targets: List[str] = list(match_event_keys or [])
    if since_iso:
        try:
            since_dt = _datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
        except Exception:
            return {"ok": False, "error": f"invalid since_iso: {since_iso}"}
        if not _os.path.exists(audit_file):
            return {"ok": True, "reverted": [], "skipped": list(targets), "reason": "no audit file"}
        with open(audit_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("action") != "approve_candidate":
                    continue
                ek = rec.get("after", {}) or {}
                ek = ek.get("event_key")
                ts_raw = rec.get("ts")
                if not (ek and ts_raw):
                    continue
                try:
                    ts = _datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                except Exception:
                    continue
                if ts >= since_dt:
                    targets.append(ek)
    targets = sorted(set(targets))
    reverted = []
    for ek in targets:
        result = revert_event_approval(brand_id=brand_id, event_key=ek, actor=actor, reason=reason)
        reverted.append({
            "event_key": ek,
            "ok": result.get("ok"),
            "removed_record": result.get("removed_record"),
            "jsonl_before_lines": result.get("jsonl_before_lines"),
            "jsonl_after_lines": result.get("jsonl_after_lines"),
        })
    return {
        "ok": True,
        "reverted": reverted,
        "event_keys_targeted": targets,
    }


def _serialize_actor_for_audit(actor: Any) -> Any:
    """Forward the actor field to the audit row in source-attested form.

    Strings get a small wrapper dict so we can record the disambiguation
    method (legacy default fallback). Structured dicts are stored verbatim
    because every field has provenance attached by the caller.
    """
    if isinstance(actor, dict):
        return actor
    if isinstance(actor, str) and actor.strip():
        return {
            "actor_id": None,
            "actor_id_method": "legacy_string_fallback",
            "actor_display_name": actor,
            "actor_display_name_source": "legacy_caller_supplied_string",
            "actor_authenticated": False,
            "upgrade_hint": "Caller should pass _resolve_v23_actor() output for stable identity.",
        }
    return None


def _render_actor_label(actor: Any) -> str:
    """Render a short, truthful human-readable actor label for production_path_notes.

    Never invents a name. Falls back to the cookie digest prefix when no
    readable name is present.
    """
    if isinstance(actor, dict):
        if actor.get("actor_display_name"):
            return f"[self-declared: {actor.get('actor_display_name')[:40]}!] actor_id={actor.get('actor_id','?')}"
        return f"actor_id={actor.get('actor_id','?')} (cookie_digest_prefix={actor.get('actor_session_cookie_digest_prefix','?')})"
    if isinstance(actor, str) and actor.strip():
        return f"[legacy-actor-string] {actor}"
    return "actor_id=<unset>"


def _build_event_key_from_candidate(
    brand_id: str, candidate: Dict[str, Any]
) -> str:
    """Stable, idempotent event_key for a candidate approval.

    V2.3 format: <brand>:<full-slug>:<YYYY-MM-DD>

    Full slug (e.g. 'alfred-dunhill-championship') is preserved verbatim —
    no middle-of-word truncation. Short hashes are appended only when the
    slug genuinely overflows the max length cap. The date uses
    candidate.start or public_peak, whichever is the most specific
    applicable ISO date. If neither is valid, raises ValueError because
    we cannot satisfy the season-year guard and must refuse to write.
    """
    slug = _slug_from_candidate_id(candidate.get("id") or "")
    for k in ("start", "public_peak"):
        raw = candidate.get(k)
        if not isinstance(raw, str) or not raw:
            continue
        try:
            _date_iso(raw)
            return f"{brand_id}:{slug}:{raw}"
        except ValueError:
            continue
    raise ValueError(
        f"candidate '{candidate.get('id')}' has no usable start/public_peak date — "
        "cannot create a verified spine entry without a date."
    )


def build_approval_record(
    brand_id: str,
    candidate: Dict[str, Any],
    actor: Optional[Any] = None,
) -> Dict[str, Any]:
    """Translate a Calendar V2 candidate → marketing_calendar.upsert_event input.

    Preserves every evidence field the candidate carries so the spine entry
    is auditable. Mark as source_origin = internal_strategy (the only valid
    enum for human-initiated writes). trusted_for_planning = True.

    Idempotency: caller-supplied event_key encodes brand+slug+date so the same
    candidate approved twice resolves to the same event_key, and
    marketing_calendar.upsert_event returns 'noop' on the second call.

    V2.3 actor: may be a string (legacy "operator") OR a structured dict
    produced by _resolve_v23_actor() in app.py. Structured actors carry
    actor_id, actor_id_method, optional actor_display_name + provenance
    fields. They're forwarded verbatim to production_path_notes so the
    audit row preserves the actual fingerprint, not a fake name.

    Raises ValueError when:
      - brand_id invalid
      - candidate has no verifiable start/public_peak date
        (a research_lead without a date cannot be approved)
    """
    _validate_brand(brand_id)

    # Reject research_leads without dates — Slice 3 explicit rule.
    start = candidate.get("start")
    public_peak = candidate.get("public_peak")
    end = candidate.get("end")
    if not (isinstance(start, str) and start) and not (isinstance(public_peak, str) and public_peak):
        raise ValueError(
            f"candidate '{candidate.get('id')}' has no start/public_peak date — "
            "this is a research_lead and cannot be approved. Verify the date first."
        )

    start_d: Optional[_date] = None
    try:
        first_date_str = start if isinstance(start, str) and start else public_peak
        if first_date_str:
            start_d = _date_iso(first_date_str)
    except ValueError as e:
        raise ValueError(f"candidate date is malformed: {e}")

    end_d: Optional[_date] = None
    if isinstance(end, str) and end:
        try:
            end_d = _date_iso(end)
        except ValueError:
            end_d = start_d
    if end_d is None:
        end_d = start_d

    peak_d: Optional[_date] = None
    if isinstance(public_peak, str) and public_peak:
        try:
            peak_d = _date_iso(public_peak)
        except ValueError:
            peak_d = None

    title = (candidate.get("name") or "").strip() or f"(approved candidate {candidate.get('id')})"
    tier = (candidate.get("suggested_tier") or "C-PIN").strip()
    confidence = (candidate.get("confidence") or "low").strip().lower()

    record: Dict[str, Any] = {
        "event_key": _build_event_key_from_candidate(brand_id, candidate),
        "brand_id": brand_id,
        # V2.10 — explicit approved status. Without this, the new
        # event_key row in the operator-store is created with status=None
        # and the timeline filter (`status == "approved"`) skips it.
        # Result: the candidate is "approved in store but invisible in
        # calendar" — the exact V2.10 §5 regression.
        "status": "approved",
        "title": title,
        "type": "moment",
        "event_start": (start_d or _date.today()).isoformat(),
        "event_end": (end_d or start_d or _date.today()).isoformat(),
        "calendar_year": (start_d or _date.today()).year,
        "season_label": _infer_season(start_d or _date.today()),
        "source_origin": "internal_strategy",
        "trusted_for_planning": True,
        # Carry over evidence / provenance so the spine entry is auditable.
        "production_path_warnings": [],
        "production_path_notes": [
            f"Approved from Calendar V2 candidate by {(_render_actor_label(actor))} "
            f"at {_datetime.utcnow().isoformat()}Z. Source: {candidate.get('source','(none)')}."
        ],
        "evidence": {
            "source": candidate.get("source"),
            "source_date": candidate.get("source_date"),
            "geography": candidate.get("geography"),
            "relevance": candidate.get("relevance_to_swing_shack") or candidate.get("relevance"),
            "opportunity": candidate.get("opportunity"),
            "why_it_matters": candidate.get("why_it_matters"),
            "verification_status": candidate.get("verification_status"),
            "venue_status": candidate.get("venue_status"),
            "date_status": candidate.get("date_status"),
        },
        "candidate_metadata": {
            "candidate_id": candidate.get("id"),
            "category": candidate.get("category"),
            "tier": tier,
            "confidence": confidence,
            "recommended_lead_time_weeks": candidate.get("recommended_lead_time_weeks"),
        },
    }
    if peak_d is not None:
        record["public_peak"] = peak_d.isoformat()
    if confidence == "high":
        record["verification_status"] = "verified_primary"
    elif confidence == "medium":
        record["verification_status"] = "verified_secondary"
    else:
        record["verification_status"] = candidate.get("verification_status") or "unverified"
    if tier:
        record["tier"] = tier

    # Carry derived runway from any pre-existing phase suggestion on the candidate.
    rl_weeks = candidate.get("recommended_lead_time_weeks")
    if rl_weeks and start_d is not None:
        try:
            rl_weeks_i = int(rl_weeks)
        except (TypeError, ValueError):
            rl_weeks_i = None
        if rl_weeks_i:
            record["recommended_lead_time_weeks"] = rl_weeks_i
            # Add a planning note so a human can decide whether to commit.
            try:
                plan_start = start_d - _timedelta(weeks=rl_weeks_i)
                record["candidate_metadata"]["suggested_planning_start"] = plan_start.isoformat()
                record["production_path_notes"].append(
                    f"Suggested planning start: {plan_start.isoformat()} "
                    f"({rl_weeks_i} weeks before {(start_d).isoformat()})."
                )
            except Exception:
                pass

    return record


# ──────────────────────────────────────────────────────────────────────
# apply-shopping-moment  — used by "Add all suggested dates" button
# ──────────────────────────────────────────────────────────────────────

def build_shopping_moment_records(
    brand_id: str,
    moment_id: Optional[str] = None,
    moment_name: Optional[str] = None,
    public_peak: Optional[str] = None,
    planning_start: Optional[str] = None,
    campaign_window_start: Optional[str] = None,
    campaign_window_end: Optional[str] = None,
    deadlines: Optional[Iterable[Dict[str, Any]]] = None,
    phases: Optional[Iterable[Dict[str, Any]]] = None,
    added_by: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Bulk-build every deadline + phase as an independent event record.

    Each phase becomes its own `moment` record scoped to the moment's
    phase start date. Each deadline becomes its own `reminder` record.

    Idempotency: the event_key encodes `<brand>:<moment-slug>-<date>`,
    so calling twice with the same input yields the same records (the
    upstream upsert_event returns `noop` for unchanged material input).

    Returns: ordered list of records (deadlines + phases, all sharing
    the same parent event_key prefix of `<brand>:<moment-slug>`).
    """
    _validate_brand(brand_id)
    if not moment_name:
        raise ValueError("moment_name required")
    if not public_peak:
        raise ValueError("public_peak required (YYYY-MM-DD)")

    peak_day = _date_iso(public_peak)
    moment_slug = _slugify(moment_name, max_len=24)
    prefix = f"{brand_id}:{moment_slug}"
    base_year = peak_day.year
    records: List[Dict[str, Any]] = []

    # Parent event record (the moment itself, on public_peak)
    parent: Dict[str, Any] = {
        "event_key": f"{prefix}-{peak_day.isoformat()}",
        "brand_id": brand_id,
        "title": moment_name.strip(),
        "type": "moment",
        "event_start": peak_day.isoformat(),
        "event_end": peak_day.isoformat(),
        "calendar_year": base_year,
        "season_label": _infer_season(peak_day),
        "source_origin": "internal_strategy",
        "trusted_for_planning": True,
        "verification_status": "verified_primary",
        "tier": "A-PIN" if moment_id and "A-PIN" in (moment_id or "") else "B-PIN",
        "shopping_moment": True,
        "production_path_warnings": [],
        "production_path_notes": [
            f"Shopping moment applied from Calendar V1 SPA by "
            f"'{added_by or 'operator'}' at {_datetime.utcnow().isoformat()}Z."
        ],
    }
    if moment_id:
        parent["source_id"] = moment_id
    if planning_start:
        parent["planning_start"] = planning_start
    if campaign_window_start:
        parent["campaign_window_start"] = campaign_window_start
    if campaign_window_end:
        parent["campaign_window_end"] = campaign_window_end
    records.append(parent)

    # Deadlines → reminders
    for d in (deadlines or []):
        if not isinstance(d, dict):
            continue
        due = d.get("due") or d.get("date") or ""
        label = d.get("label") or d.get("title") or "deadline"
        try:
            due_day = _date_iso(due)
        except ValueError:
            continue
        records.append({
            "event_key": f"{prefix}-dl-{_slugify(label, 16)}-{due_day.isoformat()}",
            "brand_id": brand_id,
            "title": f"{moment_name.strip()}: {label}",
            "type": "reminder",
            "event_start": due_day.isoformat(),
            "event_end": due_day.isoformat(),
            "calendar_year": due_day.year,
            "season_label": _infer_season(due_day),
            "source_origin": "internal_strategy",
            "trusted_for_planning": True,
            "verification_status": "verified_primary",
            "tier": "C-PIN",
            "parent_event_key": parent["event_key"],
            "production_path_warnings": [],
            "production_path_notes": [
                f"Deadline applied from Calendar V1 SPA by "
                f"'{added_by or 'operator'}'."
            ],
        })

    # Phases → moment events (one per phase)
    for p in (phases or []):
        if not isinstance(p, dict):
            continue
        ps = p.get("start") or p.get("date") or ""
        label = p.get("label") or "phase"
        try:
            start_day = _date_iso(ps)
        except ValueError:
            continue
        records.append({
            "event_key": f"{prefix}-ph-{_slugify(label, 16)}-{start_day.isoformat()}",
            "brand_id": brand_id,
            "title": f"{moment_name.strip()} — {label}",
            "type": "moment",
            "event_start": start_day.isoformat(),
            "event_end": start_day.isoformat(),
            "calendar_year": start_day.year,
            "season_label": _infer_season(start_day),
            "source_origin": "internal_strategy",
            "trusted_for_planning": True,
            "verification_status": "verified_primary",
            "tier": "C-PIN",
            "parent_event_key": parent["event_key"],
            "production_path_warnings": [],
            "production_path_notes": [
                f"Runway phase applied from Calendar V1 SPA by "
                f"'{added_by or 'operator'}'."
            ],
        })

    return records
