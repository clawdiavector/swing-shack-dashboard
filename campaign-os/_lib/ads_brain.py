"""Ads brain — score every Meta ad and say what to do with it.

Two halves, both read-only on Meta:

    fetch_snapshot()   Graph API reads at ad level: insights for the current
                       and previous window, quality rankings, placements, and
                       the ad / ad set / creative settings Ads Manager shows.
    score_snapshot()   Pure, deterministic rules over that snapshot. No model.
                       Returns findings, each with the evidence and one action.

Nothing here can change an ad. The rules recommend; a person acts in Ads
Manager. Thresholds live in THRESHOLDS and are starting values measured against
the 2026-09-07..2026-10-07 read of both accounts, not tuned constants.

The synthetic seed file data/meta-ads.json is never read.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

GRAPH_BASE = "https://graph.facebook.com"
DEFAULT_API_VERSION = os.environ.get("INSTAGRAM_GRAPH_API_VERSION") or "v26.0"
SCHEMA = "https://campaign-os/ads-brain/v1"

THRESHOLDS = {
    # click_goal_leak: share of link clicks that become landing page views.
    "leak_min_link_clicks": 200,
    "leak_max_lpv_rate": 0.30,
    # open_ended: non-lead ad running this long with no end date.
    "open_ended_min_days": 28,
    # single_ad: one ad carries this share of its ad set's spend.
    "single_ad_min_share": 0.95,
    "single_ad_min_spend": 300.0,
    # fatigue: frequency over the window, with CTR falling vs previous window.
    "fatigue_min_frequency": 3.5,
    "fatigue_ctr_drop": 0.20,
    # cost per lead rising vs previous window.
    "cpl_rise": 0.25,
    "cpl_min_leads": 5,
    # CPM rising vs previous window.
    "cpm_rise": 0.25,
    "cpm_min_impressions": 3000,
    # best_lead_ad: enough leads to trust the cost.
    "best_lead_min_leads": 10,
    # spend_mix: share of spend on ads that produce leads.
    "lead_spend_min_share": 0.40,
    # instagram_absent: Instagram share of impressions.
    "instagram_min_share": 0.05,
    "instagram_min_impressions": 10000,
}

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}

_LEAD = "lead"
_MESSAGE = "onsite_conversion.messaging_conversation_started_7d"
_LPV = "landing_page_view"
_LINK_CLICK = "link_click"
_VIDEO_VIEW = "video_view"

_INSIGHT_FIELDS = (
    "ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name,objective,"
    "impressions,reach,frequency,clicks,spend,cpm,ctr,inline_link_clicks,"
    "actions"
)
_RANKING_FIELDS = "quality_ranking,engagement_rate_ranking,conversion_rate_ranking"
_AD_FIELDS = (
    "id,name,effective_status,"
    "campaign{id,name,objective,effective_status,start_time,stop_time,daily_budget,lifetime_budget},"
    "adset{id,name,effective_status,optimization_goal,daily_budget,lifetime_budget,start_time,end_time},"
    "creative{id,body,title,call_to_action_type,object_type,video_id,image_url,thumbnail_url,"
    "link_url,object_story_spec,effective_object_story_id}"
)


# ── small helpers ────────────────────────────────────────────────────────

def _num(x, cast=float):
    try:
        return cast(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def _action(row: dict, action_type: str) -> float:
    for a in row.get("actions") or []:
        if a.get("action_type") == action_type:
            return _num(a.get("value")) or 0.0
    return 0.0


def _money(x) -> str:
    return f"R{(x or 0):,.0f}" if (x or 0) >= 100 else f"R{(x or 0):,.2f}"


def _pct(x) -> str:
    return f"{round((x or 0) * 100)}%"


def _parse_time(s):
    """Meta returns '2026-09-30T23:59:00+0200'. Returns aware datetime or None."""
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            d = _dt.datetime.strptime(str(s), fmt)
            return d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)
        except ValueError:
            continue
    return None


def is_stale(path, max_age_hours: float, now: _dt.datetime | None = None) -> bool:
    """True when a cache file is missing, unreadable or older than max_age_hours.

    Age comes from the file's own ``fetched_at`` so a copied file keeps the age
    of the data, not of the copy.
    """
    now = now or _dt.datetime.now(_dt.timezone.utc)
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        fetched = _dt.datetime.fromisoformat(str(doc["fetched_at"]).replace("Z", "+00:00"))
    except Exception:
        return True
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=_dt.timezone.utc)
    return (now - fetched).total_seconds() > max_age_hours * 3600


def period_windows(days: int = 31, today: _dt.date | None = None) -> dict:
    """Same windows the paid-media report uses: today excluded, equal lengths."""
    today = today or _dt.date.today()
    cur_end = today - _dt.timedelta(days=1)
    cur_start = today - _dt.timedelta(days=days)
    prev_end = today - _dt.timedelta(days=days + 1)
    prev_start = today - _dt.timedelta(days=days * 2)
    return {
        "days": days,
        "current": {"since": cur_start.isoformat(), "until": cur_end.isoformat()},
        "previous": {"since": prev_start.isoformat(), "until": prev_end.isoformat()},
    }


# ── fetch ────────────────────────────────────────────────────────────────

def _graph_get(path: str, token: str, params: dict):
    """GET one Graph API page. Returns (json, None) or (None, error). Read-only."""
    qp = dict(params or {})
    qp["access_token"] = token
    url = f"{GRAPH_BASE}{path}?{urllib.parse.urlencode(qp)}"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode() or "{}")
            msg = (body.get("error") or {}).get("message", "")
        except Exception:
            msg = ""
        return None, f"HTTP {e.code}: {msg[:200]}"
    except Exception as e:  # network, timeout, bad JSON
        return None, type(e).__name__


def _get_all(get, path: str, params: dict, max_pages: int = 10):
    """Follow paging cursors. Returns (rows, error)."""
    rows, after = [], None
    for _ in range(max_pages):
        p = dict(params)
        if after:
            p["after"] = after
        body, err = get(path, p)
        if err:
            return rows, err
        rows.extend(body.get("data") or [])
        paging = body.get("paging") or {}
        after = (paging.get("cursors") or {}).get("after")
        if not after or not paging.get("next"):
            break
    return rows, None


def _metrics(row: dict) -> dict:
    link_clicks = _action(row, _LINK_CLICK) or (_num(row.get("inline_link_clicks")) or 0.0)
    return {
        "spend": _num(row.get("spend")) or 0.0,
        "impressions": _num(row.get("impressions"), int) or 0,
        "reach": _num(row.get("reach"), int) or 0,
        "frequency": _num(row.get("frequency")) or 0.0,
        "clicks": _num(row.get("clicks"), int) or 0,
        "ctr": _num(row.get("ctr")) or 0.0,
        "cpm": _num(row.get("cpm")) or 0.0,
        "link_clicks": int(link_clicks),
        "landing_page_views": int(_action(row, _LPV)),
        "leads": int(_action(row, _LEAD)),
        "messages": int(_action(row, _MESSAGE)),
        "video_views": int(_action(row, _VIDEO_VIEW)),
        "quality_ranking": row.get("quality_ranking"),
        "engagement_rate_ranking": row.get("engagement_rate_ranking"),
        "conversion_rate_ranking": row.get("conversion_rate_ranking"),
    }


def _creative(c: dict) -> dict:
    c = c or {}
    spec = c.get("object_story_spec") or {}
    video = spec.get("video_data") or {}
    link = spec.get("link_data") or {}
    cta = (video.get("call_to_action") or link.get("call_to_action") or {})
    link_url = (c.get("link_url") or link.get("link")
                or (cta.get("value") or {}).get("link"))
    if c.get("video_id") or video:
        media = "video"
    elif c.get("image_url") or link.get("picture") or link.get("image_hash"):
        media = "image"
    else:
        media = (c.get("object_type") or "").lower() or None
    return {
        "id": c.get("id"),
        "body": c.get("body") or video.get("message") or link.get("message"),
        "title": c.get("title") or video.get("title") or link.get("name"),
        "cta": c.get("call_to_action_type") or cta.get("type"),
        "media_type": media,
        "link_url": link_url,
        "thumbnail_url": c.get("thumbnail_url"),
        "story_id": c.get("effective_object_story_id"),
    }


def fetch_snapshot(brand_id: str, account_id: str, token: str, *,
                   days: int = 31, api_version: str | None = None,
                   get=None, today: _dt.date | None = None) -> dict:
    """Read one ad account at ad level. Each part fails independently and is
    recorded in ``errors``; scoring skips the rules a missing part would feed.

    ``get(path, params) -> (json, error)`` is injectable for tests.
    """
    ver = api_version or DEFAULT_API_VERSION
    if get is None:
        def get(path, params):
            return _graph_get(path, token, params)
    win = period_windows(days, today)
    base = f"/{ver}/{account_id}"
    errors = []

    def insights(time_range, fields, breakdowns=None):
        params = {"level": "ad", "fields": fields, "limit": 500,
                  "time_range": json.dumps(time_range)}
        if breakdowns:
            params["breakdowns"] = breakdowns
        return _get_all(get, f"{base}/insights", params)

    cur, err = insights(win["current"], f"{_INSIGHT_FIELDS},{_RANKING_FIELDS}")
    if err:
        # Rankings are ad-level only and the first thing Meta rejects; retry without.
        errors.append(f"current insights with rankings: {err}")
        cur, err = insights(win["current"], _INSIGHT_FIELDS)
        if err:
            errors.append(f"current insights: {err}")
    prev, err = insights(win["previous"], _INSIGHT_FIELDS)
    if err:
        errors.append(f"previous insights: {err}")
    place, err = insights(win["current"],
                          "ad_id,spend,impressions,inline_link_clicks,actions",
                          breakdowns="publisher_platform,platform_position")
    if err:
        errors.append(f"placements: {err}")
    settings, err = _get_all(get, f"{base}/ads", {"fields": _AD_FIELDS, "limit": 100})
    if err:
        errors.append(f"ad settings: {err}")

    prev_by = {r.get("ad_id"): r for r in prev or []}
    set_by = {s.get("id"): s for s in settings or []}
    place_by: dict = {}
    for r in place or []:
        place_by.setdefault(r.get("ad_id"), []).append({
            "publisher_platform": r.get("publisher_platform"),
            "platform_position": r.get("platform_position"),
            "spend": _num(r.get("spend")) or 0.0,
            "impressions": _num(r.get("impressions"), int) or 0,
            "link_clicks": int(_action(r, _LINK_CLICK)
                               or (_num(r.get("inline_link_clicks")) or 0)),
            "landing_page_views": int(_action(r, _LPV)),
        })

    def record(ad_id, row, current, previous):
        s = set_by.get(ad_id) or {}
        camp = dict(s.get("campaign") or {})
        adset = dict(s.get("adset") or {})
        # Insights rows carry the ids and names even when the settings call failed.
        for d, prefix in ((camp, "campaign"), (adset, "adset")):
            d["id"] = d.get("id") or row.get(f"{prefix}_id")
            d["name"] = d.get("name") or row.get(f"{prefix}_name")
        camp["objective"] = camp.get("objective") or row.get("objective")
        return {
            "ad_id": ad_id,
            "ad_name": row.get("ad_name") or s.get("name"),
            "effective_status": s.get("effective_status"),
            "campaign": camp,
            "adset": adset,
            "creative": _creative(s.get("creative")),
            "current": current,
            "previous": previous,
            "placements": place_by.get(ad_id, []),
        }

    cur_ids = {r.get("ad_id") for r in cur or []}
    ads = [record(r.get("ad_id"), r, _metrics(r),
                  _metrics(prev_by[r.get("ad_id")]) if r.get("ad_id") in prev_by else None)
           for r in cur or []]
    # Ads that delivered last window but not this one: a lead ad that stopped
    # is the most important thing this file can notice.
    ads += [record(ad_id, r, _metrics({}), _metrics(r))
            for ad_id, r in prev_by.items() if ad_id not in cur_ids]

    return {
        "schema": SCHEMA,
        "brand_id": brand_id,
        "ad_account_id": account_id,
        "api_version": ver,
        "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "period": win,
        "ads": ads,
        "errors": errors,
        "data_source": "meta_graph_api",
    }


# ── score ────────────────────────────────────────────────────────────────

def _is_running(ad: dict, now: _dt.datetime) -> bool:
    """ACTIVE and not past its end date. Meta keeps reporting ACTIVE for a
    campaign whose stop_time has passed (Ads Manager shows it as Completed)."""
    if (ad.get("effective_status") or "").upper() != "ACTIVE":
        return False
    for end in ((ad.get("campaign") or {}).get("stop_time"),
                (ad.get("adset") or {}).get("end_time")):
        t = _parse_time(end)
        if t and t <= now:
            return False
    return True


def _has_end_date(ad: dict) -> bool:
    return bool((ad.get("campaign") or {}).get("stop_time")
                or (ad.get("adset") or {}).get("end_time"))


def _days_running(ad: dict, now: _dt.datetime):
    start = (_parse_time((ad.get("adset") or {}).get("start_time"))
             or _parse_time((ad.get("campaign") or {}).get("start_time")))
    return (now - start).days if start else None


def _is_lead_ad(ad: dict) -> bool:
    obj = ((ad.get("campaign") or {}).get("objective") or "").upper()
    prev = ad.get("previous") or {}
    return ("LEAD" in obj or ad["current"]["leads"] > 0 or (prev.get("leads") or 0) > 0)


def _is_traffic_ad(ad: dict) -> bool:
    goal = ((ad.get("adset") or {}).get("optimization_goal") or "").upper()
    obj = ((ad.get("campaign") or {}).get("objective") or "").upper()
    return goal in ("LINK_CLICKS", "LANDING_PAGE_VIEWS") or obj in ("OUTCOME_TRAFFIC", "LINK_CLICKS")


def _cpl(m: dict):
    return (m["spend"] / m["leads"]) if m and m.get("leads") else None


def _finding(rule, severity, level, what, action, evidence, ad=None):
    f = {"rule": rule, "severity": severity, "level": level,
         "what": what, "action": action, "evidence": evidence}
    if ad:
        f.update({"ad_id": ad.get("ad_id"), "ad_name": ad.get("ad_name"),
                  "campaign_name": (ad.get("campaign") or {}).get("name")})
    return f


def score_snapshot(snapshot: dict, *, now: _dt.datetime | None = None,
                   thresholds: dict | None = None) -> dict:
    """Deterministic verdict for one brand. Same snapshot in, same findings out."""
    t = dict(THRESHOLDS)
    t.update(thresholds or {})
    now = now or _dt.datetime.now(_dt.timezone.utc)
    ads = snapshot.get("ads") or []
    delivered = [a for a in ads if a["current"]["spend"] > 0]
    running = [a for a in ads if _is_running(a, now)]
    have_settings = any(a.get("effective_status") for a in ads)
    findings = []

    total_spend = sum(a["current"]["spend"] for a in delivered)
    total_leads = sum(a["current"]["leads"] for a in delivered)
    lead_spend = sum(a["current"]["spend"] for a in delivered if a["current"]["leads"] > 0)

    # 1. Lead ads existed and none is running now.
    lead_ads = [a for a in ads if _is_lead_ad(a)]
    if have_settings and lead_ads and not any(_is_running(a, now) for a in lead_ads):
        best = max(lead_ads, key=lambda a: ((a.get("previous") or {}).get("leads") or 0)
                   + a["current"]["leads"])
        m = best["current"] if best["current"]["leads"] else (best.get("previous") or best["current"])
        findings.append(_finding(
            "lead_ads_not_running", "high", "account",
            "No lead ad is running. The last one has stopped or passed its end date.",
            f"Restart '{best.get('ad_name')}' or launch a replacement lead ad.",
            {"last_window_leads": m.get("leads"), "cost_per_lead": _cpl(m)},
            best))

    for a in ads:
        cur, prev = a["current"], a.get("previous")
        live = _is_running(a, now)
        goal = ((a.get("adset") or {}).get("optimization_goal") or "").upper()

        # 2. Buying link clicks that never load the page.
        if (cur["link_clicks"] >= t["leak_min_link_clicks"] and (live or not have_settings)):
            rate = cur["landing_page_views"] / cur["link_clicks"]
            if rate < t["leak_max_lpv_rate"] and goal != "LANDING_PAGE_VIEWS":
                real = cur["spend"] / cur["landing_page_views"] if cur["landing_page_views"] else None
                findings.append(_finding(
                    "click_goal_leak", "high", "ad",
                    f"Only {_pct(rate)} of {cur['link_clicks']:,} link clicks became page visits"
                    + (f", so each real visit costs {_money(real)}." if real else "."),
                    "Change the ad set's performance goal from link clicks to landing page views."
                    if goal == "LINK_CLICKS" else
                    "Check the ad set's performance goal and that the landing page has the Meta pixel.",
                    {"link_clicks": cur["link_clicks"], "landing_page_views": cur["landing_page_views"],
                     "lpv_rate": round(rate, 3), "optimization_goal": goal or None,
                     "cost_per_landing_page_view": real}, a))

        # 3. Traffic ad that lands on the home page.
        link = (a.get("creative") or {}).get("link_url")
        if live and link and _is_traffic_ad(a):
            path = urllib.parse.urlparse(link).path.strip("/")
            if not path:
                findings.append(_finding(
                    "home_page_destination", "medium", "ad",
                    "The button sends people to the home page, not a booking or service page.",
                    "Point the ad at the page for what it advertises (bookings, fitting, coaching).",
                    {"link_url": link}, a))

        # 4. Non-lead ad running open-ended.
        days_on = _days_running(a, now)
        if (live and not _has_end_date(a) and not _is_lead_ad(a)
                and days_on is not None and days_on >= t["open_ended_min_days"]):
            findings.append(_finding(
                "open_ended_non_lead", "medium", "ad",
                f"Running for {days_on} days with no end date and no leads to show for "
                f"{_money(cur['spend'])} this window.",
                "Set an end date, or decide what result this ad is meant to produce.",
                {"days_running": days_on, "spend": cur["spend"]}, a))

        if prev:
            # 6. Fatigue.
            if (cur["frequency"] >= t["fatigue_min_frequency"] and prev["ctr"] > 0
                    and (prev["ctr"] - cur["ctr"]) / prev["ctr"] >= t["fatigue_ctr_drop"]):
                findings.append(_finding(
                    "fatigue", "high", "ad",
                    f"People have seen this {cur['frequency']:.1f} times and click-through fell "
                    f"from {prev['ctr']:.2f}% to {cur['ctr']:.2f}%.",
                    "Replace the creative or widen the audience.",
                    {"frequency": cur["frequency"], "ctr": cur["ctr"], "previous_ctr": prev["ctr"]}, a))
            # 7. Cost per lead rising.
            c_cpl, p_cpl = _cpl(cur), _cpl(prev)
            if (live and c_cpl and p_cpl and cur["leads"] >= t["cpl_min_leads"]
                    and prev["leads"] >= t["cpl_min_leads"]
                    and (c_cpl - p_cpl) / p_cpl >= t["cpl_rise"]):
                findings.append(_finding(
                    "cost_per_lead_rising", "medium", "ad",
                    f"Cost per lead rose from {_money(p_cpl)} to {_money(c_cpl)}.",
                    "Test a new creative against it before raising the budget.",
                    {"cost_per_lead": c_cpl, "previous_cost_per_lead": p_cpl,
                     "leads": cur["leads"], "previous_leads": prev["leads"]}, a))
            # 8. CPM rising.
            if (live and prev["cpm"] > 0
                    and cur["impressions"] >= t["cpm_min_impressions"]
                    and prev["impressions"] >= t["cpm_min_impressions"]
                    and (cur["cpm"] - prev["cpm"]) / prev["cpm"] >= t["cpm_rise"]):
                findings.append(_finding(
                    "cpm_rising", "low", "ad",
                    f"It costs more to show: {_money(prev['cpm'])} per 1,000 views last window, "
                    f"{_money(cur['cpm'])} now.",
                    "Watch it. If cost per result follows, refresh the creative.",
                    {"cpm": cur["cpm"], "previous_cpm": prev["cpm"]}, a))

        # 9. Meta ranks it below average against competing ads.
        low = [k for k in ("quality_ranking", "engagement_rate_ranking", "conversion_rate_ranking")
               if str(cur.get(k) or "").upper().startswith("BELOW_AVERAGE")]
        if live and low:
            findings.append(_finding(
                "below_average_ranking", "medium", "ad",
                "Meta ranks this ad below average for "
                + ", ".join(k.replace("_ranking", "").replace("_", " ") for k in low) + ".",
                "Replace or rework the creative; below-average ads pay more for the same reach.",
                {k: cur.get(k) for k in low}, a))

        # 13. Instagram barely delivering.
        pl = a.get("placements") or []
        pl_imp = sum(p["impressions"] for p in pl)
        if live and pl_imp >= t["instagram_min_impressions"]:
            ig = sum(p["impressions"] for p in pl if p.get("publisher_platform") == "instagram")
            if ig / pl_imp < t["instagram_min_share"]:
                findings.append(_finding(
                    "instagram_absent", "low", "ad",
                    f"Only {_pct(ig / pl_imp)} of views are on Instagram; the rest are on Facebook.",
                    "If Instagram matters for this ad, give it its own ad set or a vertical cut.",
                    {"instagram_share": round(ig / pl_imp, 3), "impressions": pl_imp}, a))

    # 5. Ad sets where nothing is being tested.
    by_set: dict = {}
    for a in delivered:
        by_set.setdefault((a.get("adset") or {}).get("id"), []).append(a)
    for set_ads in by_set.values():
        set_spend = sum(x["current"]["spend"] for x in set_ads)
        top = max(set_ads, key=lambda x: x["current"]["spend"])
        if (set_spend >= t["single_ad_min_spend"]
                and top["current"]["spend"] / set_spend >= t["single_ad_min_share"]
                and (_is_running(top, now) or not have_settings)):
            findings.append(_finding(
                "single_ad_no_test", "medium", "ad",
                f"One ad carries {_pct(top['current']['spend'] / set_spend)} of this ad set's "
                f"{_money(set_spend)}, so nothing is being compared.",
                "Add a second creative to the ad set and let them run against each other.",
                {"adset_spend": set_spend, "ads_in_adset": len(set_ads)}, top))

    # 10. The lead ad worth scaling.
    proven = [a for a in running if a["current"]["leads"] >= t["best_lead_min_leads"]]
    if proven:
        best = min(proven, key=lambda a: _cpl(a["current"]))
        findings.append(_finding(
            "best_lead_ad", "info", "ad",
            f"Cheapest proven leads: {best['current']['leads']} at "
            f"{_money(_cpl(best['current']))} each.",
            "Raise this ad's budget in steps of about 20% and watch cost per lead.",
            {"leads": best["current"]["leads"], "cost_per_lead": _cpl(best["current"])}, best))

    # 11. Spend mix.
    if total_spend > 0 and lead_ads:
        share = lead_spend / total_spend
        if share < t["lead_spend_min_share"]:
            findings.append(_finding(
                "spend_mix", "high" if share < t["lead_spend_min_share"] / 2 else "medium", "account",
                f"{_pct(share)} of {_money(total_spend)} went to ads that produced leads; "
                "the rest bought clicks and views.",
                "Move budget from traffic and awareness to the lead ads.",
                {"lead_spend_share": round(share, 3), "total_spend": total_spend,
                 "lead_spend": lead_spend}))

    # 12. Every ad is a video.
    media = [(a.get("creative") or {}).get("media_type") for a in delivered]
    media = [m for m in media if m]
    if len(media) >= 3 and all(m == "video" for m in media):
        findings.append(_finding(
            "all_video", "low", "account",
            f"All {len(media)} ads that ran are videos. No static image has been tested.",
            "Test a static from a measured post template against the best video.",
            {"ads_with_known_media": len(media)}))

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9),
                                 -((f.get("evidence") or {}).get("spend") or 0)))
    return {
        "schema": SCHEMA,
        "brand_id": snapshot.get("brand_id"),
        "fetched_at": snapshot.get("fetched_at"),
        "period": snapshot.get("period"),
        "summary": {
            "spend": round(total_spend, 2),
            "leads": total_leads,
            "cost_per_lead": round(lead_spend / total_leads, 2) if total_leads else None,
            "ads_delivered": len(delivered),
            "ads_running": len(running) if have_settings else None,
            "lead_spend_share": round(lead_spend / total_spend, 3) if total_spend else None,
        },
        "findings": findings,
        "counts": {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITY_ORDER},
        "errors": snapshot.get("errors") or [],
        "note": "Recommendations only. Nothing here changes an ad.",
    }


def build(brand_id: str, account_id: str, token: str, *, days: int = 31,
          data_dir=None, get=None, api_version: str | None = None) -> dict:
    """Fetch, score and (when data_dir is given) cache one brand's verdict."""
    snap = fetch_snapshot(brand_id, account_id, token, days=days, get=get,
                          api_version=api_version)
    out = score_snapshot(snap)
    out["ads"] = snap["ads"]
    if data_dir and snap["ads"]:
        d = Path(data_dir) / "ads-brain"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{brand_id}__{days}d.json").write_text(
            json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out
