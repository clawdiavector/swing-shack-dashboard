"""Flag scout suggestions set in another part of South Africa (audit, 3 Nov 2026).

The scout offered Stick (Paarl) the Telkom PGA at Country Club Johannesburg as
"the most local elite event Stick has". Brands are separate companies in separate
places; a suggestion naming a place in another province is marked far away.
"""

from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))

from _lib import brand_place as bp  # noqa: E402

TELKOM = "Telkom PGA Championship 2026 — Country Club Johannesburg (Woodmead), 5–8 Nov"


def test_a_johannesburg_event_is_far_for_stick():
    assert bp.far_from_brand("stick", TELKOM) == {"place": "Johannesburg", "home": "Paarl"}


def test_the_same_event_is_local_for_swing_shack():
    assert bp.far_from_brand("swing-shack", TELKOM) is None


def test_a_place_in_the_brands_own_province_is_not_far():
    assert bp.far_from_brand("stick", "Franschhoek — short trip, long drive") is None
    assert bp.far_from_brand("stick", "Cape Town Open, then a fitting in Paarl") is None


def test_other_provinces_are_caught_for_swing_shack():
    far = bp.far_from_brand("swing-shack", "Alfred Dunhill Championship — Leopard Creek, Malelane")
    assert far == {"place": "Leopard Creek", "home": "Johannesburg"}
    assert bp.far_from_brand("swing-shack", "Durban Country Club (25-28 February)")["place"] == "Durban"


def test_short_names_match_whole_words_only():
    assert bp.far_from_brand("stick", "Golf in JHB this weekend")["place"] == "JHB"
    assert bp.far_from_brand("stick", "Watch the jhbx stream") is None


def test_international_events_and_bag_drop_are_never_far():
    assert bp.far_from_brand("stick", "YGT Final — Wynn Las Vegas, 4-5 Nov") is None
    assert bp.far_from_brand("bag-drop", TELKOM) is None
    assert bp.far_from_brand("stick", "") is None
