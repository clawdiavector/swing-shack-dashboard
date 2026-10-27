"""Foreman morning summary — posts today, approval queue, failing jobs (2026-10-26)."""
from __future__ import annotations

import datetime as dt
import os
import sys

import pytest

CAMPAIGN_OS = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, CAMPAIGN_OS)

from _lib import foreman_morning_summary as fms  # noqa: E402
from _lib.jobs.layer2 import foreman_morning_summary as job  # noqa: E402

TODAY = dt.date(2026, 10, 26)
BASE = "https://example.test"


def _section(**overrides):
    base = {
        "brand_id": "stick",
        "scheduled_today": ["Wed fitting reel", "Vice irons drop"],
        "pending": ["Black Friday plan"],
        "approve_url": f"{BASE}/?page=review&brand=stick",
    }
    base.update(overrides)
    return base


def test_summary_text_lists_schedule_approval_and_failures():
    failures = [{"job": "site_audit", "verdict": "FAILED"}]
    text = fms.summary_text({"stick": _section()}, TODAY, failures)
    assert text.startswith("Morning summary, Mon 26 Oct.")
    assert "Failing jobs: site_audit (FAILED)" in text
    assert "Scheduled today (2):" in text
    assert "• Wed fitting reel" in text
    assert "Awaiting approval (1):" in text
    assert "• Black Friday plan" in text
    assert f"Approve drafts: {BASE}/?page=review&brand=stick" in text


def test_job_skips_telegram_when_flag_off(monkeypatch):
    monkeypatch.delenv("FOREMAN_MORNING_SUMMARY_TELEGRAM", raising=False)
    monkeypatch.setattr(fms, "build_payload", lambda **_: {"text": "x", "date": TODAY.isoformat(),
                                                           "scheduled_today": 0, "pending_approval": 0,
                                                           "failing_jobs": 0})
    out = job.run()
    assert out["ok"] and out["telegram"]["skipped"]


def test_job_sends_when_flag_on(monkeypatch):
    monkeypatch.setenv("FOREMAN_MORNING_SUMMARY_TELEGRAM", "on")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    monkeypatch.setattr(fms, "build_payload", lambda **_: {"text": "hello", "date": TODAY.isoformat(),
                                                           "scheduled_today": 0, "pending_approval": 0,
                                                           "failing_jobs": 0})
    monkeypatch.setattr(job.tg, "send_message", lambda text: {"ok": True, "message_id": 99})
    out = job.run()
    assert out["ok"] and out["telegram"]["message_id"] == 99


@pytest.fixture(scope="module")
def summary_app(tmp_path_factory):
    base = tmp_path_factory.mktemp("morning-summary-route")
    (base / "important-dates").mkdir(parents=True)
    (base / "important-dates" / "2027.json").write_text('{"dates": []}', encoding="utf-8")
    mp = pytest.MonkeyPatch()
    mp.setenv("DATA_DIR", str(base))
    mp.setenv("BUNDLED_DATA_DIR", str(os.path.join(CAMPAIGN_OS, "..", "data")))
    mp.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    sys.modules.pop("app", None)
    import app as app_module

    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    app_module._GIT_SYNC_DONE = True
    yield app_module
    mp.undo()
    # Importing app above cached the temp calendar dir; later tests must not inherit it.
    import _lib

    sys.modules.pop("app", None)
    for name in ("intelligence", "marketing_calendar"):
        sys.modules.pop(f"_lib.{name}", None)
        if hasattr(_lib, name):
            delattr(_lib, name)


def test_morning_summary_route_requires_job_bearer(summary_app):
    anon = summary_app.app.test_client(cos_anon=True)
    assert anon.get("/api/jobs/morning-summary?brand=stick").status_code == 401
    r = anon.get(
        "/api/jobs/morning-summary?brand=stick",
        headers={"Authorization": "Bearer test-job-token-not-a-secret"},
    )
    d = r.get_json()
    assert r.status_code == 200 and d["ok"]
    assert d["text"].startswith("Morning summary,")
    assert "scheduled_today" in d and "pending_approval" in d and "failing_jobs" in d
    assert summary_app.app.test_client().get("/api/jobs/morning-summary?brand=nope").status_code == 400
