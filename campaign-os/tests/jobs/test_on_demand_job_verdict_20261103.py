"""On-demand jobs are not LATE/NEVER for being idle; every registered job has schedule metadata."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[2]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib.jobs import runner  # noqa: E402
from _lib.jobs.registry import JOBS  # noqa: E402
from _lib.jobs.schedules import schedule_for  # noqa: E402

NOW = datetime(2026, 11, 3, 6, 0, tzinfo=timezone.utc)


def _row(status: str, age_h: float) -> dict:
    at = (NOW - timedelta(hours=age_h)).isoformat()
    return {"job": "render_batch", "brand": "swing-shack", "phase": "finished", "status": status,
            "started": at, "finished": at}


def test_every_enabled_job_has_schedule_metadata():
    missing = [n for n, s in JOBS.items() if getattr(s, "enabled", True) and not schedule_for(n)]
    assert missing == [], missing


def test_on_demand_idle_is_skipped_not_late():
    assert runner.verdict_for("render_batch", [_row("OK", 647)], now=NOW, brand="swing-shack") == "SKIPPED"
    assert runner.verdict_for("render_batch", [], now=NOW, brand="stick") == "SKIPPED"


def test_on_demand_failure_still_shows():
    assert runner.verdict_for("render_batch", [_row("FAILED", 1)], now=NOW, brand="swing-shack") == "FAILED"


def test_clocked_job_still_late():
    row = _row("OK", 100) | {"job": "asset_qc"}
    assert runner.verdict_for("asset_qc", [row], now=NOW, brand="swing-shack") == "LATE"
