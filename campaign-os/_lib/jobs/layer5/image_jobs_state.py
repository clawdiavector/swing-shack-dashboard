"""Shared Krea async image job state ($DATA_DIR/draft-assets/_image-jobs.json)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from ..layer1._io import atomic_write, read_json, utc_now_iso

SCHEMA = "campaign-os/image-jobs/v1"
REL_PATH = "draft-assets/_image-jobs.json"


def _empty_doc() -> dict[str, Any]:
    return {"schema": SCHEMA, "generated_at": utc_now_iso(), "jobs": {}}


def load_doc() -> dict[str, Any]:
    raw = read_json(REL_PATH)
    if not isinstance(raw, dict):
        return _empty_doc()
    raw.setdefault("schema", SCHEMA)
    jobs = raw.get("jobs")
    if not isinstance(jobs, dict):
        raw["jobs"] = {}
    return raw


def save_doc(doc: dict[str, Any]) -> None:
    doc["schema"] = SCHEMA
    doc["generated_at"] = utc_now_iso()
    atomic_write(REL_PATH, doc)


def get_entry(item_id: str) -> dict[str, Any] | None:
    jobs = load_doc().get("jobs")
    if not isinstance(jobs, dict):
        return None
    entry = jobs.get(item_id)
    return entry if isinstance(entry, dict) else None


def upsert_submit(
    item_id: str,
    *,
    job_id: str,
    brand: str,
    size: str,
    est_usd: float,
    retry_count: int = 0,
) -> None:
    doc = load_doc()
    jobs = doc.setdefault("jobs", {})
    if not isinstance(jobs, dict):
        jobs = {}
        doc["jobs"] = jobs
    now = utc_now_iso()
    prev = jobs.get(item_id) if isinstance(jobs.get(item_id), dict) else {}
    jobs[item_id] = {
        "job_id": job_id,
        "brand": brand,
        "size": size,
        "est_usd": est_usd,
        "submitted_at": now,
        "last_status": "running",
        "last_poll_at": None,
        "polls": 0,
        "retry_count": int(prev.get("retry_count") if prev.get("retry_count") is not None else retry_count),
        "settled_at": prev.get("settled_at"),
    }
    save_doc(doc)


def update_poll(item_id: str, *, last_status: str) -> None:
    doc = load_doc()
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return
    entry = jobs.get(item_id)
    if not isinstance(entry, dict):
        return
    entry["last_poll_at"] = utc_now_iso()
    entry["last_status"] = last_status
    entry["polls"] = int(entry.get("polls") or 0) + 1
    save_doc(doc)


def mark_settled(item_id: str) -> None:
    doc = load_doc()
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return
    entry = jobs.get(item_id)
    if not isinstance(entry, dict):
        return
    entry["settled_at"] = utc_now_iso()
    save_doc(doc)


def is_settled(item_id: str) -> bool:
    entry = get_entry(item_id)
    return bool(entry and entry.get("settled_at"))


def drop_entry(item_id: str) -> None:
    doc = load_doc()
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict) or item_id not in jobs:
        return
    del jobs[item_id]
    save_doc(doc)


def retry_count(item_id: str, *, row_fallback: int | None = None) -> int:
    entry = get_entry(item_id)
    if entry is not None:
        try:
            return max(0, int(entry.get("retry_count") or 0))
        except (TypeError, ValueError):
            return 0
    if row_fallback is not None:
        return max(0, int(row_fallback))
    return 0


def increment_retry(item_id: str, *, row_fallback: int | None = None) -> int:
    doc = load_doc()
    jobs = doc.setdefault("jobs", {})
    if not isinstance(jobs, dict):
        jobs = {}
        doc["jobs"] = jobs
    entry = jobs.get(item_id)
    if not isinstance(entry, dict):
        base = retry_count(item_id, row_fallback=row_fallback)
        entry = {
            "job_id": "",
            "brand": "",
            "size": "1024x1024",
            "est_usd": 0.04,
            "submitted_at": utc_now_iso(),
            "last_status": "failed",
            "retry_count": base,
        }
        jobs[item_id] = entry
    base = int(entry.get("retry_count") if entry.get("retry_count") is not None else (row_fallback or 0))
    entry["retry_count"] = base + 1
    entry["last_status"] = "failed"
    entry["job_id"] = ""
    entry.pop("settled_at", None)
    save_doc(doc)
    return int(entry["retry_count"])


def parse_submitted_at(entry: dict[str, Any]) -> Optional[datetime]:
    raw = entry.get("submitted_at")
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
