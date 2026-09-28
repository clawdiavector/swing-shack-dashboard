"""Template catalog — reference URLs for operator UI."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from _lib.template_catalog import template_display_meta, template_label  # noqa: E402


def test_template_label_shortens_id():
    assert template_label("stick-service-start") == "service-start"
    assert template_label("ss-did-you-know") == "did-you-know"


def test_stick_service_start_has_reference_urls():
    meta = template_display_meta("stick", "stick-service-start")
    assert meta["template_id"] == "stick-service-start"
    assert meta["template_reference_urls"]
    assert meta["template_reference_urls"][0].startswith("/brand-directory/stick/templates/")
    assert "ref-01" in meta["template_reference_urls"][0]


def test_swing_shack_did_you_know_resolves_pack_relative_refs():
    meta = template_display_meta("swing-shack", "ss-did-you-know")
    assert meta["template_id"] == "ss-did-you-know"
    assert meta["template_reference_urls"]
    first = meta["template_reference_urls"][0]
    assert first == "/brand-directory/swing-shack/templates/did-you-know/references/ref-01.jpg"
