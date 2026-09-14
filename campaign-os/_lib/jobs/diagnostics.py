"""Diagnostic bundle writer — campaign-os/diagnostic-bundle/v1 (t38)."""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import shutil
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Optional

from .errors import classify, fingerprint
from .redaction import redact_obj
from .suggested_checks import checks_for

log = logging.getLogger("campaign-os.jobs.diagnostics")

SCHEMA = "campaign-os/diagnostic-bundle/v1"
RETENTION_DAYS = 30
RETENTION_MAX = 200
RUN_ID_RE = re.compile(r"^[0-9A-Za-z:_.-]{1,80}$")

_REMEDIATION_ACTIONS = [
    "read_repo",
    "edit_job_module",
    "add_contract_test",
    "rerun_job",
]
_REMEDIATION_FORBIDDEN = [
    "print_secret_values",
    "set_env",
    "push_any_branch",
    "merge",
    "publish",
    "write_data_dir",
    "redeploy",
]


def _data_dir() -> str:
    return os.environ.get("DATA_DIR") or "/data"


def _diagnostics_root() -> str:
    return os.path.join(_data_dir(), "diagnostics")


def bundle_path(job_id: str, run_id: str) -> str:
    return os.path.join(_diagnostics_root(), job_id, f"{run_id}.json")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _file_meta(rel: str) -> dict[str, Any]:
    path = os.path.join(_data_dir(), rel)
    exists = os.path.exists(path)
    age_h = None
    size = None
    if exists:
        try:
            st = os.stat(path)
            size = int(st.st_size)
            age_h = round((time.time() - st.st_mtime) / 3600.0, 3)
        except OSError:
            exists = False
    return {"path": rel, "exists": exists, "age_h": age_h, "bytes": size}


def _output_meta(rel: str, every_seconds: int) -> dict[str, Any]:
    meta = _file_meta(rel)
    stale = False
    if meta["exists"] and meta["age_h"] is not None and every_seconds > 0:
        stale = meta["age_h"] > (every_seconds * 1.5) / 3600.0
    meta["stale"] = stale
    return meta


def _credentials_presence(spec: Any) -> dict[str, bool]:
    names = getattr(spec, "credentials", ()) or ()
    return {name: bool(os.environ.get(name)) for name in names}


def _app_sha() -> Optional[str]:
    raw = os.environ.get("RAILWAY_GIT_COMMIT_SHA")
    if not raw:
        return None
    return str(raw)[:7]


def _env_block() -> dict[str, Any]:
    base = _data_dir()
    writable = False
    free_mb = 0
    try:
        writable = os.access(base, os.W_OK)
    except OSError:
        writable = False
    try:
        usage = shutil.disk_usage(base if os.path.isdir(base) else os.path.dirname(base) or "/")
        free_mb = int(usage.free // (1024 * 1024))
    except OSError:
        free_mb = 0
    return {
        "app_sha": _app_sha(),
        "python": platform.python_version(),
        "data_dir": base,
        "data_dir_writable": writable,
        "data_dir_free_mb": free_mb,
    }


def _history(job_id: str) -> dict[str, Any]:
    from . import ledger

    rows = ledger.read_rows(job_id)
    last_success_at = None
    consecutive = 0
    finished = [r for r in rows if r.get("phase") == "finished"]
    for row in reversed(finished):
        if row.get("status") == "OK":
            last_success_at = row.get("finished") or row.get("started")
            break
        consecutive += 1

    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - 7 * 86400
    week = []
    for row in finished:
        finished_at = _parse_iso(row.get("finished") or row.get("started"))
        if finished_at is None:
            continue
        if finished_at.timestamp() >= cutoff:
            week.append(row)
    if week:
        ok = sum(1 for r in week if r.get("status") == "OK")
        success_rate_7d = round(ok / len(week), 3)
    else:
        success_rate_7d = 0.0

    return {
        "last_success_at": last_success_at,
        "consecutive_failures": consecutive,
        "success_rate_7d": success_rate_7d,
        "heal_attempts_24h": 0,
    }


def _recent_errors(started: Optional[str], finished: Optional[str]) -> list[dict]:
    path = os.path.join(_data_dir(), "error-log.jsonl")
    if not os.path.isfile(path):
        return []
    start_dt = _parse_iso(started)
    end_dt = _parse_iso(finished) or datetime.now(timezone.utc)
    if start_dt is None:
        return []
    out: list[dict] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = _parse_iso(row.get("ts") or row.get("timestamp"))
                if ts is None:
                    continue
                if start_dt <= ts <= end_dt:
                    out.append(row)
                    if len(out) >= 5:
                        break
    except OSError:
        return []
    return out


def _upstream_from_result(result: Any) -> list[dict]:
    if not isinstance(result, dict):
        return []
    hint = result.get("upstream")
    if isinstance(hint, list):
        return hint
    return []


def _exc_fields(exc: Optional[BaseException], error: Optional[str]) -> dict[str, str]:
    if exc is None:
        return {"type": "", "message": str(error or "")[:500], "traceback_tail": ""}
    import traceback

    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return {
        "type": type(exc).__name__,
        "message": str(exc)[:500],
        "traceback_tail": tb,
    }


def _remediation_scope(job_id: str) -> dict[str, Any]:
    module = f"campaign-os/_lib/jobs/layer1/{job_id}.py"
    return {
        "allowed_paths": [
            module,
            "campaign-os/tests/jobs/test_layer1_contracts.py",
        ],
        "allowed_actions": list(_REMEDIATION_ACTIONS),
        "forbidden": list(_REMEDIATION_FORBIDDEN),
    }


def build_bundle(
    *,
    spec: Any,
    run_id: str,
    attempt: int,
    status: str,
    started: str,
    finished: str,
    duration_s: float,
    error: Optional[str],
    exc: Optional[BaseException] = None,
    result: Any = None,
) -> dict[str, Any]:
    job_id = spec.name
    verdict = "TIMEOUT" if status == "TIMEOUT" else "FAILED"
    if status == "STUCK":
        verdict = "STUCK"

    error_class, _evidence = classify(
        exc=exc, message=error, spec=spec, result=result, status=status
    )
    msg_for_fp = error if error is not None else (str(exc) if exc else "")
    fp = fingerprint(job_id, error_class, msg_for_fp)
    checks = checks_for(error_class, job_id)

    bundle: dict[str, Any] = {
        "schema": SCHEMA,
        "job_id": job_id,
        "run_id": run_id,
        "attempt": attempt,
        "ts": _iso_now(),
        "verdict": verdict,
        "criticality": getattr(spec, "criticality", "MEDIUM"),
        "best_effort": bool(getattr(spec, "best_effort", False)),
        "error_class": error_class,
        "error_fingerprint": fp,
        "exception": _exc_fields(exc, error),
        "stderr_tail": "",
        "timing": {
            "started": started,
            "finished": finished,
            "duration_s": duration_s,
            "timeout_s": getattr(spec, "timeout_seconds", 60),
        },
        "env": _env_block(),
        "credentials": _credentials_presence(spec),
        "inputs": [_file_meta(p) for p in (getattr(spec, "reads", ()) or ())],
        "outputs": [
            _output_meta(p, getattr(spec, "every_seconds", 0))
            for p in (getattr(spec, "writes", ()) or ())
        ],
        "upstream": _upstream_from_result(result),
        "recent_errors": _recent_errors(started, finished),
        "history": _history(job_id),
        "suggested_checks": checks,
        "remediation_scope": _remediation_scope(job_id),
    }
    return redact_obj(bundle)


def prune(job_id: str) -> None:
    """Retention: 30 days then max 200 per job. Failures swallowed."""
    try:
        directory = os.path.join(_diagnostics_root(), job_id)
        if not os.path.isdir(directory):
            return
        now = time.time()
        cutoff = now - RETENTION_DAYS * 86400
        entries: list[tuple[float, str]] = []
        for name in os.listdir(directory):
            if not name.endswith(".json"):
                continue
            path = os.path.join(directory, name)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if mtime < cutoff:
                try:
                    os.unlink(path)
                except OSError:
                    pass
                continue
            entries.append((mtime, path))
        if len(entries) <= RETENTION_MAX:
            return
        entries.sort(key=lambda item: item[0])
        for _mtime, path in entries[: len(entries) - RETENTION_MAX]:
            try:
                os.unlink(path)
            except OSError:
                pass
    except Exception:  # noqa: BLE001
        log.warning("diagnostics prune failed job=%s", job_id, exc_info=True)


def write_bundle(
    *,
    spec: Any,
    run_id: str,
    attempt: int,
    status: str,
    started: str,
    finished: str,
    duration_s: float,
    error: Optional[str],
    exc: Optional[BaseException] = None,
    result: Any = None,
) -> Optional[str]:
    """Write redacted bundle; return path or None on failure."""
    try:
        bundle = build_bundle(
            spec=spec,
            run_id=run_id,
            attempt=attempt,
            status=status,
            started=started,
            finished=finished,
            duration_s=duration_s,
            error=error,
            exc=exc,
            result=result,
        )
        path = bundle_path(spec.name, run_id)
        parent = os.path.dirname(path)
        os.makedirs(parent, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=parent, prefix=f".{run_id}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(bundle, fh, indent=2, default=str)
                fh.write("\n")
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        prune(spec.name)
        return path
    except Exception:  # noqa: BLE001
        log.warning("write_bundle failed job=%s run_id=%s", getattr(spec, "name", "?"), run_id, exc_info=True)
        return None


def read_bundle(run_id: str) -> Optional[dict[str, Any]]:
    """Find and return a redacted bundle by run_id, or None."""
    if not RUN_ID_RE.match(run_id or ""):
        return None
    root = _diagnostics_root()
    if not os.path.isdir(root):
        return None
    try:
        for job_id in os.listdir(root):
            path = os.path.join(root, job_id, f"{run_id}.json")
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                return redact_obj(data)
    except Exception:  # noqa: BLE001
        return None
    return None


def list_open_failures() -> list[dict[str, Any]]:
    """Open incidents for non-best_effort jobs (FAILED/STUCK with a finished row)."""
    from . import ledger
    from .registry import JOBS
    from .runner import _last_finished, _last_success, verdict_for

    now = datetime.now(timezone.utc)
    out: list[dict[str, Any]] = []
    for name, spec in sorted(JOBS.items()):
        if getattr(spec, "best_effort", False):
            continue
        rows = ledger.read_rows(name)
        verdict = verdict_for(name, rows, now=now)
        if verdict not in ("FAILED", "STUCK"):
            continue
        last = _last_finished(rows)
        if last is None:
            continue
        error = last.get("error")
        error_class, _ = classify(message=error, spec=spec, status=last.get("status"))
        fp = fingerprint(name, error_class, error)
        checks = checks_for(error_class, name)
        success = _last_success(rows)
        consecutive = 0
        for row in reversed([r for r in rows if r.get("phase") == "finished"]):
            if row.get("status") == "OK":
                break
            consecutive += 1
        run_id = last.get("run_id")
        bundle_ref = None
        if run_id and os.path.isfile(bundle_path(name, run_id)):
            bundle_ref = f"/api/jobs/diagnostics/{run_id}"
        out.append(
            {
                "job": name,
                "verdict": verdict,
                "error_class": error_class,
                "error_fingerprint": fp,
                "last_error_at": last.get("finished") or last.get("started"),
                "consecutive_failures": consecutive,
                "top_suggested_check": checks[0] if checks else None,
                "bundle_ref": bundle_ref,
                "last_success_at": (success or {}).get("finished"),
            }
        )
    return out
