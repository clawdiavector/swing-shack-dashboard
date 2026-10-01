"""Template gallery API payload — stick brand smoke."""

from __future__ import annotations

import json

import pytest

from _lib.template_gallery import build_template_gallery


def test_stick_gallery_has_templates_and_bible():
    gallery = build_template_gallery("stick")
    assert gallery["brand_id"] == "stick"
    bible = gallery.get("brand_bible") or {}
    assert bible.get("philosophy") or bible.get("composition_rules")
    templates = gallery.get("templates") or []
    assert len(templates) >= 7
    for row in templates:
        previews = row.get("preview_urls")
        assert previews is not None
        assert isinstance(previews, list)
        assert previews or previews == []


def test_stick_service_frame_preview_leads_with_golden():
    gallery = build_template_gallery("stick")
    frame = next(
        row
        for row in gallery.get("templates") or []
        if row.get("template_id") == "stick-service-frame"
    )
    previews = frame.get("preview_urls") or []
    assert previews
    assert "golden/render-instagram" in previews[0]
    assert any("references/" in url for url in previews[1:])


def test_catalog_cover_uses_latest_composed_post(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    sidecar = tmp_path / "draft-assets"
    sidecar.mkdir()
    (sidecar / "draft-live.json").write_text(
        json.dumps(
            {
                "asset_id": "draft-live",
                "brand_id": "stick",
                "updatedAt": "2026-10-01T12:00:00Z",
                "archetype": {"id": "stick-service-frame"},
                "composed": {
                    "instagram": "/brand-images/stick/composed-draft-live-instagram.png"
                },
            }
        ),
        encoding="utf-8",
    )
    gallery = build_template_gallery("stick")
    frame = next(
        row
        for row in gallery.get("templates") or []
        if row.get("template_id") == "stick-service-frame"
    )
    previews = frame.get("preview_urls") or []
    assert previews[0] == "/brand-images/stick/composed-draft-live-instagram.png"
    assert any("golden/render-instagram" in url for url in previews[1:])


def test_unknown_brand_raises():
    with pytest.raises(ValueError, match="unknown"):
        build_template_gallery("not-a-real-brand-id-xyz")
