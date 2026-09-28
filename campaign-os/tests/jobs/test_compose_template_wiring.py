"""Compose template auto-wire + brand-scoped catalog API."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from _lib.archetypes import (  # noqa: E402
    enrich_compose_template_fields,
    infer_post_type,
    list_compose_templates,
    resolve_archetype_choice,
    suggest_template_for_record,
    validate_template_id,
)


def test_infer_post_type_did_you_know():
    assert infer_post_type({"title": "Did you know bounce helps?"}) == "did_you_know"


def test_suggest_service_frame_for_fitting_pillar():
    s = suggest_template_for_record(
        "swing-shack",
        {"pillar_id": "ss-fitting", "has_product_item": False},
    )
    assert s["template_id"] == "ss-service-frame"
    assert s["resolution"] == "rule"


def test_explicit_template_id_on_enrich():
    out = enrich_compose_template_fields(
        "stick",
        {"template_id": "stick-service-frame", "title": "Fitting"},
    )
    assert out["template_id"] == "stick-service-frame"
    assert out["template_resolution"] == "explicit"


def test_auto_template_default_when_no_signals():
    out = enrich_compose_template_fields("swing-shack", {"title": "Summer social"})
    assert out["template_id"] == "ss-photo-post"
    assert out["template_resolution"] in ("default", "rule", "fallback")


def test_list_compose_templates_brand_scoped():
    stick = {t["id"] for t in list_compose_templates("stick")}
    ss = {t["id"] for t in list_compose_templates("swing-shack")}
    assert "stick-service-frame" in stick
    assert "stick-service-frame" not in ss
    assert validate_template_id("stick", "stick-service-frame")
    assert not validate_template_id("swing-shack", "stick-service-frame")


def test_resolve_explicit_beats_rules():
    ctx = {
        "pillar_in": ["ss-fitting"],
        "has_product_item": False,
        "post_type": "",
        "template_id": "ss-photo-post",
        "subject": "",
    }
    tid, res = resolve_archetype_choice("swing-shack", ctx)
    assert tid == "ss-photo-post"
    assert res == "pinned"
