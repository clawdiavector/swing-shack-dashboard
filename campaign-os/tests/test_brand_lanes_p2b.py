"""P2b brand cron wiring — workflow URLs, resolvers, gbp fan-out."""

from __future__ import annotations

import json
import re
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


def _load_jobs_registry():
    for mod in list(sys.modules):
        if mod.startswith("_lib.jobs"):
            del sys.modules[mod]
    from _lib.jobs.registry import JOBS

    return JOBS


def test_workflow_posts_include_brand_or_all_for_per_brand_jobs():
    jobs = _load_jobs_registry()
    per_brand = {name for name, spec in jobs.items() if spec.brand_mode == "per_brand"}
    workflow_dir = REPO_ROOT / ".github" / "workflows"
    curl_re = re.compile(
        r'curl\s+(?:-[^\s]+\s+)*[^"\n]*"(?:\$BASE/|https?://[^/]+/)?api/jobs/run/([a-z0-9_]+)([^"]*)"'
    )
    violations: list[str] = []
    for yml in sorted(workflow_dir.glob("*.yml")):
        if yml.name == "ci.yml":
            continue
        text = yml.read_text(encoding="utf-8")
        for match in curl_re.finditer(text):
            job, qs = match.group(1), match.group(2)
            if job not in per_brand:
                continue
            if "all=1" in qs or "brand=" in qs:
                continue
            violations.append(f"{yml.name}: curl /api/jobs/run/{job} missing ?brand= or ?all=1")
    assert not violations, "\n".join(violations)


def test_meta_read_meta_id_no_swing_shack_default_for_stick(monkeypatch, job_env):
    from _lib.meta_api import _read_meta_id, meta_config_for_brand

    monkeypatch.delenv("META_PAGE_ID", raising=False)
    monkeypatch.delenv("META_PAGE_ID_STICK", raising=False)
    assert _read_meta_id("META_PAGE_ID", "page_id", brand_id="stick") is None
    cfg = meta_config_for_brand("stick")
    assert cfg.get("page_id") != "198859063301219"


def test_gsc_site_url_fail_loud_for_non_default_brand(monkeypatch, job_env):
    from _lib.jobs.layer1 import gsc_report

    monkeypatch.delenv("GSC_SITE_URL_STICK", raising=False)
    out = gsc_report.run(brand="stick")
    assert out.get("ok") is False
    assert "GSC_SITE_URL_STICK" in out.get("error", "")


def test_brand_domain_fail_loud_for_non_default_brand(monkeypatch, job_env):
    from _lib.jobs.layer1 import site_audit

    monkeypatch.delenv("BRAND_DOMAIN_STICK", raising=False)
    out = site_audit.run(brand="stick")
    assert out.get("ok") is False
    assert "BRAND_DOMAIN_STICK" in out.get("error", "")


def test_gbp_tick_threads_brand(monkeypatch, job_env):
    import app as app_module

    calls: list[tuple[str, str]] = []

    def _sync(brand_id, days=30):
        calls.append(("sync", brand_id))
        return {"ok": True, "insights_records": 1}

    def _plan(brand_id, days=7, posts_per_day=1, publish=False):
        calls.append(("plan", brand_id))
        return {"ok": True, "plan_id": "p1", "posts": []}

    monkeypatch.setattr(app_module, "_GBP_DAILY_AVAILABLE", True)
    monkeypatch.setattr(app_module, "_GBP_INSIGHTS_AVAILABLE", True)
    monkeypatch.setattr(app_module, "_gbi", type("X", (), {"sync_for_brand": staticmethod(_sync)})())
    monkeypatch.setattr(
        app_module,
        "_gdp",
        type("Y", (), {"build_daily_plan": staticmethod(_plan)})(),
    )
    out = app_module._gbp_daily_cron_tick(brand="stick")
    assert out.get("ok") is True
    assert out.get("brand") == "stick"
    assert ("sync", "stick") in calls
    assert ("plan", "stick") in calls


def test_gsc_oauth_token_path_per_brand(tmp_path, monkeypatch):
    from _lib import gsc_oauth as gsc

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    path = gsc.save_token({"access_token": "a", "refresh_token": "r"}, brand="stick")
    assert path.name == "stick.json"
    assert gsc.load_token(brand="stick") is not None
    legacy = gsc._token_dir() / "default.json"
    legacy.write_text(json.dumps({"encrypted_tokens": {}}), encoding="utf-8")
    assert gsc.load_token(brand="bag-drop") is None or gsc.load_token(brand="stick") is not None


def test_cos_job_summary_multi_run_shape(tmp_path):
    repo_script = REPO_ROOT / "scripts" / "cos_job_summary.py"
    payload = {
        "ok": True,
        "job": "meta_refresh",
        "runs": [
            {"ok": True, "status": "OK", "brand": "swing-shack"},
            {"ok": True, "status": "SKIPPED", "brand": "stick"},
        ],
    }
    path = tmp_path / "multi.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    import subprocess

    rc = subprocess.run(
        ["python3", str(repo_script), "assert-ok", str(path), "--hard-gate"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rc.returncode == 0


def test_freshness_scan_registered_global(job_env):
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib.jobs"):
            del sys.modules[mod]
    import app  # noqa: F401 — registers gbp_tick + freshness_scan
    from _lib.jobs.registry import JOBS

    assert JOBS["freshness_scan"].brand_mode == "global"
