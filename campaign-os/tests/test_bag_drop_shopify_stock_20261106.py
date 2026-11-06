"""Bag Drop's stock list comes from its Shopify store (2026-11-06).

Swing Shack and Stick upload a weekly stock CSV; stock_pulse turns the dated snapshots
into "new", "still", "stuck" and the feed candidates that story ideas, the daily target
and retail posts read. The Bag Drop has no CSV: its stock is the public product list on
thebagdrop.co.za. A daily job reads it and saves the same snapshot rows.

Shopify's public list has no counts, only whether each variant can be bought, and most
Bag Drop pieces are one-offs. So a variant for sale counts 1, a sold one 0: "new" is a
fresh listing, "still"/"stuck" is a piece listed for weeks without selling.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent
REPO_ROOT = CAMPAIGN_OS.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def _product(pid, title, variants, ptype="Drivers", vendor="Callaway"):
    return {"id": pid, "title": title, "vendor": vendor, "product_type": ptype, "handle": f"h{pid}",
            "variants": [{"id": vid, "title": vt, "sku": sku, "available": avail}
                         for vid, vt, sku, avail in variants]}


PRODUCTS = [
    _product(1, "Callaway Paradym Driver Head", [(11, "Default Title", "BD-001", True)]),
    _product(2, "Titleist Vokey SM9 Wedge", [(21, "56 / 10", "", True), (22, "60 / 8", "BD-003", False)],
             ptype="Wedges", vendor="Titleist"),
]


def test_rows_use_the_stock_list_shape():
    from _lib import shopify_stock as ss

    rows = ss.to_rows(PRODUCTS)
    assert rows == [
        {"sku": "BD-001", "name": "Callaway Paradym Driver Head", "variant": "", "qty": 1, "alert": None},
        {"sku": "shopify-21", "name": "Titleist Vokey SM9 Wedge", "variant": "56 / 10", "qty": 1, "alert": None},
        {"sku": "BD-003", "name": "Titleist Vokey SM9 Wedge", "variant": "60 / 8", "qty": 0, "alert": None},
    ]


def test_fetch_reads_every_page_and_waits_once_on_too_many_requests():
    from _lib import shopify_stock as ss

    calls, sleeps = [], []
    pages = {1: [PRODUCTS[0]], 2: [PRODUCTS[1]], 3: []}

    def get(url):
        calls.append(url)
        page = int(url.rsplit("page=", 1)[1])
        if page == 2 and len([c for c in calls if c.endswith("page=2")]) == 1:
            return 429, b""
        return 200, json.dumps({"products": pages[page]}).encode()

    out = ss.fetch_products("thebagdrop.co.za", get=get, sleep=sleeps.append)
    assert [p["id"] for p in out] == [1, 2]
    assert calls[0] == "https://thebagdrop.co.za/products.json?limit=250&page=1"
    assert len(sleeps) == 1


def test_fetch_gives_up_after_a_second_refusal():
    from _lib import shopify_stock as ss

    with pytest.raises(RuntimeError):
        ss.fetch_products("thebagdrop.co.za", get=lambda url: (429, b""), sleep=lambda s: None)


def test_job_saves_a_dated_snapshot_that_stock_pulse_reads(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from _lib import shopify_stock as ss
    from _lib import stock_pulse
    from _lib.jobs.layer1 import shopify_stock as job

    monkeypatch.setattr(ss, "fetch_products", lambda domain, **k: PRODUCTS)
    out = job.run(brand="bag-drop")
    assert out["ok"] is True and out["rows"] == 3 and out["for_sale"] == 2
    snaps = stock_pulse.load_snapshots("bag-drop")
    assert len(snaps) == 1 and len(snaps[0]["rows"]) == 3


def test_a_new_listing_shows_as_new(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from _lib import shopify_stock as ss
    from _lib import stock_pulse

    stock_pulse.save_snapshot("bag-drop", ss.to_rows(PRODUCTS[:1]), on="2026-11-01")
    stock_pulse.save_snapshot("bag-drop", ss.to_rows(PRODUCTS), on="2026-11-06")
    status = {r["name"]: r["status"] for r in stock_pulse.analyse(stock_pulse.load_snapshots("bag-drop"))}
    assert status["Titleist Vokey SM9 Wedge"] == "new"


def test_only_brands_with_a_store_run(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from _lib.jobs.layer1 import shopify_stock as job

    out = job.run(brand="swing-shack")
    assert out["ok"] is False and "no shopify store" in out["error"].lower()


def test_the_job_is_registered_and_scheduled():
    from _lib.jobs.layer1 import layer1_specs

    spec = {s.name: s for s in layer1_specs()}["shopify_stock"]
    assert spec.brands == ("bag-drop",)
    wf = (REPO_ROOT / ".github" / "workflows" / "layer1-daily-cron.yml").read_text(encoding="utf-8")
    assert "/api/jobs/run/shopify_stock?all=1" in wf
