"""Monthly ad budget per brand: where the month stands, where it is heading, and whether it fits.

Read-only on Meta. Two halves:

    figures()    reads this month's spend and the live ad sets' budgets from Meta (by the ads_brief job, daily)
                 and keeps the plain numbers, with no budget attached.
    evaluate()   puts a monthly budget against those numbers. Pure. The page calls it every time, so changing
                 the budget shows the new picture at once without another read of Meta.

A person sets the budget. This module never changes an ad. The projection is spend so far plus what the live
ad sets are set to spend for the rest of the month (daily budgets until their end date, the unspent part of a
lifetime budget). Meta may spend up to a quarter more than a daily budget on a day, evened out over the week,
so a worst case at 1.25 times the daily run rate is shown as well.
"""
from __future__ import annotations

import calendar
import datetime as _dt
import json

from . import ads_brain

SCHEMA = "https://campaign-os/ads-budget/v1"
OVERDELIVERY = 1.25
SAST = _dt.timezone(_dt.timedelta(hours=2))
# Share of the budget at which a projection is called out before it is over.
WATCH_AT = 1.0


def _major(minor) -> float:
    """Meta budgets come as strings in the currency's smallest unit (cents)."""
    try:
        return float(minor) / 100.0
    except (TypeError, ValueError):
        return 0.0


def _date(value):
    d = ads_brain._parse_time(value)
    return d.astimezone(SAST).date() if d else None


def month_bounds(today: _dt.date) -> tuple[_dt.date, _dt.date]:
    return today.replace(day=1), today.replace(day=calendar.monthrange(today.year, today.month)[1])


def _live_budgets(adsets: list[dict], today: _dt.date, month_end: _dt.date) -> tuple[list[dict], float, float]:
    """Each running budget once, with what it is still expected to spend this month.

    Returns (rows, daily_live_today, future_total). A campaign-level budget is counted once, however many
    ad sets sit under it, and an ad set with its own budget never also counts its campaign's.
    """
    rows, seen_campaigns = [], set()
    daily_today, future = 0.0, 0.0
    after_today = today + _dt.timedelta(days=1)
    for s in adsets:
        if s.get("effective_status") not in (None, "ACTIVE"):
            continue
        end = _date(s.get("end_time"))
        start = _date(s.get("start_time"))
        camp = s.get("campaign") or {}
        d_daily, d_life = _major(s.get("daily_budget")), _major(s.get("lifetime_budget"))
        key, name, rem = s.get("id"), s.get("name"), _major(s.get("budget_remaining"))
        if not d_daily and not d_life:
            cid = s.get("campaign_id") or camp.get("id")
            if cid in seen_campaigns:
                continue
            seen_campaigns.add(cid)
            d_daily, d_life = _major(camp.get("daily_budget")), _major(camp.get("lifetime_budget"))
            key, name = cid, camp.get("name") or name
            rem = d_life
        if not d_daily and not d_life:
            continue
        if end and end < today:
            continue
        first = max(after_today, start or after_today)
        last = min(month_end, end) if end else month_end
        live_today = (not start or start <= today) and (not end or end >= today)
        if d_daily:
            days = max(0, (last - first).days + 1)
            expected = d_daily * days
            if live_today:
                daily_today += d_daily
            rows.append({"id": key, "name": name, "kind": "daily", "amount": d_daily,
                         "days_left": days, "expected": round(expected, 2),
                         "ends": end.isoformat() if end else None})
            future += expected
        else:
            total_days = max(1, ((end or month_end) - today).days + 1)
            month_days = max(0, (month_end - today).days + 1)
            share = min(1.0, month_days / total_days) if end and end > month_end else 1.0
            expected = max(0.0, rem) * share
            rows.append({"id": key, "name": name, "kind": "lifetime", "amount": d_life,
                         "days_left": month_days, "expected": round(expected, 2),
                         "ends": end.isoformat() if end else None})
            future += expected
    return rows, daily_today, future


def build_figures(*, mtd_spend: float, today_spend: float, adsets: list[dict], today: _dt.date,
                  errors: list | None = None) -> dict:
    """The plain numbers, from what was read. Pure."""
    first, last = month_bounds(today)
    rows, daily_today, future = _live_budgets(adsets, today, last)
    # Today is partly spent already: only what is left of today's budgets is still to come.
    left_today = max(0.0, daily_today - today_spend)
    daily_after = sum(r["amount"] for r in rows if r["kind"] == "daily" and r["days_left"] > 0)
    return {
        "schema": SCHEMA, "month": first.strftime("%Y-%m"), "as_of": today.isoformat(),
        "days_left_after_today": (last - today).days,
        "mtd_spend": round(mtd_spend, 2), "today_spend": round(today_spend, 2),
        "daily_run_rate": round(daily_after, 2),
        "expected_rest_of_month": round(future + left_today, 2),
        "worst_case_rest_of_month": round(future * OVERDELIVERY + left_today * OVERDELIVERY, 2),
        "sets": sorted(rows, key=lambda r: -r["expected"]),
        "errors": list(errors or [])[:3],
    }


def evaluate(figures: dict, budget) -> dict:
    """Put a monthly budget against the figures. Pure; ``budget`` of None or 0 means none is set."""
    f = dict(figures or {})
    mtd = f.get("mtd_spend") or 0.0
    projected = round(mtd + (f.get("expected_rest_of_month") or 0.0), 2)
    worst = round(mtd + (f.get("worst_case_rest_of_month") or 0.0), 2)
    f.update({"budget": budget or None, "projected_total": projected, "worst_case_total": worst})
    days = f.get("days_left_after_today") or 0
    if not budget:
        f.update({"status": "NO_BUDGET", "headline": "No monthly budget set yet.", "left": None, "safe_per_day": None})
        return f
    left = round(budget - mtd, 2)
    f["left"] = left
    f["used_pct"] = round(100 * mtd / budget, 1)
    f["safe_per_day"] = round(left / days, 2) if days > 0 and left > 0 else (0.0 if left <= 0 else round(left, 2))
    if mtd >= budget:
        status, head = "OVER", f"The month's budget of {_r(budget)} is already spent ({_r(mtd)}). Pause the running ad sets."
    elif projected > budget * WATCH_AT:
        status, head = "AT_RISK", (f"On the current settings the month ends near {_r(projected)}, "
                                   f"over the {_r(budget)} budget by {_r(projected - budget)}.")
    elif worst > budget:
        status, head = "WATCH", (f"Fits on paper ({_r(projected)}), but Meta may spend up to a quarter more on a "
                                 f"day: worst case {_r(worst)}.")
    else:
        status, head = "OK", f"On track: {_r(projected)} expected of a {_r(budget)} budget."
    f.update({"status": status, "headline": head})
    return f


def _r(x) -> str:
    return f"R{x:,.0f}"


def brief_view(ev: dict) -> dict:
    """The part of an evaluation that goes into the daily brief."""
    keys = ("month", "as_of", "budget", "mtd_spend", "projected_total", "worst_case_total", "left",
            "safe_per_day", "daily_run_rate", "status", "headline", "complete")
    return {k: ev.get(k) for k in keys}


def add_action(daily: dict, ev: dict, limit: int = 3) -> None:
    """Put an over-budget warning first among the brief's top actions. Scoring is frozen, so this is not a rule."""
    if ev.get("status") not in ("OVER", "AT_RISK"):
        return
    over = ev["status"] == "OVER"
    action = {
        "rule": "monthly_budget", "status": ev["status"], "severity": "high",
        "action": ("Pause the running ad sets: the monthly budget is spent." if over else
                   "Bring the ad sets' daily budgets down, or raise the monthly budget on purpose."),
        "why": ev["headline"], "ads": [], "ad_ids": [], "days_open": 0,
    }
    daily["top_actions"] = ([action] + [a for a in daily.get("top_actions") or []
                                        if a.get("rule") != "monthly_budget"])[:limit]


# ── Meta read (read-only) ───────────────────────────────────────────────────

_ADSET_FIELDS = ("id,name,effective_status,daily_budget,lifetime_budget,budget_remaining,start_time,end_time,"
                 "campaign_id,campaign{id,name,daily_budget,lifetime_budget}")


def fetch_figures(account_id: str, token: str, *, today: _dt.date, api_version: str | None = None,
                  get=None) -> dict:
    ver = api_version or ads_brain.DEFAULT_API_VERSION
    if get is None:
        def get(path, params):
            return ads_brain._graph_get(path, token, params)
    base = f"/{ver}/{account_id}"
    errors = []
    first, _ = month_bounds(today)

    def spend(since, until):
        got, err = ads_brain._get_all(get, f"{base}/insights", {
            "fields": "spend", "time_range": json.dumps({"since": since.isoformat(), "until": until.isoformat()})})
        if err:
            errors.append(f"spend {since}..{until}: {err}")
            return None
        return sum(float(r.get("spend") or 0) for r in got)

    mtd, tod = spend(first, today), spend(today, today)
    sets, err = ads_brain._get_all(get, f"{base}/adsets", {
        "fields": _ADSET_FIELDS, "limit": 200,
        "filtering": json.dumps([{"field": "effective_status", "operator": "IN", "value": ["ACTIVE"]}])})
    if err:
        errors.append(f"ad sets: {err}")
        sets = []
    out = build_figures(mtd_spend=mtd or 0.0, today_spend=tod or 0.0, adsets=sets, today=today, errors=errors)
    # A figure Meta would not give is not zero: say so, so the page never shows a false all-clear.
    out["complete"] = mtd is not None and tod is not None and not err
    return out
