"""Learning from the ads the suggestions page proposed. Pure; the ads_brief job keeps the log.

    remember()   each morning, every runnable suggestion goes into the log once, with what it predicted
    match()      an ad whose campaign carries the suggested name, or whose text is the post's caption, is that
                 suggestion running. After the 7-day test it is judged against the prediction. A suggestion nobody
                 ran in 30 days expires.
    learned()    what finished tests really cost, per ad type and per type + subject, and how often they beat,
                 matched or missed. ads_suggest.build() uses it for the next suggestions.

Log: brands/<brand>/ads-suggest/log.json. Bookings are not joined yet (ClubLab has no analytics link), so a verdict
is on the ad's own result: leads, chats, page visits or video views.
"""
from __future__ import annotations

import datetime as _dt

from . import ads_creative

SCHEMA = "https://campaign-os/ads-suggest-log/v1"
TEST_DAYS = 7
EXPIRE_DAYS = 30
# Cost per result within this share of the prediction counts as matched.
MARGIN = 0.15
RESULT_KEY = {"lead_form": "leads", "messages": "messages", "traffic": "landing_page_views",
              "awareness": "video_views"}
UNIT = {"lead_form": "lead", "messages": "chat", "traffic": "page visit", "awareness": "view"}
VERDICT_TEXT = {"BEAT": "Beat the estimate", "MATCHED": "Matched the estimate", "MISSED": "Cost more than estimated",
                "NO_RESULT": "No results", "NO_ESTIMATE": "First measure (no estimate to beat)"}


def _date(ts):
    try:
        return _dt.date.fromisoformat(str(ts)[:10])
    except ValueError:
        return None


def remember(log: list, doc: dict, today: _dt.date) -> list:
    """Add today's runnable suggestions that are not in the log yet."""
    out = [dict(e) for e in log or []]
    have = {e["key"] for e in out}
    for s in (doc or {}).get("suggestions") or []:
        if s.get("ad_type") not in RESULT_KEY:
            continue
        key = f"{s['post_id']}:{s['ad_type']}"
        if key in have:
            continue
        sp = s.get("spend") or {}
        out.append({
            "key": key, "brand_id": doc.get("brand_id"), "post_id": s["post_id"], "permalink": s.get("permalink"),
            "caption": (s.get("caption") or "")[:120], "caption_key": ads_creative._norm(s.get("caption")),
            "ad_type": s["ad_type"], "theme": s.get("theme"), "campaign_name": s["names"]["campaign"],
            "suggested_on": today.isoformat(), "status": "SUGGESTED",
            "expected": {"daily": sp.get("daily"), "total": sp.get("total"), "results": sp.get("expected_results"),
                         "cost_per_result": sp.get("unit_cost"), "unit": UNIT[s["ad_type"]]},
        })
        have.add(key)
    return out


def _verdict(expected_cost, spend, results) -> str:
    if not results:
        return "NO_RESULT" if spend else "NO_RESULT"
    if not expected_cost:
        return "NO_ESTIMATE"
    ratio = (spend / results) / expected_cost
    if ratio <= 1 - MARGIN:
        return "BEAT"
    if ratio <= 1 + MARGIN:
        return "MATCHED"
    return "MISSED"


def match(log: list, ads: list, today: _dt.date) -> list:
    """Join running ads to logged suggestions; judge finished tests; expire ones nobody ran."""
    out = []
    for e in log or []:
        e = dict(e)
        if e.get("status") in ("DONE", "EXPIRED"):
            out.append(e)
            continue
        mine = [a for a in ads or []
                if (a.get("campaign") or {}).get("name") == e["campaign_name"]
                or (e.get("caption_key") and ads_creative._norm((a.get("creative") or {}).get("body"))
                    == e["caption_key"])]
        if not mine:
            if e["status"] == "SUGGESTED" and (today - _date(e["suggested_on"])).days > EXPIRE_DAYS:
                e["status"], e["closed_on"] = "EXPIRED", today.isoformat()
            out.append(e)
            continue
        key = RESULT_KEY[e["ad_type"]]
        spend = round(sum((a.get("current") or {}).get("spend") or 0 for a in mine), 2)
        results = sum((a.get("current") or {}).get(key) or 0 for a in mine)
        starts = [d for d in (_date((a.get("adset") or {}).get("start_time")) for a in mine) if d]
        started = min(starts) if starts else today
        e.update({"status": "RUNNING", "ad_ids": sorted(str(a["ad_id"]) for a in mine),
                  "started": started.isoformat(),
                  "actual": {"spend": spend, "results": results,
                             "cost_per_result": round(spend / results, 2) if results else None}})
        if (today - started).days >= TEST_DAYS:
            e.update({"status": "DONE", "closed_on": today.isoformat(),
                      "verdict": _verdict((e.get("expected") or {}).get("cost_per_result"), spend, results)})
        out.append(e)
    return out


def learned(log: list) -> dict:
    """Real cost per result from finished tests, per type and per type + subject, with beat / matched / missed."""
    def blank():
        return {"tests": 0, "spend": 0.0, "results": 0, "beat": 0, "matched": 0, "missed": 0}
    by_type, by_pair = {}, {}
    for e in log or []:
        if e.get("status") != "DONE":
            continue
        a = e.get("actual") or {}
        for bucket in (by_type.setdefault(e["ad_type"], blank()),
                       by_pair.setdefault(f"{e['ad_type']}:{e.get('theme')}", blank())):
            bucket["tests"] += 1
            bucket["spend"] += a.get("spend") or 0
            bucket["results"] += a.get("results") or 0
            v = e.get("verdict")
            bucket["beat" if v == "BEAT" else "matched" if v in ("MATCHED", "NO_ESTIMATE") else "missed"] += 1
    for bucket in list(by_type.values()) + list(by_pair.values()):
        bucket["spend"] = round(bucket["spend"], 2)
        bucket["cost_per_result"] = round(bucket["spend"] / bucket["results"], 2) if bucket["results"] else None
    return {"by_type": by_type, "by_type_theme": by_pair}


def adjust(learned_doc: dict | None, ad_type: str, theme) -> tuple[int, str]:
    """A nudge to a type's score for a subject from its track record, and the line that explains it."""
    b = ((learned_doc or {}).get("by_type_theme") or {}).get(f"{ad_type}:{theme}")
    if not b:
        return 0, ""
    line = (f"Track record for {UNIT[ad_type]} ads on {theme}: {b['tests']} run, {b['beat']} beat the estimate, "
            f"{b['missed']} missed.")
    if b["missed"] >= 2 and b["missed"] > b["beat"]:
        return -1, line
    if b["beat"] > b["missed"]:
        return 1, line
    return 0, line


# An awareness audience is worth aiming at once it has had a few days to fill, and while Meta still keeps it.
AUDIENCE_READY_DAYS = 3
AUDIENCE_KEEP_DAYS = 30


def audiences(log: list, today: _dt.date) -> list[dict]:
    """Watched audiences from awareness ads that ran, newest first, that are ready to aim a follow-up ad at."""
    out = []
    for e in log or []:
        if e.get("ad_type") != "awareness" or e.get("status") not in ("RUNNING", "DONE"):
            continue
        started = _date(e.get("started"))
        if not started or not AUDIENCE_READY_DAYS <= (today - started).days <= AUDIENCE_KEEP_DAYS:
            continue
        out.append({"name": f"{e['campaign_name']}_watched50", "campaign_name": e["campaign_name"],
                    "started": started.isoformat(), "caption": e.get("caption")})
    return sorted(out, key=lambda a: a["started"], reverse=True)
