"""Layer 2 data_archive job + freshness / queue ignore behaviour."""

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


def _purge_job_modules() -> None:
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib.jobs"):
            del sys.modules[mod]


@pytest.fixture()
def data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("COS_JOB_CANCEL", raising=False)
    _purge_job_modules()
    return tmp_path


def _ts_days_ago(days: float) -> str:
    return (
        (datetime.now(timezone.utc) - timedelta(days=days))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _write_json_dict(data_dir: Path, rel: str, *, age_days: float) -> Path:
    path = data_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"generated": _ts_days_ago(age_days), "payload": True}),
        encoding="utf-8",
    )
    return path


def test_data_archive_registered_in_layer2_specs(data_dir):
    from _lib.jobs.layer2 import LAYER2_JOB_NAMES, layer2_specs

    assert "data_archive" in LAYER2_JOB_NAMES
    names = {s.name for s in layer2_specs()}
    assert "data_archive" in names
    spec = next(s for s in layer2_specs() if s.name == "data_archive")
    assert spec.timeout_seconds == 120
    assert spec.best_effort is True
    assert "archive/manifest.json" in spec.writes


def test_rotten_dict_archived_and_excluded_from_freshness(data_dir):
    from _lib.jobs.layer2 import data_archive

    rel = "seo-rankings.json"
    _write_json_dict(data_dir, rel, age_days=50)

    result = data_archive.run()
    assert result.get("ok") is True
    assert result.get("archived") == 1

    doc = json.loads((data_dir / rel).read_text(encoding="utf-8"))
    assert doc.get("_campaign_os_archive", {}).get("ignored") is True
    assert doc.get("payload") is True

    import app as app_module

    summary = app_module._build_freshness_on_demand(str(data_dir))
    rotten_paths = {e["path"] for e in summary.get("rotten_files", [])}
    assert rel not in rotten_paths
    assert summary["by_staleness"].get("archived", 0) >= 1


def test_already_archived_is_noop(data_dir):
    from _lib.jobs.layer2 import data_archive

    rel = "old-metrics.json"
    path = _write_json_dict(data_dir, rel, age_days=50)
    first = data_archive.run()
    assert first.get("archived") == 1

    second = data_archive.run()
    assert second.get("ok") is True
    assert second.get("archived") == 0
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["_campaign_os_archive"]["ignored"] is True


def test_stale_file_not_archived(data_dir):
    from _lib.jobs.layer2 import data_archive

    rel = "stale-only.json"
    _write_json_dict(data_dir, rel, age_days=20)
    result = data_archive.run()
    assert result.get("ok") is True
    assert result.get("archived") == 0
    doc = json.loads((data_dir / rel).read_text(encoding="utf-8"))
    assert "_campaign_os_archive" not in doc


def test_archive_directory_not_walked_for_freshness(data_dir):
    archive_dir = data_dir / "archive" / "2026-09-22"
    archive_dir.mkdir(parents=True)
    (archive_dir / "buried.json").write_text(
        json.dumps({"generated": _ts_days_ago(90)}),
        encoding="utf-8",
    )
    _write_json_dict(data_dir, "live.json", age_days=5)

    import app as app_module

    summary = app_module._build_freshness_on_demand(str(data_dir))
    walked = {rel.replace("\\", "/") for rel in []}
    for ap, rp in app_module._walk_data_json_files(str(data_dir)):
        walked.add(rp.replace("\\", "/"))
    assert "archive/2026-09-22/buried.json" not in walked
    assert summary["total_files"] == 1


def test_agent_queue_writer_skips_archived_paths(data_dir):
    from _lib.jobs.layer2 import agent_queue_writer, data_archive

    rel = "rotten-queue.json"
    _write_json_dict(data_dir, rel, age_days=55)
    data_archive.run()

    (data_dir / "freshness.json").write_text(
        json.dumps({"rotten_files": [{"path": rel}], "stale_files": []}),
        encoding="utf-8",
    )
    (data_dir / "slot-planner.json").write_text(json.dumps({"empty_slots": []}), encoding="utf-8")

    result = agent_queue_writer.run()
    assert result.get("ok") is True
    doc = json.loads((data_dir / "agent-queue.json").read_text(encoding="utf-8"))
    refresh_rows = [r for r in doc["rows"] if r.get("action") == "refresh_data"]
    assert not any(rel in r.get("payload_ref", "") for r in refresh_rows)


def test_array_relocated_with_stub(data_dir):
    from _lib.jobs.layer2 import data_archive

    rel = "lists/items.json"
    path = data_dir / rel
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps([{"generated": _ts_days_ago(60)}]), encoding="utf-8")

    result = data_archive.run()
    assert result.get("ok") is True
    assert result.get("archived") == 1

    stub = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(stub, dict)
    relocated = stub["_campaign_os_archive"]["relocated_to"]
    assert relocated.startswith("archive/")
    assert (data_dir / relocated).is_file()
