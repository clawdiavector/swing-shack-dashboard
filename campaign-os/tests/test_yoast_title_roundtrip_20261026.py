"""Yoast SEO title write must round-trip through WordPress read-back (PR #193).

Proves the same path the Fix/Improve buttons use: write_field(..., field='title')
then GET read-back. Fake WordPress only — no live site.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from _lib import seo_meta_publish as smp  # noqa: E402
from test_seo_fixer import FakeWP, GOOD_TITLE  # noqa: E402

PAGE_ID = 2255
BEFORE_TEMPLATE = "Membership - Swing Shack"
PROBE = GOOD_TITLE


def test_title_write_round_trips_when_wordpress_keeps_the_value():
    wp = FakeWP(behaviour="accept")
    out = smp.write_field(wp, PAGE_ID, "title", PROBE, BEFORE_TEMPLATE)
    assert out["ok"] and out["verified"]
    assert wp.pages[PAGE_ID]["title"] == PROBE
    assert smp.current_value(wp._view(wp.pages[PAGE_ID]), "title") == PROBE


def test_title_write_fails_verification_when_wordpress_drops_the_value():
    wp = FakeWP(behaviour="ignore")
    out = smp.write_field(wp, PAGE_ID, "title", PROBE, BEFORE_TEMPLATE)
    assert not out["ok"] and not out["verified"]
    assert "does not show it" in (out.get("error") or "")
