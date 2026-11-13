"""Every rand price in a caption is checked against the brand's real prices.

Christelle's rule: no number without a source, and an unverified price is never used.
The real prices are public: each venue's ClubLab booking list (services and packages)
and each shop's Shopify products.json. Prices Herman approved that are not live yet
(a deal, next year's memberships) go in data/brand-directory/<brand>/prices-approved.json
with their source. The old seeded catalogue in app.py marked made-up prices as verified
(fitting R1,500, "4 Players + Beer"), so it must not come back.

Fixtures are real responses saved on 13 Nov 2026.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "scripts"))

from _lib import price_truth as P  # noqa: E402
import caption_lint as L  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "prices"


def fake_get(url: str):
    if "clublab.app" in url:
        kind = "services" if "/services" in url else "packages"
        fid = url.rsplit("facilityId=", 1)[1]
        return 200, (FIX / f"clublab-{kind}-{fid}.json").read_bytes()
    if "shop.stickgolf.co.za" in url:
        if "page=1" in url:
            return 200, (FIX / "shopify-stick.json").read_bytes()
        return 200, b'{"products": []}'
    return 500, b""


def failing_get(url: str):
    raise OSError("network down")


# --- reading prices out of text ------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Full bag fitting R2,000.", [("R2,000", 2000)]),
        ("Only R 820 for an hour", [("R 820", 820)]),
        ("Now R12,999.00 in store", [("R12,999.00", 12999)]),
        ("R1 500 or R540", [("R1 500", 1500), ("R540", 540)]),
        ("30% OFF all bags", []),
        ("Ready? Real golfers only.", []),
    ],
)
def test_finds_rand_prices(text, expected):
    assert P.find_prices(text) == expected


# --- live prices -------------------------------------------------------------------


def test_swing_shack_live_prices_come_from_clublab(tmp_path):
    res = P.live_prices("swing-shack", get=fake_get, cache_dir=tmp_path)
    by_rand = {i["rand"]: i for i in res["items"]}
    assert res["errors"] == []
    assert by_rand[2000]["name"].startswith("Full Bag Fitting")
    assert by_rand[820]["source"].startswith("ClubLab")
    assert 7200 in by_rand  # 10x 60 min coaching pack
    assert 1500 in by_rand  # driver and woods fitting really is R1,500


def test_stick_live_prices_include_the_shop(tmp_path):
    res = P.live_prices("stick", get=fake_get, cache_dir=tmp_path)
    rands = {i["rand"] for i in res["items"]}
    assert {700, 1000, 12999} <= rands


def test_live_prices_are_cached(tmp_path):
    P.live_prices("swing-shack", get=fake_get, cache_dir=tmp_path)
    again = P.live_prices("swing-shack", get=failing_get, cache_dir=tmp_path)
    assert again["errors"] == [] and again["items"]


def test_unreachable_source_is_reported_not_hidden(tmp_path):
    res = P.live_prices("swing-shack", get=failing_get, cache_dir=tmp_path)
    assert res["items"] == []
    assert res["errors"] and "ClubLab" in res["errors"][0]


def test_unknown_brand_has_no_sources(tmp_path):
    res = P.live_prices("takomo", get=fake_get, cache_dir=tmp_path)
    assert res["items"] == [] and res["errors"]


# --- approved prices -------------------------------------------------------------


def test_approved_prices_need_a_source_and_expire(tmp_path):
    f = tmp_path / "prices-approved.json"
    f.write_text(json.dumps({"prices": [
        {"rand": 22500, "what": "Progress loyalty 2027", "source": "Herman, 9 Nov", "until": "2027-12-31"},
        {"rand": 999, "what": "old deal", "source": "Herman", "until": "2026-11-01"},
        {"rand": 111, "what": "no source given"},
    ]}), encoding="utf-8")
    got = P.approved_prices("swing-shack", path=f, today=dt.date(2026, 11, 13))
    assert [p["rand"] for p in got] == [22500]


def test_swing_shack_has_the_progress_loyalty_price_approved():
    got = P.approved_prices("swing-shack", today=dt.date(2026, 11, 13))
    assert 22500 in {p["rand"] for p in got}


# --- checking a caption -------------------------------------------------------------


def test_check_text_splits_known_and_unknown(tmp_path):
    prices = P.price_list("swing-shack", get=fake_get, cache_dir=tmp_path, today=dt.date(2026, 11, 13))
    res = P.check_text("Full bag fitting R2,000. Progress loyalty R22,500. Coaching R950.", prices)
    assert [k["token"] for k in res["known"]] == ["R2,000", "R22,500"]
    assert res["unknown"] == ["R950"]


CAPTION = "Full bag fitting at Swing Shack, {price}.\nBook a fitting via the link in bio.\nKeep Swinging"


def _price_findings(res):
    return [f for f in res["findings"] if f["code"] == "price-figure"]


def test_lint_passes_a_live_price(tmp_path):
    prices = P.price_list("swing-shack", get=fake_get, cache_dir=tmp_path, today=dt.date(2026, 11, 13))
    res = L.lint("swing-shack", CAPTION.format(price="R2,000"), cross_brand=False, prices=prices)
    assert _price_findings(res) == []


def test_lint_hard_fails_a_made_up_price(tmp_path):
    prices = P.price_list("swing-shack", get=fake_get, cache_dir=tmp_path, today=dt.date(2026, 11, 13))
    # R1,750 is in no Swing Shack list. (R1,800 looked made up but is "I Dabble", a real package.)
    res = L.lint("swing-shack", CAPTION.format(price="R1,750"), cross_brand=False, prices=prices)
    found = _price_findings(res)
    assert found and found[0]["level"] == L.HARD
    assert "R1,750" in found[0]["message"]


def test_lint_only_asks_for_a_check_when_prices_could_not_be_read(tmp_path):
    prices = P.price_list("swing-shack", get=failing_get, cache_dir=tmp_path, today=dt.date(2026, 11, 13))
    res = L.lint("swing-shack", CAPTION.format(price="R1,800"), cross_brand=False, prices=prices)
    found = _price_findings(res)
    assert found and found[0]["level"] == L.CHECK


def test_lint_without_prices_behaves_as_before():
    res = L.lint("swing-shack", CAPTION.format(price="R2,000"), cross_brand=False)
    found = _price_findings(res)
    assert found and found[0]["level"] == L.CHECK


# --- the made-up catalogue stays gone --------------------------------------------


def test_made_up_seed_catalogue_is_gone():
    src = (CAMPAIGN_OS / "app.py").read_text(encoding="utf-8")
    assert "_seed_swing_shack_products" not in src
    assert "4 Players + Beer" not in src
