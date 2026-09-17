"""tL8-2 — holiday_inject job contract tests."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

FIXED_TODAY = dt.date(2026, 9, 17)


def _purge_modules() -> None:
    for mod in list(sys.modules):
        if (
            mod == "app"
            or mod.startswith("_lib.jobs")
            or mod == "_lib.marketing_calendar"
        ):
            del sys.modules[mod]


@pytest.fixture()
def holiday_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    for brand in ("stick", "bag-drop", "swing-shack"):
        (tmp_path / "brand-directory" / brand).mkdir(parents=True, exist_ok=True)
    _purge_modules()
    return tmp_path


def _jsonl_lines(data_dir: Path, brand: str) -> int:
    path = data_dir / "intelligence" / "marketing-calendar" / f"{brand}.jsonl"
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def test_holiday_inject_registered(holiday_env):
    from _lib.jobs.registry import JOBS

    spec = JOBS["holiday_inject"]
    assert spec.credentials == ()
    assert spec.every_seconds == 86400
    assert spec.best_effort is False


def test_idempotent_two_runs(holiday_env):
    from _lib.jobs.layer2 import holiday_inject

    first = holiday_inject.run(today=FIXED_TODAY)
    assert first["ok"] is True
    assert first["created"] > 0
    assert first["updated"] == 0
    lines_after_first = sum(_jsonl_lines(holiday_env, b) for b in first["brands"])

    second = holiday_inject.run(today=FIXED_TODAY)
    assert second["ok"] is True
    assert second["created"] == 0
    assert second["updated"] == 0
    assert second["noop"] == first["created"]
    lines_after_second = sum(_jsonl_lines(holiday_env, b) for b in second["brands"])
    assert lines_after_first == lines_after_second


def test_source_origin_and_work_due(holiday_env):
    from _lib.jobs.layer2 import holiday_inject
    import _lib.marketing_calendar as mc

    before = mc.work_due("stick")["totals"]["event_reverification_count"]
    holiday_inject.run(today=FIXED_TODAY)
    after = mc.work_due("stick")["totals"]["event_reverification_count"]
    assert before == after

    for record in mc.canonical_records("stick"):
        if record.get("created_by") == "holiday_inject":
            assert record.get("source_origin") == "deterministic_calendar"
            assert record.get("event_date")


def test_calendar_view_sees_holiday(holiday_env):
    from _lib.jobs.layer2 import holiday_inject
    import _lib.marketing_calendar as mc

    holiday_inject.run(today=FIXED_TODAY)
    view = mc.get_calendar_view("stick", "2026-09-01", "2026-12-31")
    titles = {it.get("title") for it in view.get("items") or []}
    assert "Heritage Day" in titles
    heritage = next(it for it in view["items"] if it.get("title") == "Heritage Day")
    assert heritage.get("event_date") == "2026-09-24"


def test_distinct_event_keys_across_years(holiday_env):
    from _lib.jobs.layer2 import holiday_inject
    import _lib.marketing_calendar as mc

    holiday_inject.run(today=FIXED_TODAY)
    keys = {
        r.get("event_key")
        for r in mc.canonical_records("stick")
        if r.get("title") == "Heritage Day" and r.get("created_by") == "holiday_inject"
    }
    assert "stick:heritage-day:2026" in keys
    assert "stick:heritage-day:2027" in keys


def test_easter_dates(holiday_env):
    from _lib.jobs.layer2 import holiday_inject

    holidays = holiday_inject.sa_public_holidays_for_years((2026, 2027))
    by_title_year = {(h.title, h.observed.year): h.observed for h in holidays}

    assert by_title_year[("Good Friday", 2026)] == dt.date(2026, 4, 3)
    assert by_title_year[("Good Friday", 2027)] == dt.date(2027, 3, 26)
    assert by_title_year[("Family Day", 2026)] == dt.date(2026, 4, 6)
    assert by_title_year[("Family Day", 2027)] == dt.date(2027, 3, 29)


def test_observed_sunday_rule(holiday_env):
    from _lib.jobs.layer2 import holiday_inject

    holidays = holiday_inject.sa_public_holidays_for_years((2027,))
    goodwill = next(h for h in holidays if h.title == "Day of Goodwill")
    assert goodwill.statutory == dt.date(2027, 12, 26)
    assert goodwill.observed == dt.date(2027, 12, 27)


def test_audit_integrity(holiday_env):
    from _lib.jobs.layer2 import holiday_inject
    import _lib.marketing_calendar as mc

    holiday_inject.run(today=FIXED_TODAY)
    audit = mc.audit_brand_records("stick")
    assert audit["integrity_ok"] is True
    assert audit["invalid_source_origin"] == []
    assert audit["invalid_brand_event_keys"] == []
