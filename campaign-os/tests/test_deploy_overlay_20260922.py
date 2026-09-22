"""Deploy overlay: runtime volume must not be clobbered by bundled seed."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

import app as app_module


def _campaign_doc(marker: str) -> dict:
    return {
        "campaigns": {marker: {"assets": {}}},
        "activeCampaignId": marker,
        "portfolioMetadata": {},
    }


def test_load_data_prefers_runtime_even_when_older(monkeypatch, tmp_path):
    runtime = tmp_path / "vol"
    runtime.mkdir()
    bundled_root = tmp_path / "repo"
    (bundled_root / "data").mkdir(parents=True)
    runtime_file = runtime / "campaign-data.json"
    bundled_file = bundled_root / "data" / "campaign-data.json"
    runtime_file.write_text(json.dumps(_campaign_doc("runtime")), encoding="utf-8")
    bundled_file.write_text(json.dumps(_campaign_doc("bundled")), encoding="utf-8")
    now = time.time()
    os.utime(bundled_file, (now + 3600, now + 3600))

    monkeypatch.setenv("DATA_DIR", str(runtime))
    monkeypatch.setattr(app_module, "REPO_ROOT", str(bundled_root))

    doc = app_module.load_data()
    assert doc["activeCampaignId"] == "runtime"


def test_load_data_never_writes_runtime_file(monkeypatch, tmp_path):
    runtime = tmp_path / "vol"
    runtime.mkdir()
    bundled_root = tmp_path / "repo"
    (bundled_root / "data").mkdir(parents=True)
    runtime_file = runtime / "campaign-data.json"
    bundled_file = bundled_root / "data" / "campaign-data.json"
    runtime_file.write_text(json.dumps(_campaign_doc("keep")), encoding="utf-8")
    bundled_file.write_text(json.dumps(_campaign_doc("newer")), encoding="utf-8")
    now = time.time()
    os.utime(bundled_file, (now + 7200, now + 7200))
    before = runtime_file.read_bytes()
    mtime_before = os.path.getmtime(runtime_file)

    monkeypatch.setenv("DATA_DIR", str(runtime))
    monkeypatch.setattr(app_module, "REPO_ROOT", str(bundled_root))

    for _ in range(3):
        app_module.load_data()

    assert runtime_file.read_bytes() == before
    assert os.path.getmtime(runtime_file) == mtime_before


def test_load_data_falls_back_to_bundled_when_runtime_absent(monkeypatch, tmp_path):
    runtime = tmp_path / "vol"
    runtime.mkdir()
    bundled_root = tmp_path / "repo"
    (bundled_root / "data").mkdir(parents=True)
    bundled_file = bundled_root / "data" / "campaign-data.json"
    bundled_file.write_text(json.dumps(_campaign_doc("seed")), encoding="utf-8")

    monkeypatch.setenv("DATA_DIR", str(runtime))
    monkeypatch.setattr(app_module, "REPO_ROOT", str(bundled_root))

    doc = app_module.load_data()
    assert doc["activeCampaignId"] == "seed"
    assert not (runtime / "campaign-data.json").exists()


def test_boot_seed_creates_missing_canonical_files(monkeypatch, tmp_path):
    runtime = tmp_path / "vol"
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    for name in ("campaign-data.json", "scheduled-items.json", "publish-queue.json"):
        (bundled / name).write_text("{}", encoding="utf-8")

    monkeypatch.setattr(app_module, "DATA_DIR", str(runtime))
    monkeypatch.setattr(app_module, "BUNDLED_DATA_DIR", str(bundled))
    app_module._boot_seed_persistent_data()

    for name in ("campaign-data.json", "scheduled-items.json", "publish-queue.json"):
        assert (runtime / name).is_file()


def test_boot_seed_never_overwrites_existing(monkeypatch, tmp_path):
    runtime = tmp_path / "vol"
    runtime.mkdir()
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    targets = ("campaign-data.json", "scheduled-items.json", "publish-queue.json")
    for name in targets:
        (bundled / name).write_text('{"from":"bundled"}', encoding="utf-8")
        (runtime / name).write_text(f"SENTINEL-{name}", encoding="utf-8")

    monkeypatch.setattr(app_module, "DATA_DIR", str(runtime))
    monkeypatch.setattr(app_module, "BUNDLED_DATA_DIR", str(bundled))
    app_module._boot_seed_persistent_data()
    app_module._boot_seed_persistent_data()

    for name in targets:
        assert (runtime / name).read_text(encoding="utf-8") == f"SENTINEL-{name}"


def test_init_repo_does_not_touch_data_dir(monkeypatch, tmp_path):
    runtime = tmp_path / "vol"
    runtime.mkdir()
    monkeypatch.setenv("DATA_DIR", str(runtime))
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-not-a-secret")
    monkeypatch.setattr(app_module, "DATA_DIR", str(runtime))

    def walk_snapshot(root):
        return sorted(
            (dirpath, tuple(sorted(fnames)))
            for dirpath, _d, fnames in os.walk(root)
        )

    before = walk_snapshot(str(runtime))
    app_module._GIT_SYNC_DONE = False
    app_module._boot_git_sync()
    after = walk_snapshot(str(runtime))
    assert before == after
    for dirpath, _fnames in after:
        assert ".git" not in Path(dirpath).parts


def test_git_push_is_disabled(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("subprocess must not run")

    monkeypatch.setattr(subprocess, "run", boom)
    ok, msg = app_module.git_push("test")
    assert ok is False
    assert "disabled" in msg.lower()


def test_calendar_alerts_write_to_volume_not_bundled(monkeypatch, tmp_path):
    runtime = tmp_path / "vol"
    bundled = tmp_path / "bundled"
    brand = "swing-shack"
    (bundled / "brand-directory" / brand).mkdir(parents=True)
    bundled_alerts = bundled / "brand-directory" / brand / "calendar_alerts.jsonl"
    bundled_alerts.write_text("", encoding="utf-8")
    bundled_before = bundled_alerts.read_bytes()

    monkeypatch.setenv("DATA_DIR", str(runtime))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(bundled))

    from _lib import marketing_calendar as mc

    monkeypatch.setattr(mc, "_DATA_DIR", runtime)
    monkeypatch.setattr(mc, "_BRAND_DIR", runtime / "brand-directory")
    monkeypatch.setattr(mc, "_BUNDLED_DATA_DIR", bundled / "brand-directory")

    mc.create_alert_if_new(
        {
            "brand_id": brand,
            "alert_type": "event_changed",
            "priority": "normal",
            "message": "overlay test",
        }
    )

    assert bundled_alerts.read_bytes() == bundled_before
    volume_alerts = runtime / "brand-directory" / brand / "calendar_alerts.jsonl"
    assert volume_alerts.is_file()
    assert "overlay test" in volume_alerts.read_text(encoding="utf-8")


def test_marketing_lanes_root_is_volume(monkeypatch, tmp_path):
    runtime = tmp_path / "vol"
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    monkeypatch.setenv("DATA_DIR", str(runtime))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(bundled))

    from _lib import marketing_lanes as ml

    assert ml._data_root() == runtime
    assert runtime.exists()


def test_freshness_walk_excludes_repo_dir(monkeypatch, tmp_path):
    runtime = tmp_path / "vol"
    runtime.mkdir()
    (runtime / "repo").mkdir()
    (runtime / "repo" / "a.json").write_text("{}", encoding="utf-8")
    (runtime / "live.json").write_text('{"generated_at":"2026-01-01T00:00:00Z"}', encoding="utf-8")

    summary = app_module._build_freshness_on_demand(str(runtime))
    assert summary["total_files"] == 1


def test_admin_data_sync_bundled_still_works(monkeypatch, tmp_path, cos_session):
    runtime = tmp_path / "vol"
    runtime.mkdir()
    bundled_root = tmp_path / "repo"
    (bundled_root / "data").mkdir(parents=True)
    bundled_file = bundled_root / "data" / "campaign-data.json"
    bundled_file.write_text(json.dumps(_campaign_doc("synced")), encoding="utf-8")

    monkeypatch.setenv("DATA_DIR", str(runtime))
    monkeypatch.setattr(app_module, "REPO_ROOT", str(bundled_root))

    resp = cos_session.post("/api/admin/data-sync-bundled")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("ok") is True
    runtime_doc = json.loads((runtime / "campaign-data.json").read_text(encoding="utf-8"))
    assert runtime_doc["activeCampaignId"] == "synced"


def test_data_sync_bundled_requires_auth(cos_app):
    client = cos_app.test_client(cos_anon=True)
    resp = client.post("/api/admin/data-sync-bundled")
    assert resp.status_code == 401
