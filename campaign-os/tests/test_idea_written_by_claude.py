"""Ideas are fleshed out by Claude, not by a model key on the server.

The card asks; Claude (a session on someone's computer) reads what is waiting, writes the idea out and
posts it back. The server cleans what comes back exactly as it did for a model's answer.
"""
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

from _lib import idea_builder as ib  # noqa: E402
from _lib import mail_intake as mi  # noqa: E402

TODAY = date(2026, 10, 27)
HERMAN = "herman@example.test"
ANSWER = {
    "concept": {"name": "Ladies Fitting Day", "one_line": "A relaxed fitting day for women.",
                "why_it_works": "Few brands speak to women.", "audience": "Women who play or want to start"},
    "offer": {"what": "A fitting day with a Black Friday offer to confirm", "to_confirm": ["Which products", "The offer"]},
    "content": [{"kind": "post", "title": "Invitation", "idea": "A real fitting", "caption_direction": "Warm and plain"}],
    "shots": ["A woman being fitted in the studio"],
    "next_steps": [{"step": "Confirm the offer with Herman", "who": "Christelle"}],
    "questions": ["Which products are on offer?"], "risks": ["Offer not confirmed in time"],
}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAIL_INTAKE_SENDERS", HERMAN)


def idea(brand="stick", mid="m1", text="What if we ran Black Friday deals aimed at ladies?"):
    it = mi.file_message({"message_id": mid, "from": f"Herman <{HERMAN}>", "subject": "Ideas", "text": text}, TODAY)
    return mi.set_brand_date(it["id"], brand, "2026-11-27") if brand else it


# ── asking ────────────────────────────────────────────────────────────

def test_asking_needs_a_brand_and_refuses_bag_drop():
    assert "brand" in ib.request_flesh(idea(brand=None, mid="a")["id"])["error"]
    assert "Bag Drop" in ib.request_flesh(idea(brand="bag-drop", mid="b")["id"])["error"]


def test_asking_marks_the_card_and_asking_twice_changes_nothing():
    it = idea()
    first = ib.request_flesh(it["id"])
    assert first["ok"] and first["item"]["flesh_requested_at"]
    again = ib.request_flesh(it["id"])
    assert again["item"]["flesh_requested_at"] == first["item"]["flesh_requested_at"]


# ── what is waiting ───────────────────────────────────────────────────

def test_pending_lists_asked_cards_with_the_prompt_to_write_from():
    a, b = idea(mid="a"), idea(mid="b", text="What if we ran a winter league night?")
    ib.request_flesh(a["id"])
    pending = ib.pending_requests(TODAY)
    assert [p["id"] for p in pending] == [a["id"]]
    p = pending[0]
    assert p["brand"] == "stick" and p["messages"][0]["role"] == "system"
    text = " ".join(m["content"] for m in p["messages"])
    assert "ladies" in text and "Paarl" in text and "Swing Shack" not in text
    assert b["id"] not in [x["id"] for x in pending]


def test_a_written_card_is_no_longer_pending():
    it = idea()
    ib.request_flesh(it["id"])
    ib.save_written(it["id"], ANSWER, TODAY)
    assert ib.pending_requests(TODAY) == []


# ── what comes back ───────────────────────────────────────────────────

def test_a_written_idea_is_stored_and_the_request_cleared():
    it = idea()
    ib.request_flesh(it["id"])
    r = ib.save_written(it["id"], json.dumps(ANSWER), TODAY)
    assert r["ok"] and r["item"]["fleshed"]["concept"]["name"] == "Ladies Fitting Day"
    assert r["item"]["fleshed"]["written_by"] == "Claude" and not r["item"].get("flesh_requested_at")


def test_the_same_clean_up_applies_to_what_claude_writes():
    it = idea()
    bad = json.loads(json.dumps(ANSWER))
    bad["offer"]["what"] = "20% off ladies' clubs"
    r = ib.save_written(it["id"], bad, TODAY)
    assert r["ok"] and "20%" not in r["item"]["fleshed"]["offer"]["what"]
    bad["content"][0]["idea"] = "Shot at Swing Shack in Johannesburg"
    r = ib.save_written(it["id"], bad, TODAY)
    assert not r["ok"] and "another brand" in r["error"]


def test_a_bad_answer_stores_nothing():
    it = idea()
    r = ib.save_written(it["id"], "not json", TODAY)
    assert not r["ok"] and "fleshed" not in mi.get_item(it["id"])


# ── routes ────────────────────────────────────────────────────────────

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


def test_card_asks_claude_writes_card_shows_it(loaded_app, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAIL_INTAKE_SENDERS", HERMAN)
    client = loaded_app.app.test_client()
    it = mi.file_message({"message_id": "r1", "from": f"Herman <{HERMAN}>", "subject": "Ideas",
                          "text": "What if we ran a ladies fitting day?"}, date.today())
    day = (date.today() + timedelta(days=40)).isoformat()
    r = client.post(f"/api/mail-intake/{it['id']}/ask", json={"brand": "stick", "date": day})
    assert r.status_code == 200 and r.get_json()["item"]["flesh_requested_at"]
    waiting = client.get("/api/jobs/mail-intake/pending").get_json()
    assert [p["id"] for p in waiting["pending"]] == [it["id"]]
    w = client.post(f"/api/jobs/mail-intake/{it['id']}/written", json=ANSWER)
    assert w.status_code == 200 and w.get_json()["item"]["fleshed"]["concept"]["name"] == "Ladies Fitting Day"
    shown = client.get("/api/mail-intake?brand=all").get_json()["ideas"][0]
    assert shown["fleshed"]["concept"]["name"] == "Ladies Fitting Day"
    assert client.get("/api/jobs/mail-intake/pending").get_json()["pending"] == []


def test_a_bad_written_answer_is_a_plain_400(loaded_app, monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAIL_INTAKE_SENDERS", HERMAN)
    client = loaded_app.app.test_client()
    it = mi.file_message({"message_id": "r2", "from": f"Herman <{HERMAN}>", "subject": "Ideas",
                          "text": "What if we ran a ladies fitting day?"}, date.today())
    mi.set_brand_date(it["id"], "stick", "2099-01-01")
    r = client.post(f"/api/jobs/mail-intake/{it['id']}/written", json={"concept": "just words"})
    assert r.status_code == 400 and r.get_json()["ok"] is False
