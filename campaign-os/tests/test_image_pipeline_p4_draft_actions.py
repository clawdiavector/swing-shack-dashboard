"""P4 — /api/drafts/<id>/regenerate|recompose|swap and draft_asset reject reason."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def _purge() -> None:
    for mod in list(sys.modules):
        if mod.startswith("_lib.") or mod == "app":
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


def _seed_draft(tmp_path: Path, *, with_photos: bool = True, gbp_sibling: bool = False) -> str:
    brand = "stick"
    campaign_id = "camp-stick"
    asset_id = "asset-main"
    gbp_id = "asset-gbp"
    moment_id = "calendar_candidate:stick:cal-1"
    item_id = f"draft_asset:{campaign_id}:{asset_id}"

    (tmp_path / "brands.json").write_text(
        json.dumps({"brands": {brand: {"id": brand, "campaign_ids": [campaign_id]}}}),
        encoding="utf-8",
    )
    data = {
        "campaigns": {
            campaign_id: {
                "identity": {"name": "T", "brand": brand},
                "assets": {
                    asset_id: {
                        "name": "Main",
                        "caption": "Headline line\nBody\nCTA here",
                        "approvalStatus": "pending",
                        "platform": "instagram",
                    },
                    gbp_id: {
                        "name": "GBP",
                        "caption": "GBP body",
                        "approvalStatus": "pending",
                        "platform": "gbp",
                    },
                },
            }
        }
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(data), encoding="utf-8")

    draft_dir = tmp_path / "draft-assets"
    draft_dir.mkdir(parents=True, exist_ok=True)
    img_a = draft_dir / "images" / "a.png"
    img_b = draft_dir / "images" / "b.png"
    img_a.parent.mkdir(parents=True, exist_ok=True)
    img_a.write_bytes(b"\x89PNG\r\n\x1a\n" + b"a" * 40)
    img_b.write_bytes(b"\x89PNG\r\n\x1a\n" + b"b" * 40)

    sidecar = {
        "asset_id": asset_id,
        "brand_id": brand,
        "source_inbox_item_id": moment_id,
        "action": "compose_post",
        "photo_candidates": [
            {"index": 0, "path": str(img_a), "url": "/u/a.png"},
            {"index": 1, "path": str(img_b), "url": "/u/b.png"},
        ],
        "qc": {"verdict": "pass", "selected": 0, "candidates": []},
    }
    if gbp_sibling:
        sidecar["composed"] = {"instagram": "/u/ig.png", "gbp": "/u/gbp.png"}
    (draft_dir / f"{asset_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    (draft_dir / f"{gbp_id}.json").write_text(
        json.dumps(
            {
                "asset_id": gbp_id,
                "brand_id": brand,
                "source_inbox_item_id": moment_id,
                "action": "draft_gbp",
            }
        ),
        encoding="utf-8",
    )

    if with_photos:
        pass
    (tmp_path / "agent-queue.json").write_text(json.dumps({"rows": []}), encoding="utf-8")
    return item_id


def test_regenerate_at_cap_returns_409(app_client, monkeypatch):
    client, tmp_path, headers = app_client
    item_id = _seed_draft(tmp_path)
    from _lib import ops_layers

    monkeypatch.setattr(ops_layers, "brand_images_today", lambda _b: {"images_today": 2, "cap": 2, "at_cap": True})
    rv = client.post(f"/api/drafts/{item_id}/regenerate", headers=headers, json={"note": "fix logo"})
    assert rv.status_code == 409
    body = rv.get_json()
    assert body.get("at_cap") is True
    assert body.get("brand_id") == "stick"


def test_regenerate_enqueues_draft_photo(app_client, monkeypatch):
    client, tmp_path, headers = app_client
    item_id = _seed_draft(tmp_path)
    from _lib import ops_layers

    monkeypatch.setattr(ops_layers, "brand_images_today", lambda _b: {"images_today": 0, "cap": 2, "at_cap": False})
    rv = client.post(f"/api/drafts/{item_id}/regenerate", headers=headers, json={"note": "darker background"})
    assert rv.status_code == 200
    assert "draft_photo" in (rv.get_json().get("enqueued") or [])
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    actions = [r.get("action") for r in queue.get("rows") or []]
    assert "draft_photo" in actions
    sidecar = json.loads((tmp_path / "draft-assets" / "asset-main.json").read_text(encoding="utf-8"))
    assert sidecar.get("review_regenerate_note") == "darker background"
    assert "composed" not in sidecar


def test_recompose_no_provider_call(app_client, tmp_path):
    client, _, headers = app_client
    item_id = _seed_draft(tmp_path)
    fake_png = b"\x89PNG\r\n\x1a\n" + b"x" * 32
    calls = {"compose": 0, "gen": 0}

    def _fake_compose(**_kwargs):
        calls["compose"] += 1
        return {"instagram": fake_png, "gbp": fake_png}

    def _fail_gen(**_kwargs):
        calls["gen"] += 1
        raise AssertionError("provider must not be called")

    with patch("_lib.archetype_compose.compose_post_for_channels", side_effect=_fake_compose), patch(
        "_lib.image_gen_router.generate_image_with_persistence", side_effect=_fail_gen
    ):
        rv = client.post(
            f"/api/drafts/{item_id}/recompose",
            headers=headers,
            json={"headline": "New hook", "cta": "Book now"},
        )
    assert rv.status_code == 200
    body = rv.get_json()
    assert body.get("ok") is True
    assert "instagram" in (body.get("composed") or {})
    assert calls["compose"] == 1
    assert calls["gen"] == 0


def test_swap_recompose_other_candidate(app_client, tmp_path):
    client, _, headers = app_client
    item_id = _seed_draft(tmp_path)
    seen_index: list[int] = []

    def _fake_compose(**kwargs):
        photo_bytes = kwargs.get("photo_bytes") or b""
        seen_index.append(0 if photo_bytes.endswith(b"a" * 40) else 1)
        return {"instagram": photo_bytes + b"composed"}

    with patch("_lib.archetype_compose.compose_post_for_channels", side_effect=_fake_compose):
        rv = client.post(f"/api/drafts/{item_id}/swap", headers=headers, json={"candidate_index": 1})
    assert rv.status_code == 200
    sidecar = json.loads((tmp_path / "draft-assets" / "asset-main.json").read_text(encoding="utf-8"))
    assert sidecar.get("qc", {}).get("selected") == 1


def test_draft_reject_requires_reason(app_client, tmp_path):
    client, _, headers = app_client
    item_id = _seed_draft(tmp_path)
    rv = client.post(f"/api/inbox/unified/{item_id}/reject", headers=headers, json={})
    assert rv.status_code == 400
    assert "reason" in (rv.get_json().get("error") or "").lower()


def test_draft_reject_records_feedback(app_client, tmp_path):
    client, tmp_path, headers = app_client
    item_id = _seed_draft(tmp_path)
    rv = client.post(
        f"/api/inbox/unified/{item_id}/reject",
        headers=headers,
        json={"reason": "off brand colours"},
    )
    assert rv.status_code == 200
    perf_path = tmp_path / "brand-directory" / "stick" / "feedback" / "image-performance.json"
    assert perf_path.is_file(), "feedback record file missing"
    perf = json.loads(perf_path.read_text(encoding="utf-8"))
    records = perf.get("records") or []
    assert records
    last = records[-1]
    assert last.get("notes") == "off brand colours"
    assert last.get("captured_signal", {}).get("qc_snapshot")


def test_gbp_draft_hidden_when_composed_gbp_on_parent(app_client, tmp_path):
    _purge()
    item_id = _seed_draft(tmp_path, gbp_sibling=True)
    from _lib import unified_inbox

    payload = unified_inbox.list_items(status="pending", item_type="draft_asset", brand="stick")
    ids = {i["meta"]["asset_id"] for i in payload.get("items") or []}
    assert "asset-main" in ids
    assert "asset-gbp" not in ids
    assert item_id  # fixture wires main draft
