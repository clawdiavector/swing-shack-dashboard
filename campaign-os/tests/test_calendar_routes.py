"""Routes for faded suggestions, undo, plans and alerts (Flask test client)."""
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

KEY = "note:capetowncycletour:2027-03-14"          # an important date in the repo's 2027 list
NAMED = {"X-Actor-Display-Name": "Christelle"}


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    # The operator's important-dates list, as a fixture of our own.
    (tmp_path / "important-dates").mkdir()
    (tmp_path / "important-dates" / "2027.json").write_text(json.dumps({"dates": [
        {"event_name": "Cape Town Cycle Tour", "start_date": "2027-03-14", "end_date": "2027-03-14",
         "event_type": "SA_SPORT", "notes": "B/C-tier Western Cape Sport.", "status": "VERIFIED"},
    ]}), encoding="utf-8")
    for mod in list(sys.modules):
        if mod == "app":
            del sys.modules[mod]
    import app as app_module

    app_module._GIT_SYNC_DONE = True
    return app_module.app.test_client(), app_module, tmp_path


def _ghosts(client, month="2027-03"):
    return client.get(f"/api/calendar-suggestions/stick?month={month}").get_json()["items"]


def _approve(client, key=KEY, pillars=("stick-retail",)):
    return client.post("/api/calendar-suggestions/stick/approve", headers=NAMED,
                       json={"month": "2027-03", "key": key, "pillars": list(pillars)})


def test_approve_then_undo_with_the_token_the_server_gave(env):
    client, _, _ = env
    assert any(i["key"] == KEY for i in _ghosts(client))
    r = _approve(client)
    assert r.status_code == 200 and r.get_json()["undo"]["token"]
    assert not any(i["key"] == KEY for i in _ghosts(client))
    undo = r.get_json()["undo"]
    assert client.post("/api/calendar-suggestions/stick/undo", json={"undo": undo}).status_code == 200
    assert any(i["key"] == KEY for i in _ghosts(client))
    # a token works once
    again = client.post("/api/calendar-suggestions/stick/undo", json={"undo": undo})
    assert again.status_code == 404


def test_undo_cannot_be_pointed_at_another_record(env):
    client, _, _ = env
    r = _approve(client)
    forged = dict(r.get_json()["undo"], calendar_id="cal-someone-elses", event_key="stick:other:2027-01-01")
    # the real token still reverses the real action, ignoring the forged ids
    ok = client.post("/api/calendar-suggestions/stick/undo", json={"undo": forged})
    assert ok.status_code == 200
    assert any(i["key"] == KEY for i in _ghosts(client))
    # no token, or a made-up one, does nothing
    for undo in ({}, {"kind": "approve", "key": KEY, "calendar_id": "cal-x"}, {"token": "und-nope"}):
        assert client.post("/api/calendar-suggestions/stick/undo", json={"undo": undo}).status_code == 404


def test_reject_and_undo_a_date(env):
    client, _, _ = env
    r = client.post("/api/calendar-suggestions/stick/reject", headers=NAMED, json={"month": "2027-03", "key": KEY})
    assert r.status_code == 200 and r.get_json()["undo"]["token"]
    assert not any(i["key"] == KEY for i in _ghosts(client))
    client.post("/api/calendar-suggestions/stick/undo", json={"undo": r.get_json()["undo"]})
    assert any(i["key"] == KEY for i in _ghosts(client))


def test_a_failed_approval_leaves_no_stray_suggestion(env, monkeypatch):
    client, app_module, _ = env

    def boom(*a, **k):
        raise RuntimeError("store down")

    monkeypatch.setattr(app_module, "planning_approve_candidate", boom)
    r = _approve(client)
    assert r.status_code == 500
    items = _ghosts(client)
    assert [i["key"] for i in items if i["key"] == KEY] == [KEY]          # the date is still offered
    assert not [i for i in items if i["source"] != "date" and "Cycle" in i["title"]]   # and no duplicate row


def test_a_scout_find_already_on_the_calendar_is_not_offered_again(env):
    client, app_module, _ = env
    from _lib import marketing_calendar as mc

    assert _approve(client).status_code == 200            # Cycle Tour goes on the calendar
    for title, by in (("Cape Town Cycle Tour 2027", "desk-foreman"), ("Cape Town Cycle Tour weekend push", "operator")):
        mc.add_candidate("stick", {"type": "moment", "title": title, "event_start": "2027-03-14",
                                   "event_end": "2027-03-14", "public_peak": "2027-03-14",
                                   "created_by": by, "source_type": "agent" if by != "operator" else "operator",
                                   "is_suggested": by == "operator"}, initial_status="candidate")
    titles = [i["title"] for i in _ghosts(client)]
    assert "Cape Town Cycle Tour 2027" not in titles          # an agent's repeat of what is on the calendar
    assert "Cape Town Cycle Tour weekend push" in titles      # but something the operator typed stays


def test_alerts_route_is_authed_and_shaped(env):
    client, _, _ = env
    r = client.get("/api/calendar-alerts?brand=stick")
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] and set(d) >= {"alerts", "count", "screaming"}
    assert client.get("/api/calendar-alerts?brand=nope").status_code == 400
    anon = app_client_anon(client)
    assert anon.get("/api/calendar-alerts?brand=stick").status_code == 401


def app_client_anon(client):
    import app as app_module

    return app_module.app.test_client(cos_anon=True)
