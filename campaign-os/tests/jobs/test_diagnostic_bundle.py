"""t38 — diagnostic bundle schema, credentials booleans, retention, write guard."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib.jobs.diagnostics import (  # noqa: E402
    SCHEMA,
    build_bundle,
    prune,
    write_bundle,
)
from _lib.jobs.registry import register  # noqa: E402
from _lib.jobs.runner import run_job  # noqa: E402
from _lib.jobs.spec import JobSpec  # noqa: E402


def test_schema_literal_pinned():
    assert SCHEMA == "campaign-os/diagnostic-bundle/v1"


def test_credentials_booleans_only(tmp_path, monkeypatch):
    secret = "supersecretvalue_for_ga4_test_12345"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GA4_PROPERTY_ID", "123456")
    monkeypatch.setenv("GA4_SERVICE_ACCOUNT_JSON_PATH", secret)

    spec = JobSpec(
        name="ga4_report",
        fn=lambda: {"ok": False, "error": "auth"},
        every_seconds=86400,
        credentials=("GA4_PROPERTY_ID", "GA4_SERVICE_ACCOUNT_JSON_PATH"),
        writes=("ga4-report.json",),
    )
    bundle = build_bundle(
        spec=spec,
        run_id="20260914T020202Z-ga4_report-cred01",
        attempt=1,
        status="FAILED",
        started="2026-09-14T02:02:02Z",
        finished="2026-09-14T02:02:03Z",
        duration_s=1.0,
        error="invalid_grant",
    )
    assert bundle["schema"] == "campaign-os/diagnostic-bundle/v1"
    assert bundle["best_effort"] is False
    for key, value in bundle["credentials"].items():
        assert isinstance(value, bool), f"credentials[{key}] not bool"
    blob = json.dumps(bundle)
    assert secret not in blob


def test_retention_max_count(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = "ga4_report"
    directory = tmp_path / "diagnostics" / job
    directory.mkdir(parents=True)
    for i in range(205):
        path = directory / f"20260914T000000Z-{job}-{i:04d}.json"
        path.write_text("{}\n")
        os.utime(path, (time.time() - i, time.time() - i))
    prune(job)
    remaining = sorted(directory.glob("*.json"))
    assert len(remaining) == 200
    names = {p.name for p in remaining}
    # oldest five (highest age index 200-204) should be gone
    for i in range(200, 205):
        assert f"20260914T000000Z-{job}-{i:04d}.json" not in names


def test_retention_age_30_days(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    job = "meta_refresh"
    directory = tmp_path / "diagnostics" / job
    directory.mkdir(parents=True)
    old = directory / "old.json"
    new = directory / "new.json"
    old.write_text("{}\n")
    new.write_text("{}\n")
    old_mtime = time.time() - 31 * 86400
    os.utime(old, (old_mtime, old_mtime))
    prune(job)
    assert not old.exists()
    assert new.exists()


def test_write_bundle_guard_does_not_fail_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    def _fn():
        return {"ok": False, "error": "boom"}

    register(
        JobSpec(
            name="diag_guard_job",
            fn=_fn,
            every_seconds=3600,
            criticality="LOW",
            retries=0,
            writes=("diag-guard.json",),
        )
    )

    def _boom(**_kwargs):
        raise RuntimeError("bundle writer exploded")

    monkeypatch.setattr("_lib.jobs.diagnostics.write_bundle", _boom)
    # Also patch the import site used inside run_job
    import _lib.jobs.runner as runner_mod

    monkeypatch.setattr(runner_mod, "write_bundle", _boom, raising=False)

    # Force the import inside run_job to see the raising function
    import _lib.jobs.diagnostics as diag_mod

    monkeypatch.setattr(diag_mod, "write_bundle", _boom)

    row = run_job("diag_guard_job", triggered_by="test")
    assert row["status"] == "FAILED"
    assert row["ok"] is False
    assert row["run_id"]
