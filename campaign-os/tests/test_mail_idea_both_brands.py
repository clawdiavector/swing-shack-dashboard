"""One idea for both brands: the card becomes two, one Stick and one Swing Shack.

The brands are separate companies, so each card is fleshed out and planned on its own.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import mail_intake as mi  # noqa: E402

HERMAN = "herman@example.test"
TODAY = date(2026, 10, 29)


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAIL_INTAKE_SENDERS", HERMAN)


def _idea(mid="b1", text="What if we made a survival guide for golfers' partners?"):
    return mi.file_message({"message_id": mid, "from": f"Herman <{HERMAN}>", "subject": "Ideas", "text": text}, TODAY)


def test_both_brands_makes_one_card_per_brand_with_the_same_idea():
    it = _idea()
    mi.set_brand_date(it["id"], None, "2026-11-20")
    cards = mi.split_for_both_brands(it["id"])
    assert sorted(c["brand"] for c in cards) == ["stick", "swing-shack"]
    assert len({c["id"] for c in cards}) == 2 and it["id"] in {c["id"] for c in cards}
    for c in cards:
        assert c["summary"] == it["summary"] and c["date"] == "2026-11-20"
        assert c["kind"] == "idea" and c["status"] == "open" and c["needs"] == []
    assert len(mi.list_items(kind="idea")) == 2


def test_the_copy_starts_clean_and_the_original_keeps_its_work():
    it = _idea("b2")
    mi.set_brand_date(it["id"], "stick", None)
    mi._update(it["id"], fleshed={"concept": {"name": "Stick version"}}, plan_id="pl-1", brief_id="brf-x")
    cards = {c["brand"]: c for c in mi.split_for_both_brands(it["id"])}
    assert cards["stick"]["id"] == it["id"] and cards["stick"]["fleshed"]["concept"]["name"] == "Stick version"
    copy = cards["swing-shack"]
    assert not copy.get("fleshed") and not copy.get("plan_id") and not copy.get("brief_id")
    assert not copy.get("calendar_id") and copy["needs"] == ["date"]


def test_each_brand_list_shows_only_its_own_card():
    it = _idea("b3")
    mi.split_for_both_brands(it["id"])
    assert [c["brand"] for c in mi.list_items("stick", kind="idea")] == ["stick"]
    assert [c["brand"] for c in mi.list_items("swing-shack", kind="idea")] == ["swing-shack"]


def test_splitting_twice_does_not_make_a_third_card():
    it = _idea("b4")
    mi.split_for_both_brands(it["id"])
    mi.split_for_both_brands(it["id"])
    assert len(mi.list_items(kind="idea")) == 2


def test_the_copy_survives_the_resplit_on_read():
    it = _idea("b5", "Ideas:\n1. A survival guide for partners.\n2. A ladies day at the shop.")
    first = mi.list_items(kind="idea")[-1]
    mi.split_for_both_brands(first["id"])
    before = len(mi.list_items(kind="idea"))
    mi.resplit_existing(TODAY)
    assert len(mi.list_items(kind="idea")) == before
    assert it


def test_unknown_or_non_idea_cards_are_refused():
    assert mi.split_for_both_brands("mi-nope") is None
    todo = mi.file_message({"message_id": "b6", "from": f"Herman <{HERMAN}>", "subject": "Urgent",
                            "text": "Please fix the price on the website today."}, TODAY)
    if todo["kind"] != "idea":
        with pytest.raises(ValueError):
            mi.split_for_both_brands(todo["id"])


# ── the route ─────────────────────────────────────────────────────────

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


def test_the_both_route_returns_the_two_cards(loaded_app):
    client = loaded_app.app.test_client()
    it = _idea("b7")
    r = client.post(f"/api/mail-intake/{it['id']}/both", json={"date": "2026-11-20"})
    j = r.get_json()
    assert r.status_code == 200 and j["ok"]
    assert sorted(c["brand"] for c in j["items"]) == ["stick", "swing-shack"]
    assert all(c["date"] == "2026-11-20" for c in j["items"])
