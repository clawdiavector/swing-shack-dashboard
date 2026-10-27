"""Foreman's two weekly messages: Monday 9am (what we sell this week) and Tuesday (report links)."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import plan_todo as pt  # noqa: E402

MONDAY = dt.date(2026, 10, 26)


def test_the_week_runs_monday_to_sunday():
    assert pt.week_bounds(dt.date(2026, 10, 28)) == (MONDAY, dt.date(2026, 11, 1))
    assert pt.week_bounds(MONDAY) == (MONDAY, dt.date(2026, 11, 1))


def test_the_monday_message_lists_each_facility_with_its_calendar():
    text = pt.weekly_selling_text({
        "stick": {"items": [{"date": "2026-10-28", "title": "Psycho Bunny arrivals"}]},
        "swing-shack": {"items": []},
    }, MONDAY)
    assert text.startswith("Good morning. What we are selling this week, Mon 26 Oct to Sun 1 Nov.")
    assert "— Stick —\n• Wed 28 Oct: Psycho Bunny arrivals" in text
    assert "— Swing Shack —\nNothing on the calendar yet." in text


def test_items_outside_the_week_are_left_out_and_the_rest_are_in_date_order():
    text = pt.weekly_selling_text({"stick": {"items": [
        {"date": "2026-11-02", "title": "Next week"},
        {"date": "2026-10-30", "title": "Friday one"},
        {"date": "2026-10-27", "title": "Tuesday one"},
    ]}}, MONDAY)
    assert "Next week" not in text
    assert text.index("Tuesday one") < text.index("Friday one")


def test_the_tuesday_message_carries_one_link_per_facility():
    text = pt.weekly_report_text({"stick": "https://x/s", "swing-shack": "https://x/ss"}, dt.date(2026, 10, 27))
    assert text.startswith("Good morning. The weekly report, Tue 27 Oct.")
    assert "Stick: https://x/s" in text and "Swing Shack: https://x/ss" in text


@pytest.fixture(scope="module")
def loaded_app(tmp_path_factory):
    base = tmp_path_factory.mktemp("cosdata")
    mp = pytest.MonkeyPatch()
    mp.setenv("DATA_DIR", str(base))
    mp.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    sys.modules.pop("app", None)
    import app as app_module

    app_module._GIT_SYNC_DONE = True
    yield app_module
    mp.undo()


def test_the_routes_need_the_job_token_and_the_report_link_needs_a_login(loaded_app, monkeypatch, tmp_path):
    from _lib import marketing_calendar as mc

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(mc, "_CALENDAR_DIR", tmp_path / "intelligence" / "marketing-calendar")
    monkeypatch.setattr(mc, "_CALENDAR_DIR_READY", False)
    monkeypatch.setattr(loaded_app, "COS_JOB_TOKEN", "test-job-token-not-a-secret")
    auth = {"Authorization": "Bearer test-job-token-not-a-secret"}
    anon = loaded_app.app.test_client(cos_anon=True)

    for path in ("/api/jobs/weekly-selling-message", "/api/jobs/weekly-report-message"):
        assert anon.get(path).status_code == 401
        assert anon.get(path + "?brand=nope", headers=auth).status_code == 400

    r = anon.get("/api/jobs/weekly-selling-message?brand=stick", headers=auth).get_json()
    assert r["ok"] and r["text"].startswith("Good morning. What we are selling this week,")

    r = anon.get("/api/jobs/weekly-report-message", headers=auth).get_json()
    assert r["ok"] and "Stick:" in r["text"] and "Swing Shack:" in r["text"]
    link = r["links"]["stick"]
    assert link.endswith("/weekly-report?brand=stick")
    # the page needs a login: anonymous goes to sign-in
    path = "/" + link.split("//", 1)[1].split("/", 1)[1]
    r2 = anon.get(path)
    assert r2.status_code == 302 and "login" in r2.headers["Location"]
