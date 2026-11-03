"""Flesh out an idea: a whole concept, content, shots and next steps, from the idea and the brand's verified facts.

The model call is injected. What is tested is what goes in, what is let through, and what is stored.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _lib import idea_builder as ib  # noqa: E402
from _lib import mail_intake as mi  # noqa: E402

TODAY = date(2026, 10, 26)
HERMAN = "herman@example.test"

GOOD = {
    "concept": {"name": "Ladies' Black Friday Fitting Day", "one_line": "A relaxed day for women to get fitted and shop.",
                "why_it_works": "Women are under-served in golf retail and few brands speak to them directly.",
                "audience": "Women who play or want to start"},
    "offer": {"what": "A ladies-only fitting day with a Black Friday offer on selected ladies' products",
              "to_confirm": ["Which products are on offer", "The size of the offer"]},
    "content": [
        {"kind": "post", "title": "The invitation", "idea": "A real fitting in progress", "caption_direction": "Calm, warm, plain invitation"},
        {"kind": "story", "title": "Countdown", "idea": "Three days to go", "caption_direction": "Short, with the booking link"},
    ],
    "shots": ["A woman being fitted in the studio", "The ladies' range on the shelf"],
    "next_steps": [{"step": "Confirm the offer with Herman", "who": "Christelle"},
                   {"step": "Book a photographer for the fitting day", "who": "Christelle"}],
    "questions": ["Is the offer on clubs, apparel or both?"],
    "risks": ["Offer not confirmed in time for the shoot"],
}


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MAIL_INTAKE_SENDERS", HERMAN)


def idea(text="Black Friday deals aimed specifically at ladies.", brand="stick", mid="m1"):
    it = mi.file_message({"message_id": mid, "from": f"Herman <{HERMAN}>", "subject": "Ideas", "text": "What if " + text}, TODAY)
    return mi.set_brand_date(it["id"], brand, "2026-11-27") if brand else it


def chat_returning(obj, calls=None):
    def chat(messages):
        if calls is not None:
            calls.append(messages)
        return obj if isinstance(obj, str) else json.dumps(obj)
    return chat


# ── what goes in ──────────────────────────────────────────────────────

def test_the_prompt_carries_the_idea_and_only_this_brands_facts():
    msgs = ib.build_messages(idea(), TODAY)
    text = " ".join(m["content"] for m in msgs)
    assert "Black Friday deals aimed specifically at ladies" in text and "Paarl" in text
    assert "Swing Shack" not in text


def test_swing_shack_prompt_has_no_stick_or_paarl():
    text = " ".join(m["content"] for m in ib.build_messages(idea(brand="swing-shack", mid="m2"), TODAY))
    assert "Paarl" not in text and "Stick" not in text


def test_the_prompt_states_the_standing_rules():
    text = " ".join(m["content"] for m in ib.build_messages(idea(), TODAY)).lower()
    for needle in ("do not invent", "real photos", "to confirm"):
        assert needle in text


# ── what is let through ───────────────────────────────────────────────

def test_a_good_answer_is_kept_whole():
    out = ib.clean(json.dumps(GOOD), "Black Friday deals for ladies", "stick")
    assert out["concept"]["name"].startswith("Ladies") and len(out["content"]) == 2 and out["next_steps"][0]["who"] == "Christelle"


def test_code_fences_and_chatter_around_the_json_are_ignored():
    raw = "Here you go:\n```json\n" + json.dumps(GOOD) + "\n```\nHope that helps."
    assert ib.clean(raw, "x", "stick")["concept"]["audience"]


def test_amounts_the_idea_did_not_give_become_to_confirm():
    bad = json.loads(json.dumps(GOOD))
    bad["offer"]["what"] = "15% off ladies' clubs and R500 off a fitting"
    out = ib.clean(json.dumps(bad), "Black Friday deals aimed at ladies", "stick")
    assert "15%" not in out["offer"]["what"] and "R500" not in out["offer"]["what"]
    assert "to confirm" in out["offer"]["what"]


def test_an_amount_that_is_in_the_idea_is_kept():
    bad = json.loads(json.dumps(GOOD))
    bad["offer"]["what"] = "15% off ladies' clubs"
    out = ib.clean(json.dumps(bad), "Give ladies 15% off on Black Friday", "stick")
    assert "15%" in out["offer"]["what"]


def test_the_other_brand_in_the_answer_is_refused():
    bad = json.loads(json.dumps(GOOD))
    bad["content"][0]["idea"] = "Shot at Swing Shack in Johannesburg"
    with pytest.raises(ib.IdeaError):
        ib.clean(json.dumps(bad), "x", "stick")
    bad["content"][0]["idea"] = "Shot at Stick in Paarl"
    with pytest.raises(ib.IdeaError):
        ib.clean(json.dumps(bad), "x", "swing-shack")


def test_generated_imagery_is_dropped_from_shots_and_content():
    bad = json.loads(json.dumps(GOOD))
    bad["shots"] = ["An AI-generated woman holding a club", "A woman being fitted in the studio"]
    out = ib.clean(json.dumps(bad), "x", "stick")
    assert out["shots"] == ["A woman being fitted in the studio"]


def test_lists_are_capped_and_wrong_shapes_are_refused():
    big = json.loads(json.dumps(GOOD))
    big["content"] = big["content"] * 10
    assert len(ib.clean(json.dumps(big), "x", "stick")["content"]) == ib.MAX_CONTENT
    with pytest.raises(ib.IdeaError):
        ib.clean("not json at all", "x", "stick")
    with pytest.raises(ib.IdeaError):
        ib.clean(json.dumps({"concept": "just a string"}), "x", "stick")


# ── flesh out ─────────────────────────────────────────────────────────

def test_it_needs_a_brand_and_refuses_bag_drop():
    never = lambda m: (_ for _ in ()).throw(AssertionError("must not call the model"))
    assert "brand" in ib.flesh_out(idea(brand=None, mid="a")["id"], never, TODAY)["error"]
    assert "Bag Drop" in ib.flesh_out(idea(brand="bag-drop", mid="b")["id"], never, TODAY)["error"]


def test_the_result_is_stored_on_the_idea():
    it = idea()
    r = ib.flesh_out(it["id"], chat_returning(GOOD), TODAY)
    assert r["ok"] and r["item"]["fleshed"]["concept"]["name"].startswith("Ladies")
    assert mi.get_item(it["id"])["fleshed"]["generated_at"]


def test_bad_json_is_tried_once_more_then_reported():
    it, calls = idea(), []
    replies = iter(["nope", json.dumps(GOOD)])
    r = ib.flesh_out(it["id"], lambda m: calls.append(m) or next(replies), TODAY)
    assert r["ok"] and len(calls) == 2
    r = ib.flesh_out(idea(mid="z")["id"], lambda m: "nope", TODAY)
    assert not r["ok"] and "try again" in r["error"].lower()


def test_a_model_failure_changes_nothing():
    it = idea()

    def boom(m):
        raise RuntimeError("timeout")
    r = ib.flesh_out(it["id"], boom, TODAY)
    assert not r["ok"] and "fleshed" not in mi.get_item(it["id"])


# ── the plan uses it ──────────────────────────────────────────────────

def test_a_new_plan_takes_its_shots_and_notes_from_the_fleshed_out_idea():
    it = idea()
    ib.flesh_out(it["id"], chat_returning(GOOD), TODAY)
    r = mi.idea_plan(it["id"], TODAY)
    shoots = [i for i in r["plan"]["items"] if i["kind"] == "shoot" and not i["needs_real_video"]]
    assert shoots and shoots[0]["shots"][0] == "A woman being fitted in the studio" and shoots[0]["shots_suggested"]
    posts = [i for i in r["plan"]["items"] if i["kind"] == "post"]
    assert any("Ladies' Black Friday Fitting Day" in (p.get("note") or "") for p in posts)
    decide = next(i for i in r["plan"]["items"] if i["kind"] == "decide")
    assert "relaxed day for women" in decide["note"]
