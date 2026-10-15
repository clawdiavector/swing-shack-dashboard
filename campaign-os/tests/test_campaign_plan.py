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


def test_sync_brief_status_unsticks_a_plan():
    p = cp.propose_plan("stick", brief("draft"), today=TODAY)["plan"]
    assert not cp.approve_plan("stick", p["plan_id"])["ok"]
    cp.sync_brief_status(cp.get_plan("stick", p["plan_id"]), brief("approved"))
    assert cp.get_plan("stick", p["plan_id"])["brief_status"] == "approved"
    assert cp.approve_plan("stick", p["plan_id"])["ok"]


def _approved_plan():
    p = cp.propose_plan("stick", brief(), today=TODAY)["plan"]
    assert cp.approve_plan("stick", p["plan_id"])["ok"]
    return p["plan_id"]


class FakeCalendar:
    def __init__(self):
        self.rows, self.moved = [], []

    def add(self, brand, record, status):
        rec = dict(record, calendar_id=f"cal-{len(self.rows)}", status=status)
        self.rows.append(rec)
        return rec

    def transition(self, brand, cid, status, reason=""):
        self.moved.append((cid, status))


def test_place_needs_approved_plan():
    p = cp.propose_plan("stick", brief(), today=TODAY)["plan"]
    r = cp.place_on_calendar("stick", p["plan_id"], add_record=FakeCalendar().add)
    assert not r["ok"] and "approve" in r["error"]


def test_place_creates_content_and_reminders_once():
    pid = _approved_plan()
    cal = FakeCalendar()
    r = cp.place_on_calendar("stick", pid, add_record=cal.add)
    assert r["ok"] and r["placed"] == len(cal.rows) > 0
    types = {row["plan_item_kind"]: row["type"] for row in cal.rows}
    assert types["post"] == "moment" and types["story"] == "content"   # a post is a moment the Create pipeline can draft
    assert types["shoot"] == "reminder" and types["boost"] == "reminder"
    assert all(row["status"] == "approved" for row in cal.rows)
    again = cp.place_on_calendar("stick", pid, add_record=cal.add)
    assert again["placed"] == 0 and len(cal.rows) == r["placed"]


def test_removed_steps_are_not_placed():
    p = cp.propose_plan("stick", brief(), today=TODAY)["plan"]
    gone = p["items"][0]
    cp.edit_item("stick", p["plan_id"], gone["item_id"], {"status": "removed"})
    cp.approve_plan("stick", p["plan_id"])
    cal = FakeCalendar()
    cp.place_on_calendar("stick", p["plan_id"], add_record=cal.add)
    assert all(row["plan_item_id"] != gone["item_id"] for row in cal.rows)


def test_take_off_undoes_and_unblocks_reopen():
    pid = _approved_plan()
    cal = FakeCalendar()
    cp.place_on_calendar("stick", pid, add_record=cal.add)
    assert not cp.reopen_plan("stick", pid)["ok"]
    r = cp.take_off_calendar("stick", pid, transition=cal.transition)
    assert r["ok"] and r["removed"] == len(cal.rows)
    assert all(status == "ignored" for _, status in cal.moved)
    assert cp.get_plan("stick", pid)["placed_at"] is None
    assert cp.reopen_plan("stick", pid)["ok"]


def test_one_failed_step_is_reported_not_hidden():
    pid = _approved_plan()
    cal = FakeCalendar()

    def flaky(brand, record, status):
        if record["plan_item_kind"] == "boost":
            raise ValueError("no")
        return cal.add(brand, record, status)

    r = cp.place_on_calendar("stick", pid, add_record=flaky)
    assert not r["ok"] and len(r["failed"]) == 1 and r["placed"] > 0
    retry = cp.place_on_calendar("stick", pid, add_record=cal.add)
    assert retry["placed"] == 1


def test_latest_revisions_lets_an_undo_hide_the_old_row():
    from _lib.marketing_calendar import latest_revisions
    rows = [
        {"calendar_id": "a", "status": "approved"},
        {"calendar_id": "b", "status": "approved"},
        {"calendar_id": "a", "status": "ignored"},
        {"status": "approved", "title": "no id"},
    ]
    kept = latest_revisions(rows)
    assert [(r.get("calendar_id"), r["status"]) for r in kept] == [
        ("b", "approved"), ("a", "ignored"), (None, "approved")]


def test_month_steps_lists_only_steps_not_yet_on_the_calendar():
    p = cp.propose_plan("stick", brief(d="2026-12-12"), today=TODAY)["plan"]
    gone = p["items"][0]
    cp.edit_item("stick", p["plan_id"], gone["item_id"], {"status": "removed"})
    first, last = date(2026, 11, 1), date(2026, 12, 31)
    steps = cp.month_steps("stick", first, last)
    assert steps and all(first <= date.fromisoformat(s["date"]) <= last for s in steps)
    assert gone["item_id"] not in [s["item_id"] for s in steps]
    assert steps == sorted(steps, key=lambda s: (s["date"], s["event_name"], s["title"]))
    assert steps[0]["event_name"] == "Black Friday" and steps[0]["plan_status"] == "proposed"
    # a month with nothing due is empty
    assert cp.month_steps("stick", date(2027, 6, 1), date(2027, 6, 30)) == []
    # once on the calendar they are solid there, so they leave this list
    cp.approve_plan("stick", p["plan_id"])
    assert cp.month_steps("stick", first, last)  # approved but not placed: still faded
    cp.place_on_calendar("stick", p["plan_id"],
                         add_record=lambda b, r, s: dict(r, calendar_id=r["plan_item_id"]))
    assert cp.month_steps("stick", first, last) == []


def test_month_steps_skips_superseded_plans():
    first = cp.propose_plan("stick", brief(d="2026-12-12"), today=TODAY)["plan"]
    cp.propose_plan("stick", brief(d="2026-12-12"), today=TODAY, force=True)
    ids = {s["plan_id"] for s in cp.month_steps("stick", date(2026, 11, 1), date(2026, 12, 31))}
    assert first["plan_id"] not in ids and len(ids) == 1


def test_late_is_worked_out_when_read_not_frozen_at_creation(monkeypatch):
    p = cp.propose_plan("stick", brief(d="2026-12-12"), today=TODAY)["plan"]
    assert not any(i["late"] for i in cp.get_plan("stick", p["plan_id"])["items"])
    # three weeks on, the early steps have gone overdue without anyone editing the plan
    monkeypatch.setattr(cp, "_today", lambda: date(2026, 12, 3))
    items = cp.get_plan("stick", p["plan_id"])["items"]
    overdue = [i for i in items if i["due"] < "2026-12-03"]
    assert overdue and all(i["late"] for i in overdue)
    assert not any(i["late"] for i in items if i["due"] >= "2026-12-03")
    # done and removed steps are never late
    cp.edit_item("stick", p["plan_id"], overdue[0]["item_id"], {"status": "done"})
    cp.edit_item("stick", p["plan_id"], overdue[1]["item_id"], {"status": "removed"})
    again = {i["item_id"]: i["late"] for i in cp.get_plan("stick", p["plan_id"])["items"]}
    assert again[overdue[0]["item_id"]] is False and again[overdue[1]["item_id"]] is False
    # the month list uses the same rule
    steps = cp.month_steps("stick", date(2026, 11, 1), date(2026, 12, 31))
    assert any(s["late"] for s in steps)


def test_a_boost_can_carry_a_planned_budget_and_nothing_else_can():
    p = cp.propose_plan("stick", brief(d="2026-12-12"), today=TODAY)["plan"]
    boost = next(i for i in p["items"] if i["kind"] == "boost")
    post = next(i for i in p["items"] if i["kind"] == "post")
    ok = cp.edit_item("stick", p["plan_id"], boost["item_id"], {"budget": "1,500"})
    assert ok["ok"] and ok["item"]["budget"] == 1500
    assert cp.edit_item("stick", p["plan_id"], boost["item_id"], {"budget": "R 250.50"})["item"]["budget"] == 250.5
    for bad in ("lots", -5, "NaN", 2_000_000):
        assert not cp.edit_item("stick", p["plan_id"], boost["item_id"], {"budget": bad})["ok"]
    assert not cp.edit_item("stick", p["plan_id"], post["item_id"], {"budget": 100})["ok"]
    cleared = cp.edit_item("stick", p["plan_id"], boost["item_id"], {"budget": ""})
    assert cleared["ok"] and cleared["item"]["budget"] is None
    added = cp.add_item("stick", p["plan_id"], {"title": "Second boost", "due": "2026-12-08", "kind": "boost", "budget": 800})
    assert added["ok"] and added["item"]["budget"] == 800
    assert not cp.add_item("stick", p["plan_id"], {"title": "A post", "due": "2026-12-08", "kind": "post", "budget": 800})["ok"]


def test_the_budget_goes_onto_the_calendar_entry_and_the_month_steps():
    p = cp.propose_plan("stick", brief(d="2026-12-12"), today=TODAY)["plan"]
    boost = next(i for i in p["items"] if i["kind"] == "boost")
    cp.edit_item("stick", p["plan_id"], boost["item_id"], {"budget": 1200})
    steps = cp.month_steps("stick", date(2026, 11, 1), date(2026, 12, 31))
    assert [s["budget"] for s in steps if s["step"] == "boost"] == [1200]
    cp.approve_plan("stick", p["plan_id"])
    rows = []
    cp.place_on_calendar("stick", p["plan_id"],
                         add_record=lambda b, r, s: rows.append(r) or dict(r, calendar_id=f"c{len(rows)}"))
    boost_row = next(r for r in rows if r["plan_item_kind"] == "boost")
    assert boost_row["planned_budget_zar"] == 1200 and "R1,200" in boost_row["angle"]


def _shoot(plan):
    return next(i for i in plan["items"] if i["kind"] == "shoot")


def test_a_shoot_step_takes_a_shot_list_one_per_line():
    p = cp.propose_plan("stick", brief(d="2026-12-12"), today=TODAY)["plan"]
    shoot, post = _shoot(p), next(i for i in p["items"] if i["kind"] == "post")
    r = cp.edit_item("stick", p["plan_id"], shoot["item_id"],
                     {"shots": "- The whole range laid out\n\n• Close-ups of the gift vouchers\n  A few products in use  "})
    assert r["ok"] and r["item"]["shots"] == ["The whole range laid out", "Close-ups of the gift vouchers", "A few products in use"]
    assert cp.edit_item("stick", p["plan_id"], shoot["item_id"], {"shots": ["one", "two"]})["item"]["shots"] == ["one", "two"]
    assert cp.edit_item("stick", p["plan_id"], shoot["item_id"], {"shots": ""})["item"]["shots"] == []
    assert not cp.edit_item("stick", p["plan_id"], shoot["item_id"], {"shots": ["x"] * 21})["ok"]
    assert not cp.edit_item("stick", p["plan_id"], shoot["item_id"], {"shots": ["x" * 201]})["ok"]
    assert not cp.edit_item("stick", p["plan_id"], shoot["item_id"], {"shots": 5})["ok"]
    assert not cp.edit_item("stick", p["plan_id"], post["item_id"], {"shots": ["a shot"]})["ok"]


def test_a_shoot_step_remembers_who_was_asked_even_after_the_plan_is_approved():
    p = cp.propose_plan("stick", brief(d="2026-12-12"), today=TODAY)["plan"]
    shoot = _shoot(p)
    r = cp.edit_item("stick", p["plan_id"], shoot["item_id"], {"asked": " Pieter "})
    assert r["item"]["asked"]["to"] == "Pieter" and r["item"]["asked"]["at"]
    assert not cp.edit_item("stick", p["plan_id"], next(i for i in p["items"] if i["kind"] == "post")["item_id"],
                            {"asked": "Pieter"})["ok"]
    assert cp.approve_plan("stick", p["plan_id"])["ok"]
    other = [i for i in p["items"] if i["kind"] == "shoot"][-1]
    assert cp.edit_item("stick", p["plan_id"], other["item_id"], {"asked": "Anel"})["ok"]     # allowed while locked
    assert not cp.edit_item("stick", p["plan_id"], other["item_id"], {"title": "x", "asked": "Anel"})["ok"]
    assert cp.reopen_plan("stick", p["plan_id"])["ok"]
    cleared = cp.edit_item("stick", p["plan_id"], shoot["item_id"], {"asked": ""})
    assert cleared["item"]["asked"] is None


def test_a_new_shoot_step_can_carry_a_shot_list():
    p = cp.propose_plan("stick", brief(d="2026-12-12"), today=TODAY)["plan"]
    a = cp.add_item("stick", p["plan_id"], {"title": "Shoot the window", "due": "2026-12-01", "kind": "shoot",
                                            "shots": "The window at dusk\nThe new stock"})
    assert a["ok"] and a["item"]["shots"] == ["The window at dusk", "The new stock"]
    assert not cp.add_item("stick", p["plan_id"], {"title": "A post", "due": "2026-12-01", "kind": "post",
                                                    "shots": ["no"]})["ok"]


def _placed_post(approved=True, place=True):
    p = cp.propose_plan("stick", brief(d="2026-12-12"), today=TODAY)["plan"]
    if approved:
        cp.approve_plan("stick", p["plan_id"])
    if place:
        cp.place_on_calendar("stick", p["plan_id"],
                             add_record=lambda b, r, s: dict(r, calendar_id="cal-" + r["plan_item_id"]))
    plan = cp.get_plan("stick", p["plan_id"])
    return plan, next(i for i in plan["items"] if i["kind"] == "post")


def test_a_planned_post_tells_the_caption_writer_only_what_the_plan_knows():
    p = cp.propose_plan("stick", brief(d="2026-12-12"), today=TODAY, profile="retail_push")["plan"]
    post = next(i for i in p["items"] if i["kind"] == "post")
    text = cp.post_brief(p, post)
    assert post["title"] in text and "Black Friday" in text and "2026-12-12" in text
    assert "retail push plan" in text
    assert "R" not in text.replace("Retail", "").split("plan")[-1]   # no prices or budgets slipped in
    rows = []
    cp.approve_plan("stick", p["plan_id"])
    cp.place_on_calendar("stick", p["plan_id"], add_record=lambda b, r, s: rows.append(r) or dict(r, calendar_id=f"c{len(rows)}"))
    mine = next(r for r in rows if r["plan_item_kind"] == "post")
    assert mine["type"] == "moment" and mine["angle"].startswith(post["title"])


def test_a_draft_can_be_asked_for_once_the_plan_is_approved_and_on_the_calendar():
    plan, post = _placed_post()
    seen = []
    r = cp.request_draft("stick", plan["plan_id"], post["item_id"], "Christelle",
                         enqueue=lambda moment, brand, reason: seen.append((moment, brand, reason)) or ["draft_caption"])
    assert r["ok"] and r["queued"] == ["draft_caption"]
    assert seen == [(f"calendar_candidate:stick:cal-{post['item_id']}", "stick", "plan-step")]
    kept = next(i for i in cp.get_plan("stick", plan["plan_id"])["items"] if i["item_id"] == post["item_id"])
    assert kept["draft"]["by"] == "Christelle" and kept["draft"]["queued"] == ["draft_caption"]


def test_a_draft_is_refused_with_a_plain_reason_when_it_is_too_early_or_the_wrong_kind():
    never = lambda *a: (_ for _ in ()).throw(AssertionError("must not queue"))
    plan, post = _placed_post(approved=False, place=False)
    assert "approve the plan" in cp.request_draft("stick", plan["plan_id"], post["item_id"], enqueue=never)["error"]
    plan, post = _placed_post(approved=True, place=False)
    assert "calendar first" in cp.request_draft("stick", plan["plan_id"], post["item_id"], enqueue=never)["error"]
    plan, post = _placed_post()
    story = next(i for i in plan["items"] if i["kind"] == "story")
    assert "only a post" in cp.request_draft("stick", plan["plan_id"], story["item_id"], enqueue=never)["error"]
    assert not cp.request_draft("stick", plan["plan_id"], "it-missing", enqueue=never)["ok"]
    assert not cp.request_draft("stick", "pln-missing", post["item_id"], enqueue=never)["ok"]
    cp.edit_item("stick", plan["plan_id"], post["item_id"], {"status": "done"})
    assert "already done" in cp.request_draft("stick", plan["plan_id"], post["item_id"], enqueue=never)["error"]


def test_a_failure_in_the_pipeline_is_reported_and_nothing_is_recorded():
    plan, post = _placed_post()

    def boom(*a):
        raise RuntimeError("queue is locked")

    r = cp.request_draft("stick", plan["plan_id"], post["item_id"], enqueue=boom)
    assert not r["ok"] and "queue is locked" in r["error"]
    assert "draft" not in next(i for i in cp.get_plan("stick", plan["plan_id"])["items"] if i["item_id"] == post["item_id"])
