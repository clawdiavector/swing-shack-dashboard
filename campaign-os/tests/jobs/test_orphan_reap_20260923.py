"""Orphan started rows reaped at boot — worker_death terminal row."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib.jobs import ledger  # noqa: E402
from _lib.jobs.registry import register  # noqa: E402
from _lib.jobs.runner import REAPED_ERROR_CLASS, reap_orphan_runs, verdict_for  # noqa: E402
from _lib.jobs.spec import JobSpec  # noqa: E402


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def _register_probe(*, timeout_seconds: int = 60) -> str:
    name = "orphan_reap_probe"
    register(
        JobSpec(
            name=name,
            fn=lambda: {"ok": True},
            every_seconds=3600,
            timeout_seconds=timeout_seconds,
            brand_mode="per_brand",
            brands=("swing-shack", "stick"),
            writes=("orphan-reap-probe.json",),
        )
    )
    return name


def _write_rows(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_reap_writes_terminal_row_for_orphan(data_dir):
    name = _register_probe()
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    started = (now - timedelta(seconds=300)).strftime("%Y-%m-%dT%H:%M:%SZ")
    boot_at = now - timedelta(seconds=60)
    _write_rows(
        data_dir / "job-runs.jsonl",
        [
            {
                "job": name,
                "brand": "swing-shack",
                "run_id": "orphan-1",
                "phase": "started",
                "started": started,
                "triggered_by": "schedule",
            }
        ],
    )
    appended = reap_orphan_runs(boot_at=boot_at, now=now)
    assert len(appended) == 1
    row = appended[0]
    assert row["phase"] == "finished"
    assert row["status"] == "FAILED"
    assert row["error_class"] == REAPED_ERROR_CLASS
    assert row.get("reaped") is True
    assert row["run_id"] == "orphan-1"
    assert row["brand"] == "swing-shack"


def test_reap_is_idempotent(data_dir):
    name = _register_probe()
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    started = (now - timedelta(seconds=300)).strftime("%Y-%m-%dT%H:%M:%SZ")
    boot_at = now - timedelta(seconds=60)
    _write_rows(
        data_dir / "job-runs.jsonl",
        [
            {
                "job": name,
                "brand": "stick",
                "run_id": "orphan-2",
                "phase": "started",
                "started": started,
                "triggered_by": "manual",
            }
        ],
    )
    assert len(reap_orphan_runs(boot_at=boot_at, now=now)) == 1
    assert len(reap_orphan_runs(boot_at=boot_at, now=now)) == 0


def test_reap_skips_young_orphan(data_dir):
    name = _register_probe()
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    started = (now - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    boot_at = now - timedelta(seconds=120)
    _write_rows(
        data_dir / "job-runs.jsonl",
        [
            {
                "job": name,
                "brand": "swing-shack",
                "run_id": "young-1",
                "phase": "started",
                "started": started,
                "triggered_by": "schedule",
            }
        ],
    )
    assert reap_orphan_runs(boot_at=boot_at, now=now) == []


def test_reap_skips_run_started_after_boot(data_dir):
    name = _register_probe()
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    boot_at = now - timedelta(seconds=600)
    started = (now - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_rows(
        data_dir / "job-runs.jsonl",
        [
            {
                "job": name,
                "brand": "swing-shack",
                "run_id": "live-1",
                "phase": "started",
                "started": started,
                "triggered_by": "schedule",
            }
        ],
    )
    assert reap_orphan_runs(boot_at=boot_at, now=now) == []


def test_reap_skips_completed_run(data_dir):
    name = _register_probe()
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    boot_at = now - timedelta(seconds=600)
    started = (now - timedelta(seconds=300)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_rows(
        data_dir / "job-runs.jsonl",
        [
            {
                "job": name,
                "brand": "swing-shack",
                "run_id": "done-1",
                "phase": "started",
                "started": started,
                "triggered_by": "schedule",
            },
            {
                "job": name,
                "brand": "swing-shack",
                "run_id": "done-1",
                "phase": "finished",
                "started": started,
                "finished": started,
                "status": "OK",
                "triggered_by": "schedule",
            },
        ],
    )
    assert reap_orphan_runs(boot_at=boot_at, now=now) == []


def test_verdict_after_reap_is_failed_not_stuck(data_dir):
    name = _register_probe()
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    started = (now - timedelta(seconds=300)).strftime("%Y-%m-%dT%H:%M:%SZ")
    boot_at = now - timedelta(seconds=60)
    _write_rows(
        data_dir / "job-runs.jsonl",
        [
            {
                "job": name,
                "brand": "swing-shack",
                "run_id": "v-1",
                "phase": "started",
                "started": started,
                "triggered_by": "schedule",
            }
        ],
    )
    reap_orphan_runs(boot_at=boot_at, now=now)
    rows = ledger.read_rows(name, brand="swing-shack")
    assert verdict_for(name, rows, now=now, brand="swing-shack") == "FAILED"


def test_sibling_brand_unaffected(data_dir):
    name = _register_probe()
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    boot_at = now - timedelta(seconds=60)
    ok_started = (now - timedelta(seconds=100)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ok_finished = ok_started
    stuck_started = (now - timedelta(seconds=300)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_rows(
        data_dir / "job-runs.jsonl",
        [
            {
                "job": name,
                "brand": "swing-shack",
                "run_id": "ss-stuck",
                "phase": "started",
                "started": stuck_started,
                "triggered_by": "schedule",
            },
            {
                "job": name,
                "brand": "stick",
                "run_id": "stick-ok",
                "phase": "finished",
            "started": ok_started,
            "finished": ok_finished,
            "status": "OK",
            "triggered_by": "schedule",
        },
    ],
)
    reap_orphan_runs(boot_at=boot_at, now=now)
    stick_rows = ledger.read_rows(name, brand="stick")
    assert verdict_for(name, stick_rows, now=now, brand="stick") == "OK"


def test_reap_survives_malformed_ledger(data_dir, monkeypatch):
    name = _register_probe()
    path = data_dir / "job-runs.jsonl"
    path.write_text("{not json}\n", encoding="utf-8")
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
    reap_orphan_runs(boot_at=now - timedelta(seconds=60), now=now)

    path.write_text(
        path.read_text(encoding="utf-8")
        + json.dumps(
            {
                "job": "unknown_job_xyz",
                "brand": "swing-shack",
                "run_id": "x",
                "phase": "started",
                "started": "2020-01-01T00:00:00Z",
                "triggered_by": "schedule",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    reap_orphan_runs(boot_at=now - timedelta(seconds=60), now=now)
