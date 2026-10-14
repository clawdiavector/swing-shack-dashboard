"""Week board gap state + manual enqueue + recheck."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from tests.jobs.test_layer5_create import _purge_modules, _seed_brands  # noqa: E402


@pytest.fixture()
def inbox_gap_env(monkeypatch, tmp_path):
    import shutil

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    bundled = REPO / "data"
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(bundled))
    import shutil

    shutil.copytree(
        bundled / "brand-directory" / "stick",
        tmp_path / "brand-directory" / "stick",
        dirs_exist_ok=True,
        ignore_dangling_symlinks=True,
    )
    _purge_modules()
    _seed_brands(tmp_path, brand="stick", campaign_id="camp-stick")
    from _lib import marketing_calendar as mc

    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    mc._CALENDAR_DIR = cal_dir
    mc._CALENDAR_DIR_READY = True
    rec = {
        "calendar_id": "cal-week-gap",
        "brand_id": "stick",
        "status": "approved",
        "title": "Stale image gap",
        "post_type": "mystery",
        "event_date": "2026-10-15",
        "primary_channel": "instagram",
    }
    (cal_dir / "stick.jsonl").write_text(json.dumps(rec) + "\n", encoding="utf-8")
    item_id = "calendar_candidate:stick:cal-week-gap"
    camp = json.loads((tmp_path / "campaign-data.json").read_text())
    camp["campaigns"]["camp-stick"]["assets"]["asset-gap"] = {
        "caption": "Hello",
        "approvalStatus": "draft",
        "platform": "instagram",
        "image_url": "/draft-assets/images/stick/stale-random.png",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(camp), encoding="utf-8")
    draft_dir = tmp_path / "draft-assets"
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "asset-gap.json").write_text(
        json.dumps(
            {
                "action": "draft_caption",
                "asset_id": "asset-gap",
                "source_inbox_item_id": item_id,
                "inbox_item_id": item_id,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "agent-queue.json").write_text(
        json.dumps({"schema": "campaign-os/agent-queue/v1", "generated_at": "2026-10-12T00:00:00Z", "rows": []}),
        encoding="utf-8",
    )
    import app as app_module

    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    app_module._GIT_SYNC_DONE = True
    client = app_module.app.test_client()
    return client, tmp_path, item_id


def test_week_board_gap_state(inbox_gap_env):
    client, _tmp, _item = inbox_gap_env
    resp = client.get("/api/inbox/week?brand=stick&start=2026-10-15&days=1")
    assert resp.status_code == 200
    payload = resp.get_json()
    posts = payload["days_list"][0]["posts"]
    assert len(posts) == 1
    post = posts[0]
    assert post["state"] == "gap"
    assert post.get("image_url") is None
    assert post.get("gap", {}).get("label")
    assert payload.get("gaps") and payload["gaps"][0]["count"] >= 1


def test_manual_enqueue_refuses_gap(inbox_gap_env):
    client, tmp_path, item_id = inbox_gap_env
    auth = {"Authorization": "Bearer test-job-token-not-a-secret"}
    resp = client.post("/api/ops/queue", json={"item_id": item_id, "action": "draft_photo"}, headers=auth)
    assert resp.status_code == 409
    assert resp.get_json().get("gap")

    draft_id = "camp-stick:asset-gap"
    resp2 = client.post(f"/api/drafts/{draft_id}/regenerate", json={"note": "fix photo"}, headers=auth)
    assert resp2.status_code == 409
    assert resp2.get_json().get("gap")


def test_recheck_visual(inbox_gap_env):
    client, tmp_path, item_id = inbox_gap_env
    auth = {"Authorization": "Bearer test-job-token-not-a-secret"}
    resp = client.post(f"/api/inbox/{item_id}/recheck-visual", headers=auth)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("decision", {}).get("status") == "gap"
    assert body.get("enqueued") == []

    brand_dir = tmp_path / "brand-directory" / "stick" / "visual-spec" / "archetypes.json"
    doc = json.loads(brand_dir.read_text())
    selection = doc.setdefault("selection", {})
    rules = list(selection.get("rules") or [])
    rules.append({"when": {"post_type_in": ["mystery"]}, "use": "stick-brand-statement"})
    selection["rules"] = rules
    brand_dir.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    _purge_modules()
    import app as app_module

    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    client2 = app_module.app.test_client()
    resp2 = client2.post(f"/api/inbox/{item_id}/recheck-visual", headers=auth)
    assert resp2.status_code == 200
    body2 = resp2.get_json()
    assert body2.get("decision", {}).get("status") == "trusted"
    assert "compose_post" in (body2.get("enqueued") or [])
    resp3 = client2.post(f"/api/inbox/{item_id}/recheck-visual", headers=auth)
    assert "compose_post" not in (resp3.get_json().get("enqueued") or [])
