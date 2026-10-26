"""The Today-page routes for Herman's mail, and the approve guard on dates that have passed."""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

NAMED = {"X-Actor-Display-Name": "Christelle"}
HERMAN = "herman@example.test"


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


@pytest.fixture()
def env(loaded_app, monkeypatch, tmp_path):
    from _lib import marketing_calendar as mc

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAIL_INTAKE_SENDERS", HERMAN)
    monkeypatch.setattr(mc, "_CALENDAR_DIR", tmp_path / "intelligence" / "marketing-calendar")
    monkeypatch.setattr(mc, "_CALENDAR_DIR_READY", False)
    return loaded_app.app.test_client(), loaded_app, tmp_path


def _file(text, subject="Idea", mid="m1", today=None):
    from _lib import mail_intake as mi
    return mi.file_message({"message_id": mid, "from": HERMAN, "subject": subject, "text": text},
                           today or date.today())


def test_list_splits_do_now_from_ideas_and_says_if_nobody_is_watching(env, monkeypatch):
    client, _, _ = env
    monkeypatch.delenv("AGENTMAIL_API_KEY", raising=False)
    monkeypatch.delenv("AGENTMAIL_INBOX", raising=False)
    _file("What if we ran a ladies day", mid="a")
    _file("Please change the banner today, urgent", subject="Banner", mid="b")
    j = client.get("/api/mail-intake?brand=all").get_json()
    assert j["ok"] and len(j["ideas"]) == 1 and len(j["do_now"]) == 1
    assert j["watching"]["inbox"] is False


def test_done_and_flip(env):
    client, _, _ = env
    it = _file("Please fix the banner", subject="Banner")
    assert client.post(f"/api/mail-intake/{it['id']}/kind", json={"kind": "idea"}).get_json()["item"]["kind"] == "idea"
    assert client.post(f"/api/mail-intake/{it['id']}/status", json={"status": "done"}).get_json()["ok"]
    assert client.get("/api/mail-intake").get_json()["count"] == 0
    assert client.post(f"/api/mail-intake/{it['id']}/nope", json={}).status_code == 404


def test_idea_goes_on_the_calendar_as_a_faded_suggestion_not_approved(env):
    client, _, _ = env
    day = (date.today() + timedelta(days=30)).isoformat()
    it = _file("What if we ran a ladies day", mid="c")
    assert client.post(f"/api/mail-intake/{it['id']}/to-calendar", json={"brand": "stick"}).status_code == 400  # no date
    r = client.post(f"/api/mail-intake/{it['id']}/to-calendar", json={"brand": "stick", "date": day})
    assert r.status_code == 200 and r.get_json()["item"]["calendar_id"]
    ghosts = client.get(f"/api/calendar-suggestions/stick?month={day[:7]}").get_json()["items"]
    mine = [g for g in ghosts if g["source"] == "yours" and g["date"] == day]
    assert mine and "Ladies" in mine[0]["title"] or "ladies" in mine[0]["why"].lower()


def test_a_past_date_is_refused_for_an_idea(env):
    client, _, _ = env
    it = _file("What if we ran a ladies day", mid="d")
    past = (date.today() - timedelta(days=3)).isoformat()
    r = client.post(f"/api/mail-intake/{it['id']}/to-calendar", json={"brand": "stick", "date": past})
    assert r.status_code == 400 and "passed" in r.get_json()["error"]


def test_approving_a_suggestion_whose_date_has_passed_is_refused(env):
    client, _, _ = env
    from _lib import marketing_calendar as mc
    past = (date.today() - timedelta(days=5)).isoformat()
    rec = mc.add_candidate("stick", {
        "type": "campaign", "title": "Old idea", "event_start": past, "event_end": past, "public_peak": past,
        "source_type": "operator", "source": "OPERATOR_PROVIDED", "created_by": "operator", "is_suggested": True,
    }, initial_status="candidate")
    r = client.post("/api/calendar-suggestions/stick/approve", headers=NAMED,
                    json={"month": past[:7], "key": f"row:{rec['calendar_id']}", "pillars": []})
    assert r.status_code == 400 and "passed" in r.get_json()["error"]
