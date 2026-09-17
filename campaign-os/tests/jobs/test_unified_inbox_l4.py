"""L4 unified inbox: list/approve/reject/edit + session gate + stubs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


@pytest.fixture()
def inbox_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "1.00")
    for mod in list(sys.modules):
        if (
            mod == "app"
            or mod.startswith("_lib.jobs")
            or mod.startswith("_lib.")
            or mod == "_lib.ops_layers"
            or mod == "_lib.unified_inbox"
            or mod == "_lib.intelligence"
            or mod == "_lib.marketing_calendar"
            or mod == "_lib.publish_sandbox"
        ):
            del sys.modules[mod]
    import app as app_module
    from _lib.jobs import cooldown as cd

    cd.reset_for_tests()
    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    app_module._GIT_SYNC_DONE = True
    client = app_module.app.test_client()
    return client, app_module, tmp_path


def _seed_draft(tmp_path: Path) -> tuple[str, str]:
    data = {
        "campaigns": {
            "camp-test": {
                "identity": {"name": "Test Campaign", "brand": "stick"},
                "assets": {
                    "asset-1": {
                        "name": "Draft caption",
                        "caption": "Hello world",
                        "approvalStatus": "draft",
                        "updatedAt": "2026-09-17T08:00:00Z",
                    }
                },
            }
        }
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")
    return "camp-test", "asset-1"


def test_unified_list_anon_401(inbox_app):
    _, app_module, _ = inbox_app
    anon = app_module.app.test_client(cos_anon=True)
    resp = anon.get("/api/inbox/unified")
    assert resp.status_code == 401
    body = resp.get_json()
    assert body.get("ok") is False


def test_unified_list_schema(inbox_app):
    client, _, tmp_path = inbox_app
    _seed_draft(tmp_path)
    resp = client.get("/api/inbox/unified?status=all")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("schema") == "campaign-os/unified-inbox/v1"
    assert body.get("ok") is True
    assert isinstance(body.get("items"), list)
    types = {i.get("type") for i in body["items"]}
    assert "draft_asset" in types


def test_unified_approve_reject_edit_draft(inbox_app):
    client, _, tmp_path = inbox_app
    cid, aid = _seed_draft(tmp_path)
    item_id = f"draft_asset:{cid}:{aid}"

    edit = client.post(
        f"/api/inbox/unified/{item_id}/edit",
        json={"editor": "christelle", "caption": "Edited caption"},
    )
    assert edit.status_code == 200
    assert edit.get_json().get("ok") is True
    edits = (tmp_path / "human-edits.jsonl").read_text(encoding="utf-8")
    assert "human-edit-signal" in edits

    approve = client.post(
        f"/api/inbox/unified/{item_id}/approve",
        json={"editor": "christelle"},
    )
    assert approve.status_code == 200
    assert approve.get_json().get("ok") is True
    saved = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    assert saved["campaigns"][cid]["assets"][aid]["approvalStatus"] == "approved"

    _seed_draft(tmp_path)
    reject = client.post(
        f"/api/inbox/unified/{item_id}/reject",
        json={"editor": "christelle", "reason": "not on brand"},
    )
    assert reject.status_code == 200
    assert reject.get_json().get("ok") is True
    saved2 = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    assert saved2["campaigns"][cid]["assets"][aid]["approvalStatus"] == "rejected"


def test_unified_stubs_501(inbox_app):
    client, _, _ = inbox_app
    for path in ("/api/inbox/unified/postiz-reschedule", "/api/inbox/unified/reorder"):
        resp = client.post(path, json={})
        assert resp.status_code == 501
        body = resp.get_json()
        assert body.get("stub") is True


def test_layers_l4_counts(inbox_app):
    client, _, tmp_path = inbox_app
    _seed_draft(tmp_path)
    body = client.get("/api/ops/layers").get_json()
    l4 = body["layers"]["L4"]
    assert "pending" in l4
    assert "stale" in l4
    assert "approved_today" in l4
    assert l4.get("inbox_href") == "/?page=review"


def test_unified_inbox_module_counts():
    from _lib.unified_inbox import inbox_counts, list_items

    payload = list_items(status="all")
    assert payload["schema"] == "campaign-os/unified-inbox/v1"
    counts = inbox_counts()
    assert "pending" in counts
    assert counts["verdict"] in {"OK", "LATE", "NEVER"}
