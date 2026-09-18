"""Ops agent roster for /api/ops/agents — pure functions, no Flask."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from _lib.brand_validate import validate_brand_id
from _lib.ops_layers import worst_verdict

SCHEMA = "campaign-os/ops-agents/v1"
ROSTER_SUBDIR = "ops-agents"
VALID_STATUS = frozenset({"OK", "LATE", "FAILED", "NEVER"})
VALID_LAYERS = frozenset({f"L{i}" for i in range(1, 8)} | {"all"})
AGENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
QUEUE_ROW_KEYS = frozenset({"id", "layer", "agent", "brand", "action", "payload_ref", "status"})
QUEUE_SCHEMA = "campaign-os/agent-queue/v1"

KNOWN_AGENTS: tuple[dict[str, Any], ...] = (
    {
        "id": "cos-foreman",
        "profile": "cos-foreman",
        "kind": "hermes",
        "layer": "all",
        "schedule": "on demand + 15m",
        "enabled": False,
        "expected_every_s": None,
    },
    {
        "id": "cos-scout",
        "profile": "cos-scout",
        "kind": "hermes",
        "layer": "L3",
        "schedule": "weekly + queue",
        "enabled": False,
        "expected_every_s": 604800,
    },
    {
        "id": "cos-reactive",
        "profile": "cos-reactive",
        "kind": "hermes",
        "layer": "L3",
        "schedule": "daily 07:30",
        "enabled": False,
        "expected_every_s": 86400,
    },
    {
        "id": "cos-interpreter",
        "profile": "cos-interpreter",
        "kind": "hermes",
        "layer": "L3",
        "schedule": "daily after reco",
        "enabled": False,
        "expected_every_s": 86400,
    },
    {
        "id": "cos-triage",
        "profile": "cos-triage",
        "kind": "hermes",
        "layer": "L3",
        "schedule": "daily 08:00",
        "enabled": False,
        "expected_every_s": 86400,
    },
    {
        "id": "pi-score",
        "profile": "pi-score",
        "kind": "pi",
        "layer": "L3",
        "schedule": "one-shot",
        "enabled": False,
        "expected_every_s": None,
    },
)

_SEED_BY_ID = {row["id"]: row for row in KNOWN_AGENTS}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(iso: str) -> Optional[datetime]:
    if not iso:
        return None
    try:
        text = str(iso).replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _age_seconds(iso: str) -> Optional[float]:
    dt = _parse_iso(iso)
    if dt is None:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0.0, (now - dt).total_seconds())


def _coerce_status(raw: Any) -> str:
    value = str(raw or "OK").upper()
    if value in VALID_STATUS:
        return value
    if value in {"ERROR", "FAIL"}:
        return "FAILED"
    return "FAILED"


def _coerce_layer(raw: Any) -> str:
    value = str(raw or "L3")
    if value in VALID_LAYERS:
        return value
    return "L3"


def _clamp_text(value: Any, limit: int) -> str:
    return str(value or "")[:limit]


def _clamp_writes(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for item in values[:20]:
        out.append(_clamp_text(item, 200))
    return out


def normalise_heartbeat(body: dict[str, Any]) -> dict[str, Any]:
    """Validate and clamp a heartbeat body; raises ValueError on bad id."""
    if not isinstance(body, dict):
        raise ValueError("body must be an object")
    agent_id = str(body.get("id") or "").strip()
    if not AGENT_ID_RE.match(agent_id):
        raise ValueError("invalid agent id")
    seed = _SEED_BY_ID.get(agent_id, {})
    profile = _clamp_text(body.get("profile") or seed.get("profile") or agent_id, 64)
    kind = _clamp_text(body.get("kind") or seed.get("kind") or "unknown", 32)
    layer = _coerce_layer(body.get("layer") or seed.get("layer") or "L3")
    status = _coerce_status(body.get("status"))
    action = _clamp_text(body.get("action"), 200)
    writes = _clamp_writes(body.get("writes"))
    skill = _clamp_text(body.get("skill"), 120)
    enabled_raw = body.get("enabled")
    if enabled_raw is None:
        enabled = bool(seed.get("enabled", False))
    else:
        enabled = bool(enabled_raw)
    received_at = _utc_now_iso()
    return {
        "schema": SCHEMA,
        "id": agent_id,
        "profile": profile,
        "kind": kind,
        "layer": layer,
        "status": status,
        "action": action,
        "writes": writes,
        "skill": skill,
        "enabled": enabled,
        "last_heartbeat_at": received_at,
        "received_at": received_at,
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def write_heartbeat(base_dir: Path, hb: dict[str, Any]) -> dict[str, Any]:
    """Persist one agent heartbeat to base_dir/<id>.json."""
    path = base_dir / f"{hb['id']}.json"
    _atomic_write_json(path, hb)
    return hb


def _read_heartbeat_file(path: Path) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _derive_last_status(
    *,
    reported_status: str,
    last_heartbeat_at: Optional[str],
    expected_every_s: Optional[int],
) -> str:
    if not last_heartbeat_at:
        return "NEVER"
    status = _coerce_status(reported_status)
    if status in {"FAILED"}:
        return "FAILED"
    if expected_every_s:
        age = _age_seconds(last_heartbeat_at)
        if age is not None and age > expected_every_s * 1.5:
            return "LATE"
    return "OK"


def read_roster(base_dir: Path) -> list[dict[str, Any]]:
    """Return seed ∪ observed agents with derived last_status."""
    observed: dict[str, dict[str, Any]] = {}
    if base_dir.is_dir():
        for path in sorted(base_dir.glob("*.json")):
            if path.name == "enqueue.jsonl":
                continue
            data = _read_heartbeat_file(path)
            if not data:
                continue
            agent_id = str(data.get("id") or path.stem)
            if not AGENT_ID_RE.match(agent_id):
                continue
            observed[agent_id] = data

    roster: list[dict[str, Any]] = []
    seen: set[str] = set()

    for seed in KNOWN_AGENTS:
        agent_id = seed["id"]
        seen.add(agent_id)
        hb = observed.get(agent_id)
        roster.append(_merge_agent_row(seed, hb))

    for agent_id, hb in sorted(observed.items()):
        if agent_id in seen:
            continue
        roster.append(_merge_agent_row(None, hb))

    return roster


def _merge_agent_row(seed: Optional[dict[str, Any]], hb: Optional[dict[str, Any]]) -> dict[str, Any]:
    agent_id = (hb or seed or {}).get("id") or ""
    seed = seed or {}
    hb = hb or {}
    expected_every_s = seed.get("expected_every_s")
    last_heartbeat_at = hb.get("last_heartbeat_at")
    reported_status = hb.get("status") or "NEVER"
    enabled = hb.get("enabled") if "enabled" in hb else seed.get("enabled", False)
    return {
        "id": agent_id,
        "profile": hb.get("profile") or seed.get("profile") or agent_id,
        "kind": hb.get("kind") or seed.get("kind") or "unknown",
        "layer": _coerce_layer(hb.get("layer") or seed.get("layer") or "L3"),
        "schedule": seed.get("schedule") or "—",
        "enabled": bool(enabled),
        "last_heartbeat_at": last_heartbeat_at,
        "last_status": _derive_last_status(
            reported_status=reported_status,
            last_heartbeat_at=last_heartbeat_at,
            expected_every_s=expected_every_s,
        ),
        "last_action": hb.get("action") or None,
        "last_writes": hb.get("writes") or [],
        "skill": hb.get("skill") or None,
    }


def roster_verdict(agents: list[dict[str, Any]]) -> str:
    """Worst last_status among agents that have reported at least once."""
    statuses = [
        str(a.get("last_status") or "NEVER").upper()
        for a in agents
        if a.get("last_heartbeat_at")
    ]
    return worst_verdict(statuses) if statuses else "NEVER"


def build_agents_payload(base_dir: Path) -> dict[str, Any]:
    agents = read_roster(base_dir)
    return {
        "schema": SCHEMA,
        "generated_at": _utc_now_iso(),
        "agents": agents,
    }


def _validate_queue_row(row: dict[str, str]) -> dict[str, str]:
    clean = {k: str(row.get(k, "")) for k in QUEUE_ROW_KEYS}
    missing = QUEUE_ROW_KEYS - set(clean)
    if missing:
        raise ValueError(f"queue row missing keys: {sorted(missing)}")
    clean["brand"] = validate_brand_id(clean["brand"], allow_sentinel=True)
    return clean


def _read_queue_doc(queue_path: Path) -> dict[str, Any]:
    if not queue_path.is_file():
        return {"schema": QUEUE_SCHEMA, "generated_at": _utc_now_iso(), "rows": []}
    try:
        data = json.loads(queue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema": QUEUE_SCHEMA, "generated_at": _utc_now_iso(), "rows": []}
    if not isinstance(data, dict):
        return {"schema": QUEUE_SCHEMA, "generated_at": _utc_now_iso(), "rows": []}
    rows = data.get("rows")
    if not isinstance(rows, list):
        rows = []
    return {
        "schema": str(data.get("schema") or QUEUE_SCHEMA),
        "generated_at": str(data.get("generated_at") or _utc_now_iso()),
        "rows": rows,
    }


def normalise_enqueue(body: dict[str, Any]) -> dict[str, str]:
    """Validate enqueue body; raises ValueError on bad agent id."""
    if not isinstance(body, dict):
        raise ValueError("body must be an object")
    agent = str(body.get("agent") or "").strip()
    if not AGENT_ID_RE.match(agent):
        raise ValueError("invalid agent id")
    brand = validate_brand_id(body.get("brand"))
    reason = _clamp_text(body.get("reason") or "manual", 64)
    row_id = f"manual-{brand}-{agent}-{reason}"[:80]
    payload_ref = body.get("payload_ref")
    if payload_ref is not None:
        payload_ref = _clamp_text(payload_ref, 120)
    else:
        payload_ref = f"ops-agents/enqueue#{reason}"
    action = _clamp_text(body.get("action") or "enqueue", 64)
    return _validate_queue_row(
        {
            "id": row_id,
            "layer": "L3",
            "agent": agent,
            "brand": brand,
            "action": action,
            "payload_ref": payload_ref,
            "status": "pending",
        }
    )


def append_enqueue_row(data_dir: Path, row: dict[str, str]) -> tuple[str, int]:
    """Append one pending row to agent-queue.json; returns (row_id, pending_count)."""
    queue_path = data_dir / "agent-queue.json"
    doc = _read_queue_doc(queue_path)
    rows = doc.get("rows") or []
    if not isinstance(rows, list):
        rows = []
    existing_ids = {
        str(r.get("id"))
        for r in rows
        if isinstance(r, dict) and r.get("id")
    }
    if row["id"] not in existing_ids:
        rows.append(row)
    rows = sorted(
        [_validate_queue_row(r) for r in rows if isinstance(r, dict)],
        key=lambda item: item["id"],
    )
    doc["rows"] = rows
    doc["generated_at"] = _utc_now_iso()
    doc["schema"] = QUEUE_SCHEMA
    _atomic_write_json(queue_path, doc)
    pending = sum(1 for r in rows if r.get("status") == "pending")
    return row["id"], pending


DONE_RETENTION_MAX = 200
QUEUE_DOC_SOFT_CAP = 500


def _queue_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    pending = sum(1 for r in rows if r.get("status") == "pending")
    done = sum(1 for r in rows if r.get("status") == "done")
    return {"pending": pending, "done": done, "total": len(rows)}


def _prune_done_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep newest DONE_RETENTION_MAX done rows; drop manual done rows when over soft cap."""
    pending = [r for r in rows if r.get("status") == "pending"]
    other = [r for r in rows if r.get("status") not in {"pending", "done"}]
    done = sorted(
        [r for r in rows if r.get("status") == "done"],
        key=lambda item: item["id"],
    )
    if len(done) > DONE_RETENTION_MAX:
        done = done[-DONE_RETENTION_MAX:]
    kept = sorted(pending + other + done, key=lambda item: item["id"])
    while len(kept) > QUEUE_DOC_SOFT_CAP:
        manual_done_idx = next(
            (
                idx
                for idx, row in enumerate(kept)
                if row.get("status") == "done" and str(row.get("id", "")).startswith("manual-")
            ),
            None,
        )
        if manual_done_idx is None:
            break
        kept.pop(manual_done_idx)
    return kept


def list_queue_rows(
    data_dir: Path,
    *,
    agent: Optional[str] = None,
    brand: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 200,
) -> dict[str, Any]:
    """Return filtered agent-queue rows for GET /api/ops/agent-queue."""
    queue_path = data_dir / "agent-queue.json"
    doc = _read_queue_doc(queue_path)
    rows = doc.get("rows") or []
    if not isinstance(rows, list):
        rows = []
    clean: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            clean.append(_validate_queue_row(row))
        except ValueError:
            continue
    if agent:
        clean = [r for r in clean if r.get("agent") == agent]
    if brand:
        clean = [r for r in clean if r.get("brand") == brand]
    if status:
        clean = [r for r in clean if r.get("status") == status]
    clean = sorted(clean, key=lambda item: item["id"])
    if limit > 0:
        clean = clean[:limit]
    all_rows = sorted(
        [_validate_queue_row(r) for r in rows if isinstance(r, dict)],
        key=lambda item: item["id"],
    )
    return {
        "schema": str(doc.get("schema") or QUEUE_SCHEMA),
        "generated_at": str(doc.get("generated_at") or _utc_now_iso()),
        "rows": clean,
        "counts": _queue_counts(all_rows),
    }


def mark_row_done(
    data_dir: Path,
    row_id: str,
    *,
    agent: Optional[str] = None,
) -> dict[str, Any]:
    """Mark one queue row done; returns {id, status, pending}. Raises LookupError if missing."""
    queue_path = data_dir / "agent-queue.json"
    doc = _read_queue_doc(queue_path)
    rows = doc.get("rows") or []
    if not isinstance(rows, list):
        rows = []
    clean = sorted(
        [_validate_queue_row(r) for r in rows if isinstance(r, dict)],
        key=lambda item: item["id"],
    )
    target: Optional[dict[str, str]] = None
    for row in clean:
        if row.get("id") == row_id:
            target = row
            break
    if target is None:
        raise LookupError(row_id)
    if agent and target.get("agent") != agent:
        raise PermissionError("agent does not own this queue row")
    target["status"] = "done"
    pruned = _prune_done_rows(clean)
    doc["rows"] = pruned
    doc["generated_at"] = _utc_now_iso()
    doc["schema"] = QUEUE_SCHEMA
    _atomic_write_json(queue_path, doc)
    pending = sum(1 for r in pruned if r.get("status") == "pending")
    return {"id": row_id, "status": "done", "pending": pending}
