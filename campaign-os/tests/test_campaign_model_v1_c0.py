"""Campaign Model v1 — C0 schema, origin propagation, migration."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture()
def c0_data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "intelligence" / "marketing-calendar").mkdir(parents=True)
    (tmp_path / "brand-directory" / "stick").mkdir(parents=True)
    cfg = {
        "brand_id": "stick",
        "timezone": "Africa/Johannesburg",
        "pillars": [
            {
                "pillar_id": "stick-retail",
                "name": "Retail",
                "process": "standard",
                "enabled": True,
                "lanes": ["apparel"],
            }
        ],
    }
    (tmp_path / "brand-directory" / "stick" / "calendar_config.json").write_text(
        json.dumps(cfg),
        encoding="utf-8",
    )
    yield tmp_path


def test_validate_origin_and_process_rejects_bad_kind():
    from _lib.campaigns import validate_origin, validate_process

    with pytest.raises(ValueError, match="origin.kind"):
        validate_origin({"kind": "unknown", "actor": "x", "ref": "y"})
    with pytest.raises(ValueError, match="process"):
        validate_process("cook")


def test_enrich_never_invents_campaign_id(c0_data):
    from _lib.campaigns import enrich_record_provenance

    out = enrich_record_provenance(
        {"pillars": ["stick-retail"], "created_by": "holiday_inject", "source_origin": "deterministic_calendar"},
        "stick",
    )
    assert out["pillar_id"] == "stick-retail"
    assert "campaign_id" not in out or out.get("campaign_id") is None
    assert out["origin"]["kind"] == "holiday"


def test_inbox_meta_slim_carries_origin(c0_data):
    from _lib.marketing_calendar import add_candidate
    from _lib.unified_inbox import list_items

    add_candidate(
        "stick",
        {
            "type": "moment",
            "title": "Test candidate",
            "pillars": ["stick-retail"],
            "created_by": "manual",
            "origin": {"kind": "operator", "actor": "manual", "ref": "desk"},
        },
        initial_status="candidate",
    )
    payload = list_items(status="all", brand="stick", item_type="calendar_candidate")
    items = payload.get("items") or []
    assert len(items) == 1
    slim = items[0].get("meta_slim") or {}
    assert slim.get("origin", {}).get("kind") == "operator"
    assert slim.get("pillar_id") == "stick-retail"


def test_origin_propagation_record_to_asset_to_receipt(c0_data):
    from _lib.campaigns import write_create_payload
    from _lib.jobs.layer5.draft_assets import _write_draft
    from _lib import publish_sandbox

    item_id = "calendar_candidate:stick:cal-stick-moment-test1"
    fields = {
        "pillar_id": "stick-retail",
        "campaign_id": "stick-retail-always-on",
        "lane": "apparel",
        "origin": {"kind": "cadence", "actor": "test", "ref": "cadence:1"},
        "process": "standard",
        "ref": f"inbox/{item_id}",
    }
    write_create_payload(item_id=item_id, fields=fields)
    (c0_data / "brands.json").write_text(
        json.dumps(
            {
                "brands": {
                    "stick": {
                        "id": "stick",
                        "campaign_ids": [],
                        "publish_channels": ["instagram", "facebook"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (c0_data / "campaign-data.json").write_text(json.dumps({"campaigns": {}}), encoding="utf-8")

    asset_id = _write_draft(
        brand_id="stick",
        caption="hello",
        platform="instagram",
        source_item_id=item_id,
        sidecar={"title": "Test"},
    )
    sidecar = json.loads((c0_data / "draft-assets" / f"{asset_id}.json").read_text(encoding="utf-8"))
    assert sidecar.get("origin", {}).get("kind") == "cadence"
    assert sidecar.get("campaign_id") == "stick-retail-always-on"

    row = publish_sandbox.enqueue_for_primary_channel(
        brand_id="stick",
        caption_preview="hello",
        inbox_item_id=item_id,
        asset_id=asset_id,
    )
    assert row
    assert row[0].get("origin", {}).get("kind") == "cadence"
    row[0]["human_approved"] = True
    receipt, err = publish_sandbox.dispatch_item(row[0])
    assert err is None
    assert receipt.get("origin", {}).get("kind") == "cadence"
    assert receipt.get("campaign_id") == "stick-retail-always-on"


def test_migration_dry_run_on_fixture_copy(c0_data):
    import importlib.util

    from _lib.marketing_calendar import _calendar_path

    cal = _calendar_path("stick")
    rec = {
        "calendar_id": "cal-stick-moment-broken1",
        "title": "Broken tournament",
        "pillars": ["stick-fitting"],
        "created_by": "hermes-scout",
        "source_origin": "external",
    }
    cal.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    repo = Path(__file__).resolve().parents[2]
    mig_path = repo / "scripts" / "migrate_campaign_model_v1.py"
    spec = importlib.util.spec_from_file_location("migrate_campaign_model_v1", mig_path)
    mig = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mig)

    report = mig.run_migration(dry_run=True)
    stick_changes = report["brands"].get("stick") or []
    actions = {c.get("action") for c in stick_changes}
    assert "set_type_moment" in actions or any(
        c.get("action") == "backfill_origin_legacy" for c in stick_changes
    )
    assert "create_campaign" in actions or "set_default_campaign_id" in actions
