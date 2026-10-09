"""Ads history — a year of weekly numbers for every ad, and what they add up to.

Meta keeps the history, so nothing is accumulated here: each run re-reads the
weeks and replaces the file. Three steps, the first read-only on Meta and the
other two pure:

    fetch_weekly()   Ad-level insights in whole Monday-to-Sunday weeks, in
                     chunks that fail independently, plus each ad's text and
                     how long its video was watched.
    trends()         Per-week totals for the charts, and the last four weeks
                     against the four before.
    winners()        Per-ad totals over the whole period, ranked by cost per
                     result among ads that were bought for the same result.

Nothing here scores an ad or changes one. Scoring stays in ads_brain and stays
on its 31-day window; this is the longer view beside it.
"""
from __future__ import annotations

import datetime as _dt
import json

from . import ads_brain, ads_creative

SCHEMA = "https://campaign-os/ads-history/v1"

WEEKS = 52
CHUNK_WEEKS = 13
CHART_WEEKS = 26

_KEYS = ("spend", "impressions", "link_clicks", "landing_page_views", "leads", "messages",
         "video_views")
_WATCH_FIELDS = (
    "ad_id,video_play_actions,video_thruplay_watched_actions,video_p25_watched_actions,"
    "video_p50_watched_actions,video_p75_watched_actions,video_p100_watched_actions,"
    "video_avg_time_watched_actions"
)
_CREATIVE_FIELDS = (
    "id,name,effective_status,adset{optimization_goal},"
    "creative{id,body,title,call_to_action_type,object_type,video_id,image_url,"
    "thumbnail_url,object_story_spec}"
)

# What an ad was bought for: (key, label, results needed before its cost means
# anything). The same floors the creative tests use. The ad set's goal says it
# best; the campaign objective is the fallback for ads whose settings are gone.
_RESULT_FOR_GOAL = {
    "LEAD_GENERATION": ("leads", "lead", 10),
    "QUALITY_LEAD": ("leads", "lead", 10),
    "CONVERSATIONS": ("messages", "chat", 10),
    "LANDING_PAGE_VIEWS": ("landing_page_views", "page visit", 100),
    "LINK_CLICKS": ("landing_page_views", "page visit", 100),
}
_NO_RESULT_GOALS = ("REACH", "IMPRESSIONS", "AD_RECALL_LIFT", "THRUPLAY")
_RESULT_FOR_OBJECTIVE = {
    "OUTCOME_LEADS": ("leads", "lead", 10),
    "LEAD_GENERATION": ("leads", "lead", 10),
    "MESSAGES": ("messages", "chat", 10),
    "OUTCOME_TRAFFIC": ("landing_page_views", "page visit", 100),
    "LINK_CLICKS": ("landing_page_views", "page visit", 100),
}
_NO_RESULT_OBJECTIVES = ("OUTCOME_AWARENESS", "REACH", "BRAND_AWARENESS", "VIDEO_VIEWS")
RESULT_ORDER = ("leads", "messages", "landing_page_views")


def last_full_week(today: _dt.date) -> _dt.date:
    """Monday of the most recent week that has fully ended."""
    return today - _dt.timedelta(days=today.weekday() + 7)


def week_starts(today: _dt.date, weeks: int = WEEKS) -> list:
    last = last_full_week(today)
    return [(last - _dt.timedelta(weeks=i)).isoformat() for i in range(weeks - 1, -1, -1)]


def _first(actions) -> float:
    """Meta returns video metrics as a one-item action list."""
    for a in actions or []:
        v = ads_brain._num(a.get("value"))
        if v is not None:
            return v
    return 0.0


def _watch(row: dict) -> dict:
    return {
        "plays": int(_first(row.get("video_play_actions"))),
        "thruplays": int(_first(row.get("video_thruplay_watched_actions"))),
        "p25": int(_first(row.get("video_p25_watched_actions"))),
        "p50": int(_first(row.get("video_p50_watched_actions"))),
        "p75": int(_first(row.get("video_p75_watched_actions"))),
        "p100": int(_first(row.get("video_p100_watched_actions"))),
        "avg_seconds": round(_first(row.get("video_avg_time_watched_actions")), 1),
    }


def fetch_weekly(brand_id: str, account_id: str, token: str, *, weeks: int = WEEKS,
                 api_version: str | None = None, get=None, today: _dt.date | None = None,
                 previous: dict | None = None) -> dict:
    """Read ``weeks`` whole weeks at ad level. ``previous`` is the last file
    written: a chunk Meta refuses today keeps the weeks it had yesterday."""
    ver = api_version or ads_brain.DEFAULT_API_VERSION
    if get is None:
        def get(path, params):
            return ads_brain._graph_get(path, token, params)
    today = today or _dt.date.today()
    starts = week_starts(today, weeks)
    base = f"/{ver}/{account_id}"
    previous = previous or {}
    errors, rows = [], []

    for i in range(0, len(starts), CHUNK_WEEKS):
        chunk = starts[i:i + CHUNK_WEEKS]
        until = (_dt.date.fromisoformat(chunk[-1]) + _dt.timedelta(days=6)).isoformat()
        got, err = ads_brain._get_all(get, f"{base}/insights", {
            "level": "ad", "fields": ads_brain._INSIGHT_FIELDS, "limit": 500,
            "time_increment": 7,
            "time_range": json.dumps({"since": chunk[0], "until": until})})
        if err:
            errors.append(f"weeks {chunk[0]} to {until}: {err}")
            rows += [r for r in previous.get("rows") or [] if r.get("week") in chunk]
            continue
        for r in got:
            # A row with no week cannot be placed on a chart.
            if r.get("date_start") not in chunk or not r.get("ad_id"):
                continue
            m = ads_brain._metrics(r)
            rows.append(dict(
                {k: m[k] for k in _KEYS}, week=r["date_start"], ad_id=r["ad_id"],
                ad_name=r.get("ad_name"), campaign_id=r.get("campaign_id"),
                campaign_name=r.get("campaign_name"), objective=r.get("objective")))

    since = starts[0]
    until = (_dt.date.fromisoformat(starts[-1]) + _dt.timedelta(days=6)).isoformat()
    # Asked for on their own so an unsupported field cannot take the weeks down.
    got, err = ads_brain._get_all(get, f"{base}/insights", {
        "level": "ad", "fields": _WATCH_FIELDS, "limit": 500,
        "time_range": json.dumps({"since": since, "until": until})})
    if err:
        errors.append(f"video watch time: {err}")
        watch = previous.get("watch") or {}
    else:
        watch = {r["ad_id"]: w for r in got if r.get("ad_id")
                 for w in [_watch(r)] if w["plays"] or w["thruplays"]}

    got, err = ads_brain._get_all(get, f"{base}/ads", {"fields": _CREATIVE_FIELDS, "limit": 100})
    if err:
        errors.append(f"ad text: {err}")
        creatives = previous.get("creatives") or {}
    else:
        creatives = {}
        for a in got:
            c = ads_brain._creative(a.get("creative"))
            creatives[a.get("id")] = {
                "body": c["body"], "title": c["title"], "media_type": c["media_type"],
                "cta": c["cta"], "effective_status": a.get("effective_status"),
                "optimization_goal": (a.get("adset") or {}).get("optimization_goal")}

    return {
        "schema": SCHEMA, "brand_id": brand_id, "ad_account_id": account_id,
        "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "period": {"since": since, "until": until, "weeks": weeks},
        "rows": sorted(rows, key=lambda r: (r["week"], r["ad_id"])),
        "watch": watch, "creatives": creatives, "errors": errors,
    }


# ── trends ───────────────────────────────────────────────────────────────

def _is_lead_row(r: dict) -> bool:
    return (r.get("objective") or "").upper() in ("OUTCOME_LEADS", "LEAD_GENERATION") \
        or bool(r.get("leads"))


def _week_total(week: str, rows: list) -> dict:
    t = {k: sum(r.get(k) or 0 for r in rows) for k in _KEYS}
    t["spend"] = round(t["spend"], 2)
    # Spend on lead campaigns, so a week they ran and got nothing still costs.
    lead_spend = sum(r.get("spend") or 0 for r in rows if _is_lead_row(r))
    t["lead_spend"] = round(lead_spend, 2)
    t["cost_per_lead"] = round(lead_spend / t["leads"], 2) if t["leads"] else None
    t["week"] = week
    t["ads"] = sum(1 for r in rows if (r.get("spend") or 0) > 0)
    return t


def _block(weeks: list) -> dict:
    t = {k: round(sum(w[k] for w in weeks), 2) for k in _KEYS + ("lead_spend",)}
    t["cost_per_lead"] = round(t["lead_spend"] / t["leads"], 2) if t["leads"] else None
    return t


def trends(history: dict, chart_weeks: int = CHART_WEEKS) -> dict:
    """Every week in the period, including the ones with no delivery, so a
    pause shows as a gap and not as a shorter chart."""
    period = history.get("period") or {}
    if not period.get("since"):
        return {"weeks": [], "last_4": None, "prior_4": None, "change": {}}
    start = _dt.date.fromisoformat(period["since"])
    by_week: dict = {}
    for r in history.get("rows") or []:
        by_week.setdefault(r["week"], []).append(r)
    weeks = []
    for i in range(period.get("weeks") or 0):
        w = (start + _dt.timedelta(weeks=i)).isoformat()
        weeks.append(_week_total(w, by_week.get(w, [])))
    # Do not chart the empty run before the account's first week of delivery.
    first = next((i for i, w in enumerate(weeks) if w["spend"] > 0), len(weeks))
    weeks = weeks[max(first, len(weeks) - chart_weeks):]
    last, prior = weeks[-4:], weeks[-8:-4]
    out = {"weeks": weeks, "last_4": _block(last) if len(last) == 4 else None,
           "prior_4": _block(prior) if len(prior) == 4 else None, "change": {}}
    if out["last_4"] and out["prior_4"]:
        for k in ("spend", "leads", "cost_per_lead", "landing_page_views"):
            cur, prev = out["last_4"][k], out["prior_4"][k]
            out["change"][k] = round((cur - prev) / prev, 3) if cur is not None and prev else None
    return out


# ── winners ──────────────────────────────────────────────────────────────

opening = ads_creative.opening


def _result(goal, objective, totals: dict):
    goal, objective = (goal or "").upper(), (objective or "").upper()
    if goal in _RESULT_FOR_GOAL:
        return _RESULT_FOR_GOAL[goal]
    if goal in _NO_RESULT_GOALS:
        return None
    if objective in _RESULT_FOR_OBJECTIVE:
        return _RESULT_FOR_OBJECTIVE[objective]
    if objective in _NO_RESULT_OBJECTIVES:
        return None
    # Nothing says what it was bought for: go by what it mostly produced. A
    # chat campaign that picked up one stray lead is still a chat campaign.
    if totals.get("leads") or totals.get("messages"):
        if totals.get("messages", 0) > totals.get("leads", 0):
            return "messages", "chat", 10
        return "leads", "lead", 10
    if totals.get("landing_page_views"):
        return "landing_page_views", "page visit", 100
    return None


def winners(history: dict, top: int = 5) -> dict:
    """Per-ad totals over the period. Ads are only compared with ads bought for
    the same result, and only called proven past the same floor the creative
    tests use."""
    period = history.get("period") or {}
    creatives = history.get("creatives") or {}
    watch = history.get("watch") or {}
    last_week = ((_dt.date.fromisoformat(period["until"]) - _dt.timedelta(days=6)).isoformat()
                 if period.get("until") else None)
    by_ad: dict = {}
    for r in history.get("rows") or []:
        by_ad.setdefault(r["ad_id"], []).append(r)

    ads = []
    for ad_id, rows in by_ad.items():
        rows = [r for r in rows if (r.get("spend") or 0) > 0 or (r.get("impressions") or 0) > 0]
        if not rows:
            continue
        latest = max(rows, key=lambda r: r["week"])
        t = {k: sum(r.get(k) or 0 for r in rows) for k in _KEYS}
        t["spend"] = round(t["spend"], 2)
        c = creatives.get(ad_id) or {}
        res = _result(c.get("optimization_goal"), latest.get("objective"), t)
        count = t[res[0]] if res else 0
        w = watch.get(ad_id)
        ads.append({
            "ad_id": ad_id, "ad_name": latest.get("ad_name"),
            "campaign_name": latest.get("campaign_name"), "objective": latest.get("objective"),
            "first_week": min(r["week"] for r in rows), "last_week": latest["week"],
            "weeks_active": len({r["week"] for r in rows}),
            "still_running": latest["week"] == last_week,
            "format": c.get("media_type"), "opening": opening(c.get("body")),
            "title": c.get("title"),
            "themes": sorted(ads_creative.subject(
                latest.get("campaign_name"), latest.get("ad_name"), c.get("title"), c.get("body"))),
            **t,
            "result": ({"key": res[0], "label": res[1], "count": count,
                        "cost": round(t["spend"] / count, 2) if count else None,
                        "proven": count >= res[2]} if res else None),
            # Share of impressions that watched three seconds: did the opening hold.
            "hook_rate": (round(t["video_views"] / t["impressions"], 4)
                          if t["video_views"] and t["impressions"] else None),
            "watch": w,
            # Of those who stayed three seconds, how many watched it through.
            "hold_rate": (round(w["thruplays"] / t["video_views"], 4)
                          if w and w["thruplays"] and t["video_views"] else None),
        })

    ranked = {}
    for key in RESULT_ORDER:
        group = [a for a in ads if a["result"] and a["result"]["key"] == key
                 and a["result"]["count"]]
        group.sort(key=lambda a: (not a["result"]["proven"], a["result"]["cost"]))
        if group:
            ranked[key] = {"label": group[0]["result"]["label"], "ads": group[:top],
                           "proven": sum(1 for a in group if a["result"]["proven"]),
                           "compared": len(group)}

    themes: dict = {}
    for a in ads:
        if not (a["result"] and a["result"]["key"] == "leads"):
            continue
        for theme in a["themes"]:
            t = themes.setdefault(theme, {"theme": theme, "ads": 0, "spend": 0.0, "leads": 0})
            t["ads"] += 1
            t["spend"] = round(t["spend"] + a["spend"], 2)
            t["leads"] += a["leads"]
    lead_themes = sorted(
        (dict(t, cost_per_lead=round(t["spend"] / t["leads"], 2)) for t in themes.values()
         if t["leads"]),
        key=lambda t: t["cost_per_lead"])

    # Meta counts three-second views on an image ad it has animated by itself.
    # That says nothing about an opening anyone filmed.
    hooks = sorted((a for a in ads if a["hook_rate"] and a["impressions"] >= 3000
                    and a["format"] != "image"),
                   key=lambda a: -a["hook_rate"])[:top]
    return {
        "schema": SCHEMA, "period": period, "ads_with_delivery": len(ads),
        "ranked": ranked, "lead_themes": lead_themes, "best_openings": hooks,
        "by_ad": {a["ad_id"]: a for a in ads},
    }


def proven_for(win: dict, themes, metric_key: str):
    """The cheapest proven ad for this result that shares a theme, if any.
    What the video ideas point at as 'this already worked'."""
    themes = set(themes or ())
    proven = [a for a in ((win or {}).get("by_ad") or {}).values()
              if a.get("result") and a["result"]["key"] == metric_key and a["result"]["proven"]
              and a.get("opening") and themes & set(a["themes"])]
    return min(proven, key=lambda a: a["result"]["cost"], default=None)
