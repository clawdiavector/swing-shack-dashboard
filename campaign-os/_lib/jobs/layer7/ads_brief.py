"""Daily Meta ads brief per brand, plus the weekly one on Mondays.

Reads Meta (read-only) through _lib.ads_brain, scores the 31-day window with
the frozen Scoring V1, and writes under brands/<brand>/ads-brief/.
"""

from __future__ import annotations

import datetime as _dt

from _lib import ads_brain, ads_brief, ads_creative
from _lib.brand_validate import validate_brand_id

from ..layer1._io import as_dict, as_list, io_for_job

JOB_NAME = "ads_brief"
LATEST = "ads-brief/latest.json"
WEEKLY = "ads-brief/weekly-latest.json"
STATE = "ads-brief/state.json"
EVENTS = "ads-brief/events.json"
TESTS = "ads-creative/tests.json"
ORGANIC = "post-outcomes.json"


def run(*, brand: str | None = None, today: _dt.date | None = None,
        get=None, get_as=None) -> dict:
    """Build today's brief for one brand. ``today``, ``get`` and ``get_as`` are for tests."""
    if not brand:
        return {"ok": False, "error": "brand required"}
    try:
        lane_brand = validate_brand_id(brand)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    account, token = ads_brain.resolve_credentials(lane_brand)
    if not account or not (token or get):
        return {"ok": False, "error": "no ad account or token for this brand"}

    today = today or ads_brief.sast_today()
    io = io_for_job(JOB_NAME, lane_brand)
    kw = {"get": get, "get_as": get_as, "today": today}
    full = ads_brain.fetch_snapshot(lane_brand, account, token, days=31, **kw)
    if not full["ads"]:
        # Nothing readable: leave yesterday's brief in place rather than blank it.
        return {"ok": False, "error": "Meta returned no ads", "errors": full["errors"][:3]}
    scored = ads_brain.score_snapshot(full)
    recent = ads_brain.fetch_snapshot(lane_brand, account, token, days=7,
                                      insights_only=True, **kw)

    prev_state = io.read(STATE, allow_flat_fallback=False)
    state = as_dict(prev_state) if prev_state else None
    daily, new_state, new_events = ads_brief.build_daily(lane_brand, scored, recent, state, today)

    # Creative loop: move open tests on, then propose new ones.
    tests = as_list(io.read(TESTS, allow_flat_fallback=False))
    organic = as_list(as_dict(io.read(ORGANIC, allow_flat_fallback=False)).get("outcomes"))
    tests = ads_creative.track(
        tests, full,
        lambda days: ads_brain.fetch_snapshot(lane_brand, account, token, days=days,
                                              insights_only=True, **kw),
        today)
    tests += ads_creative.plan(lane_brand, scored, full, organic, tests, today)
    daily["creative"] = ads_creative.summarise(tests, today)
    # Why a card has no organic reel: nothing on file, no reels, or none on theme.
    daily["creative"]["organic"] = {
        "posts_on_file": len(organic),
        "reels": sum(1 for o in organic if o.get("format_type") == "reel"),
        "reels_with_a_theme": sum(1 for o in organic if o.get("format_type") == "reel"
                                  and ads_creative.themes_of(o.get("caption_preview"))),
        # A reel Meta returned no reach for scores zero and can never be picked.
        "reels_with_reach": sum(1 for o in organic if o.get("format_type") == "reel"
                                and (o.get("reach") or 0) > 0),
        "with_a_link": sum(1 for o in organic if o.get("permalink")),
    }
    events = ads_brief.merge_events(as_list(io.read(EVENTS, allow_flat_fallback=False)), new_events)

    io.write(LATEST, daily)
    io.write(f"ads-brief/daily/{daily['date']}.json", daily)
    io.write(STATE, new_state)
    io.write(EVENTS, events)
    io.write(TESTS, tests)

    wrote_weekly = False
    if today.weekday() == 0 or not io.read(WEEKLY, allow_flat_fallback=False):
        weekly = ads_brief.build_weekly(daily, events, today)
        io.write(WEEKLY, weekly)
        io.write(f"ads-brief/weekly/{daily['date']}.json", weekly)
        wrote_weekly = True

    return {
        "ok": True, "brand": lane_brand, "date": daily["date"],
        "headline": daily["headline"], "wrote_weekly": wrote_weekly,
        "scoring_version": daily["scoring_version"],
        "creative_tests": {k: len(daily["creative"][k]) for k in ("proposed", "running")},
        "organic": daily["creative"]["organic"],
        "errors": daily["errors"][:3],
    }
