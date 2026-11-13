"""Questions people really ask Google, per brand, for Plan > Ideas.

The old FAQ page (Classic, retired 30 Sep) showed 8 template rows from August such as
"What is /philosophy/?". This replaces it with Google's public search suggestions for
each brand's topics, kept only when they are question-shaped and about this brand's
area and business. Seeds live in data/brand-directory/<brand>/faq-seeds.json.

Fixture: real suggestions saved 13 Nov 2026.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO = CAMPAIGN_OS.parent
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import faq_questions as F  # noqa: E402

SUGGEST = json.loads((Path(__file__).parent / "fixtures" / "faq" / "google-suggest-20261113.json").read_text(encoding="utf-8"))


def fake_get(url: str):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q", [""])[0]
    body = SUGGEST.get(q, [q, []])
    return 200, json.dumps(body).encode("utf-8")


def failing_get(url: str):
    raise OSError("network down")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("is club fitting worth it for high handicappers", True),
        ("how much is club fitting", True),
        ("golf lessons johannesburg prices", True),
        ("golf club fitting cost", True),
        ("golf club fitting chart", False),
        ("golf simulator johannesburg", False),
    ],
)
def test_question_shaped(text, expected):
    assert F.is_question(text) is expected


SS = {"area": ["johannesburg", "joburg", "south africa"], "drop_words": ["for home", "for sale", "golf course"]}
STICK = {"area": ["paarl", "cape town", "western cape", "south africa"], "drop_words": []}


@pytest.mark.parametrize(
    "text,seeds,keep",
    [
        ("how much is club fitting at golf galaxy", SS, False),   # another shop
        ("what is a trackman in baseball", SS, False),            # another sport
        ("is club fitting worth it reddit", SS, False),
        ("how much is a golf simulator for home", SS, False),     # buying one, not a bay
        ("golf lessons johannesburg prices", SS, True),
        ("golf lessons johannesburg prices", STICK, False),       # Stick is in Paarl
        ("golf club fitting pretoria", STICK, False),
        ("golf lessons cape town prices", STICK, True),
        ("is club fitting worth it for beginners", STICK, True),
    ],
)
def test_keeps_only_this_brands_questions(text, seeds, keep):
    assert F.keep(text, seeds) is keep


def test_find_questions_for_swing_shack(tmp_path):
    res = F.questions_for("swing-shack", get=fake_get, cache_dir=tmp_path, sleep=lambda s: None)
    qs = [q["question"] for q in res["questions"]]
    assert res["errors"] == []
    assert "Is club fitting worth it for high handicappers?" in qs
    assert "Golf lessons johannesburg prices" in qs
    assert not any("galaxy" in q.lower() or "baseball" in q.lower() or "for home" in q.lower() for q in qs)
    assert len(qs) == len({q.lower() for q in qs})  # no repeats
    assert all(q["from"] for q in res["questions"])  # each says what was searched


def test_stick_gets_no_johannesburg_questions(tmp_path):
    res = F.questions_for("stick", get=fake_get, cache_dir=tmp_path, sleep=lambda s: None)
    qs = " ".join(q["question"].lower() for q in res["questions"])
    assert res["questions"]
    assert "johannesburg" not in qs and "pretoria" not in qs


def test_questions_are_kept_for_a_week(tmp_path):
    F.questions_for("swing-shack", get=fake_get, cache_dir=tmp_path, sleep=lambda s: None)
    again = F.questions_for("swing-shack", get=failing_get, cache_dir=tmp_path, sleep=lambda s: None)
    assert again["questions"] and again["errors"] == []


def test_google_unreachable_is_reported(tmp_path):
    res = F.questions_for("swing-shack", get=failing_get, cache_dir=tmp_path, sleep=lambda s: None)
    assert res["questions"] == [] and res["errors"]


def test_every_brand_has_seeds():
    for brand in ("stick", "swing-shack", "bag-drop"):
        seeds = F.load_seeds(brand)
        assert seeds["queries"], brand
        assert "area" in seeds, brand


def test_api_returns_questions(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    import app as app_module

    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    monkeypatch.setattr(F, "_get", fake_get)
    monkeypatch.setattr(F, "_sleep", lambda s: None)
    monkeypatch.setattr(F, "CACHE_DIR_OVERRIDE", tmp_path, raising=False)
    client = app_module.app.test_client()
    r = client.get("/api/faq/questions?brand=swing-shack", headers={"Authorization": "Bearer test-job-token-not-a-secret"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True and body["brand"] == "swing-shack"
    assert any("worth it" in q["question"] for q in body["questions"])
    # The test harness signs clients in by default; cos_anon=True is a signed-out visitor.
    anon = app_module.app.test_client(cos_anon=True)
    assert anon.get("/api/faq/questions?brand=swing-shack").status_code == 401


@pytest.mark.parametrize(
    "text",
    [
        "how much is club fitting at edwin watts",
        "how much is club fitting at scheels",
        "what is cool clubs fitting",
        "how to choose a disc golf driver",
        "is a top golf membership worth it",
        "is a golf now membership worth it",
        "how much can you make regripping golf clubs",
        "how much is a golf simulator for your home",
    ],
)
def test_drops_seen_live_on_13_nov(text):
    assert F.keep(text, {"area": ["any"], "drop_words": []}) is False or "home" in text


def test_simulator_for_your_home_is_dropped_for_swing_shack():
    assert F.keep("how much is a golf simulator for your home", F.load_seeds("swing-shack")) is False


def test_at_most_four_questions_per_search(tmp_path):
    res = F.questions_for("swing-shack", get=fake_get, cache_dir=tmp_path, sleep=lambda s: None)
    per = {}
    for q in res["questions"]:
        per[q["from"]] = per.get(q["from"], 0) + 1
    assert per and max(per.values()) <= F.PER_SEARCH
    assert F.PER_SEARCH == 4


def test_list_starts_with_one_question_per_topic(tmp_path):
    res = F.questions_for("stick", get=fake_get, cache_dir=tmp_path, sleep=lambda s: None)
    froms = [q["from"] for q in res["questions"]]
    topics = list(dict.fromkeys(froms))
    assert len(topics) > 1
    assert froms[: len(topics)] == topics  # first pass: one from each search, in seed order
