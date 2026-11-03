"""T4 retail campaign generator — plan, layout rotation, job registration."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import calendar_suggestions as cs  # noqa: E402
from _lib import retail_campaign as rc  # noqa: E402
from _lib.archetypes import archetype_by_id  # noqa: E402
from _lib.jobs.registry import JOBS  # noqa: E402


def test_three_swing_shack_product_archetypes_registered():
    for arch_id, layout in rc.ARCHETYPE_TO_LAYOUT.items():
        arch = archetype_by_id("swing-shack", arch_id)
        assert arch, arch_id
        assert arch.get("template_pack")
        assert arch.get("product_layout") == layout
        assert arch.get("renderer") == "product_post"


def test_stock_suggestions_call_layout_for(monkeypatch):
    monkeypatch.setattr(rc, "product_layout_history", lambda brand: ["type-hero", "one-hero"])
    items = cs.stock_items(
        "swing-shack",
        "2026-11",
        [{"name": "Titleist Pro V1", "reason": "heavy", "idea": "Ball fitting"}],
        {},
        [],
        [],
        date(2026, 11, 3),
    )
    assert len(items) == 1
    assert items[0]["product_layout"] == "pick-yours"
    assert items[0]["archetype_id"] == "ss-product-pick-yours"


def test_plan_week_reports_photo_gap(monkeypatch):
    monkeypatch.setattr(rc, "_stock_lines", lambda brand: [{"name": "Mystery Widget", "idea": "", "status": "heavy"}])
    monkeypatch.setattr(rc, "_approved_photo_entries", lambda brand: {})
    plan = rc.plan_week("swing-shack", start=date(2026, 11, 3), days=2)
    assert plan["gaps"] == [{"product": "Mystery Widget", "reason": "no_approved_photo"}]
    assert plan["posts"] == []


def test_run_without_lodge_writes_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        rc,
        "plan_week",
        lambda brand, start=None, days=rc.WEEKDAY_COUNT: {
            "ok": True,
            "brand_id": brand,
            "posts": [],
            "gaps": [],
            "planned": 0,
        },
    )
    out = rc.run(brand="swing-shack", today=date(2026, 11, 3), lodge=False)
    assert out["ok"] is True
    assert "lodge" not in out
    path = tmp_path / "brands" / "swing-shack" / "retail-campaign" / "latest.json"
    assert path.is_file()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["brand_id"] == "swing-shack"


def test_retail_campaign_job_registered():
    spec = JOBS.get("retail_campaign")
    assert spec is not None
    assert spec.brand_mode == "per_brand"
    assert "swing-shack" in spec.brands
