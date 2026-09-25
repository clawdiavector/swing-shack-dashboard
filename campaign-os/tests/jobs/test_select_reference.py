"""Unit tests for image_draft_context._select_reference ranking + fallbacks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAMPAIGN_OS = HERE.parent.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


@pytest.fixture()
def brand_root(tmp_path):
    brand = "stick"
    root = tmp_path / "brand-directory"
    (root / brand / "references").mkdir(parents=True)
    (root / brand / "images").mkdir(parents=True)
    return brand, root


def _write_ref(root: Path, brand: str, ref_id: str, **fields):
    row = {"ref_id": ref_id, "is_learnable": True, "created": 1.0, **fields}
    path = root / brand / "references" / f"{ref_id}.reference-dna.json"
    path.write_text(json.dumps(row), encoding="utf-8")
    return row


def test_select_reference_platform_match(brand_root):
    from _lib.jobs.layer5.image_draft_context import _select_reference

    brand, root = brand_root
    _write_ref(root, brand, "ref-ig", platform="instagram", pillar="demo", created=10.0)
    _write_ref(root, brand, "ref-fb", platform="facebook", pillar="demo", created=99.0)
    degraded: list[dict[str, str]] = []
    picked = _select_reference(
        brand,
        platform="instagram",
        pillar="demo",
        root=root,
        degraded=degraded,
    )
    assert picked is not None
    assert picked["id"] == "ref-ig"


def test_select_reference_pillar_fallback(brand_root):
    from _lib.jobs.layer5.image_draft_context import _select_reference

    brand, root = brand_root
    _write_ref(root, brand, "ref-a", platform="facebook", pillar="venue", created=5.0)
    _write_ref(root, brand, "ref-b", platform="facebook", pillar="trackman", created=1.0)
    degraded: list[dict[str, str]] = []
    picked = _select_reference(
        brand,
        platform="instagram",
        pillar="trackman",
        root=root,
        degraded=degraded,
    )
    assert picked is not None
    assert picked["id"] == "ref-b"


def test_select_reference_drive_fallback(brand_root):
    from _lib.jobs.layer5.image_draft_context import _select_reference

    brand, root = brand_root
    images = root / brand / "images"
    img = images / "hero.jpg"
    img.write_bytes(b"\xff\xd8\xff\xd8fake-jpeg")
    dna = {
        "product_tags": ["trackman"],
        "created": 3.0,
    }
    (images / "hero.jpg.visual-dna.json").write_text(json.dumps(dna), encoding="utf-8")
    degraded: list[dict[str, str]] = []
    picked = _select_reference(
        brand,
        platform="instagram",
        pillar="trackman",
        root=root,
        degraded=degraded,
    )
    assert picked is not None
    assert picked["source"] == "drive"
    assert picked["bytes_path"].endswith("hero.jpg")


def test_select_reference_none(brand_root):
    from _lib.jobs.layer5.image_draft_context import _select_reference

    brand, root = brand_root
    degraded: list[dict[str, str]] = []
    picked = _select_reference(
        brand,
        platform="instagram",
        pillar="missing",
        root=root,
        degraded=degraded,
    )
    assert picked is None
    assert degraded
