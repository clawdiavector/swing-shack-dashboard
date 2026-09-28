"""Post cost ledger — rollups, per-post totals, no double-charge on regen."""

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
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def test_rollup_total_matches_line_sum(ledger_env, tmp_path):
    from _lib import cost_ledger, llm_spend

    llm_spend.record(
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
    llm_spend.record(
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
    summary = cost_ledger.summary_for_inbox_item(ITEM)
    lines = _ledger_lines(tmp_path)
    assert len(lines) == 2
    assert summary["total_usd"] == pytest.approx(sum(float(r["usd"]) for r in lines))
    assert summary["by_kind"]["text"] == pytest.approx(0.002)
    assert summary["by_kind"]["image"] == pytest.approx(0.04)


def test_per_post_totals_by_event_key(ledger_env):
    from _lib import cost_ledger, llm_spend

    llm_spend.record(
        0.01,
        route="test",
        kind="image",
        brand_id="stick",
        inbox_item_id=ITEM,
        draft_asset_id="draft-a",
        event_key=EVENT,
        action="draft_photo",
        cost_source="estimate",
    )
    by_event = cost_ledger.summary_for_event_key(EVENT)
    by_item = cost_ledger.summary_for_inbox_item(ITEM)
    assert by_event["total_usd"] == by_item["total_usd"] == pytest.approx(0.01)
    assert by_event["event_key"] == EVENT


def test_regen_edit_adds_one_line_without_double_router_record(ledger_env, tmp_path):
    from _lib import llm_spend
    from _lib.image_gen_router import edit_image

    llm_spend.record(
        0.04,
        route="image_gen_router.generate",
        kind="image",
        brand_id="swing-shack",
        inbox_item_id=ITEM,
        draft_asset_id="draft-photo",
        event_key=EVENT,
        action="draft_photo",
        provider="openrouter",
        cost_source="openrouter",
    )
    before = len(_ledger_lines(tmp_path))

    fake_result = type(
        "EditResult",
        (),
        {"cost_estimate_usd": 0.05, "bytes": b"x", "model": "m", "provider": "openrouter", "usage": {}},
    )()

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
            cost_source="openrouter",
            retry_of="pcl-original",
        )

    lines = _ledger_lines(tmp_path)
    assert len(lines) == before + 1
    assert lines[-1]["kind"] == "edit"
    assert lines[-1]["retry_of"] == "pcl-original"
    summary = __import__("_lib.cost_ledger", fromlist=["summary_for_inbox_item"]).summary_for_inbox_item(ITEM)
    assert summary["total_usd"] == pytest.approx(0.09)
    assert summary["call_count"] == 2


def test_post_cost_key_idempotency_skips_duplicate_line(ledger_env, tmp_path):
    from _lib import cost_ledger

    key = "pcl-deadbeef0001"
    cost_ledger.append_line(
        usd=0.01,
        brand_id="swing-shack",
        kind="image",
        route="test",
        inbox_item_id=ITEM,
        action="draft_photo",
        cost_source="estimate",
        post_cost_key=key,
    )
    cost_ledger.append_line(
        usd=0.99,
        brand_id="swing-shack",
        kind="image",
        route="test",
        inbox_item_id=ITEM,
        action="draft_photo",
        cost_source="estimate",
        post_cost_key=key,
    )
    assert len(_ledger_lines(tmp_path)) == 1


def test_ops_cost_today_auth(cos_anon_client):
    r = cos_anon_client.get("/api/ops/cost/today")
    assert r.status_code == 401
