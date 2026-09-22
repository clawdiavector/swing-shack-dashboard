"""P1b brand UI — connected accounts, ops jobs, SPA fetch audit."""

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

CONNECTED_HTML = (CAMPAIGN_OS / "connected-accounts.html").read_text(encoding="utf-8")
OPS_HTML = (CAMPAIGN_OS / "ops-jobs.html").read_text(encoding="utf-8")
SPA_HTML = (CAMPAIGN_OS / "campaign-os.html").read_text(encoding="utf-8")
BRANDS_FILE = REPO_ROOT / "data" / "brands.json"

CATALOG_IDS = {
    "postiz",
    "meta",
    "gbp",
    "ga4",
    "gsc",
    "youtube",
    "ubersuggest",
    "google_drive",
    "krea",
}


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


def test_p1b_connected_accounts_html_uses_integrations_not_categories():
    assert 'id="brand-select"' in CONNECTED_HTML
    assert "Object.entries(brandsObj)" in CONNECTED_HTML
    assert "d.integrations" in CONNECTED_HTML
    assert "d.categories" not in CONNECTED_HTML.replace("categories[]", "")
    assert "campaign_os_active_brand" in CONNECTED_HTML
    assert "pill-na" in CONNECTED_HTML
    assert "CORE_SIX" in CONNECTED_HTML


def test_p1b_ops_jobs_html_brand_filter_and_applies_column():
    assert 'id="brand-select"' in OPS_HTML
    assert "Object.entries(brandsObj)" in OPS_HTML
    assert "Applies to" in OPS_HTML
    assert "renderAppliesChips" in OPS_HTML
    assert "jobRunQuery" in OPS_HTML
    assert "?reason=manual' + jobRunQuery" in OPS_HTML or "jobRunQuery(jobMeta)" in OPS_HTML
    assert "status === 409" in OPS_HTML


def test_p1b_spa_no_brand_id_reads_and_fetch_literals():
    assert "S.brand_id" not in SPA_HTML
    assert "switchBrand" in SPA_HTML
    assert "localStorage.setItem('campaign_os_active_brand'" in SPA_HTML
    assert "loadStrategyCard()" in SPA_HTML.split("async function switchBrand")[1].split("function toggleBrandDropdown")[0]
    assert "loadWorkspace()" in SPA_HTML.split("async function switchBrand")[1].split("function toggleBrandDropdown")[0]
    assert "function activeBrandId()" in SPA_HTML
    assert re.search(r"API\.get\('/api/gbp/daily-poster/latest\?brand_id=swing-shack", SPA_HTML) is None
    assert re.search(r"API\.get\('/api/brand-settings/swing-shack", SPA_HTML) is None
    assert re.search(r"brand_id:\s*'swing-shack'", SPA_HTML) is None


def test_p1b_stick_integrations_all_ten_visible(job_env):
    client, _, _ = job_env
    resp = client.get("/api/connected-accounts/status?brand=stick")
    assert resp.status_code == 200
    data = resp.get_json()
    items = data.get("integrations") or []
    ids = {it["id"] for it in items}
    assert ids == CATALOG_IDS
    assert len(items) == 9
    assert "windsor" not in ids
    by_id = {it["id"]: it for it in items}
    for iid in ("postiz", "meta", "gbp", "google_drive"):
        assert by_id[iid]["state"] == "missing"
        assert by_id[iid]["applies"] is True
    for iid in ("ga4", "gsc", "ubersuggest"):
        assert by_id[iid]["state"] == "missing"
        assert by_id[iid]["applies"] is True
    for iid in ("youtube", "krea"):
        assert by_id[iid]["state"] == "na"
        assert by_id[iid]["applies"] is False
        assert (by_id[iid].get("na_reason") or "").strip()


def test_p1b_stick_summary_counts_match(job_env):
    client, _, _ = job_env
    data = client.get("/api/connected-accounts/status?brand=stick").get_json()
    summary = data.get("summary") or {}
    items = data.get("integrations") or []
    assert summary.get("connected", 0) + summary.get("partial", 0) + summary.get("missing", 0) + summary.get("na", 0) == len(items)
    assert summary.get("missing") == 7
    assert summary.get("na") == 2


def test_p1b_jobs_status_brands_carry_applies(job_env):
    client, _, _ = job_env
    st = client.get("/api/jobs/status", headers=_auth()).get_json()
    meta = next(j for j in st["jobs"] if j["name"] == "meta_refresh")
    assert meta["brand_mode"] == "per_brand"
    brands = meta.get("brands") or []
    assert brands
    for entry in brands:
        assert "applies" in entry
        if entry.get("applies") is False:
            assert entry.get("skipped_reason")


def test_p1b_per_brand_run_requires_brand_query(job_env):
    client, _, _ = job_env
    bad = client.post("/api/jobs/run/meta_refresh?reason=manual", headers=_auth())
    assert bad.status_code == 400
    ok = client.post("/api/jobs/run/meta_refresh?reason=manual&brand=swing-shack", headers=_auth())
    assert ok.status_code == 200


def test_p1b_connected_accounts_renderer_emits_row_per_id():
    assert "groupIntegrations" in CONNECTED_HTML
    assert "renderAccordion" in CONNECTED_HTML
    assert "integrations.filter" not in CONNECTED_HTML
