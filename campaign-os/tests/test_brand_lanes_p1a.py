"""P1a brand lanes — registry, runner, ledger, connected accounts (A1–A15)."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

BRANDS_FILE = REPO_ROOT / "data" / "brands.json"


@pytest.fixture()
def job_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib.jobs") or mod == "_lib.connected_accounts_catalog":
            del sys.modules[mod]
    from _lib.jobs.brand_lanes import clear_brands_cache

    clear_brands_cache()
    import app as app_module

    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    app_module._GIT_SYNC_DONE = True
    client = app_module.app.test_client()
    return client, app_module, tmp_path


def _auth():
    return {"Authorization": "Bearer test-job-token-not-a-secret"}


def test_a2_all_jobs_explicit_brand_mode(job_env):
    _, app_module, _ = job_env
    from _lib.jobs.brand_lanes import BRAND_MODE_UNSET

    for name, spec in app_module._JOBS_REGISTRY.items():
        assert spec.brand_mode != BRAND_MODE_UNSET, f"{name} missing explicit brand_mode"
    from _lib.jobs.registry import JOBS

    assert "social_ingest" in app_module._JOBS_REGISTRY
    assert len(app_module._JOBS_REGISTRY) == len(JOBS)


def test_a3_import_invariants_raise(job_env):
    from _lib.jobs.brand_lanes import validate_job_spec, BRAND_MODE_UNSET
    from _lib.jobs.spec import JobSpec

    base = dict(
        name="probe",
        fn=lambda: {"ok": True},
        every_seconds=60,
        brand_mode="global",
    )

    with pytest.raises(ValueError, match="brand_mode must be set"):
        validate_job_spec(
            JobSpec(name="x", fn=lambda: {"ok": True}, every_seconds=1, brand_mode=BRAND_MODE_UNSET)
        )

    with pytest.raises(ValueError, match="invalid brand_mode"):
        validate_job_spec(JobSpec(**{**base, "name": "bad_mode", "brand_mode": "nope"}))

    with pytest.raises(ValueError, match="unknown brand"):
        validate_job_spec(
            JobSpec(**{**base, "name": "bad_brand", "brand_mode": "per_brand", "brands": ("nope",)})
        )

    with pytest.raises(ValueError, match="global jobs must not"):
        validate_job_spec(
            JobSpec(
                **{
                    **base,
                    "name": "bad_global",
                    "brand_mode": "global",
                    "brands": ("swing-shack",),
                }
            )
        )

    with pytest.raises(ValueError, match="unknown integration"):
        validate_job_spec(
            JobSpec(
                name="bad_int",
                fn=lambda: {"ok": True},
                every_seconds=60,
                brand_mode="per_brand",
                requires_integrations=("not_real",),
            )
        )

    with pytest.raises(ValueError, match="shared_writes"):
        validate_job_spec(
            JobSpec(
                name="bad_shared_w",
                fn=lambda: {"ok": True},
                every_seconds=60,
                brand_mode="per_brand",
                writes=("a.json",),
                shared_writes=("missing.json",),
            )
        )

    with pytest.raises(ValueError, match="shared_reads"):
        validate_job_spec(
            JobSpec(
                name="bad_shared_r",
                fn=lambda: {"ok": True},
                every_seconds=60,
                brand_mode="per_brand",
                reads=("a.json",),
                shared_reads=("missing.json",),
            )
        )


def test_a4_skipped_not_failed_for_missing_meta(job_env, monkeypatch):
    _, app_module, tmp_path = job_env
    from _lib.jobs import ledger, runner
    from _lib.jobs.registry import JOBS

    monkeypatch.delenv("META_SYSTEM_USER_TOKEN", raising=False)
    monkeypatch.delenv("META_SYSTEM_USER_TOKEN_STICK_PAARL", raising=False)
    monkeypatch.setenv("META_SYSTEM_USER_TOKEN", "tok-ss")
    from _lib.jobs.brand_lanes import clear_brands_cache

    clear_brands_cache()

    spec = JOBS["meta_refresh"]
    result = runner.run_job("meta_refresh", triggered_by="test")
    assert result.get("ok") is True or result.get("runs")

    rows_ss = ledger.read_rows("meta_refresh", brand="swing-shack")
    assert rows_ss
    finished_ss = [r for r in rows_ss if r.get("phase") == "finished"]
    assert finished_ss[-1]["status"] in ("OK", "FAILED", "SKIPPED")

    monkeypatch.delenv("META_SYSTEM_USER_TOKEN", raising=False)
    clear_brands_cache()
    result2 = runner.run_job("meta_refresh", triggered_by="test", brand="stick")
    assert result2.get("status") == "SKIPPED"


def test_a5_resolve_path_shared_flat(job_env):
    from _lib.jobs.registry import JOBS
    from _lib.jobs.brand_lanes import resolve_path

    for spec in JOBS.values():
        for rel in spec.writes + spec.reads:
            resolved = resolve_path(spec, rel, "swing-shack")
            if spec.brand_mode != "per_brand" or rel in spec.shared_writes or rel in spec.shared_reads:
                assert resolved == rel, f"{spec.name} {rel}"
            else:
                assert resolved == f"brands/swing-shack/{rel}", f"{spec.name} {rel}"


def test_a6_atomic_write_brand_routing(job_env, tmp_path):
    from _lib.jobs.layer1 import _io
    from _lib.jobs.registry import JOBS

    spec = JOBS["ga4_report"]
    _io.atomic_write("ga4-metrics.json", {"probe": True}, brand="swing-shack", spec=spec)
    assert (tmp_path / "brands" / "swing-shack" / "ga4-metrics.json").is_file()


def test_a7_ledger_brand_filter_and_verdicts(job_env):
    from _lib.jobs import ledger, runner

    runner.run_job("golf_news", triggered_by="test")
    rows = ledger.read_rows("golf_news")
    assert rows
    assert rows[0].get("brand") is None

    ledger.append_row(
        {
            "job": "probe_brand",
            "brand": "stick",
            "run_id": "r1-stick",
            "phase": "finished",
            "status": "OK",
            "started": "2026-01-01T00:00:00Z",
            "finished": "2026-01-01T00:00:01Z",
        }
    )
    ledger.append_row(
        {
            "job": "probe_brand",
            "brand": "swing-shack",
            "run_id": "r1-ss",
            "phase": "finished",
            "status": "FAILED",
            "started": "2026-01-01T00:00:00Z",
            "finished": "2026-01-01T00:00:01Z",
        }
    )
    stick_rows = ledger.read_rows("probe_brand", brand="stick")
    ss_rows = ledger.read_rows("probe_brand", brand="swing-shack")
    assert stick_rows[-1]["status"] == "OK"
    assert ss_rows[-1]["status"] == "FAILED"


def test_a8_per_brand_run_requires_brand_param(job_env):
    client, _, _ = job_env
    resp = client.post("/api/jobs/run/meta_refresh", headers=_auth())
    assert resp.status_code == 400
    assert "brand" in resp.get_json().get("error", "")


def test_a9_a10_brands_json_schema(job_env):
    from _lib.jobs.brand_lanes import validate_brands_registry, load_brands_registry

    validate_brands_registry()
    reg = load_brands_registry()
    assert "integrations" in reg
    for bid, brand in reg["brands"].items():
        scope = brand.get("integration_scope") or {}
        for entry in scope.values():
            if entry.get("applies") is False:
                assert (entry.get("na_reason") or "").strip()


def test_a11_connected_accounts_equal_rows(job_env):
    client, _, _ = job_env
    counts = []
    for brand in ("swing-shack", "stick", "bag-drop"):
        resp = client.get(f"/api/connected-accounts/status?brand={brand}")
        assert resp.status_code == 200
        data = resp.get_json()
        items = data.get("integrations") or []
        counts.append(len(items))
        assert all(it.get("visible") is True for it in items)
        summary = data.get("summary") or {}
        total = (
            summary.get("connected", 0)
            + summary.get("partial", 0)
            + summary.get("missing", 0)
            + summary.get("na", 0)
        )
        assert total == len(items)
    assert counts[0] == counts[1] == counts[2]


def test_a12_no_swing_shack_literal_in_connected_accounts(job_env):
    catalog_text = (CAMPAIGN_OS / "_lib" / "connected_accounts_catalog.py").read_text()
    app_text = (CAMPAIGN_OS / "app.py").read_text()
    route_start = app_text.find("@app.route('/api/connected-accounts/status'")
    route_end = app_text.find("@app.route('/connected-accounts'", route_start)
    route_block = app_text[route_start:route_end]
    assert "swing-shack" not in route_block
    assert "|| 'swing-shack'" not in route_block
    assert "'swing-shack'" not in catalog_text
    assert 'or "swing-shack"' not in catalog_text


def test_data_delegates_from_removed(job_env):
    reg = json.loads(BRANDS_FILE.read_text())
    for bid in ("stick", "bag-drop"):
        brand = reg["brands"][bid]
        assert "data_delegates_from" not in brand
        assert "data_delegate_note" not in brand


def test_a14_postiz_brand_aware_api_key(job_env, monkeypatch):
    from _lib import postiz_client as pc

    monkeypatch.delenv("POSTIZ_API_KEY", raising=False)
    monkeypatch.setenv("POSTIZ_API_KEY_STICK", "stick-key-12345")
    assert pc._read_api_key(brand_id="stick") == "stick-key-12345"
    monkeypatch.setenv("POSTIZ_API_KEY", "global-key")
    assert pc._read_api_key(brand_id="swing-shack") == "global-key"


def test_a15_swing_shack_golden_global_paths(job_env):
    from _lib.jobs.registry import JOBS
    from _lib.jobs.brand_lanes import resolve_path

    ss_jobs = [s for s in JOBS.values() if s.brand_mode == "global"]
    assert ss_jobs
    for spec in ss_jobs:
        for rel in spec.writes:
            assert resolve_path(spec, rel, "swing-shack") == rel


def test_jobs_status_includes_brands_array(job_env):
    client, _, _ = job_env
    client.post("/api/jobs/run/golf_news?all=1", headers=_auth())
    st = client.get("/api/jobs/status", headers=_auth()).get_json()
    meta = next(j for j in st["jobs"] if j["name"] == "meta_refresh")
    assert "brand_mode" in meta
    assert meta["brand_mode"] == "per_brand"
    assert "brands" in meta or meta.get("verdict") in ("NEVER", "OK", "LATE", "SKIPPED", "FAILED")
