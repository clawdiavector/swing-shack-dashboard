"""SEO/GEO fix queue: tiers, memory between runs, and the site_audit hook.

Policy: wiki decisions/seo-geo-automation-tiers-2026-10-19. Only meta
descriptions on non-homepage pages may ever publish automatically; everything
else, including anything unknown, asks first. The queue never writes to the site.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from _lib import seo_fix_queue as q  # noqa: E402

T1 = "2026-10-19T04:00:00Z"
T2 = "2026-10-20T04:00:00Z"


def f(ftype, page="Coaching", severity="medium", msg="m"):
    return {"type": ftype, "page": page, "severity": severity, "message": msg}


# ── classify ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ftype,page,expected",
    [
        ("missing_meta_description", "Coaching", q.PUBLISH_AUTO),
        ("meta_description_short", "Membership", q.PUBLISH_AUTO),
        ("missing_meta_description", "Homepage", q.PUBLISH_ASK),
        ("missing_price", "Coaching", q.PUBLISH_ASK),
        ("missing_location", "Coaching", q.PUBLISH_ASK),
        ("unclear_entity", "Club Fitting", q.PUBLISH_ASK),
        ("images_missing_alt", "Coaching", q.PUBLISH_ASK),
        ("something_new_we_never_saw", "Coaching", q.PUBLISH_ASK),
    ],
)
def test_classify(ftype, page, expected):
    assert q.classify(ftype, page) == expected


# ── sync ────────────────────────────────────────────────────────────────────


def test_new_findings_become_drafts_with_counts():
    out = q.sync(
        "swing-shack",
        [f("missing_meta_description"), f("images_missing_alt")],
        [f("no_qa_blocks")],
        None,
        T1,
        geo_fixes={"no_qa_blocks": "Add FAQ section"},
    )
    assert out["counts"] == {"open": 3, "auto_eligible": 1, "asks_first": 2}
    by_type = {i["type"]: i for i in out["items"]}
    assert by_type["no_qa_blocks"]["fix"] == "Add FAQ section"
    assert by_type["no_qa_blocks"]["apply_via"] == "missing_faq"
    assert by_type["missing_meta_description"]["apply_via"] == "missing_meta_description"
    assert all(i["status"] == "draft" and i["brand"] == "swing-shack" for i in out["items"])


def test_ids_are_stable_and_do_not_duplicate_across_runs():
    first = q.sync("swing-shack", [f("missing_h1")], [], None, T1)
    second = q.sync("swing-shack", [f("missing_h1")], [], first, T2)
    assert [i["id"] for i in first["items"]] == [i["id"] for i in second["items"]]
    assert len(second["items"]) == 1
    assert second["items"][0]["first_seen"] == T1


def test_same_type_on_two_pages_is_two_items():
    out = q.sync("swing-shack", [f("missing_h1", "Coaching"), f("missing_h1", "Membership")], [], None, T1)
    assert len(out["items"]) == 2


def test_a_persons_decision_sticks():
    first = q.sync("swing-shack", [f("missing_h1")], [], None, T1)
    first["items"][0]["status"] = "dismissed"
    second = q.sync("swing-shack", [f("missing_h1")], [], first, T2)
    assert second["items"][0]["status"] == "dismissed"
    assert second["counts"]["open"] == 0


def test_fixed_findings_resolve_and_reappear_as_drafts():
    first = q.sync("swing-shack", [f("missing_h1")], [], None, T1)
    gone = q.sync("swing-shack", [], [], first, T2)
    assert gone["items"][0]["status"] == "resolved"
    assert gone["items"][0]["resolved_at"] == T2
    assert gone["counts"]["open"] == 0
    back = q.sync("swing-shack", [f("missing_h1")], [], gone, "2026-10-21T04:00:00Z")
    assert len(back["items"]) == 1
    assert back["items"][0]["status"] == "draft"


def test_resolved_history_is_capped():
    prev = {"items": [{"id": f"r{n}", "status": "resolved", "resolved_at": f"2026-01-{n % 28 + 1:02d}"} for n in range(150)]}
    out = q.sync("swing-shack", [], [], prev, T1)
    assert len(out["items"]) == q.MAX_RESOLVED_KEPT


@pytest.mark.parametrize("brand", ["stick", "bag-drop", "", "swing-shack-typo"])
def test_other_brands_are_refused(brand):
    with pytest.raises(ValueError):
        q.sync(brand, [f("missing_h1")], [], None, T1)


# ── site_audit hook ─────────────────────────────────────────────────────────

HTML = "<html><head><title>x</title></head><body>hello</body></html>"


@pytest.fixture()
def data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def _queue_path(root: Path, brand: str) -> Path:
    return root / "brands" / brand / "seo-fix-queue.json"


def test_site_audit_writes_queue_for_swing_shack(data_dir):
    from _lib.jobs.layer1 import site_audit

    with patch.object(site_audit, "_fetch_page", return_value=HTML):
        result = site_audit.run(brand="swing-shack")
    assert result["ok"]
    queue = json.loads(_queue_path(data_dir, "swing-shack").read_text())
    assert queue["brand"] == "swing-shack"
    assert queue["counts"]["open"] > 0
    # An unknown or sensitive finding must not be auto-publishable.
    for item in queue["items"]:
        if item["publish_policy"] == q.PUBLISH_AUTO:
            assert item["type"] in q.AUTO_PUBLISH_TYPES and item["page"] != "Homepage"


def test_site_audit_does_not_queue_for_stick(data_dir, monkeypatch):
    from _lib.jobs.layer1 import site_audit

    monkeypatch.setenv("BRAND_DOMAIN_STICK", "stickgolf.co.za")
    with patch.object(site_audit, "_fetch_page", return_value=HTML):
        site_audit.run(brand="stick")
    assert not _queue_path(data_dir, "stick").exists()
    assert not _queue_path(data_dir, "swing-shack").exists()


def test_a_queue_failure_never_fails_the_audit(data_dir):
    from _lib.jobs.layer1 import site_audit

    with patch.object(site_audit, "_fetch_page", return_value=HTML), patch.object(
        q, "sync", side_effect=RuntimeError("boom")
    ):
        result = site_audit.run(brand="swing-shack")
    assert result["ok"]
