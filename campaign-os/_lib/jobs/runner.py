"""Run jobs with hard timeout; ledger entry+exit; status/digest/verdicts."""

from __future__ import annotations

import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from . import ledger
from .registry import JOBS
from .spec import JobSpec


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        raw = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _make_run_id(name: str, started: datetime) -> str:
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{name}-{secrets.token_hex(3)}"


def _extract_rows(result: Any) -> Optional[int]:
    if not isinstance(result, dict):
        return None
    if isinstance(result.get("rows"), int):
        return result["rows"]
    if isinstance(result.get("posts"), int):
        return result["posts"]
    if isinstance(result.get("total_files"), int):
        return result["total_files"]
    ig = result.get("ig_posts")
    fb = result.get("fb_posts")
    if isinstance(ig, int) or isinstance(fb, int):
        return (ig or 0) + (fb or 0)
    return None


def _status_from_result(result: Any) -> tuple[str, Optional[str]]:
    """Return (status, error). status is OK | FAILED."""
    if not isinstance(result, dict):
        return "FAILED", "job returned non-dict"
    if result.get("ok") is False:
        err = result.get("error")
        if err is not None:
            err = str(err)[:500]
        return "FAILED", err
    if result.get("ok") is True:
        return "OK", None
    # No ok key (e.g. raw freshness walk) — treat as OK unless error present
    if result.get("error"):
        return "FAILED", str(result["error"])[:500]
    return "OK", None


def run_job(name: str, triggered_by: str = "schedule") -> dict:
    """Look up JOBS[name], run fn() in a thread with hard timeout,
    write ledger row on entry and exit, return the exit row (+ response fields).
    """
    spec = JOBS.get(name)
    if spec is None:
        return {"ok": False, "job": name, "status": "FAILED", "error": "unknown job"}

    started_dt = _utc_now()
    started = _iso(started_dt)
    run_id = _make_run_id(name, started_dt)

    ledger.append_row(
        {
            "job": name,
            "run_id": run_id,
            "phase": "started",
            "started": started,
            "triggered_by": triggered_by,
        }
    )

    box: dict[str, Any] = {"result": None, "exc": None}

    def _target() -> None:
        try:
            box["result"] = spec.fn()
        except Exception as exc:  # noqa: BLE001 — ledger must capture any crash
            box["exc"] = exc

    thread = threading.Thread(target=_target, name=f"job-{name}", daemon=True)
    t0 = time.monotonic()
    thread.start()
    thread.join(timeout=spec.timeout_seconds)
    duration_s = round(time.monotonic() - t0, 3)
    finished = _iso(_utc_now())

    if thread.is_alive():
        status = "TIMEOUT"
        error = f"exceeded timeout_seconds={spec.timeout_seconds}"
        rows = None
        result_ok = False
    elif box["exc"] is not None:
        status = "FAILED"
        error = str(box["exc"])[:500]
        rows = None
        result_ok = False
    else:
        status, error = _status_from_result(box["result"])
        rows = _extract_rows(box["result"])
        result_ok = status == "OK"

    exit_row = {
        "job": name,
        "run_id": run_id,
        "phase": "finished",
        "started": started,
        "finished": finished,
        "status": status,
        "triggered_by": triggered_by,
        "rows": rows,
        "writes": list(spec.writes),
        "error": error,
        "duration_s": duration_s,
    }
    ledger.append_row(
        {
            "job": name,
            "run_id": run_id,
            "phase": "finished",
            "started": started,
            "finished": finished,
            "status": status,
            "triggered_by": triggered_by,
            "rows": rows,
            "writes": list(spec.writes),
            "error": error,
        }
    )

    return {
        "ok": result_ok,
        "job": name,
        "status": status,
        "duration_s": duration_s,
        "rows": rows,
        "writes": list(spec.writes),
        "run_id": run_id,
        "error": error,
        "started": started,
        "finished": finished,
        "triggered_by": triggered_by,
        "phase": "finished",
    }


def _finished_by_run_id(rows: list[dict]) -> dict[str, dict]:
    return {
        r["run_id"]: r
        for r in rows
        if r.get("phase") == "finished" and r.get("run_id")
    }


def _stuck_started(rows: list[dict], spec: JobSpec, now: datetime) -> Optional[dict]:
    finished = _finished_by_run_id(rows)
    threshold = spec.timeout_seconds * 2
    for row in reversed(rows):
        if row.get("phase") != "started":
            continue
        rid = row.get("run_id")
        if rid and rid in finished:
            continue
        started = _parse_iso(row.get("started"))
        if started is None:
            continue
        age = (now - started).total_seconds()
        if age > threshold:
            return row
    return None


def _last_finished(rows: list[dict]) -> Optional[dict]:
    for row in reversed(rows):
        if row.get("phase") == "finished":
            return row
    return None


def _last_success(rows: list[dict]) -> Optional[dict]:
    for row in reversed(rows):
        if row.get("phase") == "finished" and row.get("status") == "OK":
            return row
    return None


def verdict_for(name: str, rows: list[dict], *, now: Optional[datetime] = None) -> str:
    """OK | LATE | FAILED | STUCK | NEVER — see plan §3.4."""
    spec = JOBS.get(name)
    if spec is None:
        return "NEVER"
    now = now or _utc_now()

    if not rows:
        return "NEVER"

    if _stuck_started(rows, spec, now) is not None:
        return "STUCK"

    last = _last_finished(rows)
    if last is None:
        return "NEVER"

    if last.get("status") != "OK":
        if spec.best_effort:
            return "LATE"
        return "FAILED"

    success = _last_success(rows)
    if success is None:
        return "NEVER"
    success_at = _parse_iso(success.get("finished") or success.get("started"))
    if success_at is None:
        return "NEVER"
    age = (now - success_at).total_seconds()
    if age < spec.every_seconds * 1.5:
        return "OK"
    return "LATE"


def build_status() -> dict:
    """Full status table with timestamps for UI / watchdog."""
    now = _utc_now()
    names = sorted(JOBS.keys())
    grouped = ledger.last_rows_per_job(names)
    jobs_out = []
    for name in names:
        spec = JOBS[name]
        rows = grouped.get(name) or []
        verdict = verdict_for(name, rows, now=now)
        success = _last_success(rows)
        last = _last_finished(rows)
        last_success_at = None
        last_success_age_h = None
        if success:
            finished = _parse_iso(success.get("finished") or success.get("started"))
            if finished is not None:
                last_success_at = _iso(finished)
                last_success_age_h = round((now - finished).total_seconds() / 3600.0, 3)
        jobs_out.append(
            {
                "name": name,
                "verdict": verdict,
                "criticality": spec.criticality,
                "last_success_at": last_success_at,
                "last_success_age_h": last_success_age_h,
                "last_status": (last or {}).get("status"),
                "last_error": (last or {}).get("error"),
            }
        )
    return {"jobs": jobs_out}


def build_digest() -> bytes:
    """Timestamp-free stable bytes — only name + verdict, sorted."""
    import json

    now = _utc_now()
    names = sorted(JOBS.keys())
    grouped = ledger.last_rows_per_job(names)
    payload = {
        "jobs": [
            {
                "name": name,
                "verdict": verdict_for(name, grouped.get(name) or [], now=now),
            }
            for name in names
        ]
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
