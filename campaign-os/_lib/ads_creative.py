"""Ads creative loop — what to test next, and what the last test proved.

Two pure steps over the ads brain's output, run by the ads_brief job:

    plan()    For each campaign the frozen scoring says has nothing to compare
              (or a tired or weak creative), write a test card: the control ad,
              the challengers to try, and the rule that will decide it. The rule
              is fixed before the test starts.
    track()   Notice when a challenger is launched (a new ad appears in the
              campaign), wait for enough evidence, decide by the card's rule and
              keep the result.

Challengers come from what already exists: the brand's best recent organic
posts, and the measured post templates for a format the campaign has not tried.
Nothing here writes copy with a model, and nothing creates or changes an ad:
a person launches the challenger in Ads Manager.
"""
from __future__ import annotations

import datetime as _dt
import math
import re

SCHEMA = "https://campaign-os/ads-creative/v1"

# Findings that mean "this needs another creative". (rule, status or None).
TRIGGERS = (
    ("fatigue", None),
    ("below_average_ranking", "CREATIVE_QUALITY"),
    ("below_average_ranking", "HOOK_OR_AUDIENCE"),
    ("single_ad_no_test", "MULTIPLE_CREATIVES_DELIVERY_CONCENTRATED"),
    ("single_ad_no_test", "ONE_CREATIVE_ONLY"),
)

DESIGN = {
    "min_days": 14,          # never decide earlier, whatever the numbers say
    "max_days": 42,          # stop waiting after six weeks
    "win_margin": 0.15,      # cost per result must differ by this much to call it
    "expire_days": 30,       # a proposal nobody launched
    "max_open_per_brand": 3,
}

# What a result is for each ad set goal, and how many each arm needs.
_METRICS = {
    "LEAD_GENERATION": ("leads", "lead", 10),
    "QUALITY_LEAD": ("leads", "lead", 10),
    "CONVERSATIONS": ("messages", "chat", 10),
    "LANDING_PAGE_VIEWS": ("landing_page_views", "page visit", 100),
    "LINK_CLICKS": ("landing_page_views", "page visit", 100),
}

THEMES = {
    "fitting": ("fitting", "fitted", "get measured", "measured", "trackman", "specs"),
    "coaching": ("coach", "lesson", "feedback on your swing", "practice"),
    "putter": ("putt",),
    "irons": ("iron",),
    "driver": ("driver", "off the tee"),
    "grip": ("grip",),
    "bags": ("bag",),
    "membership": ("member",),
}

# The measured template to reach for when a campaign has only run video.
TEMPLATE_FOR_THEME = {
    "swing-shack": {"fitting": "ss-fitting-headline", "putter": "ss-fitting-headline",
                    "irons": "ss-fitting-headline", "driver": "ss-fitting-headline",
                    "coaching": "ss-lesson-corner", "_default": "ss-service-promo"},
    "stick": {"coaching": "stick-coaching-poster-v1", "_default": "stick-service-hero-v1"},
}

OPEN = ("PROPOSED", "RUNNING")


def themes_of(*texts) -> set:
    blob = " ".join(t for t in texts if t).lower()
    return {theme for theme, words in THEMES.items() if any(w in blob for w in words)}


def _norm(text) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()[:60]


def _metric(ad: dict):
    goal = ((ad.get("adset") or {}).get("optimization_goal") or "").upper()
    return _METRICS.get(goal)


def _arm(m: dict, key: str) -> dict:
    results = (m or {}).get(key) or 0
    spend = (m or {}).get("spend") or 0.0
    return {"spend": round(spend, 2), "results": results,
            "cost_per_result": round(spend / results, 2) if results else None}


def _organic_challenger(control_themes: set, control_media: str, organic: list, used: set,
                        taken: set):
    """Best recent organic post on the same theme that is not already an ad or
    in another test. Prefers the format the campaign has not tried."""
    best = None
    for o in organic or []:
        caption = o.get("caption_preview") or ""
        shared = control_themes & themes_of(caption)
        if (not shared or not o.get("permalink") or _norm(caption) in used
                or o.get("post_id") in taken):
            continue
        fmt = "video" if o.get("format_type") == "reel" else "image"
        rank = (fmt != control_media, o.get("score") or 0)
        if best is None or rank > best[0]:
            best = (rank, o, fmt, shared)
    if not best:
        return None
    _, o, fmt, shared = best
    return {
        "kind": "ORGANIC_POST", "format": fmt, "ready": True,
        "title": "Promote an organic post that already worked",
        "caption": o.get("caption_preview"), "permalink": o.get("permalink"),
        "why": f"Scored {o.get('score')} on reach {o.get('reach'):,} in the last 30 days, "
               f"on the same theme ({', '.join(sorted(shared))}).",
        "post_id": o.get("post_id"),
    }


def _template_challenger(brand_id: str, control_themes: set, control_media: str):
    """A static from a measured template, when the campaign has only run video.
    The copy still has to be written, so this one is not ready to launch."""
    if control_media != "video":
        return None
    table = TEMPLATE_FOR_THEME.get(brand_id) or {}
    theme = next((t for t in sorted(control_themes) if t in table), None)
    archetype = table.get(theme) or table.get("_default")
    if not archetype:
        return None
    return {
        "kind": "TEMPLATE_STATIC", "format": "image", "ready": False,
        "title": "A static image from a measured template",
        "archetype": archetype,
        "why": "This campaign has only run video. A static costs nothing to render "
               "and tests the format.",
        "next_step": f"Write the headline, then render with /render-post "
                     f"--brand {brand_id} --archetype {archetype}.",
    }


def plan(brand_id: str, scored: dict, snapshot: dict, organic: list, tests: list,
         today: _dt.date) -> list:
    """New test cards for campaigns that need a creative and have no open test."""
    ads = {a["ad_id"]: a for a in snapshot.get("ads") or []}
    open_campaigns = {t["campaign_id"] for t in tests if t["status"] in OPEN}
    slots = DESIGN["max_open_per_brand"] - len(open_campaigns)
    used = {_norm((a.get("creative") or {}).get("body")) for a in ads.values()} - {""}
    taken = {c.get("post_id") for t in tests if t["status"] in OPEN
             for c in t["challengers"] if c.get("post_id")}

    candidates = []
    for order, (rule, status) in enumerate(TRIGGERS):
        for f in scored.get("findings") or []:
            if f["rule"] != rule or (status and f.get("status") != status):
                continue
            ad = ads.get(f.get("ad_id"))
            metric = _metric(ad) if ad else None
            if not ad or not metric:
                continue  # awareness and unknown goals have no result to compare
            leads_first = 0 if metric[0] == "leads" else 1
            candidates.append((leads_first, order, -ad["current"]["spend"], f, ad, metric))
    candidates.sort(key=lambda c: c[:3])

    cards = []
    for _, _, _, f, ad, (key, label, min_results) in candidates:
        campaign_id = (ad.get("campaign") or {}).get("id")
        if slots <= 0 or campaign_id in open_campaigns:
            continue
        creative = ad.get("creative") or {}
        media = creative.get("media_type") or "video"
        themes = themes_of((ad.get("campaign") or {}).get("name"), ad.get("ad_name"),
                           creative.get("body"), creative.get("title"))
        challengers = [c for c in (
            _organic_challenger(themes, media, organic, used, taken),
            _template_challenger(brand_id, themes, media)) if c]
        if not challengers:
            continue
        taken.update(c["post_id"] for c in challengers if c.get("post_id"))
        control = _arm(ad["current"], key)
        per_day = control["results"] / max((snapshot.get("period") or {}).get("days") or 31, 1)
        est = math.ceil(2 * min_results / per_day) if per_day else None
        cards.append({
            "id": f"{campaign_id}:{today.isoformat()}", "brand_id": brand_id,
            "status": "PROPOSED", "proposed_on": today.isoformat(),
            "campaign_id": campaign_id, "campaign_name": (ad.get("campaign") or {}).get("name"),
            "trigger": {"rule": f["rule"], "status": f.get("status"), "what": f["what"]},
            "themes": sorted(themes),
            "control": dict(control, ad_id=ad["ad_id"], ad_name=ad.get("ad_name"),
                            format=media, body=(creative.get("body") or "")[:160]),
            "metric": {"key": key, "label": label},
            "challengers": challengers,
            "design": {
                "how": "Run it as an A/B test in Ads Manager so both creatives get shown. "
                       "Adding it to the same ad set lets Meta starve one of them.",
                "min_results_per_arm": min_results, "min_days": DESIGN["min_days"],
                "max_days": DESIGN["max_days"], "win_margin": DESIGN["win_margin"],
                "estimated_days": est,
                "budget_warning": bool(est is None or est > DESIGN["max_days"]),
                "rule": f"After at least {DESIGN['min_days']} days and {min_results} {label}s "
                        f"each, the cheaper cost per {label} wins if it is at least "
                        f"{DESIGN['win_margin']:.0%} cheaper. Otherwise no clear winner.",
            },
            # Everything in the campaign today; a new id later is the challenger.
            "known_ad_ids": sorted(a["ad_id"] for a in ads.values()
                                   if (a.get("campaign") or {}).get("id") == campaign_id),
        })
        open_campaigns.add(campaign_id)
        slots -= 1
    return cards


def _decide(test: dict, control: dict, challenger: dict, days: int):
    d = test["design"]
    enough = (control["results"] >= d["min_results_per_arm"]
              and challenger["results"] >= d["min_results_per_arm"])
    if days >= d["min_days"] and enough:
        ratio = challenger["cost_per_result"] / control["cost_per_result"]
        if ratio <= 1 - d["win_margin"]:
            return "CHALLENGER_WON"
        if ratio >= 1 + d["win_margin"]:
            return "CONTROL_WON"
        if days >= d["max_days"]:
            return "NO_CLEAR_WINNER"
        return None
    if days >= d["max_days"]:
        return "INCONCLUSIVE_LOW_VOLUME"
    return None


def track(tests: list, snapshot: dict, window, today: _dt.date) -> list:
    """Advance every open test one step. ``window(days)`` returns an
    insights-only snapshot covering the last ``days`` days, for RUNNING tests."""
    ads = snapshot.get("ads") or []
    out = []
    for t in tests:
        t = dict(t)
        if t["status"] == "PROPOSED":
            new = sorted(a["ad_id"] for a in ads
                         if (a.get("campaign") or {}).get("id") == t["campaign_id"]
                         and a["ad_id"] not in t["known_ad_ids"]
                         and a["current"]["spend"] > 0)
            age = (today - _dt.date.fromisoformat(t["proposed_on"])).days
            if new:
                t.update(status="RUNNING", launched_on=today.isoformat(), challenger_ad_ids=new)
            elif age > DESIGN["expire_days"]:
                t.update(status="EXPIRED", closed_on=today.isoformat())
        elif t["status"] == "RUNNING":
            days = (today - _dt.date.fromisoformat(t["launched_on"])).days
            if days >= 1:
                by_id = {a["ad_id"]: a["current"] for a in (window(days).get("ads") or [])}
                key = t["metric"]["key"]
                control = _arm(by_id.get(t["control"]["ad_id"]), key)
                arms = [dict(_arm(by_id.get(i), key), ad_id=i) for i in t["challenger_ad_ids"]]
                # Judge the control against the challenger that got the most delivery.
                challenger = max(arms, key=lambda a: a["spend"])
                t["progress"] = {"days": days, "control": control, "challenger": challenger}
                if days >= t["design"]["min_days"] and control["spend"] == 0:
                    result = "INCONCLUSIVE_CONTROL_STOPPED"
                else:
                    result = _decide(t, control, challenger, days)
                if result:
                    t.update(status="DECIDED", result=result, closed_on=today.isoformat())
        out.append(t)
    return out


def summarise(tests: list, today: _dt.date, recent_days: int = 30) -> dict:
    """What the brief shows: open tests, and those closed in the last month."""
    since = (today - _dt.timedelta(days=recent_days)).isoformat()
    closed = [t for t in tests if t["status"] in ("DECIDED", "EXPIRED")
              and (t.get("closed_on") or "") >= since]
    decided = [t for t in tests if t["status"] == "DECIDED"]
    return {
        "schema": SCHEMA,
        "proposed": [t for t in tests if t["status"] == "PROPOSED"],
        "running": [t for t in tests if t["status"] == "RUNNING"],
        "closed_recently": closed,
        "record": {r: sum(1 for t in decided if t.get("result") == r)
                   for r in ("CHALLENGER_WON", "CONTROL_WON", "NO_CLEAR_WINNER",
                             "INCONCLUSIVE_LOW_VOLUME", "INCONCLUSIVE_CONTROL_STOPPED")},
    }
