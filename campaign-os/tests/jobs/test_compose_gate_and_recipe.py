"""Compose gate deferral, krea poll compose enqueue, recipe cache."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


@pytest.fixture()
def tmp_data(monkeypatch, tmp_path):
    import shutil

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    bundled = CAMPAIGN_OS.parent / "data"
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(bundled))
    src = bundled / "brand-directory" / "stick"
    dst = tmp_path / "brand-directory" / "stick"
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    return tmp_path


def _seed_approved_calendar(tmp_path: Path, item_id: str) -> None:
    from _lib import marketing_calendar as mc

    _, brand, cal_id = item_id.split(":", 2)
    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    mc._CALENDAR_DIR = cal_dir
    mc._CALENDAR_DIR_READY = True
    (cal_dir / f"{brand}.jsonl").write_text(
        json.dumps(
            {
                "calendar_id": cal_id,
                "status": "approved",
                "title": "Test",
                "pillar_id": "stick-coaching",
                "post_type": "coaching_promo",
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_compose_deferred_until_photo_waiting(tmp_data, monkeypatch):
    from _lib.jobs.layer5 import draft_assets as da

    item_id = "calendar_candidate:stick:evt-1"
    _seed_approved_calendar(tmp_data, item_id)
    rows = [
        {
            "id": "q1",
            "status": "pending",
            "action": "draft_photo",
            "brand": "stick",
            "payload_ref": f"inbox/{item_id}",
        },
        {
            "id": "q2",
            "status": "pending",
            "action": "compose_post",
            "brand": "stick",
            "payload_ref": f"inbox/{item_id}",
        },
    ]
    (tmp_data / "agent-queue.json").write_text(
        json.dumps({"schema": "campaign-os/agent-queue/v1", "rows": rows}),
        encoding="utf-8",
    )
    (tmp_data / "draft-assets").mkdir(exist_ok=True)
    (tmp_data / "brands.json").write_text(json.dumps({"brands": {"stick": {"id": "stick", "campaign_ids": ["c1"]}}}), encoding="utf-8")
    (tmp_data / "campaign-data.json").write_text(json.dumps({"campaigns": {"c1": {"identity": {"brand": "stick"}, "assets": {}}}}), encoding="utf-8")

    compose_called = {"n": 0}

    def fake_photo(row, **kwargs):
        row["status"] = "waiting"
        return None, None

    def fake_compose(*args, **kwargs):
        compose_called["n"] += 1
        return None, None

    ctx = MagicMock(lineage={"calendar": {}}, aspect="1024x1024", job="x", platform_spec={})
    monkeypatch.setattr(da, "build_image_draft_context", lambda *a, **k: ctx)
    monkeypatch.setattr(da, "_find_caption_draft_for_item", lambda _i: ("cap-1", "caption"))
    monkeypatch.setattr(da, "_backfill_draft_names", lambda *a, **k: 0)
    monkeypatch.setattr(da, "_reject_caption_only_drafts", lambda *a, **k: 0)
    monkeypatch.setattr(da, "_retire_orphan_queue_rows", lambda *a, **k: 0)

    with patch(
        "_lib.jobs.layer5.create_photo_compose.process_draft_photo_row",
        fake_photo,
    ), patch(
        "_lib.jobs.layer5.create_photo_compose.process_compose_post_row",
        fake_compose,
    ):
        out = da.run(brand="stick")

    assert compose_called["n"] == 0
    assert out.get("ok") is True


def test_krea_finalize_enqueues_compose(tmp_data, monkeypatch):
    from _lib.jobs.layer5 import krea_poll_draft_images as poll

    item_id = "calendar_candidate:stick:evt-2"
    rows = [
        {
            "id": "w1",
            "status": "waiting",
            "action": "draft_photo",
            "brand": "stick",
            "payload_ref": f"inbox/{item_id}",
        }
    ]
    (tmp_data / "agent-queue.json").write_text(
        json.dumps({"schema": "campaign-os/agent-queue/v1", "rows": rows}),
        encoding="utf-8",
    )

    png = tmp_data / "draft-assets" / "images" / "stick" / "images" / "krea-stick-job1.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    png.write_bytes(b"\x89PNG\r\n\x1a\n")

    monkeypatch.setattr(
        poll.image_jobs_state,
        "get_entry",
        lambda _i: {"job_id": "job1", "brand": "stick", "size": "1024x1024", "est_usd": 0.04},
    )
    monkeypatch.setattr(poll.image_jobs_state, "is_settled", lambda _i: False)
    monkeypatch.setattr(poll.image_jobs_state, "mark_settled", lambda _i: None)
    monkeypatch.setattr(poll.image_jobs_state, "drop_entry", lambda _i: None)
    monkeypatch.setattr(poll, "_moment_has_image", lambda *a: False)
    monkeypatch.setattr(poll, "_moment_has_composed", lambda *a: False)
    monkeypatch.setattr(poll, "_finalize_draft_from_poll", lambda **k: "draft-abc")

    enqueued = {"n": 0}
    from _lib import l5_create_enqueue

    def fake_enqueue(**kwargs):
        enqueued["n"] += 1
        if kwargs.get("rows") is not None:
            kwargs["rows"].append({"action": "compose_post", "status": "pending"})
        return True

    monkeypatch.setattr(l5_create_enqueue, "enqueue_compose_post_for_moment", fake_enqueue)

    row = rows[0]
    poll._complete_row(
        row,
        brand_id="stick",
        item_id=item_id,
        job_entry={"job_id": "job1", "size": "1024x1024", "est_usd": 0.04},
        png_path=png,
    )
    assert enqueued["n"] == 1
    assert row["status"] == "done"


def test_create_actions_lodge_then_image_gen_recipe(tmp_data):
    from _lib import marketing_calendar as mc
    from _lib.l5_create_enqueue import create_actions_for_moment

    item_id = "calendar_candidate:stick:svc-hero-1"
    cal_dir = tmp_data / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    mc._CALENDAR_DIR = cal_dir
    mc._CALENDAR_DIR_READY = True
    (cal_dir / "stick.jsonl").write_text(
        json.dumps(
            {
                "calendar_id": "svc-hero-1",
                "status": "approved",
                "title": "Club fitting hero",
                "pillars": ["stick-fitting"],
                "post_type": "service_hero",
                "template_id": "stick-service-hero-v1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lodge = create_actions_for_moment("stick", item_id, phase="lodge")
    assert lodge == ["draft_caption"]
    image = create_actions_for_moment("stick", item_id, phase="image")
    assert "draft_gen_slots" in image
    assert "compose_post" in image


def test_recipe_cache_hit(tmp_data, monkeypatch):
    from _lib import template_recipe as tr

    brand = "stick"
    pack = "templates/coaching-poster-v1"
    recipe = tr.load_recipe_json(brand, pack)
    assert recipe and recipe.get("schema") == tr.RECIPE_SCHEMA

    bucket = tr.cache_bucket_key(
        brand_id=brand,
        recipe=recipe,
        item_id="calendar_candidate:stick:x",
        pillar_id="stick-coaching",
    )
    path = tr.cache_file_path(brand_id=brand, template_pack=pack, slot_id="background", bucket_hash=bucket)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"cached")
    tr.write_cache_entry(path, brand_id=brand, slot_id="background", bucket_hash=bucket)
    assert tr.cache_is_fresh(path, policy_key="coaching_service_7d")

    bucket2 = tr.cache_bucket_key(
        brand_id=brand,
        recipe=recipe,
        item_id="calendar_candidate:stick:promo-1",
        pillar_id="stick-coaching",
    )
    path2 = tr.cache_file_path(brand_id=brand, template_pack=pack, slot_id="background", bucket_hash=bucket2)
    assert path2 == path or path2.parent == path.parent
    assert tr.cache_is_fresh(path, policy_key="coaching_service_7d")


def test_recipe_cache_ttl_expired(tmp_data):
    from _lib import template_recipe as tr
    import os
    import time

    brand = "stick"
    pack = "templates/coaching-poster-v1"
    recipe = tr.load_recipe_json(brand, pack)
    bucket = tr.cache_bucket_key(brand_id=brand, recipe=recipe, item_id="calendar_candidate:stick:old")
    path = tr.cache_file_path(brand_id=brand, template_pack=pack, slot_id="background", bucket_hash=bucket)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"old")
    old = time.time() - (8 * 86400)
    os.utime(path, (old, old))
    assert tr.cache_is_fresh(path, policy_key="coaching_service_7d") is False


def test_service_hero_selection():
    from _lib.archetypes import select_archetype
    import _lib.marketing_calendar as mc

    def fake_records(brand_id):
        return [
            {
                "calendar_id": "hero-1",
                "status": "approved",
                "post_type": "service_hero",
                "pillar_id": "stick-coaching",
                "title": "Hero",
            }
        ]

    orig = mc.canonical_records
    mc.canonical_records = fake_records
    try:
        arch = select_archetype("stick", "calendar_candidate:stick:hero-1")
        assert arch.get("id") == "stick-service-hero-v1"
    finally:
        mc.canonical_records = orig
