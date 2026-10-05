"""Gen background plate prompts — no marketing title in Krea scene."""

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
def tmp_data(monkeypatch, tmp_path):
    import shutil

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    bundled = CAMPAIGN_OS.parent / "data"
    monkeypatch.setenv("BUNDLED_DATA_DIR", str(bundled))
    src = bundled / "brand-directory" / "stick"
    dst = tmp_path / "brand-directory" / "stick"
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    from _lib import marketing_calendar as mc

    cal_dir = tmp_path / "intelligence" / "marketing-calendar"
    cal_dir.mkdir(parents=True, exist_ok=True)
    mc._CALENDAR_DIR = cal_dir
    mc._CALENDAR_DIR_READY = True
    return tmp_path


def test_background_scene_excludes_marketing_title(tmp_data):
    from _lib.jobs.layer5.draft_gen_slots import _resolve_prompt
    from _lib.jobs.layer5.image_draft_context import ImageDraftContext, build_image_draft_context

    item_id = "calendar_candidate:stick:bg-test-1"
    (tmp_data / "intelligence" / "marketing-calendar" / "stick.jsonl").write_text(
        json.dumps(
            {
                "calendar_id": "bg-test-1",
                "status": "approved",
                "title": "Dave Lamprecht — coaching & fittings (gen)",
                "pillars": ["stick-coaching"],
                "post_type": "coaching_promo",
                "template_id": "stick-coaching-poster-v1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    ctx = build_image_draft_context("stick", item_id)
    prompt = _resolve_prompt("{scene}", ctx, brand_id="stick", item_id=item_id)
    assert "Dave Lamprecht" not in prompt
    assert "fittings (gen)" not in prompt
    assert "collage" in prompt.lower() or "poster" in prompt.lower()
    assert "coaching bay" in prompt.lower() or "trackman" in prompt.lower()


def test_recipe_image_phase_uses_gen_slots(tmp_data):
    from _lib.l5_create_enqueue import create_actions_for_moment

    item_id = "calendar_candidate:stick:bg-test-2"
    (tmp_data / "intelligence" / "marketing-calendar" / "stick.jsonl").write_text(
        json.dumps(
            {
                "calendar_id": "bg-test-2",
                "status": "approved",
                "title": "Marketing title should not matter",
                "pillars": ["stick-fitting"],
                "post_type": "service_hero",
                "template_id": "stick-service-hero-v1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    actions = create_actions_for_moment("stick", item_id, phase="image")
    assert actions == ["draft_gen_slots", "compose_post"]


def test_krea_image_generate_strips_negative_prompt_extra(monkeypatch):
    from _lib import krea_mcp

    captured: dict = {}

    def fake_mcp_call(method, params=None, *, timeout=120):
        captured["params"] = params
        return {"structuredContent": {"job_id": "test-job", "status": "queued"}}

    monkeypatch.setattr(krea_mcp, "mcp_call", fake_mcp_call)
    monkeypatch.setattr(krea_mcp, "_ensure_initialized", lambda: None)
    monkeypatch.setattr(krea_mcp, "_read_token_from_env", lambda: "tok")
    monkeypatch.setattr(krea_mcp, "_read_token_from_disk", lambda: None)

    krea_mcp.image_generate(
        "scene only",
        brand="stick",
        model="bfl/flux-1.1-pro",
        extra={"negative_prompt": "no text", "seed": 1},
        background_plate=True,
    )
    inner = captured["params"]["arguments"]["input"]
    assert "negative_prompt" not in inner
    assert inner.get("seed") == 1


def test_krea_ideogram_sends_pixels_without_aspect(monkeypatch):
    from _lib import krea_mcp

    captured: dict = {}

    def fake_mcp_call(method, params=None, *, timeout=120):
        captured["params"] = params
        return {"structuredContent": {"job_id": "test-job", "status": "queued"}}

    monkeypatch.setattr(krea_mcp, "mcp_call", fake_mcp_call)
    monkeypatch.setattr(krea_mcp, "_ensure_initialized", lambda: None)
    monkeypatch.setattr(krea_mcp, "_read_token_from_env", lambda: "tok")
    monkeypatch.setattr(krea_mcp, "_read_token_from_disk", lambda: None)

    krea_mcp.image_generate(
        "portrait scene",
        brand="stick",
        model="ideogram/ideogram-4",
        aspect_ratio="1024x1280",
        background_plate=True,
    )
    inner = captured["params"]["arguments"]["input"]
    assert "aspect_ratio" not in inner
    assert inner.get("width") == 1024
    assert inner.get("height") == 1280
    assert captured["params"]["arguments"]["model"] == "ideogram/ideogram-4"


def test_mcp_call_raises_on_tool_is_error(monkeypatch):
    from _lib import krea_mcp

    def fake_post(*_args, **_kwargs):
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "isError": True,
                "content": [
                    {"type": "text", "text": "Unknown parameter: negative_prompt"},
                ],
            },
        }

    monkeypatch.setattr(krea_mcp, "_post_json_rpc", fake_post)
    monkeypatch.setattr(krea_mcp, "_ensure_initialized", lambda: None)
    monkeypatch.setattr(krea_mcp, "_read_token_from_env", lambda: "tok")
    monkeypatch.setattr(krea_mcp, "_read_token_from_disk", lambda: None)

    with pytest.raises(krea_mcp.KreaUpstreamError, match="negative_prompt"):
        krea_mcp.mcp_call("tools/call", {})
