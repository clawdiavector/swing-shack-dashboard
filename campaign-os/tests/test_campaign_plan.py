"""Plan from a date: dated checklist, editing, approval rules."""
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _lib import campaign_plan as cp  # noqa: E402

TODAY = date(2026, 10, 13)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def brief(status="approved", d="2026-12-05", bid="brf-test0001"):
    return {"brief_id": bid, "status": status,
            "source_opportunity": {"name": "Black Friday", "date": d}}


def test_items_work_backwards_from_event():
    items = cp.build_items(date(2026, 12, 5), TODAY)
    by = {(i["kind"], i["days_before_event"]): i for i in items}
    assert by[("review", 7)]["due"] == "2026-11-28"
    assert by[("post", 0)]["due"] == "2026-12-05"
    assert [i["due"] for i in items] == sorted(i["due"] for i in items)


def test_boost_comes_with_real_video_shoot():
    items = cp.build_items(date(2026, 12, 5), TODAY)
    assert any(i["kind"] == "boost" for i in items)
    assert any(i["kind"] == "shoot" and i["needs_real_video"] for i in items)


def test_short_lead_has_no_boost():
    items = cp.build_items(date(2026, 10, 20), TODAY)
    assert not any(i["kind"] == "boost" for i in items)


def test_past_dates_flagged_late_not_moved():
    items = cp.build_items(date(2026, 10, 20), TODAY)
    research = next(i for i in items if i["kind"] == "research")
    assert research["due"] == "2026-09-29" and research["late"] is True


def test_propose_refuses_rejected_and_undated():
    assert not cp.propose_plan("stick", brief("rejected"), today=TODAY)["ok"]
    assert not cp.propose_plan("stick", brief(d=""), today=TODAY)["ok"]


def test_one_plan_per_brief_and_force_supersedes():
    a = cp.propose_plan("stick", brief(), today=TODAY)["plan"]
    again = cp.propose_plan("stick", brief(), today=TODAY)
    assert again["existing"] and again["plan"]["plan_id"] == a["plan_id"]
    b = cp.propose_plan("stick", brief(), force=True, today=TODAY)["plan"]
    assert b["plan_id"] != a["plan_id"]
    assert cp.get_plan("stick", a["plan_id"])["status"] == "superseded"


def test_edit_change_date_and_remove_and_add():
    p = cp.propose_plan("stick", brief(), today=TODAY)["plan"]
    it = p["items"][0]
    r = cp.edit_item("stick", p["plan_id"], it["item_id"],
                     {"due": "2026-11-20", "title": "New idea"})
    assert r["item"]["due"] == "2026-11-20" and r["item"]["source"] == "operator"
    assert not cp.edit_item("stick", p["plan_id"], it["item_id"],
                            {"kind": "nope"})["ok"]
    assert not cp.edit_item("stick", p["plan_id"], it["item_id"],
                            {"item_id": "x"})["ok"]
    cp.edit_item("stick", p["plan_id"], it["item_id"], {"status": "removed"})
    a = cp.add_item("stick", p["plan_id"],
                    {"title": "Email list", "due": "2026-11-30", "kind": "post"})
    assert a["ok"] and len(a["plan"]["items"]) == len(p["items"]) + 1


def test_approve_needs_approved_brief():
    p = cp.propose_plan("stick", brief("draft"), today=TODAY)["plan"]
    assert not cp.approve_plan("stick", p["plan_id"])["ok"]


def test_approve_locks_then_reopen():
    p = cp.propose_plan("stick", brief(), today=TODAY)["plan"]
    assert cp.approve_plan("stick", p["plan_id"])["ok"]
    first = p["items"][0]["item_id"]
    assert not cp.edit_item("stick", p["plan_id"], first, {"title": "x"})["ok"]
    assert cp.edit_item("stick", p["plan_id"], first, {"status": "done"})["ok"]
    assert cp.reopen_plan("stick", p["plan_id"])["ok"]
    assert cp.edit_item("stick", p["plan_id"], first, {"title": "x"})["ok"]


def test_boost_without_video_blocks_approval():
    p = cp.propose_plan("stick", brief(), today=TODAY)["plan"]
    for i in p["items"]:
        if i["kind"] == "shoot" and i["needs_real_video"]:
            cp.edit_item("stick", p["plan_id"], i["item_id"],
                         {"status": "removed"})
    r = cp.approve_plan("stick", p["plan_id"])
    assert not r["ok"] and "real human video" in r["error"]
