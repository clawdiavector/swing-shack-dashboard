"""Product posts rotate one angle each (product only / matched service / Shopify) so they don't read as repeats."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "scripts"))

from _lib import product_angle as pa  # noqa: E402
from _lib import retail_campaign as rc  # noqa: E402
from _lib.service_tiein import service_tiein_line  # noqa: E402
from _lib.store_notice import NOTICES  # noqa: E402

BALL = "Vice Pro Air White Sleeve"
CAP = "Polo Bunny Classic Polo"


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def test_available_angles_per_brand_and_product():
    assert pa.available("stick", BALL) == ["product", "service", "shopify"]
    # no service matches a polo; Swing Shack has no online store line
    assert pa.available("stick", CAP) == ["product", "shopify"]
    assert pa.available("swing-shack", BALL) == ["product", "service"]
    assert pa.available("swing-shack", CAP) == ["product"]


def test_never_the_same_angle_twice_in_a_row_when_there_is_a_choice():
    recent: list[str] = []
    for _ in range(9):
        a = pa.next_angle("stick", BALL, recent)
        if recent:
            assert a != recent[-1]
        recent.append(a)
    # all three get used, evenly
    assert {recent.count(a) for a in pa.ANGLES} == {3}


def test_least_recently_used_angle_comes_next():
    assert pa.next_angle("stick", BALL, ["service", "shopify"]) == "product"
    assert pa.next_angle("stick", BALL, ["product", "shopify"]) == "service"


def test_only_one_angle_available_is_allowed_to_repeat():
    assert pa.next_angle("swing-shack", CAP, ["product"]) == "product"


def test_apply_angle_adds_exactly_one_line():
    base = "Vice Pro Air, in store.\nDM us for details.\nBetter begins here."
    product = pa.apply_angle(base, "product", BALL, "stick")
    service = pa.apply_angle(base, "service", BALL, "stick")
    shopify = pa.apply_angle(base, "shopify", BALL, "stick")
    assert product == base
    assert service_tiein_line(BALL, "stick") in service and NOTICES["stick"] not in service
    assert NOTICES["stick"] in shopify and service_tiein_line(BALL, "stick") not in shopify
    assert shopify.splitlines()[-1] == "Better begins here."


def test_rotation_is_remembered_between_calls():
    seen = [pa.caption_with_rotation("Vice Pro Air, in store.", BALL, "stick")[1] for _ in range(3)]
    assert len(set(seen)) == 3
    assert pa.recent_angles("stick")[-3:] == seen
    # brands keep their own rotation
    assert pa.recent_angles("swing-shack") == []


def test_retail_week_captions_rotate(monkeypatch):
    picks = [
        {"date": f"2026-11-0{i}", "name": BALL, "idea": "", "status": "", "photo_entries": []}
        for i in range(3, 6)
    ]
    monkeypatch.setattr(rc, "pick_week_products", lambda *a, **k: (picks, []))
    monkeypatch.setattr(rc, "_stick_template", lambda entries: "stick-product-post")
    plan = rc.plan_week("stick")
    angles = [p["angle"] for p in plan["posts"]]
    assert len(set(angles)) == 3
    for p in plan["posts"]:
        cap = p["caption"]
        has_service = service_tiein_line(BALL, "stick") in cap
        has_shop = NOTICES["stick"] in cap
        assert (has_service, has_shop) == {"product": (False, False), "service": (True, False),
                                           "shopify": (False, True)}[p["angle"]]


def test_build_caption_without_angle_is_unchanged():
    assert rc.build_caption("stick", BALL) == f"{BALL} is in store now.\nBook a fitting at Stick.\nBetter begins here."
