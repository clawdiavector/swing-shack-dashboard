"""L4 unified inbox bearer auth — list + approve/reject/edit; stubs stay session-only."""

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
def inbox_bearer_app(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    for mod in list(sys.modules):
        if (
            mod == "app"
            or mod.startswith("_lib.jobs")
            or mod.startswith("_lib.")
            or mod == "_lib.ops_layers"
            or mod == "_lib.unified_inbox"
        ):
            del sys.modules[mod]
    import app as app_module

    app_module.COS_JOB_TOKEN = "test-job-token-not-a-secret"
    app_module._GIT_SYNC_DONE = True
    client = app_module.app.test_client(cos_anon=True)
    session = app_module.app.test_client()
    return client, session, app_module, tmp_path


def _auth():
    return {"Authorization": "Bearer test-job-token-not-a-secret"}


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


def test_unified_list_anon_401(inbox_bearer_app):
    client, _, _, tmp_path = inbox_bearer_app
    _seed_draft(tmp_path)
    resp = client.get("/api/inbox/unified?status=all")
    assert resp.status_code == 401
    assert resp.get_json().get("ok") is False


def test_unified_list_bearer_200(inbox_bearer_app):
    client, _, _, tmp_path = inbox_bearer_app
    _seed_draft(tmp_path)
    resp = client.get("/api/inbox/unified?status=all", headers=_auth())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("ok") is True
    assert body.get("schema") == "campaign-os/unified-inbox/v1"
    assert isinstance(body.get("items"), list)


def test_unified_approve_bearer(inbox_bearer_app):
    client, _, _, tmp_path = inbox_bearer_app
    cid, aid = _seed_draft(tmp_path)
    item_id = f"draft_asset:{cid}:{aid}"
    resp = client.post(
        f"/api/inbox/unified/{item_id}/approve",
        headers=_auth(),
        json={"editor": "foreman"},
    )
    assert resp.status_code == 200
    assert resp.get_json().get("ok") is True
    saved = json.loads((tmp_path / "campaign-data.json").read_text(encoding="utf-8"))
    assert saved["campaigns"][cid]["assets"][aid]["approvalStatus"] == "approved"


def test_unified_list_session_ok(inbox_bearer_app):
    _, session, _, tmp_path = inbox_bearer_app
    _seed_draft(tmp_path)
    resp = session.get("/api/inbox/unified?status=all")
    assert resp.status_code == 200
    assert resp.get_json().get("ok") is True


def test_unified_approve_session_ok(inbox_bearer_app):
    _, session, _, tmp_path = inbox_bearer_app
    cid, aid = _seed_draft(tmp_path)
    item_id = f"draft_asset:{cid}:{aid}"
    resp = session.post(
        f"/api/inbox/unified/{item_id}/approve",
        json={"editor": "christelle"},
    )
    assert resp.status_code == 200
    assert resp.get_json().get("ok") is True


def test_unified_stubs_still_session_only(inbox_bearer_app):
    client, _, _, _ = inbox_bearer_app
    for path in ("/api/inbox/unified/postiz-reschedule", "/api/inbox/unified/reorder"):
        resp = client.post(path, headers=_auth(), json={})
        assert resp.status_code == 401


def test_bad_bearer_token_401(inbox_bearer_app):
    client, _, _, tmp_path = inbox_bearer_app
    _seed_draft(tmp_path)
    resp = client.get(
        "/api/inbox/unified",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401
