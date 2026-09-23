"""Run jobs with hard timeout; Tier-0 retry; ledger entry+exit; status/digest/verdicts."""

from __future__ import annotations

import inspect
import logging
import secrets
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from . import ledger
from .brand_lanes import (
    partition_brands,
    resolve_brands,
    skipped_brands,
)
from .errors import RETRYABLE, classify, fingerprint
from .registry import JOBS
from .descriptions import description_for
from .outcome import summarize_result
from .schedules import schedule_for
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


def _make_run_id(name: str, started: datetime, brand: str | None = None) -> str:
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    brand_part = f"-{brand}" if brand else ""
    return f"{stamp}-{name}{brand_part}-{secrets.token_hex(3)}"


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
    if result.get("skipped") is True:
        reason = result.get("reason") or "skipped by job"
        return "SKIPPED", str(reason)[:500]
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


def _call_job_fn(spec: JobSpec, brand: str | None) -> Any:
    if brand is None or spec.brand_mode != "per_brand":
        return spec.fn()
    try:
        params = inspect.signature(spec.fn).parameters
    except (TypeError, ValueError):
        return spec.fn()
    if "brand" in params:
        return spec.fn(brand=brand)
    return spec.fn()


def _run_once(spec: JobSpec, brand: str | None = None) -> tuple[str, Optional[str], Optional[int], Any, Optional[BaseException], float]:
    """Execute one attempt in a daemon thread with hard timeout."""
    box: dict[str, Any] = {"result": None, "exc": None}

    def _target() -> None:
        try:
            box["result"] = _call_job_fn(spec, brand)
        except Exception as exc:  # noqa: BLE001 — ledger must capture any crash
            box["exc"] = exc

    thread = threading.Thread(
        target=_target,
        name=f"job-{spec.name}{f'-{brand}' if brand else ''}",
        daemon=True,
    )
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


def _append_skipped_row(
    *,
    name: str,
    run_id: str,
    started: str,
    triggered_by: str,
    brand: str | None,
    reason: str,
) -> dict:
    finished = _iso(_utc_now())
    exit_row = {
        "job": name,
        "brand": brand,
        "run_id": run_id,
        "phase": "finished",
        "started": started,
        "finished": finished,
        "status": "SKIPPED",
        "triggered_by": triggered_by,
        "error": reason,
        "duration_s": 0.0,
        "attempt": 1,
        "attempts": 1,
        "result_summary": {"skipped": True, "reason": reason},
    }
    ledger.append_row(
        {
            "job": name,
            "brand": brand,
            "run_id": run_id,
            "phase": "started",
            "started": started,
            "triggered_by": triggered_by,
        }
    )
    ledger.append_row(exit_row)
    return {
        "ok": True,
        "job": name,
        "brand": brand,
        "status": "SKIPPED",
        "duration_s": 0.0,
        "run_id": run_id,
        "error": reason,
        "started": started,
        "finished": finished,
        "triggered_by": triggered_by,
        "phase": "finished",
        "attempt": 1,
        "attempts": 1,
        "skipped": True,
    }


def _run_job_single(
    spec: JobSpec,
    name: str,
    triggered_by: str,
    brand: str | None,
) -> dict:
    started_dt = _utc_now()
    started = _iso(started_dt)
    run_id = _make_run_id(name, started_dt, brand)

    ledger.append_row(
        {
            "job": name,
            "brand": brand,
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

        status, error, rows, result, exc, duration_s = _run_once(spec, brand)
        error_class, _ = classify(
            exc=exc, message=error, spec=spec, result=result, status=status
        )

        if status in ("OK", "SKIPPED"):
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
                "brand": brand,
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
    skipped = status == "SKIPPED"
    fp = fingerprint(name, error_class, error) if not (result_ok or skipped) else None

    exit_row = {
        "job": name,
        "brand": brand,
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
        "error_class": error_class if not (result_ok or skipped) else None,
        "error_fingerprint": fp,
        "result_summary": summarize_result(result),
    }
    ledger.append_row(exit_row)

    if not result_ok and not skipped:
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
        "ok": result_ok or skipped,
        "skipped": skipped,
        "job": name,
        "brand": brand,
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
        "error_class": error_class if not (result_ok or skipped) else None,
        "error_fingerprint": fp,
    }


def run_job(
    name: str,
    triggered_by: str = "schedule",
    brand: str | None = None,
) -> dict:
    """Look up JOBS[name], run fn() with Tier-0 retry for RETRYABLE classes,
    write ledger rows, optionally write a diagnostic bundle on non-OK.

    For per_brand jobs without an explicit brand, fans out to all resolved brands.
    """
    spec = JOBS.get(name)
    if spec is None:
        return {"ok": False, "job": name, "status": "FAILED", "error": "unknown job"}

    if not getattr(spec, "enabled", True):
        finished = _iso(_utc_now())
        return {
            "ok": True,
            "job": name,
            "status": "SKIPPED",
            "skipped": True,
            "reason": "job disabled",
            "finished": finished,
            "triggered_by": triggered_by,
        }

    if spec.brand_mode == "per_brand":
        if brand is not None:
            resolved = set(resolve_brands(spec)) | set(skipped_brands(spec)) | set(spec.brands)
            if brand not in resolved and brand not in resolve_brands(spec):
                runnable, skip = partition_brands(spec)
                if brand not in runnable and brand not in skip:
                    return {
                        "ok": False,
                        "job": name,
                        "brand": brand,
                        "status": "FAILED",
                        "error": f"brand {brand!r} not in resolved set",
                    }
            if brand in skipped_brands(spec) or (
                spec.requires_integrations and brand not in resolve_brands(spec)
            ):
                started_dt = _utc_now()
                return _append_skipped_row(
                    name=name,
                    run_id=_make_run_id(name, started_dt, brand),
                    started=_iso(started_dt),
                    triggered_by=triggered_by,
                    brand=brand,
                    reason="integration credentials missing for brand",
                )
            return _run_job_single(spec, name, triggered_by, brand)

        runnable, skip = partition_brands(spec)
        runs: list[dict] = []
        for skip_brand in skip:
            started_dt = _utc_now()
            runs.append(
                _append_skipped_row(
                    name=name,
                    run_id=_make_run_id(name, started_dt, skip_brand),
                    started=_iso(started_dt),
                    triggered_by=triggered_by,
                    brand=skip_brand,
                    reason="integration credentials missing for brand",
                )
            )
        if not runnable and not runs:
            started_dt = _utc_now()
            return _append_skipped_row(
                name=name,
                run_id=_make_run_id(name, started_dt, None),
                started=_iso(started_dt),
                triggered_by=triggered_by,
                brand=None,
                reason="no brands resolved for job",
            )
        for run_brand in runnable:
            runs.append(_run_job_single(spec, name, triggered_by, run_brand))
        if len(runs) == 1:
            return runs[0]
        return {"ok": all(r.get("ok") for r in runs), "job": name, "runs": runs}

    return _run_job_single(spec, name, triggered_by, None)


def _finished_by_run_id(rows: list[dict]) -> dict[str, dict]:
    return {
        r["run_id"]: r
        for r in rows
        if r.get("phase") == "finished" and r.get("run_id")
    }


def _latest_finished_at(rows: list[dict]) -> Optional[datetime]:
    for row in reversed(rows):
        if row.get("phase") != "finished":
            continue
        ts = _parse_iso(row.get("finished") or row.get("started"))
        if ts is not None:
            return ts
    return None


REAPED_ERROR_CLASS = "worker_death"
_REAPED_ERROR_MSG = "no finished row — process died mid-run; reaped at boot"


def reap_orphan_runs(*, boot_at: datetime, now: datetime | None = None) -> list[dict]:
    """Append terminal rows for started runs whose worker died before finishing."""
    appended: list[dict] = []
    try:
        now = now or _utc_now()
        grouped = ledger.last_rows_per_job_brand(sorted(JOBS))
        for (job_name, brand), rows in grouped.items():
            spec = JOBS.get(job_name)
            if spec is None:
                continue
            finished = _finished_by_run_id(rows)
            for row in rows:
                if row.get("phase") != "started":
                    continue
                rid = row.get("run_id")
                if not rid or rid in finished:
                    continue
                started = _parse_iso(row.get("started"))
                if started is None or started >= boot_at:
                    continue
                threshold = spec.timeout_seconds * 2
                age = (now - started).total_seconds()
                if age <= threshold:
                    continue
                error = _REAPED_ERROR_MSG
                exit_row = {
                    "job": job_name,
                    "brand": brand,
                    "run_id": rid,
                    "phase": "finished",
                    "started": row.get("started"),
                    "finished": _iso(now),
                    "status": "FAILED",
                    "triggered_by": row.get("triggered_by") or "schedule",
                    "error": error,
                    "duration_s": None,
                    "attempt": 1,
                    "attempts": 1,
                    "error_class": REAPED_ERROR_CLASS,
                    "error_fingerprint": fingerprint(job_name, REAPED_ERROR_CLASS, error),
                    "reaped": True,
                }
                ledger.append_row(exit_row)
                appended.append(exit_row)
                finished[rid] = exit_row
    except Exception:
        log.exception("reap_orphan_runs failed")
    return appended


def _stuck_started(rows: list[dict], spec: JobSpec, now: datetime) -> Optional[dict]:
    finished = _finished_by_run_id(rows)
    threshold = spec.timeout_seconds * 2
    latest_finished_at = _latest_finished_at(rows)
    for row in reversed(rows):
        if row.get("phase") != "started":
            continue
        rid = row.get("run_id")
        if rid and rid in finished:
            continue
        started = _parse_iso(row.get("started"))
        if started is None:
            continue
        if latest_finished_at is not None and started < latest_finished_at:
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


def _aggregate_verdict(child_verdicts: list[str]) -> str:
    """Job-level verdict: worst non-SKIPPED child; SKIPPED only if all children skipped."""
    non_skipped = [v for v in child_verdicts if v != "SKIPPED"]
    if not non_skipped:
        return "SKIPPED" if child_verdicts else "NEVER"
    priority = {"STUCK": 5, "FAILED": 4, "NEVER": 3, "LATE": 2, "OK": 1, "SKIPPED": 0}
    return max(non_skipped, key=lambda v: priority.get(v, 0))


def _verdict_for_rows(spec: JobSpec, rows: list[dict], now: datetime) -> str:
    """Leaf evaluation for one already-filtered row set. Never recurses."""
    if not rows:
        return "NEVER"

    if _stuck_started(rows, spec, now) is not None:
        return "STUCK"

    last = _last_finished(rows)
    if last is None:
        return "NEVER"

    if last.get("status") == "SKIPPED":
        return "SKIPPED"

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


def verdict_for(
    name: str,
    rows: list[dict],
    *,
    now: Optional[datetime] = None,
    brand: str | None = None,
    grouped: dict[tuple[str, str | None], list[dict]] | None = None,
) -> str:
    """OK | LATE | FAILED | STUCK | NEVER | SKIPPED | DISABLED — see plan §3.4."""
    spec = JOBS.get(name)
    if spec is None:
        return "NEVER"
    if not getattr(spec, "enabled", True):
        return "DISABLED"
    now = now or _utc_now()

    if brand is not None:
        return _verdict_for_rows(spec, [r for r in rows if r.get("brand") == brand], now)

    if spec.brand_mode == "per_brand":
        brand_grouped = grouped if grouped is not None else ledger.last_rows_per_job_brand([name])
        child_verdicts = [
            _verdict_for_rows(spec, child_rows, now)
            for (job_name, b), child_rows in brand_grouped.items()
            if job_name == name and b is not None
        ]
        if child_verdicts:
            return _aggregate_verdict(child_verdicts)

    return _verdict_for_rows(spec, rows, now)


def _brand_status_entries(spec: JobSpec, grouped: dict[tuple[str, str | None], list[dict]], now: datetime) -> list[dict]:
    if spec.brand_mode != "per_brand":
        return []
    keys = sorted({b for (job, b) in grouped if job == spec.name and b is not None})
    if not keys:
        keys = list(resolve_brands(spec)) + list(skipped_brands(spec))
    runnable, skipped = partition_brands(spec)
    runnable_set = set(runnable)
    skipped_set = set(skipped)
    entries: list[dict] = []
    for brand_id in keys:
        rows = grouped.get((spec.name, brand_id)) or []
        verdict = verdict_for(spec.name, rows, now=now, brand=brand_id)
        success = _last_success(rows)
        last = _last_finished(rows)
        last_success_at = None
        last_success_age_h = None
        if success:
            finished = _parse_iso(success.get("finished") or success.get("started"))
            if finished is not None:
                last_success_at = _iso(finished)
                last_success_age_h = round((now - finished).total_seconds() / 3600.0, 3)
        entry: dict = {
            "brand": brand_id,
            "verdict": verdict,
            "applies": brand_id in runnable_set,
            "last_success_at": last_success_at,
            "last_success_age_h": last_success_age_h,
            "last_run_at": (last or {}).get("finished"),
            "last_status": (last or {}).get("status"),
            "last_error": (last or {}).get("error"),
        }
        if brand_id in skipped_set:
            entry["skipped_reason"] = "integration credentials missing for brand"
        entries.append(entry)
    return entries


def build_status() -> dict:
    """Full status table with timestamps for UI / watchdog."""
    now = _utc_now()
    names = sorted(JOBS.keys())
    grouped_brand = ledger.last_rows_per_job_brand(names)
    grouped = ledger.last_rows_per_job(names)
    jobs_out = []
    for name in names:
        spec = JOBS[name]
        rows = grouped.get(name) or []
        verdict = verdict_for(name, rows, now=now, grouped=grouped_brand)
        success = _last_success(rows)
        last = _last_finished(rows)
        last_success_at = None
        last_success_age_h = None
        if success:
            finished = _parse_iso(success.get("finished") or success.get("started"))
            if finished is not None:
                last_success_at = _iso(finished)
                last_success_age_h = round((now - finished).total_seconds() / 3600.0, 3)
        job_entry = {
            "name": name,
            "verdict": verdict,
            "criticality": spec.criticality,
            "brand_mode": spec.brand_mode,
            "last_success_at": last_success_at,
            "last_success_age_h": last_success_age_h,
            "last_run_at": (last or {}).get("finished"),
            "last_started_at": (last or {}).get("started"),
            "last_triggered_by": (last or {}).get("triggered_by"),
            "last_status": (last or {}).get("status"),
            "last_error": (last or {}).get("error"),
            "last_duration_s": (last or {}).get("duration_s"),
            "last_run_id": (last or {}).get("run_id"),
            "last_error_class": (last or {}).get("error_class"),
            "best_effort": bool(getattr(spec, "best_effort", False)),
            "enabled": bool(getattr(spec, "enabled", True)),
            "every_seconds": getattr(spec, "every_seconds", None),
            "timeout_seconds": getattr(spec, "timeout_seconds", None),
            "retries": getattr(spec, "retries", 0),
            "schedule": schedule_for(name),
            "info": description_for(name),
        }
        brands = _brand_status_entries(spec, grouped_brand, now)
        if brands:
            job_entry["brands"] = brands
        jobs_out.append(job_entry)
    return {"jobs": jobs_out}


def build_history(*, job: Optional[str] = None, limit_per_job: int = 12) -> dict:
    """Recent finished runs from job-runs.jsonl for /ops/jobs history panel."""
    limit = max(1, min(int(limit_per_job), 50))
    if job is not None:
        if job not in JOBS:
            return {"ok": False, "error": "unknown job", "jobs": {}}
        names = [job]
    else:
        names = sorted(JOBS.keys())

    grouped = ledger.last_rows_per_job(names)
    jobs_out: dict[str, list[dict]] = {}
    for name in names:
        finished = [
            r for r in grouped.get(name) or [] if r.get("phase") == "finished" and r.get("run_id")
        ]
        finished.sort(key=lambda r: r.get("finished") or r.get("started") or "", reverse=True)
        runs = []
        for row in finished[:limit]:
            runs.append(
                {
                    "run_id": row.get("run_id"),
                    "brand": row.get("brand"),
                    "started": row.get("started"),
                    "finished": row.get("finished"),
                    "status": row.get("status"),
                    "duration_s": row.get("duration_s"),
                    "triggered_by": row.get("triggered_by"),
                    "error": (row.get("error") or "")[:200] or None,
                    "error_class": row.get("error_class"),
                    "rows": row.get("rows"),
                    "result_summary": row.get("result_summary"),
                }
            )
        jobs_out[name] = runs
    return {"ok": True, "limit_per_job": limit, "jobs": jobs_out}


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
