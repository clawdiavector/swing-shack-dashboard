"""geo_observe: ask the GEO watchlist a few questions a day so the whole list is covered about weekly.

The single-query route (/api/geo/runner/run-one) can take longer than a browser waits, and the
job endpoint is synchronous, so the job works under a time budget and remembers where it stopped.
Every test fakes the OpenAI call; nothing here spends money.
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from _lib import geo_runner  # noqa: E402
from _lib.jobs.layer1 import geo_observe as job  # noqa: E402

WATCHLIST = [{"query": f"question {i}"} for i in range(10)]


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    asked = []

    def fake_run_one_query(brand, query, **kw):
        asked.append((brand, query, kw.get("model"), kw.get("grounding")))
        return {"ok": True, "query": query}

    monkeypatch.setattr(geo_runner, "_load_watchlist", lambda brand: list(WATCHLIST))
    monkeypatch.setattr(geo_runner, "run_one_query", fake_run_one_query)
    return asked


def test_asks_a_few_questions_and_remembers_where_it_stopped(env):
    first = job.run(brand="swing-shack")
    assert first["ok"] and first["rows"] == job.MAX_PER_RUN
    assert [q for _, q, _, _ in env] == [f"question {i}" for i in range(job.MAX_PER_RUN)]
    second = job.run(brand="swing-shack")
    assert second["asked"][0] == f"question {job.MAX_PER_RUN}"


def test_wraps_around_to_the_start_of_the_watchlist(env):
    for _ in range(3):
        out = job.run(brand="swing-shack")
    asked = [q for _, q, _, _ in env]
    assert asked[:10] == [f"question {i}" for i in range(10)]
    assert asked[10] == "question 0"
    assert 0 <= out["next_index"] < len(WATCHLIST)


def test_uses_the_cheap_web_grounded_model(env):
    job.run(brand="stick")
    assert {(m, g) for _, _, m, g in env} == {("gpt-4o-mini", "WEB_GROUNDED")}
    assert {b for b, _, _, _ in env} == {"stick"}


def test_stops_starting_new_questions_when_the_time_budget_is_spent(env, monkeypatch):
    ticks = iter([0, 0, job.TIME_BUDGET_SECONDS + 1, job.TIME_BUDGET_SECONDS + 2, 999, 999])
    monkeypatch.setattr(job, "_clock", lambda: next(ticks))
    out = job.run(brand="swing-shack")
    assert out["rows"] == 1 and len(env) == 1


def test_no_api_key_fails_plainly_and_asks_nothing(env, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    out = job.run(brand="swing-shack")
    assert out["ok"] is False and "OPENAI_API_KEY" in out["error"] and env == []


def test_empty_watchlist_is_fine_and_asks_nothing(env, monkeypatch):
    monkeypatch.setattr(geo_runner, "_load_watchlist", lambda brand: [])
    out = job.run(brand="swing-shack")
    assert out["ok"] and out["rows"] == 0 and env == []


def test_a_failed_question_is_recorded_and_the_cursor_still_moves(env, monkeypatch):
    def flaky(brand, query, **kw):
        env.append((brand, query, kw.get("model"), kw.get("grounding")))
        if query == "question 1":
            raise RuntimeError("OpenAI timed out")
        return {"ok": True}

    monkeypatch.setattr(geo_runner, "run_one_query", flaky)
    out = job.run(brand="swing-shack")
    assert "question 1" in out["failed"] and out["rows"] == job.MAX_PER_RUN - 1
    assert out["ok"], "one failure among several successes is not a failed run"
    assert job.run(brand="swing-shack")["asked"][0] == f"question {job.MAX_PER_RUN}"


def test_every_question_is_reached_within_about_a_week():
    assert job.MAX_PER_RUN * 7 >= 28, "a daily run must be able to cover a 28-question watchlist in a week"


def test_registered_as_a_daily_per_brand_job_for_swing_shack_and_stick():
    from _lib.jobs.registry import JOBS

    spec = JOBS["geo_observe"]
    assert spec.brand_mode == "per_brand" and set(spec.brands) == {"swing-shack", "stick"}
    assert spec.every_seconds == 86400
    assert "OPENAI_API_KEY" in spec.credentials
    assert job.TIME_BUDGET_SECONDS + 60 < spec.timeout_seconds
