"""P5b — /api/ops/images-today and /api/ops/queue for ReviewPiece regenerate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def _purge() -> None:
    for mod in list(sys.modules):
        if mod.startswith("_lib."):
            del sys.modules[mod]


@pytest.fixture()
def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-token")
    _purge()
    from app import app

    app.config["TESTING"] = True
    client = app.test_client()
    headers = {"Authorization": "Bearer test-token"}
    yield client, tmp_path, headers
    _purge()


def test_ops_images_today_uses_drafted_count(app_client, monkeypatch):
    client, tmp_path, headers = app_client
    from _lib import ops_layers

    monkeypatch.setattr(
        ops_layers,
        "load_create_stats",
        lambda: {
            "images_drafted_today": {"stick": 2, "swing-shack": 0},
            "max_images_per_day": 2,
        },
    )
    rv = client.get("/api/ops/images-today/stick", headers=headers)
    assert rv.status_code == 200
    body = rv.get_json()
    assert body["ok"] is True
    assert body["images_today"] == 2
    assert body["cap"] == 2
    assert body["at_cap"] is True

    rv2 = client.get("/api/ops/images-today/swing-shack", headers=headers)
    assert rv2.get_json()["at_cap"] is False


def test_ops_queue_draft_image_enqueues(app_client, tmp_path):
    client, _, headers = app_client
    brand = "stick"
    campaign_id = "camp-stick"
    aid = "asset-1"
    (tmp_path / "brands.json").write_text(
        json.dumps({"brands": {brand: {"id": brand, "campaign_ids": [campaign_id]}}}),
        encoding="utf-8",
    )
    (tmp_path / "campaign-data.json").write_text(
        json.dumps(
            {
                "campaigns": {
                    campaign_id: {
                        "identity": {"name": "T", "brand": brand},
                        "assets": {
                            aid: {
                                "name": "Piece",
                                "caption": "Cap",
                                "approvalStatus": "pending",
                                "platform": "instagram",
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    item_id = f"draft_asset:{campaign_id}:{aid}"
    rv = client.post(
        "/api/ops/queue",
        headers=headers,
        json={"item_id": item_id, "action": "draft_image", "dedupe_key": "draft_image-test"},
    )
    assert rv.status_code == 200
    assert rv.get_json().get("ok") is True
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    actions = [r.get("action") for r in queue.get("rows") or []]
    assert "draft_image" in actions
