"""asset_qc checks the drafts the pipeline makes. A finished post lodged by a person (render_batch /
schedule_posts) is left alone: on 29 Oct it was rejecting every lodged Stick draft for
"missing fields: schema; image file missing or empty"."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(CAMPAIGN_OS))


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "draft-assets").mkdir()
    assets = {
        "lodged-1": {"caption": "Pick your pattern.", "approvalStatus": "review"},
        "lodged-2": {"caption": "Your ball, fitted.", "approvalStatus": "review"},
        "pipe-1": {"caption": "A caption.", "approvalStatus": "review"},
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps({"campaigns": {"camp": {"assets": assets}}}))
    for aid, creator in (("lodged-1", "campaign-os/render_batch"), ("lodged-2", "campaign-os/schedule_posts.py")):
        (tmp_path / "draft-assets" / f"{aid}.json").write_text(json.dumps({
            "asset_id": aid, "campaign_id": "camp", "brand_id": "stick",
            "source_inbox_item_id": "calendar_candidate:stick:cal-1", "created_at": "2026-10-28T08:00:00Z",
            "action": "compose_post", "created_by": creator,
        }))
    # A pipeline draft with no schema is still rejected, as before.
    (tmp_path / "draft-assets" / "pipe-1.json").write_text(json.dumps({
        "asset_id": "pipe-1", "campaign_id": "camp", "brand_id": "stick",
        "source_inbox_item_id": "calendar_candidate:stick:cal-2", "created_at": "2026-10-28T08:00:00Z",
        "action": "draft_caption", "cost_estimate_usd": 0.01,
    }))
    from _lib import llm_spend

    monkeypatch.setattr(llm_spend, "status", lambda: {})
    return tmp_path


def _assets(root: Path) -> dict:
    return json.loads((root / "campaign-data.json").read_text())["campaigns"]["camp"]["assets"]


def test_lodged_posts_are_not_rejected(data):
    from _lib.jobs.layer5 import asset_qc

    out = asset_qc.run()
    assert out["ok"], out
    assets = _assets(data)
    assert assets["lodged-1"]["approvalStatus"] == "review"
    assert assets["lodged-2"]["approvalStatus"] == "review"
    assert "rejectionReason" not in assets["lodged-1"]
    assert assets["pipe-1"]["approvalStatus"] == "rejected"
    assert "missing fields: schema" in assets["pipe-1"]["rejectionReason"]


def test_lodged_posts_are_listed_as_skipped(data):
    from _lib.jobs.layer5 import asset_qc

    asset_qc.run()
    summary = json.loads((data / "asset-qc.json").read_text())
    verdicts = {r["asset_id"]: r["verdict"] for r in summary["results"]}
    assert verdicts == {"lodged-1": "skipped", "lodged-2": "skipped", "pipe-1": "fail"}
    assert summary["skipped"] == 2
