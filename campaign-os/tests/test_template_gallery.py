"""Template gallery API payload — stick brand smoke."""

from __future__ import annotations

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


def test_unknown_brand_raises():
    with pytest.raises(ValueError, match="unknown"):
        build_template_gallery("not-a-real-brand-id-xyz")
