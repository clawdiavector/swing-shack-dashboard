"""P2a brand lanes — BrandIO wiring, flat fallback, meta gate, isolation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


@pytest.fixture()
def job_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    monkeypatch.setenv("COS_FLAT_FALLBACK", "1")
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib.jobs") or mod.startswith("_lib.brand"):
            del sys.modules[mod]
    from _lib.jobs.brand_lanes import clear_brands_cache

    clear_brands_cache()
    yield tmp_path
    clear_brands_cache()


def test_brand_io_write_resolves_per_brand_path(job_env, tmp_path):
    from _lib.jobs.layer1._io import io_for_job, read_json
    from _lib.jobs.registry import JOBS

    io = io_for_job("ga4_report", "stick")
    io.write("ga4-metrics.json", {"total_sessions": 42, "pages": []})
    assert (tmp_path / "brands" / "stick" / "ga4-metrics.json").is_file()
    assert read_json("ga4-metrics.json", brand="stick", spec=JOBS["ga4_report"]) == {
        "total_sessions": 42,
        "pages": [],
    }


def test_flat_fallback_default_brand_only(job_env, tmp_path):
    from _lib.jobs.layer1._io import flat_fallback_counts, io_for_job, reset_flat_fallback_counts
    from _lib.jobs.registry import JOBS

    reset_flat_fallback_counts()
    flat = {"total_sessions": 99}
    (tmp_path / "ga4-metrics.json").write_text(json.dumps(flat))

    io_ss = io_for_job("ga4_report", "swing-shack")
    assert io_ss.read("ga4-metrics.json") == flat
    assert flat_fallback_counts()

    io_stick = io_for_job("ga4_report", "stick")
    assert io_stick.read("ga4-metrics.json") is None


def test_meta_load_token_fail_loud_missing_page(monkeypatch, job_env):
    from _lib.jobs.brand_lanes import clear_brands_cache
    from _lib.meta_live_fetch import _load_token

    monkeypatch.delenv("META_PAGE_ID", raising=False)
    monkeypatch.delenv("META_PAGE_ID_STICK", raising=False)
    monkeypatch.setenv("META_SYSTEM_USER_TOKEN_STICK_PAARL", "tok-stick")
    clear_brands_cache()
    creds = _load_token("stick")
    assert creds.get("ok") is False
    assert "META_PAGE_ID_STICK" in creds.get("error", "")


def test_per_brand_writes_prefix(job_env):
    from _lib.jobs.brand_lanes import resolve_path
    from _lib.jobs.registry import JOBS

    for name, spec in JOBS.items():
        if spec.brand_mode != "per_brand":
            continue
        for rel in spec.writes:
            if rel in spec.shared_writes:
                continue
            assert resolve_path(spec, rel, "stick").startswith("brands/stick/")


def test_two_brand_hook_bank_isolation(job_env, tmp_path):
    from _lib.jobs.layer1._io import io_for_job

    io_ss = io_for_job("insights_hooks", "swing-shack")
    io_stick = io_for_job("insights_hooks", "stick")
    io_ss.write("hook-bank.json", {"updated": "a", "total_hooks": 1, "output_buckets": {}})
    io_stick.write("hook-bank.json", {"updated": "b", "total_hooks": 2, "output_buckets": {}})
    ss = json.loads((tmp_path / "brands" / "swing-shack" / "hook-bank.json").read_text())
    stick = json.loads((tmp_path / "brands" / "stick" / "hook-bank.json").read_text())
    assert ss["total_hooks"] == 1
    assert stick["total_hooks"] == 2


def test_resolve_data_brand_identity(job_env):
    import app as app_module

    assert app_module.resolve_data_brand("stick") == "stick"
    assert app_module.resolve_data_brand("bag-drop") == "bag-drop"
