"""Idea -> Approve -> Approved date -> Make a plan -> shoot details and drafts for every post.

Closes the gaps between what the team is told Make a plan does and what it did:
approving a date that has passed, shoot steps with nothing to shoot, and one
request per post for caption drafts.
"""
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _lib import calendar_suggestions as cs  # noqa: E402
from _lib import campaign_plan as cp  # noqa: E402

TODAY = date(2026, 10, 26)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def brief(d="2026-12-12", name="Ladies Day"):
    return {"brief_id": "brf-idea0001", "status": "approved",
            "source_opportunity": {"name": name, "date": d}}


# ── approving needs a date that has not passed ────────────────────────

def test_a_date_that_has_passed_cannot_be_approved():
    r = cs.approval_date_check("2026-10-20", TODAY)
    assert r["ok"] is False and "passed" in r["error"]


def test_a_date_a_few_days_out_is_allowed_with_a_warning():
    r = cs.approval_date_check("2026-10-30", TODAY)
    assert r["ok"] is True and r["days"] == 4 and "4 days" in r["warning"]


def test_a_date_with_room_has_no_warning_and_today_counts_as_late():
    far = cs.approval_date_check("2026-12-01", TODAY)
    assert far["ok"] and not far["warning"]
    assert cs.approval_date_check("2026-10-26", TODAY)["warning"]


def test_no_date_is_refused_plainly():
    assert cs.approval_date_check("", TODAY)["ok"] is False


# ── shoot steps arrive with suggested shots ───────────────────────────

def test_shoot_steps_come_with_suggested_shots_that_name_the_date():
    p = cp.propose_plan("stick", brief(), today=TODAY)["plan"]
    shoots = [i for i in p["items"] if i["kind"] == "shoot"]
    assert shoots
    for s in shoots:
        assert s["shots"] and s["shots_suggested"] is True
        assert all(len(x) <= cp.MAX_SHOT_LEN for x in s["shots"])
        assert any("Ladies Day" in x for x in s["shots"])
        text = " ".join(s["shots"]).lower()
        assert "generat" not in text and " ai " not in f" {text} "


def test_the_boost_video_shoot_asks_for_a_person_on_camera():
    p = cp.propose_plan("stick", brief(d="2026-12-20"), today=TODAY)["plan"]
    video = [i for i in p["items"] if i["kind"] == "shoot" and i["needs_real_video"]]
    assert video and any("person" in x.lower() for x in video[0]["shots"])


def test_editing_the_shots_clears_the_suggested_flag():
    p = cp.propose_plan("stick", brief(), today=TODAY)["plan"]
    shoot = next(i for i in p["items"] if i["kind"] == "shoot")
    cp.edit_item("stick", p["plan_id"], shoot["item_id"], {"shots": "one real shot"})
    kept = next(i for i in cp.get_plan("stick", p["plan_id"])["items"] if i["item_id"] == shoot["item_id"])
    assert kept["shots"] == ["one real shot"] and not kept.get("shots_suggested")


# ── one click for every post draft ────────────────────────────────────

def _placed(approved=True, place=True):
    p = cp.propose_plan("stick", brief(), today=TODAY)["plan"]
    if approved:
        cp.approve_plan("stick", p["plan_id"])
    if place:
        cp.place_on_calendar("stick", p["plan_id"],
                             add_record=lambda b, r, s: dict(r, calendar_id="cal-" + r["plan_item_id"]))
    return cp.get_plan("stick", p["plan_id"])


def test_all_drafts_are_asked_for_in_one_go():
    plan = _placed()
    posts = [i for i in plan["items"] if i["kind"] == "post"]
    seen = []
    r = cp.request_all_drafts("stick", plan["plan_id"], "Christelle",
                              enqueue=lambda m, b, why: seen.append(m) or ["draft_caption"])
    assert r["ok"] and r["asked"] == len(posts) and r["failed"] == []
    assert len(seen) == len(posts)
    after = cp.get_plan("stick", plan["plan_id"])
    assert all(i.get("draft") for i in after["items"] if i["kind"] == "post")


def test_a_second_click_does_not_ask_again():
    plan = _placed()
    n = []
    enq = lambda m, b, why: n.append(m) or ["d"]
    cp.request_all_drafts("stick", plan["plan_id"], enqueue=enq)
    first = len(n)
    r = cp.request_all_drafts("stick", plan["plan_id"], enqueue=enq)
    assert len(n) == first and r["asked"] == 0 and r["already"] == first


def test_done_and_removed_posts_are_skipped():
    plan = _placed()
    posts = [i for i in plan["items"] if i["kind"] == "post"]
    cp.edit_item("stick", plan["plan_id"], posts[0]["item_id"], {"status": "done"})
    r = cp.request_all_drafts("stick", plan["plan_id"], enqueue=lambda *a: ["d"])
    assert r["asked"] == len(posts) - 1


def test_one_failure_does_not_stop_the_rest():
    plan = _placed()
    calls = []

    def flaky(m, b, why):
        calls.append(m)
        if len(calls) == 1:
            raise RuntimeError("queue is locked")
        return ["d"]

    r = cp.request_all_drafts("stick", plan["plan_id"], enqueue=flaky)
    assert r["ok"] is False and len(r["failed"]) == 1 and r["asked"] >= 1


def test_all_drafts_refused_until_approved_and_on_the_calendar():
    never = lambda *a: (_ for _ in ()).throw(AssertionError("must not queue"))
    plan = _placed(approved=False, place=False)
    assert "approve the plan" in cp.request_all_drafts("stick", plan["plan_id"], enqueue=never)["error"]
    plan = _placed(approved=True, place=False)
    assert "calendar first" in cp.request_all_drafts("stick", plan["plan_id"], enqueue=never)["error"]
