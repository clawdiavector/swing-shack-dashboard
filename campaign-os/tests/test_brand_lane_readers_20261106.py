"""Readers must use each brand's own data, not the frozen flat files (6 Nov 2026).

Since 18 Sep 2026 per-brand jobs write DATA_DIR/brands/<brand>/<file>. Results
(performance_view), the weekly report, the explain view and the job-status data-age
check still read DATA_DIR/<file> or the bundled repo copy, so they showed GA4 and
SEO from 18 Sep, the same numbers for every brand. On live the brand files were
fresh to 5 Nov (wiki: research/data-frozen-since-18-sep-cause-2026-11-06).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import intelligence as intel  # noqa: E402
from _lib.brand_data_paths import PER_BRAND_L1_OUTPUTS  # noqa: E402
from _lib.jobs import data_freshness as df  # noqa: E402

NOW = datetime(2026, 11, 6, 8, 0, tzinfo=timezone.utc)
OLD = {"fetched_at": "2026-09-18T09:25:40Z", "total_sessions": 1}


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _lanes(tmp_path: Path) -> None:
    _write(tmp_path / "ga4-metrics.json", OLD)
    _write(tmp_path / "brands" / "stick" / "ga4-metrics.json", {"fetched_at": "2026-11-05T12:57:00Z", "total_sessions": 161})
    _write(tmp_path / "brands" / "swing-shack" / "ga4-metrics.json", {"fetched_at": "2026-11-05T12:57:00Z", "total_sessions": 884})


# ── intelligence readers ─────────────────────────────────────────────

def test_brand_file_wins_over_the_frozen_flat_file(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _lanes(tmp_path)
    got = intel._brand_data_file("ga4-metrics.json", "stick")
    assert Path(got) == tmp_path / "brands" / "stick" / "ga4-metrics.json"


def test_other_brand_never_falls_back_to_shared_data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _write(tmp_path / "ga4-metrics.json", OLD)
    assert intel._read_json(intel._brand_data_file("ga4-metrics.json", "stick")) is None


def test_default_brand_still_reads_flat_file_before_lanes(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _write(tmp_path / "ga4-metrics.json", OLD)
    assert intel._read_json(intel._brand_data_file("ga4-metrics.json", "swing-shack")) == OLD


def test_results_page_shows_the_selected_brands_ga4(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _lanes(tmp_path)
    try:
        intel.set_request_brand("stick")
        out = intel.performance_view()
    finally:
        intel.clear_request_brand()
    assert out["ga4"]["total_sessions"] == 161
    assert out["data_as_of"]["ga4"] == "2026-11-05T12:57:00Z"


def test_weekly_report_uses_its_brands_ga4(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _lanes(tmp_path)
    out = intel.weekly_report(brand="stick")
    assert json.dumps(out).count('"total_sessions": 161') >= 1
    assert intel.get_request_brand() is None


def test_no_per_brand_file_is_read_from_a_flat_path():
    src = (CAMPAIGN_OS / "_lib" / "intelligence.py").read_text(encoding="utf-8")
    flat = re.findall(r'(?:_runtime_data_file|os\.path\.join\(DATA_DIR,)\s*\(?\s*"([^"]+)"', src)
    leaks = sorted({name for name in flat if name in PER_BRAND_L1_OUTPUTS})
    assert leaks == []


# ── job-status data age ──────────────────────────────────────────────

def _spec(**kw):
    base = dict(name="ga4_report", brand_mode="per_brand", writes=("ga4-metrics.json",), shared_writes=(), shared_reads=())
    base.update(kw)
    return SimpleNamespace(**base)


def test_per_brand_job_age_comes_from_the_brand_files(tmp_path):
    _lanes(tmp_path)
    data = df.job_data(_spec(), tmp_path, ("stick", "swing-shack"), now=NOW)
    assert data["age_days"] < 1
    assert data["file"].startswith("brands/")


def test_the_stalest_brand_decides(tmp_path):
    _lanes(tmp_path)
    _write(tmp_path / "brands" / "stick" / "ga4-metrics.json", {"fetched_at": "2026-09-29T11:10:41Z"})
    data = df.job_data(_spec(), tmp_path, ("stick", "swing-shack"), now=NOW)
    assert data["brand"] == "stick" and data["age_days"] > 30


def test_global_job_keeps_the_flat_file(tmp_path):
    _write(tmp_path / "ga4-metrics.json", {"fetched_at": "2026-11-05T08:00:00Z"})
    data = df.job_data(_spec(brand_mode="global"), tmp_path, (), now=NOW)
    assert data["file"] == "ga4-metrics.json" and data["age_days"] == 1.0
