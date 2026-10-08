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
SCORING_VERSION = "v1"

RULES = (
    "lead_ads_not_running", "click_goal_leak", "home_page_destination",
    "open_ended_non_lead", "single_ad_no_test", "fatigue", "cost_per_lead_rising",
    "cpm_rising", "below_average_ranking", "best_lead_ad", "spend_mix", "all_video",
    "instagram_absent",
)

THRESHOLDS = {
    # click_goal_leak: share of link clicks that become landing page views.
    # Healthy traffic ads in both accounts land 48-60% of their clicks.
    "leak_min_link_clicks": 200,
    "leak_max_lpv_rate": 0.40,
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
    # CPM rising vs previous window. Needs a second sign of decay to fire, and
    # never fires while cost per lead is improving.
    "cpm_rise": 0.25,
    "cpm_min_impressions": 3000,
    "cpm_support_cpl_rise": 0.10,
    "cpm_support_ctr_drop": 0.10,
    # below_average_ranking: enough delivery for Meta's ranking to mean something.
    "ranking_min_impressions": 10000,
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
# Asked for separately so an unsupported field cannot take the settings call down.
_CREATIVE_EXTRA_FIELDS = "id,creative{id,object_url,asset_feed_spec,object_story_id}"
_POST_FIELDS = "call_to_action,attachments{unshimmed_url,url,type}"
# Hosts that are Meta's own surfaces, never an advertiser's landing page.
_META_HOSTS = ("facebook.com", "fb.me", "fb.com", "instagram.com", "messenger.com", "m.me")


# Mirrors _META_ADS_ACCOUNT_FOR_BRAND / _META_ADS_TOKEN_FOR_BRAND and its
# fallbacks in app.py, so jobs can resolve them without importing app.
ACCOUNT_FOR_BRAND = {
    "stick": "act_2101557317059886",
    "swing-shack": "act_1024882912541604",
}
TOKEN_ENV_FOR_BRAND = {
    "stick": ("META_SYSTEM_USER_TOKEN_STICK", "META_SYSTEM_USER_TOKEN_STICK_PAARL",
              "META_SYSTEM_USER_TOKEN"),
    "swing-shack": ("META_SYSTEM_USER_TOKEN",),
}


def resolve_credentials(brand_id: str):
    """(account_id, token) for a brand; either is None when not configured."""
    token = next((os.environ[k] for k in TOKEN_ENV_FOR_BRAND.get(brand_id, ())
                  if os.environ.get(k)), None)
    return ACCOUNT_FOR_BRAND.get(brand_id), token


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
    v = (x or 0) * 100
    return f"{v:.1f}%" if 0 < v < 1 else f"{round(v)}%"


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


def _web_url(u):
    """The URL if it is an advertiser page, else None (Meta surface or junk)."""
    if not u or not isinstance(u, str):
        return None
    parsed = urllib.parse.urlparse(u if "://" in u else "https://" + u)
    host = (parsed.hostname or "").lower()
    if not host or "." not in host or any(host == h or host.endswith("." + h) for h in _META_HOSTS):
        return None
    return parsed.geturl()


def _destination(setting: dict, extra: dict, post, post_error) -> dict:
    """Where the ad's button goes. Boosted posts carry no link on the creative,
    so fall back through the creative's other fields to the underlying post.

    status: RESOLVED | LEAD_FORM | MESSAGING | UNKNOWN. UNKNOWN always has a reason.
    """
    c = setting.get("creative") or {}
    goal = ((setting.get("adset") or {}).get("optimization_goal") or "").upper()
    cta = (c.get("call_to_action_type") or "").upper()
    if goal in ("LEAD_GENERATION", "QUALITY_LEAD"):
        return {"status": "LEAD_FORM", "url": None, "source": "optimization_goal"}
    if goal == "CONVERSATIONS" or cta in ("MESSAGE_PAGE", "WHATSAPP_MESSAGE", "INSTAGRAM_MESSAGE"):
        return {"status": "MESSAGING", "url": None, "source": "optimization_goal"}
    spec = c.get("object_story_spec") or {}
    video, link = spec.get("video_data") or {}, spec.get("link_data") or {}
    feed_links = ((extra or {}).get("asset_feed_spec") or {}).get("link_urls") or []
    post = post or {}
    attachments = ((post.get("attachments") or {}).get("data") or [])
    candidates = [
        ("creative.link_url", c.get("link_url")),
        ("creative.object_story_spec", link.get("link")),
        ("creative.object_story_spec",
         ((video.get("call_to_action") or {}).get("value") or {}).get("link")),
        ("creative.asset_feed_spec", (feed_links[0] or {}).get("website_url") if feed_links else None),
        ("creative.object_url", (extra or {}).get("object_url")),
        ("post.call_to_action", ((post.get("call_to_action") or {}).get("value") or {}).get("link")),
    ] + [("post.attachments", att.get("unshimmed_url") or att.get("url")) for att in attachments]
    for source, raw in candidates:
        url = _web_url(raw)
        if url:
            return {"status": "RESOLVED", "url": url, "source": source}
    story = c.get("effective_object_story_id") or (extra or {}).get("object_story_id")
    if post_error:
        reason = f"post lookup failed: {post_error}"
    elif not story:
        reason = "creative has no link and no underlying post id"
    else:
        reason = "neither the creative nor its post returned a web link"
    return {"status": "UNKNOWN", "url": None, "source": None, "reason": reason}


def fetch_snapshot(brand_id: str, account_id: str, token: str, *,
                   days: int = 31, api_version: str | None = None,
                   get=None, get_as=None, today: _dt.date | None = None,
                   insights_only: bool = False) -> dict:
    """Read one ad account at ad level. Each part fails independently and is
    recorded in ``errors``; scoring skips the rules a missing part would feed.

    ``insights_only`` reads the two insight windows and nothing else: enough
    for numbers, not enough to score.

    ``get(path, params) -> (json, error)`` uses the ads token and
    ``get_as(token, path, params)`` a token minted during the run; both are
    injectable for tests.
    """
    ver = api_version or DEFAULT_API_VERSION
    if get is None:
        def get(path, params):
            return _graph_get(path, token, params)
    if get_as is None:
        def get_as(tok, path, params):
            return _graph_get(path, tok, params)
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
    place = settings = extras = None
    if not insights_only:
        place, err = insights(win["current"],
                              "ad_id,spend,impressions,inline_link_clicks,actions",
                              breakdowns="publisher_platform,platform_position")
        if err:
            errors.append(f"placements: {err}")
        settings, err = _get_all(get, f"{base}/ads", {"fields": _AD_FIELDS, "limit": 100})
        if err:
            errors.append(f"ad settings: {err}")
        extras, err = _get_all(get, f"{base}/ads",
                               {"fields": _CREATIVE_EXTRA_FIELDS, "limit": 100})
        if err:
            errors.append(f"creative destination fields: {err}")

    prev_by = {r.get("ad_id"): r for r in prev or []}
    set_by = {s.get("id"): s for s in settings or []}
    extra_by = {e.get("id"): (e.get("creative") or {}) for e in extras or []}

    # Destinations: only ads that delivered in either window, and the post is
    # only fetched when the creative itself gave no link.
    dest_by, post_errors, page_tokens = {}, set(), {}

    def read_post(story):
        """A post is only readable with its Page's own token. The story id is
        '<page_id>_<post_id>', and the ads token can be exchanged for that
        Page's token the same way meta_api.list_page_posts does it."""
        page_id = str(story).split("_", 1)[0]
        if page_id not in page_tokens:
            body, xerr = get(f"/{ver}/{page_id}", {"fields": "access_token"})
            page_tokens[page_id] = ((body or {}).get("access_token"), xerr)
        page_tok, xerr = page_tokens[page_id]
        if page_tok:
            return get_as(page_tok, f"/{ver}/{story}", {"fields": _POST_FIELDS})
        post, perr = get(f"/{ver}/{story}", {"fields": _POST_FIELDS})
        if perr:
            perr = f"{perr} (page token exchange: {xerr or 'no access_token returned'})"
        return post, perr

    for ad_id in sorted({r.get("ad_id") for r in (cur or [])} | set(prev_by)):
        s = set_by.get(ad_id)
        if not s:
            continue
        extra = extra_by.get(ad_id) or {}
        d = _destination(s, extra, None, None)
        story = ((s.get("creative") or {}).get("effective_object_story_id")
                 or extra.get("object_story_id"))
        if d["status"] == "UNKNOWN" and story:
            post, perr = read_post(story)
            if perr:
                post_errors.add(perr)
            d = _destination(s, extra, post, perr)
        dest_by[ad_id] = d
    errors.extend(f"post lookup: {e}" for e in sorted(post_errors))
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
            "destination": dest_by.get(ad_id) or {
                "status": "UNKNOWN", "url": None, "source": None,
                "reason": "ad settings were not returned"},
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

_LEAD_GOALS = ("LEAD_GENERATION", "QUALITY_LEAD")
_MESSAGE_GOALS = ("CONVERSATIONS",)
_AWARENESS_GOALS = ("REACH", "IMPRESSIONS", "AD_RECALL_LIFT", "THRUPLAY")
_RANKINGS = ("quality_ranking", "engagement_rate_ranking", "conversion_rate_ranking")


def _goal(ad: dict) -> str:
    return ((ad.get("adset") or {}).get("optimization_goal") or "").upper()


def _objective(ad: dict) -> str:
    return ((ad.get("campaign") or {}).get("objective") or "").upper()


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
    prev = ad.get("previous") or {}
    return ("LEAD" in _objective(ad) or _goal(ad) in _LEAD_GOALS
            or ad["current"]["leads"] > 0 or (prev.get("leads") or 0) > 0)


def _is_awareness_ad(ad: dict) -> bool:
    return "AWARENESS" in _objective(ad) or _goal(ad) in _AWARENESS_GOALS


def _is_traffic_ad(ad: dict) -> bool:
    return (_goal(ad) in ("LINK_CLICKS", "LANDING_PAGE_VIEWS")
            or _objective(ad) in ("OUTCOME_TRAFFIC", "LINK_CLICKS"))


def _acquisitions(ad: dict, m: dict) -> int:
    """Results that count as acquisition under the ad set's own goal. A chat
    is a result for a conversations ad and a by-product for a lead ad, so it
    is never added to leads."""
    if not m:
        return 0
    if _goal(ad) in _MESSAGE_GOALS:
        return m.get("messages") or 0
    return m.get("leads") or 0


def _cpl(m: dict):
    return (m["spend"] / m["leads"]) if m and m.get("leads") else None


def _rank_low(v) -> bool:
    return str(v or "").upper().startswith("BELOW_AVERAGE")


def _finding(rule, severity, level, what, action, evidence, ad=None, status=None):
    f = {"rule": rule, "severity": severity, "level": level,
         "what": what, "action": action, "evidence": evidence}
    if status:
        f["status"] = status
    if ad:
        f.update({"ad_id": ad.get("ad_id"), "ad_name": ad.get("ad_name"),
                  "campaign_name": (ad.get("campaign") or {}).get("name"),
                  "adset_name": (ad.get("adset") or {}).get("name")})
    return f


def score_snapshot(snapshot: dict, *, now: _dt.datetime | None = None,
                   thresholds: dict | None = None) -> dict:
    """Deterministic verdict for one brand. Same snapshot in, same findings out.

    A rule that cannot see what it needs says UNKNOWN or stays quiet; it never
    passes an ad it could not read.
    """
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

    # lead_ads_not_running — lead ads existed and none is running now.
    lead_ads = [a for a in ads if _is_lead_ad(a)]
    no_lead_running = bool(have_settings and lead_ads
                           and not any(_is_running(a, now) for a in lead_ads))
    if no_lead_running:
        best = max(lead_ads, key=lambda a: ((a.get("previous") or {}).get("leads") or 0)
                   + a["current"]["leads"])
        prev = best.get("previous") or {}
        # The previous window is the last complete one; the current window
        # holds only the days before the ad stopped.
        ref, ref_name = ((prev, "previous") if prev.get("leads") else (best["current"], "current"))
        ref_range = (snapshot.get("period") or {}).get(ref_name) or {}
        findings.append(_finding(
            "lead_ads_not_running", "high", "account",
            "No lead ad is running. In its last full window "
            f"'{best.get('ad_name')}' produced {ref.get('leads')} leads at "
            f"{_money(_cpl(ref))} each.",
            f"Restart '{best.get('ad_name')}' or launch a replacement lead ad.",
            {"reference_window": ref_range, "reference_window_leads": ref.get("leads"),
             "reference_window_cost_per_lead": _cpl(ref),
             "partial_window_leads": best["current"]["leads"],
             "partial_window_cost_per_lead": _cpl(best["current"])},
            best))

    for a in ads:
        cur, prev = a["current"], a.get("previous")
        live = _is_running(a, now)
        goal = _goal(a)

        # click_goal_leak — link clicks that never load the page.
        if (cur["link_clicks"] >= t["leak_min_link_clicks"] and (live or not have_settings)
                and _is_traffic_ad(a)):
            rate = cur["landing_page_views"] / cur["link_clicks"]
            if rate < t["leak_max_lpv_rate"]:
                real = cur["spend"] / cur["landing_page_views"] if cur["landing_page_views"] else None
                findings.append(_finding(
                    "click_goal_leak", "high", "ad",
                    f"Only {_pct(rate)} of {cur['link_clicks']:,} link clicks became page visits"
                    + (f", so each real visit costs {_money(real)}." if real else "."),
                    "Change the ad set's performance goal from link clicks to landing page views."
                    if goal == "LINK_CLICKS" else
                    "The ad set already optimises for page visits, so check the landing page: "
                    "load speed and that the Meta pixel fires.",
                    {"link_clicks": cur["link_clicks"], "landing_page_views": cur["landing_page_views"],
                     "lpv_rate": round(rate, 3), "optimization_goal": goal or None,
                     "cost_per_landing_page_view": real}, a))

        # home_page_destination — traffic ad that lands on the home page.
        if live and _is_traffic_ad(a):
            dest = a.get("destination") or {}
            if dest.get("status") == "RESOLVED":
                if not urllib.parse.urlparse(dest["url"]).path.strip("/"):
                    findings.append(_finding(
                        "home_page_destination", "medium", "ad",
                        "The button sends people to the home page, not a booking or service page.",
                        "Point the ad at the page for what it advertises (bookings, fitting, coaching).",
                        {"destination_url": dest["url"], "source": dest.get("source")},
                        a, status="HOME_PAGE"))
            else:
                findings.append(_finding(
                    "home_page_destination", "low", "ad",
                    "Meta did not return this ad's destination, so it could not be checked.",
                    "Open the ad in Ads Manager and confirm where the button goes.",
                    {"reason": dest.get("reason") or "no destination data in the snapshot"},
                    a, status="UNKNOWN"))

        # open_ended — running with no end date. A decision-date prompt, not a failure.
        days_on = _days_running(a, now)
        if (live and not _has_end_date(a) and not _is_lead_ad(a)
                and days_on is not None and days_on >= t["open_ended_min_days"]):
            if _is_awareness_ad(a):
                findings.append(_finding(
                    "open_ended_non_lead", "info", "ad",
                    f"Awareness ad running for {days_on} days with no review date "
                    f"({_money(cur['spend'])} this window). Evergreen awareness can be intended.",
                    "Set a review date and note what it should have achieved by then.",
                    {"days_running": days_on, "spend": cur["spend"], "objective": _objective(a)},
                    a, status="AWARENESS_REVIEW_DATE"))
            else:
                findings.append(_finding(
                    "open_ended_non_lead", "medium", "ad",
                    f"Running for {days_on} days with no end date "
                    f"({_money(cur['spend'])} this window).",
                    "Set a decision date and the result it should show by then.",
                    {"days_running": days_on, "spend": cur["spend"], "objective": _objective(a)},
                    a, status="DECISION_DATE"))

        c_cpl, p_cpl = _cpl(cur), _cpl(prev)
        cpl_change = ((c_cpl - p_cpl) / p_cpl) if (c_cpl and p_cpl) else None
        ctr_change = (((cur["ctr"] - prev["ctr"]) / prev["ctr"])
                      if (prev and prev["ctr"] > 0) else None)
        if prev:
            # fatigue — frequency pressure and measurable decay, both required.
            if (cur["frequency"] >= t["fatigue_min_frequency"] and ctr_change is not None
                    and -ctr_change >= t["fatigue_ctr_drop"]):
                findings.append(_finding(
                    "fatigue", "high", "ad",
                    f"People have seen this {cur['frequency']:.1f} times and click-through fell "
                    f"from {prev['ctr']:.2f}% to {cur['ctr']:.2f}%.",
                    "Replace the creative or widen the audience.",
                    {"frequency": cur["frequency"], "ctr": cur["ctr"], "previous_ctr": prev["ctr"]}, a))
            # cost_per_lead_rising.
            if (live and cpl_change is not None and cur["leads"] >= t["cpl_min_leads"]
                    and prev["leads"] >= t["cpl_min_leads"] and cpl_change >= t["cpl_rise"]):
                findings.append(_finding(
                    "cost_per_lead_rising", "medium", "ad",
                    f"Cost per lead rose from {_money(p_cpl)} to {_money(c_cpl)}.",
                    "Test a new creative against it before raising the budget.",
                    {"cost_per_lead": c_cpl, "previous_cost_per_lead": p_cpl,
                     "leads": cur["leads"], "previous_leads": prev["leads"]}, a))
            # cpm_rising — only with a second sign that performance is slipping.
            if (live and prev["cpm"] > 0
                    and cur["impressions"] >= t["cpm_min_impressions"]
                    and prev["impressions"] >= t["cpm_min_impressions"]
                    and (cur["cpm"] - prev["cpm"]) / prev["cpm"] >= t["cpm_rise"]):
                support = []
                if cpl_change is not None and cpl_change >= t["cpm_support_cpl_rise"]:
                    support.append("cost per lead up " + _pct(cpl_change))
                if ctr_change is not None and -ctr_change >= t["cpm_support_ctr_drop"]:
                    support.append("click-through down " + _pct(-ctr_change))
                if cur["frequency"] >= t["fatigue_min_frequency"]:
                    support.append(f"frequency {cur['frequency']:.1f}")
                cpl_improved = cpl_change is not None and cpl_change < 0
                if support and not cpl_improved:
                    findings.append(_finding(
                        "cpm_rising", "low", "ad",
                        f"It costs more to show ({_money(prev['cpm'])} to {_money(cur['cpm'])} per "
                        f"1,000 views) and performance is slipping: {', '.join(support)}.",
                        "Refresh the creative or audience before the cost per result climbs further.",
                        {"cpm": cur["cpm"], "previous_cpm": prev["cpm"], "supporting": support}, a))

        # below_average_ranking — read the three rankings together.
        if live and cur["impressions"] >= t["ranking_min_impressions"]:
            low = [k for k in _RANKINGS if _rank_low(cur.get(k))]
            if low:
                q, e, c = (_rank_low(cur.get(k)) for k in _RANKINGS)
                if c and not q and not e:
                    diagnosis = "POST_CLICK"
                    what = ("Meta ranks this ad below average for conversion rate, while its "
                            "quality and engagement are healthy. People respond to the ad but "
                            "do not follow through.")
                    action = ("Check the landing page, the offer and whether the objective "
                              "matches the result you want, before touching the creative.")
                elif q:
                    diagnosis = "CREATIVE_QUALITY"
                    what = "Meta ranks this ad's quality below average against competing ads."
                    action = "Rework the creative: Meta's quality ranking reflects the ad itself."
                elif e and not c:
                    diagnosis = "HOOK_OR_AUDIENCE"
                    what = "Meta ranks this ad below average for engagement; its quality is fine."
                    action = "Test a different opening or a different audience."
                else:
                    diagnosis = "ENGAGEMENT_AND_CONVERSION"
                    what = "Meta ranks this ad below average for engagement and conversion rate."
                    action = "Test a different opening or audience first, then check the landing page."
                findings.append(_finding(
                    "below_average_ranking", "medium", "ad", what, action,
                    dict({k: cur.get(k) for k in _RANKINGS}, impressions=cur["impressions"]),
                    a, status=diagnosis))

        # instagram_absent.
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

    # single_ad_no_test — once per ad set.
    by_set: dict = {}
    for a in delivered:
        by_set.setdefault((a.get("adset") or {}).get("id"), []).append(a)
    for set_ads in by_set.values():
        set_spend = sum(x["current"]["spend"] for x in set_ads)
        top = max(set_ads, key=lambda x: x["current"]["spend"])
        share = top["current"]["spend"] / set_spend
        if not (set_spend >= t["single_ad_min_spend"] and share >= t["single_ad_min_share"]
                and (_is_running(top, now) or not have_settings)):
            continue
        ev = {"adset_spend": set_spend, "ads_in_adset": len(set_ads),
              "top_ad_share": round(share, 3)}
        if len(set_ads) == 1:
            findings.append(_finding(
                "single_ad_no_test", "low", "adset",
                f"This ad set has one creative carrying all {_money(set_spend)}, "
                "so nothing is being compared.",
                "Add a second, clearly different creative to the ad set.",
                ev, top, status="ONE_CREATIVE_ONLY"))
        else:
            others = ", ".join(f"'{x.get('ad_name')}'" for x in set_ads if x is not top)
            findings.append(_finding(
                "single_ad_no_test", "medium", "adset",
                f"This ad set has {len(set_ads)} creatives but '{top.get('ad_name')}' gets "
                f"{_pct(share)} of the {_money(set_spend)}. Meta has stopped showing {others}.",
                f"Replace {others} with a clearly different creative, or run an A/B test "
                "so both get shown.",
                ev, top, status="MULTIPLE_CREATIVES_DELIVERY_CONCENTRATED"))

    # best_lead_ad — the lead ad worth scaling.
    proven = [a for a in running if a["current"]["leads"] >= t["best_lead_min_leads"]]
    if proven:
        best = min(proven, key=lambda a: _cpl(a["current"]))
        findings.append(_finding(
            "best_lead_ad", "info", "ad",
            f"Cheapest proven leads: {best['current']['leads']} at "
            f"{_money(_cpl(best['current']))} each.",
            "Raise this ad's budget in steps of about 20% and watch cost per lead.",
            {"leads": best["current"]["leads"], "cost_per_lead": _cpl(best["current"])}, best))

    # spend_mix — one account-level finding. Acquisition is what each ad set's
    # own goal defines: leads for lead ads, chats for conversations ads.
    acq_spend = sum(a["current"]["spend"] for a in delivered
                    if _acquisitions(a, a["current"]) > 0)
    if total_spend > 0 and lead_ads:
        share = acq_spend / total_spend
        if share < t["lead_spend_min_share"]:
            findings.append(_finding(
                "spend_mix", "high" if share < t["lead_spend_min_share"] / 2 else "medium", "account",
                f"{_pct(share)} of {_money(total_spend)} went to ads that produced a lead or, "
                "for conversation ads, a chat. The rest bought clicks and views.",
                "Restart or launch lead acquisition first; there is no running lead ad to move "
                "budget into." if no_lead_running else
                "Move budget from traffic and awareness to the lead ads.",
                {"acquisition_spend_share": round(share, 3), "total_spend": total_spend,
                 "acquisition_spend": acq_spend, "lead_spend": lead_spend},
                status="NO_LEAD_AD_RUNNING" if no_lead_running else "REALLOCATE"))

    # all_video — scoped to what this snapshot can see.
    media = [m for m in ((a.get("creative") or {}).get("media_type") for a in delivered) if m]
    if len(media) >= 3 and all(m == "video" for m in media):
        prev_static = [a for a in ads if a not in delivered
                       and ((a.get("previous") or {}).get("spend") or 0) > 0
                       and (a.get("creative") or {}).get("media_type") == "image"]
        days = (snapshot.get("period") or {}).get("days")
        what = (f"All {len(media)} ads that ran in this {days}-day window are videos; "
                "no static image ran in it.")
        if prev_static:
            what += (f" A static ('{prev_static[0].get('ad_name')}') did run in the previous "
                     "window. Nothing older than that was checked.")
        else:
            what += " None ran in the previous window either. Nothing older was checked."
        findings.append(_finding(
            "all_video", "low", "account", what,
            "Run a static alongside the best video so the two formats are compared in the "
            "same window.",
            {"ads_with_known_media": len(media), "window_days": days,
             "static_in_previous_window": bool(prev_static)}))

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9),
                                 -((f.get("evidence") or {}).get("spend") or 0)))
    fired = {f["rule"] for f in findings}
    unknown_dest = [f for f in findings
                    if f["rule"] == "home_page_destination" and f.get("status") == "UNKNOWN"]
    return {
        "schema": SCHEMA,
        "scoring_version": SCORING_VERSION,
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
            "acquisition_spend_share": round(acq_spend / total_spend, 3) if total_spend else None,
            "unknown_destinations": len(unknown_dest),
        },
        "findings": findings,
        "counts": {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITY_ORDER},
        "rules_not_fired": [r for r in RULES if r not in fired],
        "errors": snapshot.get("errors") or [],
        "note": "Recommendations only. Nothing here changes an ad.",
    }


def build(brand_id: str, account_id: str, token: str, *, days: int = 31,
          data_dir=None, get=None, get_as=None, api_version: str | None = None) -> dict:
    """Fetch, score and (when data_dir is given) cache one brand's verdict."""
    snap = fetch_snapshot(brand_id, account_id, token, days=days, get=get,
                          get_as=get_as, api_version=api_version)
    out = score_snapshot(snap)
    out["ads"] = snap["ads"]
    if data_dir and snap["ads"]:
        d = Path(data_dir) / "ads-brain"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{brand_id}__{days}d.json").write_text(
            json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out
