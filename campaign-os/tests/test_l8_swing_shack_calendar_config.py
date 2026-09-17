"""tL8-1 — swing-shack calendar_config.json contract tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

STICK_COLOURS = {"#FF3D00", "#d4a849", "#5b9bd5"}


@pytest.fixture()
def mc_module(monkeypatch, tmp_path):
    repo_brand = CAMPAIGN_OS.parent / "data" / "brand-directory"
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(repo_brand.parent))
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("_lib"):
            del sys.modules[mod]
    import _lib.marketing_calendar as mc

    return mc


def test_swing_shack_config_loads_configured(mc_module):
    cfg = mc_module.load_brand_config("swing-shack")
    assert cfg["configured"] is True
    pillar_ids = [p["pillar_id"] for p in cfg["pillars"]]
    assert pillar_ids
    assert len(pillar_ids) == len(set(pillar_ids))


def test_major_retail_lead_time_honoured(mc_module):
    cfg = mc_module.load_brand_config("swing-shack")
    template = mc_module._resolve_lead_time_template(cfg, "major_retail")
    assert template["research_start"] == 90
    assert template != mc_module.DEFAULT_LEAD_TIME_TEMPLATE["major_retail"] or (
        cfg["lead_time_rules"]["major_retail"]["research_start"] == 90
    )


def test_north_star_placeholders_marked_non_canonical(mc_module):
    cfg = mc_module.load_brand_config("swing-shack")
    for pillar in cfg["pillars"]:
        prov = pillar["north_star_target"]["source_provenance"]
        assert "canonical=false" in prov
        assert pillar["north_star_target"]["daily_volume"] is None


def test_pillar_colours_distinct_from_stick(mc_module):
    ss_colours = {p["colour"] for p in mc_module.load_brand_config("swing-shack")["pillars"]}
    assert ss_colours.isdisjoint(STICK_COLOURS)


def test_gate_pass_pillar_with_real_pillar(mc_module):
    cfg = mc_module.load_brand_config("swing-shack")
    pillar_id = cfg["pillars"][0]["pillar_id"]
    ok, _reason = mc_module._gate_pass_pillar({"pillars": [pillar_id]}, cfg)
    assert ok is True


def test_calendar_section_returns_200(cos_app):
    resp = cos_app.test_client().get("/api/calendar/section/swing-shack")
    assert resp.status_code == 200
    assert "calendar_config.json configured yet" not in resp.get_data(as_text=True)
