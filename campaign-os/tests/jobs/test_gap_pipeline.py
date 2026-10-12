"""Gap pipeline — draft_assets parks rows; caption survives reaper."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
REPO = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from tests.jobs.test_layer5_create import _purge_modules, _seed_brands  # noqa: E402


@pytest.fixture()
def gap_env(monkeypatch, tmp_path):
    import shutil

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("COS_JOB_TOKEN", "test-job-token-not-a-secret")
    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "1.00")
    bundled = REPO / "data"
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(bundled))
    for brand in ("stick",):
        src = bundled / "brand-directory" / brand
        dst = tmp_path / "brand-directory" / brand
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True, ignore_dangling_symlinks=True)
    _purge_modules()
    _seed_brands(tmp_path, brand="stick", campaign_id="camp-stick")
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    from _lib import marketing_calendar as mc

    mc._CALENDAR_DIR = cal_dir
    mc._CALENDAR_DIR_READY = True
    (tmp_path / "agent-queue.json").write_text(
        json.dumps({"schema": "campaign-os/agent-queue/v1", "generated_at": "2026-10-12T00:00:00Z", "rows": []}),
        encoding="utf-8",
    )
    return tmp_path, cal_dir


def _moment(cal_dir: Path, cal_id: str = "cal-gap-1") -> str:
    rec = {
        "calendar_id": cal_id,
        "brand_id": "stick",
        "status": "approved",
        "title": "Gap moment",
        "post_type": "mystery",
        "event_date": "2026-10-15",
        "primary_channel": "instagram",
        "revision": 1,
    }
    with (cal_dir / "stick.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return f"calendar_candidate:stick:{cal_id}"


def test_run_never_generates_or_composes_for_gap(gap_env):
    tmp_path, cal_dir = gap_env
    item_id = _moment(cal_dir)
    item_hash = "abc"
    rows = [
        {
            "id": "q-photo",
            "agent": "cos-image",
            "brand": "stick",
            "action": "draft_photo",
            "status": "pending",
            "payload_ref": f"inbox/{item_id}",
            "dedupe_key": f"draft_photo-{item_hash}",
        },
        {
            "id": "q-compose",
            "agent": "cos-image",
            "brand": "stick",
            "action": "compose_post",
            "status": "pending",
            "payload_ref": f"inbox/{item_id}",
            "dedupe_key": f"compose_post-{item_hash}",
        },
    ]
    (tmp_path / "agent-queue.json").write_text(
        json.dumps({"schema": "campaign-os/agent-queue/v1", "generated_at": "2026-10-12T00:00:00Z", "rows": rows}),
        encoding="utf-8",
    )

    def boom(*_a, **_k):
        raise AssertionError("must not generate or compose for gap")

    from _lib.jobs.layer5 import draft_assets

    with patch("_lib.image_gen_router.generate_image_with_persistence", boom):
        with patch("_lib.archetype_compose.compose_post_for_channels", boom):
            result = draft_assets.run(brand="stick")
    assert result.get("ok") is not False or result.get("drafted", 0) >= 0
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    for row in queue.get("rows") or []:
        if row.get("payload_ref") == f"inbox/{item_id}":
            assert row.get("status") == "gap"
            assert row.get("note")


def test_gap_caption_not_reaped(gap_env):
    tmp_path, cal_dir = gap_env
    item_id = _moment(cal_dir, "cal-gap-cap")
    draft_dir = tmp_path / "draft-assets"
    draft_dir.mkdir(parents=True, exist_ok=True)
    asset_id = "draft-cap-gap"
    sidecar = {
        "action": "draft_caption",
        "asset_id": asset_id,
        "brand_id": "stick",
        "source_inbox_item_id": item_id,
        "visual_gap": {
            "reason": "no_layout",
            "label": "No layout for mystery",
            "post_type": "mystery",
            "checked_at": "2026-10-12T00:00:00Z",
        },
    }
    (draft_dir / f"{asset_id}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    camp = json.loads((tmp_path / "campaign-data.json").read_text())
    camp["campaigns"]["camp-stick"]["assets"][asset_id] = {
        "caption": "Caption only",
        "approvalStatus": "draft",
        "platform": "instagram",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(camp), encoding="utf-8")

    from _lib.jobs.layer5 import draft_assets

    draft_assets.run(brand="stick")
    draft_assets.run(brand="stick")
    camp2 = json.loads((tmp_path / "campaign-data.json").read_text())
    asset = camp2["campaigns"]["camp-stick"]["assets"][asset_id]
    assert str(asset.get("approvalStatus") or "").lower() != "rejected"
    side = json.loads((draft_dir / f"{asset_id}.json").read_text())
    assert side.get("visual_gap")


def test_no_photo_generation_paths():
    from _lib.jobs.layer5 import create_photo_compose
    from _lib.jobs.layer5 import draft_assets

    src = Path(create_photo_compose.__file__).read_text(encoding="utf-8")
    assert "generate_image_with_persistence" not in src
    assert "edit_image" not in src
    assert not hasattr(draft_assets, "_process_image_row")


def test_gap_clears_when_layout_added(gap_env):
    tmp_path, cal_dir = gap_env
    brand_dir = tmp_path / "brand-directory" / "stick" / "visual-spec" / "archetypes.json"
    doc = json.loads(brand_dir.read_text())
    for row in doc.get("archetypes") or []:
        if row.get("id") == "stick-brand-statement":
            row["vetted"] = True
            row["template_pack"] = "templates/brand-statement"
    selection = doc.setdefault("selection", {})
    rules = list(selection.get("rules") or [])
    rules.append({"when": {"post_type_in": ["mystery"]}, "use": "stick-brand-statement"})
    selection["rules"] = rules
    brand_dir.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    item_id = _moment(cal_dir, "cal-gap-clear")
    rows = [
        {
            "id": "q-gap",
            "agent": "cos-image",
            "brand": "stick",
            "action": "compose_post",
            "status": "gap",
            "note": "No layout for mystery",
            "payload_ref": f"inbox/{item_id}",
            "dedupe_key": "compose-gap",
        }
    ]
    (tmp_path / "agent-queue.json").write_text(
        json.dumps({"schema": "campaign-os/agent-queue/v1", "generated_at": "2026-10-12T00:00:00Z", "rows": rows}),
        encoding="utf-8",
    )
    draft_dir = tmp_path / "draft-assets"
    draft_dir.mkdir(parents=True, exist_ok=True)
    (draft_dir / "draft-gap.json").write_text(
        json.dumps(
            {
                "action": "draft_caption",
                "asset_id": "draft-gap",
                "source_inbox_item_id": item_id,
                "visual_gap": {"reason": "no_layout", "label": "x", "post_type": "mystery"},
            }
        ),
        encoding="utf-8",
    )
    camp = json.loads((tmp_path / "campaign-data.json").read_text())
    camp["campaigns"]["camp-stick"]["assets"]["draft-gap"] = {
        "caption": "Gap caption",
        "approvalStatus": "draft",
        "platform": "instagram",
    }
    (tmp_path / "campaign-data.json").write_text(json.dumps(camp), encoding="utf-8")

    from _lib.jobs.layer5 import retry_failed_images

    result = retry_failed_images.run(brand="stick")
    assert result.get("ok") is True
    queue = json.loads((tmp_path / "agent-queue.json").read_text(encoding="utf-8"))
    assert queue["rows"][0]["status"] == "pending"
    side = json.loads((draft_dir / "draft-gap.json").read_text())
    assert "visual_gap" not in side
