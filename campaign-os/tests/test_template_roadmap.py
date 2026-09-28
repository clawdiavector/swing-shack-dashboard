"""Template roadmap coverage — stick + swing-shack row counts and status."""

from __future__ import annotations

import pytest

from _lib.template_gallery import build_template_gallery
from _lib.template_roadmap import build_template_coverage, load_template_roadmap_doc


def test_roadmap_yaml_loads():
    doc = load_template_roadmap_doc()
    brands = doc.get("brands") or {}
    assert "stick" in brands
    assert "swing-shack" in brands


def test_stick_coverage_row_count_and_ready():
    cov = build_template_coverage("stick")
    assert cov["brand_id"] == "stick"
    rows = cov.get("rows") or []
    assert len(rows) == 8
    summary = cov.get("summary") or {}
    assert summary.get("total") == 8
    ready_ids = [r["archetype_id"] for r in rows if r.get("status") == "ready"]
    assert "stick-service-frame" in ready_ids


def test_swing_shack_coverage_row_count():
    cov = build_template_coverage("swing-shack")
    rows = cov.get("rows") or []
    assert len(rows) == 8
    assert (cov.get("summary") or {}).get("total") == 8


def test_missing_rows_have_no_previews():
    for brand in ("stick", "swing-shack"):
        cov = build_template_coverage(brand)
        for row in cov.get("rows") or []:
            if row.get("status") == "missing":
                assert row.get("preview_urls") == []


def test_gallery_includes_coverage_key():
    gallery = build_template_gallery("stick")
    cov = gallery.get("coverage")
    assert cov is not None
    assert cov.get("summary", {}).get("total") == 8


def test_unknown_brand_coverage_raises():
    with pytest.raises(ValueError, match="unknown"):
        build_template_coverage("not-a-real-brand-id-xyz")
