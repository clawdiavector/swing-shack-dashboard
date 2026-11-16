"""Bag Drop's weekly report had no website numbers: no GA4 property was set.

Christelle found the property (The Bag Drop, 542532107) on 16 Nov 2026 and
gave the OS service account Viewer access. Railway has GA4_PROPERTY_BAG_DROP.
"""

from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parent.parent
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import reporting_intelligence as ri  # noqa: E402


def test_bag_drop_has_its_own_ga4_property():
    assert ri.BRAND_CONFIG["bag-drop"]["ga4_property_id"] == "542532107"


def test_each_brand_has_a_different_ga4_property():
    ids = [ri.BRAND_CONFIG[b]["ga4_property_id"] for b in ("stick", "swing-shack", "bag-drop")]
    assert len(set(ids)) == 3
