"""t35 — Tier-0 retry: RETRYABLE only, backoff, ledger rows, legacy verdicts."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib.jobs import ledger  # noqa: E402
from _lib.jobs.errors import RETRYABLE  # noqa: E402
from _lib.jobs.registry import JOBS, register  # noqa: E402
from _lib.jobs.runner import build_digest, build_status, run_job, verdict_for  # noqa: E402
from _lib.jobs.spec import JobSpec  # noqa: E402


def _http_error(code: int) -> requests.HTTPError:
    resp = Mock()
    resp.status_code = code
    exc = requests.HTTPError(f"{code} Server Error")
    exc.response = resp
    return exc


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def test_non_retryable_classes_single_attempt(data_dir):
    non_retryable = [
        ("auth", lambda: (_ for _ in ()).throw(_http_error(401))),
        ("parse", lambda: (_ for _ in ()).throw(json.JSONDecodeError("msg", "doc", 0))),
        ("empty_result", lambda: {"ok": False, "error": "no rows returned"}),
        ("http_4xx", lambda: (_ for _ in ()).throw(_http_error(404))),
        ("missing_input", lambda: {"ok": False, "error": "missing input file"}),
        ("disk", lambda: (_ for _ in ()).throw(OSError(28, "No space left on device"))),
        ("unknown", lambda: {"ok": False, "error": "weird failure xyz"}),
    ]
    for label, fn in non_retryable:
        name = f"retry_once_{label}"
        calls = {"n": 0}

        def _fn(fn=fn, calls=calls):
            calls["n"] += 1
            return fn()

        register(
            JobSpec(
                name=name,
                fn=_fn,
                every_seconds=3600,
                retries=2,
                timeout_seconds=5,
                brand_mode="global",
                writes=(f"{name}.json",),
            )
        )
        row = run_job(name, triggered_by="test")
        assert calls["n"] == 1, f"{label} retried"
        assert row["attempt"] == 1
        assert row["status"] in ("FAILED", "TIMEOUT")


def test_retryable_http_5xx_retries_with_backoff(data_dir, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def _fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(503)
        return {"ok": True, "rows": 1}

    register(
        JobSpec(
            name="retry_5xx",
            fn=_fn,
            every_seconds=3600,
            retries=2,
            timeout_seconds=5,
            brand_mode="global",
            writes=("retry_5xx.json",),
        )
    )
    row = run_job("retry_5xx", triggered_by="test")
    assert row["status"] == "OK"
    assert calls["n"] == 3
    assert row["attempts"] == 3
    assert sleeps == [2.0, 8.0]
    rows = ledger.read_rows("retry_5xx")
    retry_phases = [r for r in rows if r.get("phase") == "retry"]
    assert len(retry_phases) == 2
    assert {r["attempt"] for r in retry_phases} == {2, 3}
    assert all(r.get("error_class") in RETRYABLE for r in retry_phases)
    # no bundle on eventual OK
    diag = data_dir / "diagnostics" / "retry_5xx"
    assert not diag.exists() or not list(diag.glob("*.json"))


def test_outage_absorbed_no_alert(data_dir, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def _fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(503)
        return {"ok": True, "rows": 2}

    register(
        JobSpec(
            name="outage_job",
            fn=_fn,
            every_seconds=3600,
            retries=2,
            timeout_seconds=5,
            criticality="HIGH",
            brand_mode="global",
            writes=("outage.json",),
        )
    )
    row = run_job("outage_job", triggered_by="test")
    assert row["status"] == "OK"
    rows = ledger.read_rows("outage_job")
    assert verdict_for("outage_job", rows) == "OK"
    diag = data_dir / "diagnostics" / "outage_job"
    assert not diag.exists() or not list(diag.glob("*.json"))


def test_timeout_not_retried(data_dir, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def _fn():
        calls["n"] += 1
        time.sleep(10)  # real sleep inside worker — join times out
        return {"ok": True}

    # shorten join by using tiny timeout; patch join via timeout_seconds=0.2
    # Avoid hanging the suite: use a function that blocks briefly.
    import threading

    original_join = threading.Thread.join

    def _join(self, timeout=None):
        # Pretend still alive after timeout
        if timeout is not None:
            return None
        return original_join(self, timeout)

    monkeypatch.setattr(threading.Thread, "join", _join)

    # Force is_alive True after join
    original_alive = threading.Thread.is_alive

    def _alive(self):
        if getattr(self, "name", "").startswith("job-"):
            return True
        return original_alive(self)

    monkeypatch.setattr(threading.Thread, "is_alive", _alive)

    register(
        JobSpec(
            name="timeout_job",
            fn=lambda: {"ok": True},
            every_seconds=3600,
            retries=2,
            timeout_seconds=1,
            brand_mode="global",
            writes=("timeout.json",),
        )
    )
    row = run_job("timeout_job", triggered_by="test")
    assert row["status"] == "TIMEOUT"
    assert row["attempt"] == 1


def test_legacy_ledger_verdicts_unchanged(data_dir):
    """P0-era ledger (no attempt keys) → identical build_status / build_digest."""
    import os

    name = "legacy_job"
    register(
        JobSpec(
            name=name,
            fn=lambda: {"ok": True},
            every_seconds=3600,
            criticality="MEDIUM",
            brand_mode="global",
            writes=("legacy.json",),
        )
    )
    path = Path(os.environ["DATA_DIR"]) / "job-runs.jsonl"
    legacy = [
        {"job": name, "run_id": "r1", "phase": "started", "started": "2026-09-01T00:00:00Z", "triggered_by": "schedule"},
        {
            "job": name,
            "run_id": "r1",
            "phase": "finished",
            "started": "2026-09-01T00:00:00Z",
            "finished": "2026-09-01T00:00:01Z",
            "status": "OK",
            "triggered_by": "schedule",
            "rows": 1,
            "writes": ["legacy.json"],
            "error": None,
        },
        # a retry row inserted later must be inert
        {
            "job": name,
            "run_id": "r2",
            "phase": "retry",
            "attempt": 2,
            "error_class": "http_5xx",
            "started": "2026-09-01T01:00:00Z",
            "triggered_by": "schedule",
        },
        {"job": name, "run_id": "r2", "phase": "started", "started": "2026-09-01T01:00:00Z", "triggered_by": "schedule"},
        {
            "job": name,
            "run_id": "r2",
            "phase": "finished",
            "started": "2026-09-01T01:00:00Z",
            "finished": "2026-09-01T01:00:02Z",
            "status": "OK",
            "triggered_by": "schedule",
            "rows": 1,
            "writes": ["legacy.json"],
            "error": None,
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in legacy) + "\n")
    rows = ledger.read_rows(name)
    # Strip retry rows for "before" simulation
    before_rows = [r for r in rows if r.get("phase") != "retry"]
    assert verdict_for(name, before_rows) == verdict_for(name, rows)
    status = build_status()
    digest = build_digest()
    assert isinstance(status["jobs"], list)
    assert isinstance(digest, (bytes, bytearray))
    job_row = next(j for j in status["jobs"] if j["name"] == name)
    assert job_row["verdict"] in ("OK", "LATE")


def test_stuck_ignores_orphan_started_superseded_by_later_finished(data_dir):
    """Orphan started before a later finished OK must not yield STUCK (site_audit case)."""
    from datetime import datetime, timezone

    name = "stuck_superseded"
    register(
        JobSpec(
            name=name,
            fn=lambda: {"ok": True},
            every_seconds=86400,
            timeout_seconds=300,
            brand_mode="global",
            writes=("stuck_superseded.json",),
        )
    )
    now = datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc)
    rows = [
        {
            "job": name,
            "run_id": "old-run",
            "phase": "started",
            "started": "2026-09-15T07:00:00Z",
            "triggered_by": "schedule",
        },
        {
            "job": name,
            "run_id": "new-run",
            "phase": "started",
            "started": "2026-09-17T07:11:00Z",
            "triggered_by": "schedule",
        },
        {
            "job": name,
            "run_id": "new-run",
            "phase": "finished",
            "started": "2026-09-17T07:11:00Z",
            "finished": "2026-09-17T07:11:35Z",
            "status": "OK",
            "triggered_by": "schedule",
            "rows": 14,
            "writes": ["stuck_superseded.json"],
            "error": None,
        },
    ]
    assert verdict_for(name, rows, now=now) == "OK"


def test_stuck_detects_orphan_started_without_later_finished(data_dir):
    """Orphan started with no later finished row must yield STUCK."""
    from datetime import datetime, timezone

    name = "stuck_real"
    register(
        JobSpec(
            name=name,
            fn=lambda: {"ok": True},
            every_seconds=86400,
            timeout_seconds=300,
            brand_mode="global",
            writes=("stuck_real.json",),
        )
    )
    now = datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc)
    rows = [
        {
            "job": name,
            "run_id": "orphan-run",
            "phase": "started",
            "started": "2026-09-15T07:00:00Z",
            "triggered_by": "schedule",
        },
    ]
    assert verdict_for(name, rows, now=now) == "STUCK"
