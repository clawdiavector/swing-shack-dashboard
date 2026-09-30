"""Caption edit enqueues compose_post when a composed PNG exists."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from tests.jobs.test_layer5_create import _seed_brands, l5_app  # noqa: E402


def _seed_composed_draft(tmp_path: Path) -> tuple[str, str]:
    brand = "stick"
    campaign_id = "camp-stick"
    asset_id = "draft-compose-test"
    item_id = "proposal:stick:prop-compose"
    _seed_brands(tmp_path, brand=brand, campaign_id=campaign_id)
    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    data["campaigns"][campaign_id]["assets"][asset_id] = {
        "name": "Test draft",
        "caption": "Original caption",
        "approvalStatus": "draft",
        "platform": "instagram",
        "composed": {"instagram": "draft-assets/composed/test.png"},
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")
    sidecar = {
        "schema": "campaign-os/draft-asset/v1",
        "asset_id": asset_id,
        "brand_id": brand,
        "source_inbox_item_id": item_id,
        "composed": {"instagram": "draft-assets/composed/test.png"},
        "_poster_copy_source": "llm_hook",
        "compose_headline": "OLD HOOK",
    }
    (tmp_path / "draft-assets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "draft-assets" / f"{asset_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    (tmp_path / "agent-queue.json").write_text(
        json.dumps({"schema": "campaign-os/agent-queue/v1", "generated_at": "2026-09-30T00:00:00Z", "rows": []}),
        encoding="utf-8",
    )
    draft_item_id = f"draft_asset:{campaign_id}:{asset_id}"
    return draft_item_id, asset_id


def test_caption_edit_enqueues_compose_post_when_composed(l5_app, tmp_path):
    from _lib import unified_inbox

    draft_item_id, _asset_id = _seed_composed_draft(tmp_path)
    unified_inbox.edit_item(draft_item_id, fields={"caption": "Updated caption text"})
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    pending = [r for r in queue.get("rows") or [] if r.get("status") == "pending"]
    compose = [r for r in pending if r.get("action") == "compose_post"]
    assert len(compose) == 1
    assert compose[0].get("payload_ref") == "inbox/proposal:stick:prop-compose"


def test_caption_edit_no_enqueue_when_not_composed(l5_app, tmp_path):
    from _lib import unified_inbox

    draft_item_id, asset_id = _seed_composed_draft(tmp_path)
    sidecar = json.loads((tmp_path / "draft-assets" / f"{asset_id}.json").read_text(encoding="utf-8"))
    sidecar.pop("composed", None)
    (tmp_path / "draft-assets" / f"{asset_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    data = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    data["campaigns"]["camp-stick"]["assets"][asset_id].pop("composed", None)
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")

    unified_inbox.edit_item(draft_item_id, fields={"caption": "No compose please"})
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    compose = [r for r in queue.get("rows") or [] if r.get("action") == "compose_post"]
    assert compose == []
