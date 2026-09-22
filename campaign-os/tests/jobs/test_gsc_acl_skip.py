"""GSC ACL denial on a configured property → SKIPPED, not FAILED."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

_403 = (
    'GSC HTTP 403: {"error":{"code":403,"message":"User does not have sufficient '
    "permission for site 'sc-domain:stickgolf.co.za'.\",\"status\":\"PERMISSION_DENIED\"}}"
)
_500 = 'GSC HTTP 500: {"error":{"code":500,"message":"Backend error"}}'
_404 = 'GSC HTTP 404: {"error":{"code":404,"message":"Site not found"}}'


@pytest.fixture()
def job_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    # Both gsc lanes must look *connected* so partition_brands keeps them
    # runnable — otherwise the pre-existing missing-credential skip fires
    # first and the test proves nothing.
    monkeypatch.setenv("GSC_SITE_URL_STICK", "sc-domain:stickgolf.co.za")
    monkeypatch.setenv("GSC_SITE_URL_SWING_SHACK", "https://swingshack.co.za/")
    monkeypatch.setenv("GSC_SITE_URL", "https://swingshack.co.za/")
    monkeypatch.setenv("GA4_CREDENTIALS_JSON_STICK", "x")
    monkeypatch.setenv("GA4_CREDENTIALS_JSON_SWING_SHACK", "x")
    for mod in list(sys.modules):
        if mod.startswith("_lib.jobs"):
            del sys.modules[mod]
    from _lib.jobs.brand_lanes import clear_brands_cache

    clear_brands_cache()
    yield tmp_path
    clear_brands_cache()


def _patch(monkeypatch, message):
    from _lib.jobs.layer1 import gsc_report, ga4_report

    # Neutralise the credential pre-flight — this test is about the API's 403,
    # not about missing env.
    monkeypatch.setattr(ga4_report, "_missing_env_error", lambda brand=None: None)
    monkeypatch.setattr(gsc_report, "_get_search_console_bearer", lambda **kw: "tok")

    def _boom(*a, **kw):
        raise RuntimeError(message)

    monkeypatch.setattr(gsc_report, "_search_analytics", _boom)
    return gsc_report


def test_stick_403_acl_returns_skip_sentinel(job_env, monkeypatch):
    gsc_report = _patch(monkeypatch, _403)
    r = gsc_report.run(brand="stick")
    assert r["ok"] is True and r["skipped"] is True
    assert "stickgolf" in r["reason"]
    assert r.get("error") is None


def test_swing_shack_403_still_fails(job_env, monkeypatch):
    gsc_report = _patch(monkeypatch, _403)
    r = gsc_report.run(brand="swing-shack")
    assert r["ok"] is False and r.get("skipped") is None


@pytest.mark.parametrize("msg", [_500, _404])
def test_other_http_errors_still_fail(job_env, monkeypatch, msg):
    gsc_report = _patch(monkeypatch, msg)
    r = gsc_report.run(brand="stick")
    assert r["ok"] is False and r.get("skipped") is None


def test_runner_records_skipped_and_job_verdict_ok(job_env, monkeypatch):
    import dataclasses

    from _lib.jobs import ledger, runner
    from _lib.jobs.registry import JOBS

    def fake(*, brand=None):
        if brand == "stick":
            return {
                "ok": True,
                "skipped": True,
                "reason": "GSC property sc-domain:stickgolf.co.za not shared",
                "detail": _403,
            }
        return {"ok": True, "rows": 12}

    # JobSpec is a frozen dataclass — monkeypatch.setattr(spec, "fn", …) raises
    # FrozenInstanceError. Swap the registry entry instead.
    monkeypatch.setitem(
        JOBS, "gsc_report", dataclasses.replace(JOBS["gsc_report"], fn=fake)
    )
    runner.run_job("gsc_report", triggered_by="test", brand="stick")
    runner.run_job("gsc_report", triggered_by="test", brand="swing-shack")

    stick = [
        r
        for r in ledger.read_rows("gsc_report", brand="stick")
        if r.get("phase") == "finished"
    ]
    assert len(stick) == 1, "exactly one exit row — no second ledger"
    row = stick[0]
    assert row["status"] == "SKIPPED"
    assert row["error_class"] is None and row["error_fingerprint"] is None
    assert row["result_summary"]["skipped"] is True

    grouped = ledger.last_rows_per_job_brand(["gsc_report"])
    all_rows = ledger.read_rows("gsc_report")
    assert runner.verdict_for("gsc_report", all_rows, brand="stick") == "SKIPPED"
    assert runner.verdict_for("gsc_report", all_rows, brand="swing-shack") == "OK"
    # Job rolls up to OK: SKIPPED children never dominate a live sibling.
    assert runner.verdict_for("gsc_report", all_rows, grouped=grouped) == "OK"

    diag = job_env / "diagnostics"
    bundles = list(diag.rglob("*")) if diag.exists() else []
    assert not [b for b in bundles if "stick" in str(b)], "no bundle for a skip"
