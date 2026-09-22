"""Job output allowlist — brand-resolved paths for per_brand jobs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib.jobs.output_file import (  # noqa: E402
    _allowed_writes,
    is_path_allowed,
    list_output_files,
)
from _lib.jobs.registry import JOBS  # noqa: E402
from _lib.jobs.spec import JobSpec  # noqa: E402


def test_brand_output_path_allowed():
    assert is_path_allowed("post_conversion_score", "brands/stick/post-conversion-score.json")
    assert is_path_allowed(
        "post_conversion_score", "brands/swing-shack/post-conversion-score.json"
    )


def test_flat_output_path_still_allowed():
    assert is_path_allowed("post_conversion_score", "post-conversion-score.json")


def test_unknown_brand_path_rejected():
    assert is_path_allowed("post_conversion_score", "brands/not-a-brand/post-conversion-score.json") is False


def test_traversal_still_rejected():
    with pytest.raises(ValueError, match="path traversal"):
        is_path_allowed("post_conversion_score", "brands/stick/../../etc/passwd")


def test_list_outputs_includes_brand_paths():
    paths = [f["path"] for f in list_output_files("post_conversion_score")]
    assert "post-conversion-score.json" in paths
    assert "brands/stick/post-conversion-score.json" in paths
    assert "brands/swing-shack/post-conversion-score.json" in paths


def test_non_per_brand_paths_unchanged():
    for job in ("golf_news", "reddit_trends", "youtube_trends"):
        paths = [f["path"] for f in list_output_files(job)]
        assert not any(p.startswith("brands/") for p in paths)
    for job in ("slot_planner", "agent_queue_writer", "review_sla"):
        paths = [f["path"] for f in list_output_files(job)]
        assert not any(p.startswith("brands/") for p in paths)


def test_shared_write_stays_flat():
    spec = JobSpec(
        name="_synthetic_shared_write_test",
        fn=lambda **_: {"ok": True},
        every_seconds=60,
        brand_mode="per_brand",
        writes=("shared-out.json", "per-brand-out.json"),
        shared_writes=("shared-out.json",),
    )
    allowed = _allowed_writes(spec)
    assert "shared-out.json" in allowed
    assert "per-brand-out.json" in allowed
    assert "brands/swing-shack/shared-out.json" not in allowed
    assert "brands/swing-shack/per-brand-out.json" in allowed


def test_directory_write_allows_children():
    assert is_path_allowed("draft_assets", "draft-assets/x.json")
    files = list_output_files("draft_assets")
    draft_entry = next(f for f in files if f["path"].startswith("draft-assets"))
    assert draft_entry["kind"] == "directory"


@pytest.fixture()
def job_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib.jobs"):
            del sys.modules[mod]
    import app as app_module

    client = app_module.app.test_client()
    return client, tmp_path


def _auth():
    return {"Authorization": "Bearer test-job-token-not-a-secret"}


def test_api_reads_brand_post_conversion_score(job_app):
    client, tmp_path = job_app
    brand_path = tmp_path / "brands" / "stick" / "post-conversion-score.json"
    brand_path.parent.mkdir(parents=True)
    payload = {"posts_ranked": [], "summary": {"posts_scored": 30}}
    brand_path.write_text(json.dumps(payload), encoding="utf-8")
    resp = client.get(
        "/api/jobs/output?job=post_conversion_score&path=brands/stick/post-conversion-score.json",
        headers=_auth(),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("ok") is True
    assert body.get("data", {}).get("summary", {}).get("posts_scored") == 30
