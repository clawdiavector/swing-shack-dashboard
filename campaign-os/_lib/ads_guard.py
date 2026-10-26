"""Budget guard: pause a brand's running ad sets when its monthly budget is used up.

Meta's own account spending limit did not stop delivery in the live test of 2026-10-20 (see the wiki page
research/meta-account-spending-limit-behaviour), so the stop is done here: a job checks each brand's month
spend against its budget every hour and pauses the running ad sets itself.

    plan()   decides, from this month's figures and the running ad sets, whether to pause and which. Pure.
    act()    pauses each target, logs each pause so it can be undone, and never pauses on a failed read.

Off by default. Per brand it acts only when ``auto_pause`` is on in ads-budget/settings.json AND one-click ad
changes are switched on (ADS_WRITES_ENABLED). With it off, the same job still writes what it WOULD pause (a dry
run), which the page shows.

It pauses; it never resumes. A new month gives the budget back but a person turns the ad sets on again, since
that spends money. A person who resumes an ad set in the middle of a used-up month will see it paused again at the
next hourly check, until the budget is raised on purpose.
"""
from __future__ import annotations

import datetime as _dt
import json
import uuid

from . import ads_actions, ads_brain, ads_budget

SCHEMA = "https://campaign-os/ads-guard/v1"
KIND_SET = "pause_adset"
GUARD = "budget guard"
_ADSET_FIELDS = "id,name,effective_status,end_time,campaign{id,name}"


def trigger(figures: dict, budget) -> dict:
    """Is the budget used up, or will the next hour use it up? A failed read never triggers."""
    w = ads_budget.word((figures or {}).get("period"))
    if not budget:
        return {"go": False, "reason": f"No {w}ly budget is set."}
    if not figures or not figures.get("complete"):
        return {"go": False, "reason": f"This {w}'s spend could not be read, so nothing is paused."}
    mtd = figures.get("mtd_spend") or 0.0
    # One hour of the live ad sets' daily budgets (with Meta's usual quarter of over-delivery): what could be
    # spent before the next check.
    hour = (figures.get("daily_run_rate") or 0.0) / 24.0 * ads_budget.OVERDELIVERY
    if mtd >= budget:
        return {"go": True, "reason": f"The {w}'s budget of R{budget:,.0f} is used up (R{mtd:,.0f} spent)."}
    if mtd + hour >= budget:
        return {"go": True, "reason": f"R{budget - mtd:,.0f} of the {w}'s R{budget:,.0f} budget is left, less than the next "
                                      f"hour can spend (about R{hour:,.0f})."}
    return {"go": False, "reason": f"Within the {w}'s budget: R{mtd:,.0f} of R{budget:,.0f} spent."}


def running_sets(rows: list[dict], now: _dt.datetime) -> list[dict]:
    """Ad sets that can still deliver: active and not past their end date."""
    out = []
    for s in rows or []:
        if s.get("effective_status") not in (None, "ACTIVE"):
            continue
        end = ads_brain._parse_time(s.get("end_time"))
        if end and end < now:
            continue
        out.append({"id": str(s["id"]), "name": s.get("name"), "campaign": (s.get("campaign") or {}).get("name")})
    return out


def plan(settings: dict, figures: dict | None, running: list[dict]) -> dict:
    """What the guard would do now. Pure."""
    t = trigger(figures or {}, (settings or {}).get("monthly_budget"))
    enabled = bool((settings or {}).get("auto_pause")) and ads_actions.writes_enabled()
    return {"enabled": enabled, "auto_pause": bool((settings or {}).get("auto_pause")),
            "writes_enabled": ads_actions.writes_enabled(), "trigger": t["go"], "reason": t["reason"],
            "targets": list(running) if t["go"] else [], "running": len(running)}


def fetch_running(account_id: str, token: str, *, now: _dt.datetime, api_version: str | None = None, get=None):
    """Running ad sets from Meta (read-only). Returns (list, error)."""
    ver = api_version or ads_brain.DEFAULT_API_VERSION
    if get is None:
        def get(path, params):
            return ads_brain._graph_get(path, token, params)
    rows, err = ads_brain._get_all(get, f"/{ver}/{account_id}/adsets", {
        "fields": _ADSET_FIELDS, "limit": 200,
        "filtering": json.dumps([{"field": "effective_status", "operator": "IN", "value": ["ACTIVE"]}])})
    return running_sets(rows or [], now), err


def _entry(kind, obj_id, name, by, note=None):
    e = {"id": uuid.uuid4().hex[:12], "at": ads_actions._now(), "by": by, "kind": kind,
         "ad_id": obj_id, "ad_name": name, "before": "ACTIVE", "after": "PAUSED", "undone_at": None}
    if note:
        e["note"] = note
    return e


def _pause_one_set(adset: dict, *, graph, token: str, account_id: str):
    """Pause the ad set. Meta re-checks an ad set's whole settings on an edit and can refuse (a budget under its
    minimum), so if it refuses, pause the ad set's running ads one by one instead. Returns (kind, [objects])."""
    a = graph("GET", adset["id"], token, {"fields": "id,name,status,account_id"})
    if f"act_{a.get('account_id')}" != account_id:
        raise ads_actions.ActionRefused("That ad set does not belong to this brand's ad account.", 403)
    if a.get("status") != "ACTIVE":
        return None, []
    try:
        res = graph("POST", adset["id"], token, {"status": "PAUSED"})
        if res.get("success"):
            return KIND_SET, [(adset["id"], adset.get("name"))]
    except ads_actions.ActionRefused:
        pass
    ads = graph("GET", f"{adset['id']}/ads", token, {"fields": "id,name,status", "limit": 100}).get("data") or []
    done = []
    for ad in ads:
        if ad.get("status") == "ACTIVE" and graph("POST", ad["id"], token, {"status": "PAUSED"}).get("success"):
            done.append((ad["id"], ad.get("name")))
    return "pause_ad", done


def act(brand_id: str, p: dict, *, graph, token: str, account_id: str, read, write) -> list[dict]:
    """Carry out a plan that is enabled and triggered. Returns the log entries written (one per thing paused)."""
    if not (p.get("enabled") and p.get("trigger")):
        return []
    entries = ads_actions.load_log(brand_id, read)
    made = []
    for adset in p["targets"]:
        try:
            kind, objs = _pause_one_set(adset, graph=graph, token=token, account_id=account_id)
        except ads_actions.ActionRefused as exc:
            made.append({"error": str(exc), "adset": adset["id"]})
            continue
        for obj_id, name in objs:
            note = None if kind == KIND_SET else f"in ad set {adset.get('name')} (Meta refused to pause the ad set)"
            e = _entry(kind, obj_id, name, GUARD, note)
            entries.append(e)
            made.append(e)
    if any("id" in m for m in made):
        ads_actions._save(brand_id, entries, write)
    return made


def guarded(entries: list[dict]) -> list[dict]:
    """The pauses this guard made that are still in force (not undone), newest first."""
    return [e for e in reversed(entries or []) if e.get("by") == GUARD and not e.get("undone_at")]
