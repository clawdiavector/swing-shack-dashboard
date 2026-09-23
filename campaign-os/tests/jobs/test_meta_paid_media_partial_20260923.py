"""Paid-media failure surfaces as partial without flipping organic ok."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def test_fetch_all_with_paid_media_partial(monkeypatch):
    from _lib import meta_live_fetch as mlf
    from _lib.jobs.outcome import summarize_result

    monkeypatch.setattr(mlf, "fetch_all", lambda **_: {"ok": True, "rows": 1})
    monkeypatch.setattr(mlf, "fetch_paid_media", lambda **_: {"ok": False, "error": "no token"})
    out = mlf.fetch_all_with_paid_media(brand="stick")
    assert out["ok"] is True
    assert out["paid_media_ok"] is False
    assert out.get("partial") is True
    summary = summarize_result(out)
    assert summary.get("paid_media_ok") is False
    assert summary.get("partial") is True


def test_fetch_all_with_paid_media_both_ok(monkeypatch):
    from _lib import meta_live_fetch as mlf
    from _lib.jobs.outcome import summarize_result

    monkeypatch.setattr(mlf, "fetch_all", lambda **_: {"ok": True})
    monkeypatch.setattr(mlf, "fetch_paid_media", lambda **_: {"ok": True})
    out = mlf.fetch_all_with_paid_media(brand="swing-shack")
    assert out["ok"] is True
    assert out["paid_media_ok"] is True
    summary = summarize_result(out)
    assert "partial" not in summary


@pytest.fixture()
def job_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib"):
            del sys.modules[mod]
    yield tmp_path


def test_runner_result_summary_carries_partial(job_env, monkeypatch):
    from dataclasses import replace

    from _lib.jobs import ledger, runner
    from _lib.jobs.registry import JOBS

    monkeypatch.setenv("META_SYSTEM_USER_TOKEN", "test-token-not-secret")
    from _lib.jobs.brand_lanes import clear_brands_cache

    clear_brands_cache()

    def _stub(**_kwargs):
        return {
            "ok": True,
            "paid_media_ok": False,
            "partial": True,
            "rows": 5,
        }

    JOBS["meta_refresh"] = replace(JOBS["meta_refresh"], fn=_stub)
    runner.run_job("meta_refresh", triggered_by="test", brand="swing-shack")
    rows = ledger.read_rows("meta_refresh", brand="swing-shack")
    finished = [r for r in rows if r.get("phase") == "finished"]
    assert finished
    summary = finished[-1].get("result_summary") or {}
    assert summary.get("partial") is True
    assert summary.get("paid_media_ok") is False
    spec = JOBS["meta_refresh"]
    assert spec.timeout_seconds == 60
    assert spec.retries == 0
