"""The idea card's "Show proposed plan" route, and the split of an old one-card mail on read."""
from __future__ import annotations

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
    return loaded_app.app.test_client()


def _file(text, mid):
    from _lib import mail_intake as mi
    return mi.file_message({"message_id": mid, "from": f"Herman <{HERMAN}>", "subject": "Ideas", "text": text},
                           date.today())


def test_show_proposed_plan_makes_a_draft_plan_and_puts_nothing_on_the_calendar(env):
    it = _file("What if we ran a ladies day at the shop?", "r1")
    day = (date.today() + timedelta(days=45)).isoformat()
    r = env.post(f"/api/mail-intake/{it['id']}/plan", json={"brand": "stick", "date": day})
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] and j["plan"]["status"] == "proposed"
    assert j["item"]["plan_id"] == j["plan"]["plan_id"]
    plans = env.get("/api/plan/v1/stick/list").get_json()["plans"]
    assert [p["brief_id"] for p in plans] == [j["item"]["brief_id"]]
    assert not plans[0].get("placed_at")


def test_a_plan_without_a_brand_is_refused_in_plain_words(env):
    it = _file("What if we ran a ladies day at the shop?", "r2")
    r = env.post(f"/api/mail-intake/{it['id']}/plan", json={})
    assert r.status_code == 400 and "brand" in r.get_json()["error"]


def test_reading_the_list_splits_a_mail_that_was_filed_as_one_card(env):
    from _lib import mail_intake as mi
    it = _file("What if we ran a ladies day at the shop?", "r3")
    items = mi._read()
    items[0]["summary"] = ("Two ideas:\n\nA ladies day at the shop with a free fitting for every guest.\n\n"
                           "A winter league night in the bays with prizes from the shop.")
    for k in ("title", "idea_index", "idea_total"):
        items[0].pop(k, None)
    mi._write(items)
    j = env.get("/api/mail-intake?brand=all").get_json()
    assert len(j["ideas"]) == 2 and it
