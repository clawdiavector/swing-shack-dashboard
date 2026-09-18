"""Unit tests for _lib.brand_validate."""

from __future__ import annotations

import pytest

from _lib.brand_validate import QUEUE_BRAND_SENTINELS, validate_brand_id


def test_valid_operating_brands_pass():
    assert validate_brand_id("stick") == "stick"
    assert validate_brand_id(" swing-shack ") == "swing-shack"
    assert validate_brand_id("BAG-DROP") == "bag-drop"


def test_empty_brand_raises():
    with pytest.raises(ValueError, match="brand_id required"):
        validate_brand_id("")
    with pytest.raises(ValueError, match="brand_id required"):
        validate_brand_id(None)


def test_takomo_product_brand_rejected():
    with pytest.raises(ValueError, match="invalid brand_id 'takomo'"):
        validate_brand_id("takomo")


def test_all_sentinel_only_when_allowed():
    assert "all" in QUEUE_BRAND_SENTINELS
    with pytest.raises(ValueError, match="invalid brand_id 'all'"):
        validate_brand_id("all")
    assert validate_brand_id("all", allow_sentinel=True) == "all"
