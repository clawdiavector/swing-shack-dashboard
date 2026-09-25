"""social_ingest job — platforms, skip when Meta missing."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent.parent
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


@pytest.fixture()
def job_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib.jobs") or mod.startswith("_lib.social_history"):
            del sys.modules[mod]
    from _lib.jobs.brand_lanes import clear_brands_cache

    clear_brands_cache()
    yield tmp_path


def test_social_ingest_skips_without_meta_token(job_env, monkeypatch):
    monkeypatch.delenv("META_SYSTEM_USER_TOKEN", raising=False)
    monkeypatch.delenv("META_SYSTEM_USER_TOKEN_STICK", raising=False)
    monkeypatch.delenv("META_SYSTEM_USER_TOKEN_STICK_PAARL", raising=False)
    from _lib.jobs import runner
    from _lib.jobs.registry import JOBS

    assert "social_ingest" in JOBS
    result = runner.run_job("social_ingest", triggered_by="test", brand="swing-shack")
    assert result.get("status") == "SKIPPED" or result.get("skipped") is True


def test_social_ingest_no_channels_skips(job_env, monkeypatch):
    monkeypatch.setenv("META_SYSTEM_USER_TOKEN", "fake-token-for-test")
    from _lib.jobs.layer1 import social_ingest as mod

    out = mod.run(brand="bag-drop")
    assert out.get("skipped") is True
    assert "instagram" in (out.get("reason") or "")
