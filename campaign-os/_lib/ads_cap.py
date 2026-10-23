"""Hard stop for the monthly ad budget, using Meta's own account spending limit.

The monthly budget (ads_budget) only warns. This module can make it a real stop: Meta lets an ad account carry a
spending limit (``spend_cap``). When the spend counted against it reaches the limit, Meta stops delivering every ad
in the account. Meta enforces it, so it holds even if Campaign OS is down.

What the live test on 2026-10-20 showed about Meta's behaviour (the first version of this module assumed otherwise):

* Writing ``spend_cap`` takes whole rand; reading it back gives cents (R1,000 is written 1000 and read as 100000).
* A new limit counts only spend made AFTER it is set, and setting it resets the account's ``amount_spent`` counter
  to zero. So the limit is the room left this month, not a lifetime figure.
* ``spend_cap=0`` is ignored. The limit is removed with ``spend_cap_action=delete``.

So the limit is kept at

    the monthly budget - spend so far this month        (the room left)

and set again each day and whenever the budget changes. On the 1st the month's spend is 0, so the same rule gives
the new month a fresh budget.

Off by default. Per brand it is on only after a person has turned it on, and turning it off puts back the limit the
account had before (none, today). It never touches an ad, only the account limit. Every change is logged.
"""
from __future__ import annotations

import datetime as _dt

from . import ads_actions

FIELDS = "amount_spent,spend_cap,currency,account_status"
LOG_KIND = "set_spend_cap"


def _need_writes() -> None:
    if not ads_actions.writes_enabled():
        raise ads_actions.ActionRefused("One-click ad changes are switched off.", 403)


def desired_cap(mtd_spend: float, budget: float) -> int:
    """The room left this month, in whole rand, for Meta's limit to count from now.

    Rounded down so the limit never allows more than the budget. When the budget is already used up the limit is
    R1: Meta stops delivery after about that much more spend, which is as close to "now" as Meta allows.
    """
    return max(1, int(budget - (mtd_spend or 0.0)))


def read_account(graph, token: str, account_id: str) -> dict:
    return parse_account(graph("GET", account_id, token, {"fields": FIELDS}))


def parse_account(a: dict) -> dict:
    return {"amount_spent": int(a.get("amount_spent") or 0), "spend_cap": int(a.get("spend_cap") or 0),
            "currency": a.get("currency"), "account_status": a.get("account_status")}


def plan(settings: dict, account: dict, figures: dict | None) -> dict:
    """What the sync would do, without doing it. Pure."""
    budget = (settings or {}).get("monthly_budget")
    if not (settings or {}).get("hard_stop"):
        return {"action": "none", "reason": "Hard stop is off."}
    if not budget:
        return {"action": "none", "reason": "No monthly budget is set."}
    if account.get("currency") not in (None, "ZAR"):
        return {"action": "none", "reason": f"Account currency is {account.get('currency')}, not ZAR."}
    if not figures or not figures.get("complete"):
        return {"action": "none", "reason": "This month's spend could not be read, so no limit was set."}
    managed = (settings or {}).get("cap_managed") or {}
    existing = account.get("spend_cap") or 0
    # A limit somebody else set is theirs: only replace one we put there ourselves.
    if existing and existing != (managed.get("last_set") or 0) * 100:
        return {"action": "blocked", "reason": "The account already has a spending limit that Campaign OS did not set "
                                                "(R%.0f). Remove it in Ads Manager first." % (existing / 100)}
    cap = desired_cap(figures.get("mtd_spend") or 0.0, budget)
    if existing == cap * 100:
        return {"action": "none", "reason": "The limit is already right.", "cap": cap}
    over = (budget - (figures.get("mtd_spend") or 0.0)) < 1
    return {"action": "set", "cap": cap, "previous": existing, "stops_now": over, "room": cap}


def apply_plan(brand_id: str, p: dict, settings: dict, *, graph, token: str, account_id: str, read, write,
               by: str = "hard stop") -> dict | None:
    """Carry out a ``set`` plan: write the limit to Meta, log it, remember what to put back. Returns the log entry."""
    if p.get("action") != "set":
        return None
    _need_writes()
    res = graph("POST", account_id, token, {"spend_cap": str(p["cap"])})
    if not res.get("success"):
        raise ads_actions.ActionRefused("Meta did not confirm the spending limit. Check Ads Manager.", 502)
    managed = dict((settings or {}).get("cap_managed") or {})
    managed.setdefault("previous_cap", p["previous"])  # cents, as Meta reports it
    managed.update({"last_set": p["cap"], "at": ads_actions._now()})
    settings["cap_managed"] = managed
    entry = {"id": ads_actions.uuid.uuid4().hex[:12], "at": ads_actions._now(), "by": by, "kind": LOG_KIND,
             "ad_id": None, "ad_name": "Account spending limit", "before": p["previous"] / 100, "after": p["cap"],
             "undone_at": None}
    entries = ads_actions.load_log(brand_id, read)
    entries.append(entry)
    ads_actions._save(brand_id, entries, write)
    return entry


def release(brand_id: str, settings: dict, account: dict, *, graph, token: str, account_id: str, read, write,
            by: str = "dashboard") -> dict | None:
    """Turn the hard stop off: put back the limit the account had before ours. Only if ours is still in place."""
    managed = (settings or {}).get("cap_managed") or {}
    if not managed:
        return None
    _need_writes()
    if account.get("spend_cap") and account["spend_cap"] != (managed.get("last_set") or 0) * 100:
        raise ads_actions.ActionRefused("The account limit is no longer the one Campaign OS set, so it was changed "
                                        "somewhere else. Check Ads Manager.", 409)
    previous = int(managed.get("previous_cap") or 0)
    # Meta ignores spend_cap=0; the limit is removed with an action. A limit that existed before is put back in rand.
    res = graph("POST", account_id, token, {"spend_cap": str(previous // 100)} if previous else {"spend_cap_action": "delete"})
    if not res.get("success"):
        raise ads_actions.ActionRefused("Meta did not confirm removing the limit. Check Ads Manager.", 502)
    entry = {"id": ads_actions.uuid.uuid4().hex[:12], "at": ads_actions._now(), "by": by, "kind": LOG_KIND,
             "ad_id": None, "ad_name": "Account spending limit",
             "before": (account.get("spend_cap") or 0) / 100, "after": previous / 100, "undone_at": None, "note": "hard stop turned off"}
    entries = ads_actions.load_log(brand_id, read)
    entries.append(entry)
    ads_actions._save(brand_id, entries, write)
    settings.pop("cap_managed", None)
    return entry


def view(settings: dict, account: dict | None, p: dict | None) -> dict:
    """What the page shows about the hard stop."""
    return {
        "on": bool((settings or {}).get("hard_stop")),
        "cap": (account or {}).get("spend_cap"), "amount_spent": (account or {}).get("amount_spent"),
        "plan": p, "writes_enabled": ads_actions.writes_enabled(),
    }
