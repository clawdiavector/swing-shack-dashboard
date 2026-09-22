"""Layer 2 job contract tests — slot_planner, agent_queue_writer, review_sla."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

LAYER2_TOP_LEVEL = {
    "slot-planner.json": {
        "schema",
        "generated_at",
        "horizon_days",
        "empty_slots",
        "skipped",
        "summary",
    },
    "agent-queue.json": {"schema", "generated_at", "rows"},
    "review-sla.json": {
        "schema",
        "generated_at",
        "sla_hours",
        "summary",
        "inbox_breached",
        "calendar_breached",
        "unknown_age",
    },
}

QUEUE_ROW_KEYS = frozenset({"id", "layer", "agent", "brand", "action", "payload_ref", "status"})


def _purge_job_modules() -> None:
    for mod in list(sys.modules):
        if (
            mod == "app"
            or mod.startswith("_lib.jobs")
            or mod == "_lib.marketing_calendar"
            or mod == "_lib.intelligence"
        ):
            del sys.modules[mod]


@pytest.fixture()
def data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("COS_JOB_CANCEL", raising=False)
    _purge_job_modules()
    return tmp_path


def _assert_ok_rows(result: dict) -> None:
    assert isinstance(result, dict)
    assert result.get("ok") is True
    assert isinstance(result.get("rows"), int)


def _assert_fail_no_raise(result: dict) -> None:
    assert isinstance(result, dict)
    assert result.get("ok") is False
    assert result.get("error")


def _assert_writes(data_dir: Path, names: tuple[str, ...]) -> None:
    for name in names:
        path = data_dir / name
        assert path.is_file(), f"missing write {name}"
        obj = json.loads(path.read_text(encoding="utf-8"))
        assert set(obj.keys()) == LAYER2_TOP_LEVEL[name], (
            f"{name} keys={sorted(obj.keys())} expected={sorted(LAYER2_TOP_LEVEL[name])}"
        )


def _seed_min_calendar(data_dir: Path, brand_id: str = "stick") -> None:
    cal_dir = data_dir / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date()
    record = {
        "calendar_id": "cal-test-1",
        "event_key": "evt-test-1",
        "brand_id": brand_id,
        "pillar_id": "stick-retail",
        "status": "approved",
        "event_date": today.isoformat(),
        "title": "Occupied day",
    }
    (cal_dir / f"{brand_id}.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")


def test_layer2_jobs_registered(data_dir):
    from _lib.jobs.registry import JOBS

    for name in ("slot_planner", "agent_queue_writer", "review_sla", "holiday_inject", "data_archive"):
        assert name in JOBS
        assert JOBS[name].credentials == ()


def test_schedules_and_descriptions(data_dir):
    from _lib.jobs.descriptions import description_for
    from _lib.jobs.schedules import schedule_for

    for name in ("slot_planner", "agent_queue_writer", "review_sla", "data_archive"):
        assert schedule_for(name)
        desc = description_for(name)
        assert desc.get("title")
        assert desc.get("summary")
    desc = description_for("holiday_inject")
    assert desc.get("title")
    assert desc.get("summary")


def test_slot_planner_empty_world(data_dir):
    from _lib.jobs.layer2 import slot_planner

    fixed = datetime(2026, 9, 17, tzinfo=timezone.utc).date()
    with patch.object(slot_planner, "_today_utc", return_value=fixed):
        result = slot_planner.run()
    _assert_ok_rows(result)
    _assert_writes(data_dir, ("slot-planner.json",))
    doc = json.loads((data_dir / "slot-planner.json").read_text(encoding="utf-8"))
    skipped_brands = {row.get("brand") for row in doc["skipped"]}
    assert "swing-shack" not in skipped_brands
    assert doc["summary"]["brands_planned"] == 3


def test_slot_planner_with_calendar_record(data_dir):
    from _lib.jobs.layer2 import slot_planner

    _seed_min_calendar(data_dir)
    fixed = datetime(2026, 9, 17, tzinfo=timezone.utc).date()
    with patch.object(slot_planner, "_today_utc", return_value=fixed):
        result = slot_planner.run()
    _assert_ok_rows(result)
    doc = json.loads((data_dir / "slot-planner.json").read_text(encoding="utf-8"))
    stick_slots = [s for s in doc["empty_slots"] if s["brand"] == "stick"]
    assert not any(
        s["date"] == fixed.isoformat() and s["pillar_id"] == "stick-retail" for s in stick_slots
    )


def test_slot_planner_deterministic_except_timestamp(data_dir):
    from _lib.jobs.layer2 import slot_planner

    fixed = datetime(2026, 9, 17, tzinfo=timezone.utc).date()
    with patch.object(slot_planner, "_today_utc", return_value=fixed):
        slot_planner.run()
        first = json.loads((data_dir / "slot-planner.json").read_text(encoding="utf-8"))
        slot_planner.run()
        second = json.loads((data_dir / "slot-planner.json").read_text(encoding="utf-8"))
    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second


def test_slot_planner_failure_path(data_dir, monkeypatch):
    import _lib.marketing_calendar as mc

    def _boom(*_args, **_kwargs):
        raise RuntimeError("calendar down")

    monkeypatch.setattr(mc, "canonical_records", _boom)
    from _lib.jobs.layer2 import slot_planner

    result = slot_planner.run()
    _assert_fail_no_raise(result)


def test_agent_queue_writer_empty_world(data_dir):
    from _lib.jobs.layer2 import agent_queue_writer

    result = agent_queue_writer.run()
    _assert_ok_rows(result)
    _assert_writes(data_dir, ("agent-queue.json",))
    doc = json.loads((data_dir / "agent-queue.json").read_text(encoding="utf-8"))
    assert doc["rows"] == []


def test_agent_queue_writer_from_inputs(data_dir):
    from _lib.jobs.layer2 import agent_queue_writer

    (data_dir / "slot-planner.json").write_text(
        json.dumps(
            {
                "empty_slots": [
                    {
                        "brand": "stick",
                        "date": "2026-09-20",
                        "pillar_id": "stick-retail",
                        "pillar_name": "Retail",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (data_dir / "freshness.json").write_text(
        json.dumps({"rotten_files": [{"path": "data/seo-rankings.json"}]}),
        encoding="utf-8",
    )
    (data_dir / "recommendation-scores.json").write_text(
        json.dumps(
            {
                "do_first": [
                    {
                        "item": {
                            "hook_id": "test-hook",
                            "owner": "stick",
                            "type": "post",
                        }
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    result = agent_queue_writer.run()
    _assert_ok_rows(result)
    doc = json.loads((data_dir / "agent-queue.json").read_text(encoding="utf-8"))
    assert len(doc["rows"]) >= 3
    for row in doc["rows"]:
        assert set(row.keys()) == QUEUE_ROW_KEYS
        assert row["status"] == "pending"


def test_agent_queue_writer_idempotent_preserves_approved(data_dir):
    from _lib.jobs.layer2 import agent_queue_writer

    (data_dir / "slot-planner.json").write_text(
        json.dumps(
            {
                "empty_slots": [
                    {
                        "brand": "stick",
                        "date": "2026-09-20",
                        "pillar_id": "stick-retail",
                        "pillar_name": "Retail",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    approved = {
        "id": "approved-row",
        "layer": "L3",
        "agent": "cos-scout",
        "brand": "stick",
        "action": "fill_slot",
        "payload_ref": "manual",
        "status": "approved",
    }
    (data_dir / "agent-queue.json").write_text(
        json.dumps({"rows": [approved]}),
        encoding="utf-8",
    )
    agent_queue_writer.run()
    agent_queue_writer.run()
    doc = json.loads((data_dir / "agent-queue.json").read_text(encoding="utf-8"))
    ids = [row["id"] for row in doc["rows"]]
    assert ids.count("approved-row") == 1
    assert len(ids) == len(set(ids))


def test_agent_queue_writer_failure_path(data_dir, monkeypatch):
    from _lib.jobs.layer2 import agent_queue_writer

    monkeypatch.setattr(agent_queue_writer, "read_json", lambda _name: 1 / 0)  # noqa: ARG005
    result = agent_queue_writer.run()
    _assert_fail_no_raise(result)


def _seed_empty_campaign_data(data_dir: Path) -> None:
    (data_dir / "campaign-data.json").write_text(
        json.dumps({"campaigns": {}, "activeCampaignId": None, "portfolioMetadata": {}}),
        encoding="utf-8",
    )


def test_review_sla_empty_world(data_dir):
    from _lib.jobs.layer2 import review_sla

    _seed_empty_campaign_data(data_dir)
    result = review_sla.run()
    _assert_ok_rows(result)
    _assert_writes(data_dir, ("review-sla.json",))
    doc = json.loads((data_dir / "review-sla.json").read_text(encoding="utf-8"))
    assert doc["sla_hours"] == review_sla.SLA_HOURS
    assert doc["summary"]["total_breached"] == 0


def test_review_sla_counts_breaches(data_dir):
    from _lib.jobs.layer2 import review_sla

    _seed_empty_campaign_data(data_dir)
    old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat().replace("+00:00", "Z")
    campaign_data = {
        "campaigns": {
            "c1": {
                "identity": {"name": "Test", "brand": "swing-shack"},
                "assets": {
                    "a1": {
                        "name": "Draft",
                        "approvalStatus": "draft",
                        "updatedAt": old,
                        "platform": "instagram",
                    }
                },
            }
        }
    }
    (data_dir / "campaign-data.json").write_text(json.dumps(campaign_data), encoding="utf-8")

    cal_dir = data_dir / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    candidate = {
        "calendar_id": "cal-candidate-1",
        "event_key": "evt-candidate-1",
        "brand_id": "stick",
        "status": "candidate",
        "title": "Needs review",
        "last_verified": old,
    }
    (cal_dir / "stick.jsonl").write_text(json.dumps(candidate) + "\n", encoding="utf-8")

    result = review_sla.run()
    _assert_ok_rows(result)
    doc = json.loads((data_dir / "review-sla.json").read_text(encoding="utf-8"))
    assert doc["summary"]["inbox_breached"] >= 1
    assert doc["summary"]["calendar_breached"] >= 1
    assert doc["summary"]["total_breached"] >= 2


def test_review_sla_unknown_age_bucket(data_dir):
    from _lib.jobs.layer2 import review_sla

    _seed_empty_campaign_data(data_dir)
    campaign_data = {
        "campaigns": {
            "c1": {
                "identity": {"name": "Test", "brand": "swing-shack"},
                "assets": {
                    "a1": {
                        "name": "No timestamp",
                        "approvalStatus": "draft",
                        "platform": "instagram",
                    }
                },
            }
        }
    }
    (data_dir / "campaign-data.json").write_text(json.dumps(campaign_data), encoding="utf-8")
    result = review_sla.run()
    _assert_ok_rows(result)
    doc = json.loads((data_dir / "review-sla.json").read_text(encoding="utf-8"))
    assert doc["summary"]["inbox_unknown_age"] >= 1
