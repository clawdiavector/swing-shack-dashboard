"""Run jobs with hard timeout; Tier-0 retry; ledger entry+exit; status/digest/verdicts."""

from __future__ import annotations

import logging
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from . import ledger
from .errors import RETRYABLE, classify, fingerprint
from .registry import JOBS
from .spec import JobSpec

log = logging.getLogger("campaign-os.jobs.runner")

# Backoff before attempt N (1-indexed): attempt 2 → 2s, attempt 3 → 8s.
_BACKOFF_BEFORE_ATTEMPT = {2: 2.0, 3: 8.0}


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


def _run_once(spec: JobSpec) -> tuple[str, Optional[str], Optional[int], Any, Optional[BaseException], float]:
    """Execute one attempt in a daemon thread with hard timeout."""
    box: dict[str, Any] = {"result": None, "exc": None}

    def _target() -> None:
        try:
            box["result"] = spec.fn()
        except Exception as exc:  # noqa: BLE001 — ledger must capture any crash
            box["exc"] = exc

    thread = threading.Thread(target=_target, name=f"job-{spec.name}", daemon=True)
    t0 = time.monotonic()
    thread.start()
    thread.join(timeout=spec.timeout_seconds)
    duration_s = round(time.monotonic() - t0, 3)

    if thread.is_alive():
        return "TIMEOUT", f"exceeded timeout_seconds={spec.timeout_seconds}", None, None, None, duration_s
    if box["exc"] is not None:
        return "FAILED", str(box["exc"])[:500], None, None, box["exc"], duration_s
    status, error = _status_from_result(box["result"])
    rows = _extract_rows(box["result"])
    return status, error, rows, box["result"], None, duration_s


def run_job(name: str, triggered_by: str = "schedule") -> dict:
    """Look up JOBS[name], run fn() with Tier-0 retry for RETRYABLE classes,
    write ledger rows, optionally write a diagnostic bundle on non-OK.

    Wall-clock worst case: (retries+1) * timeout_seconds + 10s backoff budget
    (2s + 8s). Synchronous POST /api/jobs/run/<name> blocks for that long.
    """
    spec = JOBS.get(name)
    if spec is None:
        return {"ok": False, "job": name, "status": "FAILED", "error": "unknown job"}

    started_dt = _utc_now()
    started = _iso(started_dt)
    run_id = _make_run_id(name, started_dt)

    # Exactly one started row per run_id — outside the retry loop (§3.5).
    ledger.append_row(
        {
            "job": name,
            "run_id": run_id,
            "phase": "started",
            "started": started,
            "triggered_by": triggered_by,
        }
    )

    max_attempts = max(1, int(getattr(spec, "retries", 0)) + 1)
    attempt = 0
    status = "FAILED"
    error: Optional[str] = None
    rows: Optional[int] = None
    result: Any = None
    exc: Optional[BaseException] = None
    duration_s = 0.0
    error_class = "unknown"
    t_run0 = time.monotonic()

    while True:
        attempt += 1
        if attempt > 1:
            delay = _BACKOFF_BEFORE_ATTEMPT.get(attempt, 8.0)
            time.sleep(delay)

        status, error, rows, result, exc, duration_s = _run_once(spec)
        error_class, _ = classify(
            exc=exc, message=error, spec=spec, result=result, status=status
        )

        if status == "OK":
            break

        can_retry = (
            error_class in RETRYABLE
            and attempt < max_attempts
            and status != "TIMEOUT"
        )
        if not can_retry:
            break

        next_attempt = attempt + 1
        ledger.append_row(
            {
                "job": name,
                "run_id": run_id,
                "phase": "retry",
                "attempt": next_attempt,
                "error_class": error_class,
                "started": started,
                "triggered_by": triggered_by,
            }
        )

    finished = _iso(_utc_now())
    total_duration = round(time.monotonic() - t_run0, 3)
    result_ok = status == "OK"
    fp = fingerprint(name, error_class, error) if not result_ok else None

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
        "duration_s": total_duration,
        "attempt": attempt,
        "attempts": attempt,
        "error_class": error_class if not result_ok else None,
        "error_fingerprint": fp,
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
            "attempt": attempt,
            "attempts": attempt,
            "error_class": error_class if not result_ok else None,
            "error_fingerprint": fp,
        }
    )

    if not result_ok:
        try:
            from .diagnostics import write_bundle

            write_bundle(
                spec=spec,
                run_id=run_id,
                attempt=attempt,
                status=status,
                started=started,
                finished=finished,
                duration_s=total_duration,
                error=error,
                exc=exc,
                result=result,
            )
        except Exception:  # noqa: BLE001 — bundle must never fail the run
            log.warning("write_bundle raised job=%s run_id=%s", name, run_id, exc_info=True)

    return {
        "ok": result_ok,
        "job": name,
        "status": status,
        "duration_s": total_duration,
        "rows": rows,
        "writes": list(spec.writes),
        "run_id": run_id,
        "error": error,
        "started": started,
        "finished": finished,
        "triggered_by": triggered_by,
        "phase": "finished",
        "attempt": attempt,
        "attempts": attempt,
        "error_class": error_class if not result_ok else None,
        "error_fingerprint": fp,
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
