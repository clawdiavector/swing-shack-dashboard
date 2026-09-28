"""Post cost ledger — rollups, per-post totals, provider idempotency, windows."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

ITEM = "calendar_candidate:swing-shack:sk_evt_test"
EVENT = "sk_evt_test"


@pytest.fixture
def ledger_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for mod in list(sys.modules):
        if mod.startswith("_lib."):
            del sys.modules[mod]
    yield tmp_path
    for mod in list(sys.modules):
        if mod.startswith("_lib."):
            del sys.modules[mod]


def _ledger_lines(tmp_path: Path) -> list[dict]:
    from _lib import cost_ledger

    day = cost_ledger._utc_day()
    path = tmp_path / "cost-ledger" / f"{day}.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_post_cost_key_stable_per_post(ledger_env):
    from _lib import post_cost

    pck1 = post_cost.derive_post_cost_key(inbox_item_id=ITEM, event_key=EVENT)
    pck2 = post_cost.derive_post_cost_key(inbox_item_id=ITEM, event_key=EVENT)
    assert pck1 == pck2
    assert pck1.startswith("pck-")


def test_rollup_total_matches_line_sum(ledger_env, tmp_path):
    from _lib import cost_ledger, post_cost

    pck = post_cost.derive_post_cost_key(inbox_item_id=ITEM, event_key=EVENT)
    post_cost.record_spend_and_line(
        0.002,
        route="test/caption",
        kind="text",
        brand_id="swing-shack",
        inbox_item_id=ITEM,
        draft_asset_id="draft-cap1",
        event_key=EVENT,
        action="draft_caption",
        cost_source="modelled",
    )
    post_cost.record_spend_and_line(
        0.04,
        route="test/image",
        kind="image",
        brand_id="swing-shack",
        inbox_item_id=ITEM,
        draft_asset_id="draft-img1",
        event_key=EVENT,
        action="draft_photo",
        cost_source="openrouter",
    )
    summary = cost_ledger.summary_for_post_cost_key(pck)
    lines = _ledger_lines(tmp_path)
    assert len(lines) == 2
    assert all(ln.get("post_cost_key") == pck for ln in lines)
    assert summary["total_usd"] == pytest.approx(sum(float(r["usd"]) for r in lines))


def test_window_summary_matches_line_sum(ledger_env, tmp_path):
    from _lib import cost_ledger, post_cost

    post_cost.record_line(
        usd=0.03,
        brand_id="swing-shack",
        kind="image",
        route="test",
        inbox_item_id=ITEM,
        action="draft_photo",
        cost_source="estimate",
        event_key=EVENT,
    )
    day_roll = cost_ledger.window_rollup(window="day", brand="swing-shack")
    lines = _ledger_lines(tmp_path)
    assert day_roll["total_usd"] == pytest.approx(sum(float(r["usd"]) for r in lines))


def test_provider_job_id_not_double_billed(ledger_env, tmp_path):
    from _lib import post_cost

    post_cost.record_line(
        usd=0.04,
        brand_id="swing-shack",
        kind="image",
        route="test",
        inbox_item_id=ITEM,
        action="draft_photo",
        cost_source="krea",
        provider_job_id="krea-job-99",
        event_key=EVENT,
    )
    post_cost.record_line(
        usd=0.04,
        brand_id="swing-shack",
        kind="image",
        route="test",
        inbox_item_id=ITEM,
        action="draft_photo",
        cost_source="krea",
        provider_job_id="krea-job-99",
        event_key=EVENT,
    )
    assert len(_ledger_lines(tmp_path)) == 1


def test_regen_edit_adds_line_without_dup_spend_counter(ledger_env, tmp_path):
    from _lib import llm_spend, post_cost
    from _lib.image_gen_router import edit_image

    post_cost.record_spend_and_line(
        0.04,
        route="image_gen_router.generate",
        kind="image",
        brand_id="swing-shack",
        inbox_item_id=ITEM,
        draft_asset_id="draft-photo",
        event_key=EVENT,
        action="draft_photo",
        cost_source="openrouter",
    )
    calls_before = llm_spend.today_spend()["calls"]

    with patch("_lib.image_gen_router._call_openrouter_multimodal", return_value={"usage": {"cost": 0.05}}), patch(
        "_lib.image_gen_router._extract_image_from_openrouter_response", return_value=(b"\x89PNG", "image/png")
    ), patch("_lib.image_gen_router.openrouter_credentials_present", return_value=True):
        edit_image(
            b"\x89PNG",
            "brighten",
            brand_id="swing-shack",
            save=False,
            inbox_item_id=ITEM,
            draft_asset_id="draft-photo",
            event_key=EVENT,
            cost_action="draft_photo",
            retry_of="pcl-original",
        )

    assert llm_spend.today_spend()["calls"] == calls_before + 1
    assert len(_ledger_lines(tmp_path)) == 2


def test_compose_post_zero_line(ledger_env, tmp_path):
    from _lib import post_cost

    post_cost.record_line(
        usd=0.0,
        brand_id="swing-shack",
        kind="image",
        route="job:draft_assets/compose",
        inbox_item_id=ITEM,
        action="compose_post",
        cost_source="estimate",
        event_key=EVENT,
        draft_asset_id="draft-x",
    )
    lines = _ledger_lines(tmp_path)
    assert len(lines) == 1
    assert lines[0]["action"] == "compose_post"
    assert float(lines[0]["usd"]) == 0.0


def test_line_id_idempotency(ledger_env, tmp_path):
    from _lib import cost_ledger, post_cost

    pck = post_cost.derive_post_cost_key(inbox_item_id=ITEM, event_key=EVENT)
    cost_ledger.append_line(
        usd=0.01,
        brand_id="swing-shack",
        kind="image",
        route="test",
        inbox_item_id=ITEM,
        action="draft_photo",
        cost_source="estimate",
        line_id="pcl-deadbeef01",
        post_cost_key=pck,
    )
    cost_ledger.append_line(
        usd=0.99,
        brand_id="swing-shack",
        kind="image",
        route="test",
        inbox_item_id=ITEM,
        action="draft_photo",
        cost_source="estimate",
        line_id="pcl-deadbeef01",
        post_cost_key=pck,
    )
    assert len(_ledger_lines(tmp_path)) == 1


def test_ops_cost_today_auth(cos_anon_client):
    r = cos_anon_client.get("/api/ops/cost/today")
    assert r.status_code == 401


def test_daily_cap_unchanged_after_ledger_writes(ledger_env, monkeypatch):
    from _lib import llm_spend, post_cost

    monkeypatch.setenv("CAMPAIGN_OS_DAILY_LLM_CAP_USD", "0.05")
    for mod in list(sys.modules):
        if mod.startswith("_lib."):
            del sys.modules[mod]
    from _lib import llm_spend as ls2

    ok, _ = ls2.check("image", 0.04)
    assert ok
    post_cost.record_spend_and_line(
        0.04,
        route="test",
        kind="image",
        brand_id="swing-shack",
        inbox_item_id=ITEM,
        action="draft_photo",
        event_key=EVENT,
    )
    ok2, reason = ls2.check("image", 0.04)
    assert not ok2
    assert "cap" in reason.lower()
