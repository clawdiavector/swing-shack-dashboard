"""One idea per card, and a proposed plan for each idea before anything goes on the calendar."""
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

from _lib import mail_intake as mi  # noqa: E402

TODAY = date(2026, 10, 26)
HERMAN = "herman@example.test"

TWO_IDEAS = """Two ideas for discussion/consideration:

Black Friday deals aimed specifically at ladies. Both SS and Stick.

"Emotional support" for spouses/GF/BF/maybe playing partners that must endure all the complaining during and after a round. This can be a free downloadable (we collect the email) and must be hilarious while true.  It is a way to attract the non golfers as much as the golfers.

Thanks,
Herman Kriel
CEO
FiveFriday (Pty) Ltd
Mobile: +27 82 000 0000
"""


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAIL_INTAKE_SENDERS", HERMAN)


def mail(text, subject="Ideas", mid="m1"):
    return {"message_id": mid, "from": f"Herman Kriel <{HERMAN}>", "subject": subject, "text": text,
            "timestamp": "2026-10-26T07:19:00Z"}


# ── splitting ─────────────────────────────────────────────────────────

def test_two_ideas_in_one_mail_become_two_cards_without_intro_or_signature():
    mi.run_intake(fetch=lambda: [mail(TWO_IDEAS)], notify=lambda *a: None,
                  add_suggestion=lambda b, i: "", today=TODAY)
    items = mi.list_items(kind="idea")
    assert len(items) == 2
    assert {i["idea_index"] for i in items} == {1, 2} and all(i["idea_total"] == 2 for i in items)
    text = " ".join(i["summary"] for i in items)
    assert "Two ideas for" not in text and "Mobile" not in text and "FiveFriday" not in text
    assert len({i["id"] for i in items}) == 2


def test_each_card_has_its_own_title():
    mi.run_intake(fetch=lambda: [mail(TWO_IDEAS)], notify=lambda *a: None,
                  add_suggestion=lambda b, i: "", today=TODAY)
    titles = sorted(i["title"] for i in mi.list_items(kind="idea"))
    assert titles[0].startswith("Black Friday deals aimed specifically at ladies")
    assert titles[1].startswith("Emotional support") and len(titles[1]) <= 84


def test_both_brands_named_means_ask_not_guess():
    mi.run_intake(fetch=lambda: [mail(TWO_IDEAS)], notify=lambda *a: None,
                  add_suggestion=lambda b, i: "", today=TODAY)
    first = next(i for i in mi.list_items(kind="idea") if i["idea_index"] == 1)
    assert first["brand"] is None and "brand" in first["needs"]


def test_numbered_lists_split_too():
    body = "Ideas:\n1. A ladies day at the shop with a free fitting\n2. A winter league night in the bays\n3. A gift card bundle for dads\n\nThanks"
    mi.run_intake(fetch=lambda: [mail(body)], notify=lambda *a: None, add_suggestion=lambda b, i: "", today=TODAY)
    assert len(mi.list_items(kind="idea")) == 3


def test_a_single_idea_stays_one_card_and_a_request_is_never_split():
    mi.run_intake(fetch=lambda: [mail("What if we ran a ladies day at the shop?", mid="a")],
                  notify=lambda *a: None, add_suggestion=lambda b, i: "", today=TODAY)
    assert len(mi.list_items(kind="idea")) == 1
    body = "Please do these today:\n\nChange the banner on the site.\n\nReply to the supplier about stock."
    mi.run_intake(fetch=lambda: [mail(body, subject="Banner", mid="b")], notify=lambda *a: None,
                  add_suggestion=lambda b, i: "", today=TODAY)
    assert len(mi.list_items(kind="do_now")) == 1


def test_a_second_run_does_not_file_the_split_mail_again():
    kw = dict(fetch=lambda: [mail(TWO_IDEAS)], notify=lambda *a: None, add_suggestion=lambda b, i: "", today=TODAY)
    mi.run_intake(**kw)
    out = mi.run_intake(**kw)
    assert out["filed"] == 0 and len(mi.list_items(kind="idea")) == 2


def test_a_mail_already_filed_as_one_card_is_split_in_place():
    it = mi.file_message(mail(TWO_IDEAS), TODAY)           # filed the old way: one card
    items = mi._read()[:1]
    for i in items:                                         # what the first release stored
        for k in ("title", "idea_index", "idea_total"):
            i.pop(k, None)
        i["summary"] = TWO_IDEAS[:600]
    mi._write(items)
    mi.resplit_existing(TODAY)
    assert len(mi.list_items(kind="idea")) == 2 and it


def test_a_card_with_a_plan_is_never_split_away():
    mi.file_message(mail(TWO_IDEAS), TODAY)
    items = mi._read()
    for i in items:
        i.pop("idea_total", None)
        i["plan_id"] = "pln-keepme"
    mi._write(items)
    mi.resplit_existing(TODAY)
    assert len(mi.list_items(kind="idea")) == len(items)


# ── SS means Swing Shack ──────────────────────────────────────────────

def test_ss_is_swing_shack():
    assert mi.detect_brand("deals at SS") == "swing-shack"
    assert mi.detect_brand("Both SS and Stick") is None


# ── a proposed plan from an idea ──────────────────────────────────────

_N = [0]


def _idea(brand=None, day=None):
    _N[0] += 1
    it = mi.file_message(mail("What if we ran a ladies day at the shop?", mid=f"p{_N[0]}"), TODAY)
    if brand or day:
        it = mi.set_brand_date(it["id"], brand, day)
    return it


def test_a_plan_needs_a_brand_and_a_future_date():
    it = _idea()
    assert "brand" in mi.idea_plan(it["id"], TODAY)["error"]
    it = _idea("stick", "2026-10-01")
    assert "passed" in mi.idea_plan(it["id"], TODAY)["error"]


def test_a_proposed_plan_is_stored_and_remembered_on_the_card(monkeypatch):
    it = _idea("stick", "2026-12-05")
    r = mi.idea_plan(it["id"], TODAY)
    assert r["ok"] and r["plan"]["status"] == "proposed" and r["plan"]["brand_id"] == "stick"
    kept = mi.get_item(it["id"])
    assert kept["plan_id"] == r["plan"]["plan_id"] and kept["brief_id"] == r["plan"]["brief_id"]
    assert any(i["kind"] == "shoot" and i["shots"] for i in r["plan"]["items"])
    assert r["plan"]["event_date"] == "2026-12-05"
    assert mi.idea_plan(it["id"], TODAY)["plan"]["plan_id"] == r["plan"]["plan_id"]     # not made twice


def test_nothing_is_on_the_calendar_until_the_plan_is_placed():
    it = _idea("stick", "2026-12-05")
    mi.idea_plan(it["id"], TODAY)
    assert mi.get_item(it["id"])["calendar_id"] in (None, "")
