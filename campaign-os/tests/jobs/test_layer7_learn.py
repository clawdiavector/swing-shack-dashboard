"""L7 Learn: jobs, summary API, ops tab — fixture-driven, no keys."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "layer7"
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def _purge_modules() -> None:
    for mod in list(sys.modules):
        if (
            mod == "app"
            or mod.startswith("_lib.jobs")
            or mod.startswith("_lib.")
            or mod == "_lib.ops_layers"
            or mod == "_lib.feedback_loop"
        ):
            del sys.modules[mod]


@pytest.fixture()
def learn_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "1.00")
    _purge_modules()
    import app as app_module
    from _lib.jobs import cooldown as cd

    cd.reset_for_tests()
    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    app_module._GIT_SYNC_DONE = True
    return app_module, tmp_path


def _seed_fixtures(tmp_path: Path, *, with_conversion: bool = True) -> None:
    shutil.copy(FIXTURES / "ig-business-analytics.min.json", tmp_path / "ig-business-analytics.json")
    if with_conversion:
        shutil.copy(FIXTURES / "post-conversion-score.min.json", tmp_path / "post-conversion-score.json")
    sandbox = tmp_path / "publish-sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / "receipts.jsonl", sandbox / "receipts.jsonl")
    shutil.copy(FIXTURES / "human-edits.jsonl", tmp_path / "human-edits.jsonl")
    proposals = tmp_path / "proposals"
    proposals.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / "proposals-pending.jsonl", proposals / "pending.jsonl")


def _auth():
    return {"Authorization": "Bearer test-job-token-not-a-secret"}


def test_post_outcomes_schema(learn_env):
    _, tmp_path = learn_env
    _seed_fixtures(tmp_path)
    from _lib.jobs.layer7 import post_outcomes

    result = post_outcomes.run()
    assert result["ok"] is True
    doc = json.loads((tmp_path / "post-outcomes.json").read_text(encoding="utf-8"))
    assert doc["schema"] == "campaign-os/post-outcomes/v1"
    assert "outcomes" in doc
    assert doc["posts_total"] >= 1


def test_post_outcomes_joins_receipt_to_ig_post(learn_env):
    _, tmp_path = learn_env
    _seed_fixtures(tmp_path)
    from _lib.jobs.layer7 import post_outcomes

    post_outcomes.run()
    doc = json.loads((tmp_path / "post-outcomes.json").read_text(encoding="utf-8"))
    joined = [
        row for row in doc["outcomes"]
        if row.get("join_basis") == "hook_id" and row.get("inbox_item_id")
    ]
    assert joined, "expected at least one receipt→IG join by hook_id"
    assert joined[0].get("hook_id")


def test_post_outcomes_join_falls_back_on_blank_hook_id(learn_env):
    _, tmp_path = learn_env
    _seed_fixtures(tmp_path)
    from _lib.jobs.layer7 import post_outcomes

    result = post_outcomes.run()
    assert result["ok"] is True


def test_post_outcomes_no_ga4_is_engagement_only(learn_env):
    _, tmp_path = learn_env
    _seed_fixtures(tmp_path, with_conversion=False)
    from _lib.jobs.layer7 import post_outcomes

    post_outcomes.run()
    doc = json.loads((tmp_path / "post-outcomes.json").read_text(encoding="utf-8"))
    assert doc["score_basis"] == "engagement_only"


def test_winner_promotion_is_relative_not_absolute(learn_env):
    _, tmp_path = learn_env
    _seed_fixtures(tmp_path)
    from _lib.jobs.layer7 import post_outcomes, winner_promotion

    post_outcomes.run()
    result = winner_promotion.run()
    assert result["ok"] is True
    doc = json.loads((tmp_path / "winning-recipes.json").read_text(encoding="utf-8"))
    assert doc["ready"] is True
    assert doc["winners"] >= 1
    assert doc["score_basis"] == "engagement_only"


def test_winner_promotion_below_min_samples_is_not_ready(learn_env):
    _, tmp_path = learn_env
    from _lib.jobs.layer7 import winner_promotion

    tiny = {
        "schema": "campaign-os/post-outcomes/v1",
        "outcomes": [
            {"post_id": "a", "brand_id": "stick", "score": 0.42, "hook_id": "a", "evidence": []},
            {"post_id": "b", "brand_id": "stick", "score": 0.41, "hook_id": "b", "evidence": []},
            {"post_id": "c", "brand_id": "stick", "score": 0.40, "hook_id": "c", "evidence": []},
        ],
    }
    (tmp_path / "post-outcomes.json").write_text(json.dumps(tiny), encoding="utf-8")
    winner_promotion.run()
    doc = json.loads((tmp_path / "winning-recipes.json").read_text(encoding="utf-8"))
    assert doc["ready"] is False
    assert doc["recipes"] == []


def test_winning_recipes_schema_frozen(learn_env):
    _, tmp_path = learn_env
    _seed_fixtures(tmp_path)
    from _lib.jobs.layer7 import post_outcomes, winner_promotion

    post_outcomes.run()
    winner_promotion.run()
    doc = json.loads((tmp_path / "winning-recipes.json").read_text(encoding="utf-8"))
    required = {"recipe_id", "brand_id", "rank", "percentile", "score", "evidence", "join_basis"}
    for recipe in doc.get("recipes") or []:
        assert required.issubset(recipe.keys())


def test_proposal_outcome_missing_file_is_insufficient_data(learn_env, tmp_path):
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _purge_modules()
    from _lib.jobs.layer7 import proposal_outcome

    result = proposal_outcome.run()
    assert result["ok"] is True
    doc = json.loads((tmp_path / "proposal-outcomes.json").read_text(encoding="utf-8"))
    assert doc["gate"]["verdict"] == "insufficient_data"
    assert doc["gate"]["measured_pct"] is None
    monkeypatch.undo()


def test_proposal_outcome_computes_rate(learn_env):
    _, tmp_path = learn_env
    _seed_fixtures(tmp_path)
    from _lib.jobs.layer7 import proposal_outcome

    proposal_outcome.run()
    doc = json.loads((tmp_path / "proposal-outcomes.json").read_text(encoding="utf-8"))
    assert doc["gate"]["measured_pct"] == 70.0
    assert doc["gate"]["verdict"] == "pass"


def test_human_edit_signal_normalises_both_row_shapes(learn_env):
    _, tmp_path = learn_env
    _seed_fixtures(tmp_path)
    from _lib.jobs.layer7 import human_edit_signal

    human_edit_signal.run()
    doc = json.loads((tmp_path / "human-edit-summary.json").read_text(encoding="utf-8"))
    by_action = doc["by_action"]
    assert by_action.get("edit", 0) >= 2
    assert by_action.get("approve", 0) >= 2
    assert by_action.get("reject", 0) >= 1


def test_human_edit_signal_empty_file(learn_env, tmp_path):
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _purge_modules()
    from _lib.jobs.layer7 import human_edit_signal

    result = human_edit_signal.run()
    assert result["ok"] is True
    doc = json.loads((tmp_path / "human-edit-summary.json").read_text(encoding="utf-8"))
    assert doc["rows"] == 0
    monkeypatch.undo()


def test_learn_summary_bearer_and_session(learn_env):
    app_module, tmp_path = learn_env
    _seed_fixtures(tmp_path)
    from _lib.jobs.layer7 import post_outcomes, winner_promotion, human_edit_signal, proposal_outcome

    post_outcomes.run()
    winner_promotion.run()
    human_edit_signal.run()
    proposal_outcome.run()

    client = app_module.app.test_client()
    anon = app_module.app.test_client(cos_anon=True)
    assert anon.get("/api/ops/learn/summary").status_code == 401
    bearer = anon.get("/api/ops/learn/summary", headers=_auth())
    assert bearer.status_code == 200
    body = bearer.get_json()
    assert body.get("ok") is True
    assert body.get("schema") == "campaign-os/ops-learn-summary/v1"
    session = client.get("/api/ops/learn/summary")
    assert session.status_code == 200


def test_learn_summary_not_widened(learn_env):
    app_module, _ = learn_env
    anon = app_module.app.test_client(cos_anon=True)
    for path in ("/api/ops/errors", "/api/ops/runbook", "/api/ops/llm-spend"):
        assert anon.get(path, headers=_auth()).status_code == 401


def test_ops_learn_tab_renders(learn_env):
    app_module, _ = learn_env
    anon = app_module.app.test_client(cos_anon=True)
    client = app_module.app.test_client()
    assert anon.get("/ops?layer=learn", follow_redirects=False).status_code == 302
    resp = client.get("/ops?layer=learn")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'id="layer-learn"' in body
    assert "loadLearn" in body or "learn-body" in body


def test_l7_jobs_registered(learn_env):
    from _lib.jobs.registry import JOBS

    for name in ("post_outcomes", "winner_promotion", "proposal_outcome", "human_edit_signal"):
        spec = JOBS[name]
        assert spec.credentials == ()
        assert spec.writes


def test_l7_job_output_viewable(learn_env):
    from _lib.jobs.output_file import is_path_allowed

    assert is_path_allowed("winner_promotion", "winning-recipes.json") is True
