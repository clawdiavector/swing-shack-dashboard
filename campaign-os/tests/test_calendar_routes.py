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


@pytest.fixture(scope="module")
def loaded_app(tmp_path_factory):
    """The app, imported once (it takes seconds), with an important-dates list of our own."""
    base = tmp_path_factory.mktemp("cosdata")
    (base / "important-dates").mkdir()
    (base / "important-dates" / "2027.json").write_text(json.dumps({"dates": [
        {"event_name": "Cape Town Cycle Tour", "start_date": "2027-03-14", "end_date": "2027-03-14",
         "event_type": "SA_SPORT", "notes": "B/C-tier Western Cape Sport.", "status": "VERIFIED"},
    ]}), encoding="utf-8")
    mp = pytest.MonkeyPatch()
    mp.setenv("DATA_DIR", str(base))
    mp.setenv("BUNDLED_DATA_DIR", str(REPO_ROOT / "data"))
    sys.modules.pop("app", None)
    import app as app_module

    app_module._GIT_SYNC_DONE = True
    yield app_module
    mp.undo()


@pytest.fixture()
def env(loaded_app, monkeypatch, tmp_path):
    """A clean data folder for each test: briefs, the calendar, plans, decisions and undo codes."""
    from _lib import campaign_brief as cb
    from _lib import marketing_calendar as mc

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cb, "DATA_DIR_DEFAULT", str(tmp_path))
    monkeypatch.setattr(mc, "_CALENDAR_DIR", tmp_path / "intelligence" / "marketing-calendar")
    monkeypatch.setattr(mc, "_CALENDAR_DIR_READY", False)
    return loaded_app.app.test_client(), loaded_app, tmp_path


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


def _write_brief(tmp_path, bid, event_key, status="approved"):
    d = tmp_path / "briefs" / "stick"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{bid}.json").write_text(json.dumps({
        "brief_id": bid, "brand_id": "stick", "status": status, "revision": 1,
        "source_opportunity": {"event_key": event_key}}), encoding="utf-8")


def test_the_brief_index_is_read_once_and_rebuilt_only_when_a_brief_changes(env, monkeypatch):
    _, app_module, tmp_path = env
    from _lib import campaign_brief as cb

    _write_brief(tmp_path, "brf-aaaa0001", "ev-one")
    _write_brief(tmp_path, "brf-aaaa0002", "ev-two")
    reads = []
    real = cb._read_brief
    monkeypatch.setattr(cb, "_read_brief", lambda b, i: (reads.append(i), real(b, i))[1])

    first = app_module._brief_ids_by_event("stick")
    assert first == {"ev-one": "brf-aaaa0001", "ev-two": "brf-aaaa0002"}
    after_first = len(reads)
    assert after_first >= 2
    for _ in range(5):
        assert app_module._brief_ids_by_event("stick") == first
    assert len(reads) == after_first                      # five more calls, no brief opened

    first["ev-one"] = "tampered"                          # a caller changing its copy cannot poison the cache
    assert app_module._brief_ids_by_event("stick")["ev-one"] == "brf-aaaa0001"

    _write_brief(tmp_path, "brf-aaaa0001", "ev-one", status="superseded")   # a brief changes on disk
    assert app_module._brief_ids_by_event("stick") == {"ev-two": "brf-aaaa0002"}
    _write_brief(tmp_path, "brf-aaaa0003", "ev-three")                      # a brief is added
    assert app_module._brief_ids_by_event("stick") == {"ev-two": "brf-aaaa0002", "ev-three": "brf-aaaa0003"}


def test_a_failed_read_is_not_kept(env, monkeypatch):
    _, app_module, tmp_path = env
    from _lib import campaign_brief as cb

    _write_brief(tmp_path, "brf-bbbb0001", "ev-one")
    real = cb._read_brief
    monkeypatch.setattr(cb, "_read_brief", lambda b, i: None)      # unreadable right now
    assert app_module._brief_ids_by_event("stick") == {}
    monkeypatch.setattr(cb, "_read_brief", real)
    assert app_module._brief_ids_by_event("stick") == {"ev-one": "brf-bbbb0001"}   # recovered, not stuck


def _operator_row(title="Winter fitting weekend", day="2027-03-10", pillars=None):
    from _lib import marketing_calendar as mc

    rec = {"type": "campaign", "title": title, "event_start": day, "event_end": day, "public_peak": day,
           "created_by": "operator", "is_suggested": True, "summary": "A fitting weekend idea"}
    if pillars:
        rec["pillars"] = pillars
    return mc.add_candidate("stick", rec, initial_status="candidate")["calendar_id"]


def test_a_suggestion_with_no_pillar_is_given_one_when_approved(env):
    client, _, _ = env
    from _lib import marketing_calendar as mc

    cid = _operator_row()
    ghost = [i for i in _ghosts(client) if i["calendar_id"] == cid][0]
    assert ghost["pillars"] == []                               # the card will ask for one
    r = _approve(client, ghost["key"], pillars=("stick-fitting",))
    assert r.status_code == 200
    approved = [x for x in mc.latest_revisions(mc.list_records("stick"))
                if x.get("status") == "approved" and x.get("title") == "Winter fitting weekend"]
    assert approved and all(x.get("pillars") == ["stick-fitting"] for x in approved)


def test_a_suggestion_that_already_has_a_pillar_keeps_it(env):
    client, _, _ = env
    from _lib import marketing_calendar as mc

    cid = _operator_row("Coaching push", pillars=["stick-coaching"])
    ghost = [i for i in _ghosts(client) if i["calendar_id"] == cid][0]
    assert ghost["pillars"] == ["stick-coaching"]
    _approve(client, ghost["key"], pillars=("stick-retail",))   # a stray choice does not overwrite it
    approved = [x for x in mc.latest_revisions(mc.list_records("stick"))
                if x.get("status") == "approved" and x.get("title") == "Coaching push"]
    assert approved and all(x.get("pillars") == ["stick-coaching"] for x in approved)


def test_set_pillars_needs_a_pillar_and_a_real_record(env):
    from _lib import marketing_calendar as mc

    cid = _operator_row()
    with pytest.raises(ValueError):
        mc.set_pillars("stick", cid, [])
    assert mc.set_pillars("stick", "cal-missing", ["stick-retail"]) is None


def _plan_for_soon(client, tmp_path, days_out=12):
    """A draft plan for an event a little way off, so some steps are due soon or overdue."""
    import datetime as dt

    day = (dt.date.today() + dt.timedelta(days=days_out)).isoformat()
    d = tmp_path / "briefs" / "stick"
    d.mkdir(parents=True, exist_ok=True)
    (d / "brf-todo0001.json").write_text(json.dumps({
        "brief_id": "brf-todo0001", "brand_id": "stick", "status": "approved", "revision": 1,
        "source_opportunity": {"event_key": "ev-todo", "name": "Heritage Day", "date": day}}), encoding="utf-8")
    r = client.post("/api/plan/v1/stick/propose", json={"brief_id": "brf-todo0001"})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["plan"]


def test_the_todo_lists_steps_from_the_plans_and_a_done_step_leaves_it(env):
    client, _, tmp_path = env
    plan = _plan_for_soon(client, tmp_path)
    r = client.get("/api/plan-todo?brand=stick")
    d = r.get_json()
    assert r.status_code == 200 and d["ok"] and d["count"] > 0
    assert set(d["counts"]) == {"overdue", "today", "this_week", "later"}
    order = ["overdue", "today", "this_week", "later"]
    assert [s["bucket"] for s in d["steps"]] == sorted((s["bucket"] for s in d["steps"]), key=order.index)
    first = d["steps"][0]
    assert first["plan_id"] == plan["plan_id"] and first["event_name"] == "Heritage Day"
    done = client.patch(f"/api/plan/v1/stick/{first['plan_id']}/item/{first['item_id']}", json={"status": "done"})
    assert done.status_code == 200
    again = client.get("/api/plan-todo?brand=all").get_json()
    assert first["key"] not in [s["key"] for s in again["steps"]] and again["count"] == d["count"] - 1


def test_the_todo_route_checks_the_brand_and_the_login(env):
    client, app_module, _ = env
    assert client.get("/api/plan-todo?brand=nope").status_code == 400
    assert app_module.app.test_client(cos_anon=True).get("/api/plan-todo?brand=stick").status_code == 401


def test_the_morning_message_is_plain_text_readable_with_the_job_token(env, monkeypatch):
    client, app_module, tmp_path = env
    _plan_for_soon(client, tmp_path)
    monkeypatch.setattr(app_module, "COS_JOB_TOKEN", "test-job-token-not-a-secret")
    anon = app_module.app.test_client(cos_anon=True)
    assert anon.get("/api/jobs/morning-message?brand=stick").status_code == 401
    r = anon.get("/api/jobs/morning-message?brand=stick", headers={"Authorization": "Bearer test-job-token-not-a-secret"})
    d = r.get_json()
    assert r.status_code == 200 and d["ok"]
    assert d["text"].startswith("Good morning. Calendar check,")
    assert isinstance(d["overdue"], int) and isinstance(d["due_today"], int) and isinstance(d["screaming"], int)
    assert client.get("/api/jobs/morning-message?brand=nope").status_code == 400


def _brief_for(tmp_path, brief_id, event_key, day="2027-03-14"):
    d = tmp_path / "briefs" / "stick"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{brief_id}.json").write_text(json.dumps({
        "brief_id": brief_id, "brand_id": "stick", "status": "approved", "revision": 1,
        "source_opportunity": {"event_key": event_key, "name": "Cape Town Cycle Tour", "date": day}}), encoding="utf-8")


def test_undoing_an_approval_retires_the_draft_plan_made_with_it(env):
    client, _, tmp_path = env
    undo = _approve(client).get_json()["undo"]
    _brief_for(tmp_path, "brf-undo0001", undo["event_key"])
    plan = client.post("/api/plan/v1/stick/propose", json={"brief_id": "brf-undo0001"}).get_json()["plan"]
    r = client.post("/api/calendar-suggestions/stick/undo", json={"undo": dict(undo, plan_id=plan["plan_id"])})
    assert r.status_code == 200 and r.get_json()["plan_retired"] is True
    assert client.get(f"/api/plan/v1/stick/{plan['plan_id']}").get_json()["plan"]["status"] == "superseded"
    assert not [p for p in client.get("/api/plan-todo?brand=stick").get_json()["steps"] if p["plan_id"] == plan["plan_id"]]


def test_undo_will_not_retire_a_plan_for_another_date_or_one_that_was_acted_on(env):
    client, _, tmp_path = env
    undo = _approve(client).get_json()["undo"]
    _brief_for(tmp_path, "brf-other001", "stick:some-other-event:2027-03-14")
    other = client.post("/api/plan/v1/stick/propose", json={"brief_id": "brf-other001"}).get_json()["plan"]
    r = client.post("/api/calendar-suggestions/stick/undo", json={"undo": dict(undo, plan_id=other["plan_id"])})
    assert r.status_code == 200 and r.get_json()["plan_retired"] is False
    assert client.get(f"/api/plan/v1/stick/{other['plan_id']}").get_json()["plan"]["status"] == "proposed"
    # a plan that has been approved is not a throwaway draft
    undo2 = _approve(client).get_json()["undo"]
    _brief_for(tmp_path, "brf-acted001", undo2["event_key"])
    mine = client.post("/api/plan/v1/stick/propose", json={"brief_id": "brf-acted001"}).get_json()["plan"]
    assert client.post(f"/api/plan/v1/stick/{mine['plan_id']}/approve", json={}).status_code == 200
    r2 = client.post("/api/calendar-suggestions/stick/undo", json={"undo": dict(undo2, plan_id=mine["plan_id"])})
    assert r2.get_json()["plan_retired"] is False
    assert client.get(f"/api/plan/v1/stick/{mine['plan_id']}").get_json()["plan"]["status"] == "approved"


def test_triage_sorts_dates_and_not_now_and_undo_work(env):
    client, _, _ = env
    d = client.get("/api/calendar-suggestions/stick/triage").get_json()
    assert d["ok"] and d["count"] >= 1 and all(i["source"] == "date" for i in d["items"])
    first = d["items"][0]
    month = first["date"][:7]
    r = client.post("/api/calendar-suggestions/stick/later", headers=NAMED, json={"month": month, "key": first["key"]})
    assert r.status_code == 200 and r.get_json()["undo"]["kind"] == "later"
    after = client.get("/api/calendar-suggestions/stick/triage").get_json()["items"]
    assert first["key"] not in [i["key"] for i in after]                                    # out of the queue
    assert any(i["key"] == first["key"] for i in client.get(f"/api/calendar-suggestions/stick?month={month}").get_json()["items"])
    undone = client.post("/api/calendar-suggestions/stick/undo", json={"undo": r.get_json()["undo"]})
    assert undone.status_code == 200
    assert first["key"] in [i["key"] for i in client.get("/api/calendar-suggestions/stick/triage").get_json()["items"]]


def test_triage_checks_the_login_and_the_brand(env):
    client, app_module, _ = env
    assert client.get("/api/calendar-suggestions/nope/triage").status_code == 400
    assert app_module.app.test_client(cos_anon=True).get("/api/calendar-suggestions/stick/triage").status_code == 401
    assert client.post("/api/calendar-suggestions/stick/later", json={"month": "2027-03", "key": "note:x:2027-03-01"}).status_code == 404
