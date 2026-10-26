"""The Flesh out route: the model call is replaced, so no network and no cost."""
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

HERMAN = "herman@example.test"
ANSWER = {
    "concept": {"name": "Ladies Fitting Day", "one_line": "A relaxed fitting day for women.", "why_it_works": "Few brands speak to women.",
                "audience": "Women who play"},
    "offer": {"what": "A fitting day with an offer to confirm", "to_confirm": ["The offer"]},
    "content": [{"kind": "post", "title": "Invitation", "idea": "A real fitting", "caption_direction": "Warm and plain"}],
    "shots": ["A woman being fitted"], "next_steps": [{"step": "Confirm the offer", "who": "Christelle"}],
    "questions": ["Which products?"], "risks": ["Offer late"],
}


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
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAIL_INTAKE_SENDERS", HERMAN)
    return loaded_app.app.test_client(), loaded_app, monkeypatch


def _idea():
    from _lib import mail_intake as mi
    return mi.file_message({"message_id": "f1", "from": f"Herman <{HERMAN}>", "subject": "Ideas",
                            "text": "What if we ran a ladies fitting day?"}, date.today())


def test_flesh_out_stores_the_concept_and_the_plan_then_uses_it(env):
    client, app, mp = env
    mp.setattr(app, "_openrouter_chat_completion", lambda messages, **kw: (json.dumps(ANSWER), None))
    it = _idea()
    day = (date.today() + timedelta(days=40)).isoformat()
    r = client.post(f"/api/mail-intake/{it['id']}/flesh", json={"brand": "stick", "date": day})
    j = r.get_json()
    assert r.status_code == 200 and j["item"]["fleshed"]["concept"]["name"] == "Ladies Fitting Day"
    plan = client.post(f"/api/mail-intake/{it['id']}/plan", json={}).get_json()["plan"]
    assert any("Ladies Fitting Day" in (i.get("note") or "") for i in plan["items"])


def test_a_model_error_is_reported_and_nothing_is_stored(env):
    client, app, mp = env
    mp.setattr(app, "_openrouter_chat_completion", lambda messages, **kw: (None, "OpenRouter 402: no credit"))
    it = _idea()
    r = client.post(f"/api/mail-intake/{it['id']}/flesh", json={"brand": "stick", "date": "2099-01-01"})
    assert r.status_code == 400 and "try again" in r.get_json()["error"].lower()
    from _lib import mail_intake as mi
    assert "fleshed" not in mi.get_item(it["id"])


def test_without_a_brand_it_asks(env):
    client, _, _ = env
    it = _idea()
    r = client.post(f"/api/mail-intake/{it['id']}/flesh", json={})
    assert r.status_code == 400 and "brand" in r.get_json()["error"]
