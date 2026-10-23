"""Hourly budget guard: pause a brand's running ad sets when its monthly budget is used up.

Reads this month's spend and the running ad sets from Meta, decides with _lib.ads_guard, and, only when the brand
has switched ``auto_pause`` on, pauses them and logs each pause (undoable). Always writes what it found, so the page
can show a dry run. See _lib/ads_guard.py.
"""

from __future__ import annotations

import datetime as _dt

from _lib import ads_actions, ads_brain, ads_brief, ads_budget, ads_guard
from _lib.brand_validate import validate_brand_id

from ..layer1._io import as_dict, io_for_job

JOB_NAME = "ads_budget_guard"
SETTINGS = "ads-budget/settings.json"
FIGURES = "ads-budget/figures.json"
GUARD = "ads-budget/guard.json"
LOG = "ads-actions/log.json"


def run(*, brand: str | None = None, today: _dt.date | None = None, now: _dt.datetime | None = None,
        get=None, graph=None) -> dict:
    """``today``, ``now``, ``get`` and ``graph`` are for tests."""
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
    now = now or _dt.datetime.now(_dt.timezone.utc)
    io = io_for_job(JOB_NAME, lane_brand)
    settings = as_dict(io.read(SETTINGS, allow_flat_fallback=False))

    figures = ads_budget.fetch_figures(account, token, today=today, get=get)
    running, err = ads_guard.fetch_running(account, token, now=now, get=get)
    if err:
        figures["complete"] = False  # not knowing which ad sets run is not a reason to pause (or to say all is well)
        figures.setdefault("errors", []).append(f"ad sets: {err}")
    p = ads_guard.plan(settings, figures, running)

    made = []
    if p["enabled"] and p["trigger"]:
        graph = graph or (lambda method, path, tok, params=None: ads_actions.graph_call(
            method, path, tok, params, version=ads_brain.DEFAULT_API_VERSION))
        lane = f"brands/{lane_brand}/"
        made = ads_guard.act(
            lane_brand, p, graph=graph, token=token, account_id=account,
            read=lambda rel: io.read(rel[len(lane):], allow_flat_fallback=False),
            write=lambda rel, obj: io.write(rel[len(lane):], obj))

    out = {"schema": ads_guard.SCHEMA, "brand_id": lane_brand, "at": now.isoformat(timespec="seconds"),
           "plan": p, "paused": [m for m in made if "id" in m], "errors": [m for m in made if "error" in m],
           "mtd_spend": figures.get("mtd_spend"), "budget": settings.get("monthly_budget")}
    io.write(GUARD, out)
    return {"ok": True, "brand": lane_brand, "enabled": p["enabled"], "trigger": p["trigger"],
            "reason": p["reason"], "would_pause": len(p["targets"]), "paused": len(out["paused"]),
            "errors": len(out["errors"])}
