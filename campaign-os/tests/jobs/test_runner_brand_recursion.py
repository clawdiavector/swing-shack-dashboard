"""Track A — verdict_for must not recurse on brand=None ledger keys."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib.jobs import ledger  # noqa: E402
from _lib.jobs.registry import register  # noqa: E402
from _lib.jobs.runner import (  # noqa: E402
    _aggregate_verdict,
    _brand_status_entries,
    build_status,
    verdict_for,
)
from _lib.jobs.spec import JobSpec  # noqa: E402


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def _write_ledger(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _register_per_brand(name: str, *, every_seconds: int = 43200) -> JobSpec:
    spec = JobSpec(
        name=name,
        fn=lambda: {"ok": True},
        every_seconds=every_seconds,
        brand_mode="per_brand",
        brands=("swing-shack", "stick", "bag-drop"),
        writes=(f"{name}.json",),
    )
    register(spec)
    return spec


def test_verdict_for_legacy_brand_none_rows_no_recursion(data_dir):
    """Prod repro: per_brand job with only pre-P1a rows must not RecursionError."""
    name = "legacy_none_only"
    spec = _register_per_brand(name)
    now = datetime(2026, 9, 21, 8, 0, 0, tzinfo=timezone.utc)
    _write_ledger(
        data_dir / "job-runs.jsonl",
        [
            {
                "job": name,
                "run_id": "r1",
                "phase": "started",
                "started": "2026-09-10T00:00:00Z",
                "triggered_by": "schedule",
            },
            {
                "job": name,
                "run_id": "r1",
                "phase": "finished",
                "started": "2026-09-10T00:00:00Z",
                "finished": "2026-09-10T00:00:05Z",
                "status": "OK",
                "triggered_by": "schedule",
                "rows": 1,
                "writes": [f"{name}.json"],
                "error": None,
            },
        ],
    )
    rows = ledger.read_rows(name)
    result = verdict_for(name, rows, now=now)
    assert result in ("OK", "LATE", "NEVER", "FAILED", "STUCK", "SKIPPED")
    assert spec.brand_mode == "per_brand"


def test_build_status_legacy_brand_none_rows(data_dir):
    """build_status() with legacy brand-less ledger must complete."""
    name = "legacy_build_status"
    _register_per_brand(name)
    _write_ledger(
        data_dir / "job-runs.jsonl",
        [
            {
                "job": name,
                "run_id": "r1",
                "phase": "finished",
                "started": "2026-09-10T00:00:00Z",
                "finished": "2026-09-10T00:00:05Z",
                "status": "OK",
                "triggered_by": "schedule",
            },
        ],
    )
    status = build_status()
    assert isinstance(status["jobs"], list)
    job_row = next(j for j in status["jobs"] if j["name"] == name)
    assert job_row["verdict"] in ("OK", "LATE", "NEVER", "FAILED", "STUCK", "SKIPPED")


def test_brand_status_entries_mixed_none_and_stick(data_dir):
    """Mixed None + brand keys: no TypeError; brands array excludes None lane."""
    name = "mixed_brand_keys"
    spec = _register_per_brand(name)
    now = datetime(2026, 9, 21, 8, 0, 0, tzinfo=timezone.utc)
    grouped = {
        (name, None): [
            {
                "job": name,
                "phase": "finished",
                "status": "FAILED",
                "finished": "2026-09-01T00:00:00Z",
            }
        ],
        (name, "stick"): [
            {
                "job": name,
                "brand": "stick",
                "phase": "finished",
                "status": "OK",
                "finished": "2026-09-21T06:00:00Z",
            }
        ],
    }
    entries = _brand_status_entries(spec, grouped, now)
    brand_ids = [e["brand"] for e in entries]
    assert "stick" in brand_ids
    assert None not in brand_ids
    stick_entry = next(e for e in entries if e["brand"] == "stick")
    assert stick_entry["verdict"] == "OK"


def test_aggregate_verdict_ok_and_failed(data_dir):
    assert _aggregate_verdict(["OK", "FAILED"]) == "FAILED"


def test_aggregate_verdict_all_skipped(data_dir):
    assert _aggregate_verdict(["SKIPPED", "SKIPPED"]) == "SKIPPED"


def test_legacy_only_verdict_unchanged(data_dir):
    """When only brand=None rows exist, flat path still evaluates them."""
    name = "legacy_only_flat"
    _register_per_brand(name, every_seconds=43200)
    now = datetime(2026, 9, 21, 8, 0, 0, tzinfo=timezone.utc)
    rows = [
        {
            "job": name,
            "run_id": "r1",
            "phase": "finished",
            "started": "2026-09-10T00:00:00Z",
            "finished": "2026-09-10T00:00:05Z",
            "status": "OK",
            "triggered_by": "schedule",
        },
    ]
    assert verdict_for(name, rows, now=now) == "LATE"


def test_api_jobs_status_with_legacy_ledger(data_dir, monkeypatch):
    """GET /api/jobs/status returns 200 when ledger has brand-less per_brand rows."""
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    name = "api_legacy_none"
    _register_per_brand(name)
    _write_ledger(
        data_dir / "job-runs.jsonl",
        [
            {
                "job": name,
                "run_id": "r1",
                "phase": "finished",
                "started": "2026-09-10T00:00:00Z",
                "finished": "2026-09-10T00:00:05Z",
                "status": "OK",
                "triggered_by": "schedule",
            },
        ],
    )
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib.jobs"):
            del sys.modules[mod]
    import app as app_module

    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    app_module._GIT_SYNC_DONE = True
    client = app_module.app.test_client()
    resp = client.get(
        "/api/jobs/status",
        headers={"Authorization": "Bearer test-job-token-not-a-secret"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert isinstance(body.get("jobs"), list)
