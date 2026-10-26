"""Daily Meta ads brief per brand, plus the weekly one on Mondays.

Reads Meta (read-only) through _lib.ads_brain, scores the 31-day window with
the frozen Scoring V1, and writes under brands/<brand>/ads-brief/.

Beside the brief it keeps the longer view under brands/<brand>/ads-history/:
a year of weekly numbers per ad, the trends and the ads that earned their
keep. That part is an add-on and can never cost the day's brief.
"""

from __future__ import annotations

import datetime as _dt
import sys
import time

from _lib import ads_actions, ads_brain, ads_brief, ads_budget, ads_cache_warm, ads_cap, ads_creative, ads_history, ads_ideas
from _lib import ads_tracking
from _lib.brand_validate import validate_brand_id

from ..layer1._io import as_dict, as_list, io_for_job

JOB_NAME = "ads_brief"
LATEST = "ads-brief/latest.json"
WEEKLY = "ads-brief/weekly-latest.json"
STATE = "ads-brief/state.json"
EVENTS = "ads-brief/events.json"
TESTS = "ads-creative/tests.json"
ORGANIC = "post-outcomes.json"
HISTORY = "ads-history/weekly.json"
HISTORY_LATEST = "ads-history/latest.json"
TRACKING = "ads-tracking/latest.json"
# The cache warm-up only starts a refresh before this many seconds into the run (the job has 300).
WARM_DEADLINE_SECONDS = 200
BUDGET_FIGURES = "ads-budget/figures.json"
BUDGET_SETTINGS = "ads-budget/settings.json"


def _sync_hard_stop(io, brand, account, token, settings, figures, get=None):
    """Keep Meta's account spending limit at the month's budget when the hard stop is on. Never raises."""
    out = {"on": bool(settings.get("hard_stop"))}
    try:
        ver = ads_brain.DEFAULT_API_VERSION
        getter = get or (lambda path, params: ads_brain._graph_get(path, token, params))
        got, err = getter(f"/{ver}/{account}", {"fields": ads_cap.FIELDS})
        if err or not got:
            out["error"] = f"account read: {err}"
            return out
        acct = ads_cap.parse_account(got)
        figures["account"] = acct
        if not settings.get("hard_stop"):
            return out
        graph = lambda method, path, tok, params=None: ads_actions.graph_call(  # noqa: E731
            method, path, tok, params, version=ver)
        p = ads_cap.plan(settings, acct, figures)
        lane = f"brands/{brand}/"
        entry = ads_cap.apply_plan(
            brand, p, settings, graph=graph, token=token, account_id=account,
            read=lambda rel: io.read(rel[len(lane):], allow_flat_fallback=False),
            write=lambda rel, obj: io.write(rel[len(lane):], obj), by="daily job")
        if entry:
            io.write(BUDGET_SETTINGS, settings)
        out.update({"plan": p, "set": bool(entry)})
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    return out


def _app_module():
    """The running app, which owns the Meta ingest. The server starts as `python app.py`, so it is `__main__`; when
    something imported it, it is `app`. None when this is not the app (tests, scripts)."""
    for name in ("app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and hasattr(m, "_v23_ingest_paid_media"):
            return m
    return None


def run(*, brand: str | None = None, today: _dt.date | None = None,
        get=None, get_as=None) -> dict:
    """Build today's brief for one brand. ``today``, ``get`` and ``get_as`` are for tests."""
    t0 = time.monotonic()
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

    history = win = history_error = None
    try:
        history = ads_history.fetch_weekly(
            lane_brand, account, token, get=get, today=today,
            previous=as_dict(io.read(HISTORY, allow_flat_fallback=False)))
        win = ads_history.winners(history)
    except Exception as exc:  # the brief below is still written
        history, history_error = None, type(exc).__name__

    # Tracking health: links, UTMs and what GA4 saw, per running ad. An add-on: never costs the brief.
    try:
        tags, flexible, tag_err = ads_tracking.fetch_tag_info(account, token, get=get)
        ga_rows, ga_err = ads_tracking.ga4_rows(lane_brand)
        io.write(TRACKING, ads_tracking.build(lane_brand, full["ads"], tags, ga_rows, today=today,
                                              errors=[e for e in (tag_err, ga_err) if e], flexible=flexible))
    except Exception:
        pass

    # Monthly budget: this month's spend and what the live ad sets will still spend. Like the history above,
    # an add-on: a failed read never costs the day's brief.
    try:
        settings = as_dict(io.read(BUDGET_SETTINGS, allow_flat_fallback=False))
        figures = ads_budget.fetch_figures(account, token, today=today, get=get,
                                           period=ads_budget.period_of(settings))
        hard_stop = _sync_hard_stop(io, lane_brand, account, token, settings, figures, get)
        io.write(BUDGET_FIGURES, figures)
        verdict = ads_budget.evaluate(figures, settings.get("monthly_budget"))
        daily["budget"] = ads_budget.brief_view(verdict)
        daily["budget"]["hard_stop"] = hard_stop
        if figures.get("complete"):
            ads_budget.add_action(daily, verdict)
    except Exception as exc:
        daily["budget"] = {"status": "UNKNOWN", "headline": f"Could not read the month's spend ({type(exc).__name__})."}

    # Creative loop: move open tests on, then propose new ones.
    tests = as_list(io.read(TESTS, allow_flat_fallback=False))
    organic = as_list(as_dict(io.read(ORGANIC, allow_flat_fallback=False)).get("outcomes"))
    tests = ads_creative.track(
        tests, full,
        lambda days: ads_brain.fetch_snapshot(lane_brand, account, token, days=days,
                                              insights_only=True, **kw),
        today)
    tests += ads_creative.plan(lane_brand, scored, full, organic, tests, today)
    # What to film for each proposed card, from the brand's own idea file.
    tests = ads_ideas.attach(tests, ads_ideas.load_bank(lane_brand), win)
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
    if history is not None:
        io.write(HISTORY, history)
        io.write(HISTORY_LATEST, {
            "schema": ads_history.SCHEMA, "brand_id": lane_brand, "date": daily["date"],
            "period": history["period"], "trends": ads_history.trends(history),
            "winners": win, "errors": history["errors"]})

    wrote_weekly = False
    if today.weekday() == 0 or not io.read(WEEKLY, allow_flat_fallback=False):
        weekly = ads_brief.build_weekly(daily, events, today)
        io.write(WEEKLY, weekly)
        io.write(f"ads-brief/weekly/{daily['date']}.json", weekly)
        wrote_weekly = True

    # Last, and only with time to spare: refresh the Meta ad cache the weekly report reads, so its first load of the
    # day is not the one that has to ingest. Only inside the running app, which owns the ingest; never costs the brief.
    app_module = _app_module()
    cache_warm: dict
    if app_module is None:
        cache_warm = {"skipped": "not running inside the app"}
    else:
        try:
            from ..layer1._io import data_dir
            cache_warm = ads_cache_warm.warm(lane_brand, ingest=app_module._v23_ingest_paid_media,
                                             data_dir=getattr(app_module, "DATA_DIR", None) or data_dir(),
                                             deadline=t0 + WARM_DEADLINE_SECONDS)
        except Exception as exc:
            cache_warm = {"error": type(exc).__name__}

    print(f"ads_brief cache_warm {lane_brand}: {cache_warm}", flush=True)  # shows in the Railway logs

    return {
        "ok": True, "brand": lane_brand, "date": daily["date"], "cache_warm": cache_warm,
        "headline": daily["headline"], "wrote_weekly": wrote_weekly,
        "scoring_version": daily["scoring_version"],
        "creative_tests": {k: len(daily["creative"][k]) for k in ("proposed", "running")},
        "organic": daily["creative"]["organic"],
        "history": ({"weeks_with_delivery": len({r["week"] for r in history["rows"]}),
                     "ads": win["ads_with_delivery"], "errors": history["errors"][:3]}
                    if history is not None else {"error": history_error}),
        "errors": daily["errors"][:3],
    }
