"""One-shot L5 routing — create_actions_for_moment branches."""

from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
if str(CAMPAIGN_OS) not in sys.path:
    sys.path.insert(0, str(CAMPAIGN_OS))


def test_oneshot_image_phase():
    from _lib.l5_create_enqueue import create_actions_for_moment

    rec = {"render_mode": "oneshot", "title": "Line"}
    assert create_actions_for_moment("stick", "calendar_candidate:stick:cal-1", phase="image", record=rec) == [
        "draft_oneshot"
    ]


def test_template_unchanged():
    from _lib.l5_create_enqueue import create_actions_for_moment

    baseline = create_actions_for_moment("stick", "calendar_candidate:stick:cal-t", phase="image", record={"title": "x"})
    assert "draft_oneshot" not in baseline
    assert "compose_post" in baseline


def test_no_render_mode_key_same_as_template():
    from _lib.l5_create_enqueue import create_actions_for_moment

    a = create_actions_for_moment("stick", "calendar_candidate:stick:cal-a", phase="image", record={})
    b = create_actions_for_moment("stick", "calendar_candidate:stick:cal-b", phase="image", record={"render_mode": "template"})
    assert a == b


def test_draft_oneshot_not_in_photo_equiv():
    from _lib.jobs.layer5.draft_assets import _PHOTO_EQUIV

    assert "draft_oneshot" not in _PHOTO_EQUIV
