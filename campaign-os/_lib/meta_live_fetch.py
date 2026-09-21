"""fetch_facebook_analytics.py — REWRITTEN 2026-08-20 against a live working token.

Walks Meta Graph API with the live long-lived token at
~/.openclaw-instance2/workspace/clients/swing-shack/credentials/meta-token.json
and writes the per-post + business JSONs for both Instagram and Facebook.

This is what closes the 'data hole' for FB. The IG side gets the same
treatment (it was already accessible; we just hadn't refreshed it).

Run:  python3 scripts/fetch_facebook_analytics.py
Output:  data/ig-analytics.json  (real engagement per post)
         data/ig-business-analytics.json  (real account + reach)
         data/facebook-analytics.json  (real posts + shares)
         data/facebook-business-analytics.json  (real fan_count)
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _resolve_data_dir() -> Path:
    """Always write to DATA_DIR when set (Railway volume).

    The old post-conversion-score.json probe sent meta_refresh output to
    BUNDLED_DATA_DIR even though job outcomes read from $DATA_DIR.
    """
    env = os.environ.get("DATA_DIR")
    if env:
        p = Path(env)
        p.mkdir(parents=True, exist_ok=True)
        return p
    bundled = os.environ.get("BUNDLED_DATA_DIR")
    if bundled:
        return Path(bundled)
    return Path("data")


# DATA_DIR / DATA_DIR_RESOLVED — the second is the resolved-at-runtime
# path so the endpoint can override _resolve_data_dir() after import
# and have the fetcher pick up the new path. The first is the
# module-level constant for direct script invocation.
DATA_DIR = _resolve_data_dir()


def _live_data_dir() -> Path:
    """Resolve the live data dir at write time (respects overrides)."""
    return _resolve_data_dir()

# Token paths (the real long-lived token lives outside the repo).
# Order of precedence:
#   1. META_SYSTEM_USER_TOKEN env var (the CAPI System User token — never expires)
#   2. meta-token.json (the legacy long-lived user token, expires 60 days)
#   3. Railway secrets mounted at /data/credentials/...
# The CAPI System User is preferred because it has full CRU + page-level
# engagement metrics, the user token only has read-only.
CRED_PATHS = [
    Path.home() / ".openclaw-instance2/workspace/swing-shack-dashboard/data/credentials/meta-capi-system-user.json",
    Path.home() / ".openclaw-instance2/workspace/clients/swing-shack/credentials/meta-capi-system-user.json",
    Path.home() / ".openclaw-instance2/workspace/clients/swing-shack/credentials/meta-token.json",
    Path.home() / ".openclaw-instance2/workspace/swing-shack-dashboard/data/credentials/meta-token.json",
]


def _default_brand_id() -> str:
    from _lib.jobs.brand_lanes import load_brands_registry

    reg = load_brands_registry()
    return str(reg.get("default_brand_id") or "swing-shack")


def _brand_safe(brand_id: str) -> str:
    return brand_id.upper().replace("-", "_")


def _first_set_env(*names: str) -> tuple[str | None, str | None]:
    for name in names:
        val = (os.environ.get(name) or "").strip()
        if val:
            return name, val
    return None, None


def _load_token(brand: str | None = None) -> dict:
    """Resolve Meta credentials for a brand. Fail loud when required env is missing."""
    bid = brand or _default_brand_id()
    default_bid = _default_brand_id()

    from _lib.jobs.brand_lanes import load_brands_registry

    reg = load_brands_registry()
    brand_entry = (reg.get("brands") or {}).get(bid) or {}
    meta_scope = (brand_entry.get("integration_scope") or {}).get("meta") or {}
    scope_env = list(meta_scope.get("env") or [])

    token_candidates = [n for n in scope_env if "META_SYSTEM_USER_TOKEN" in n]
    if bid == default_bid:
        token_candidates = ["META_SYSTEM_USER_TOKEN", *token_candidates]
    token_env, tok = _first_set_env(*token_candidates)
    if not tok:
        if bid == default_bid:
            for p in CRED_PATHS:
                if p.exists():
                    try:
                        d = json.loads(p.read_text())
                        d["source"] = f"file:{p.name}"
                        d["token_kind"] = "capi_system_user" if "capi" in p.name else "long_lived_user"
                        d["ok"] = True
                        return d
                    except Exception:
                        continue
        missing = token_candidates[0] if token_candidates else "META_SYSTEM_USER_TOKEN"
        return {"ok": False, "error": f"{missing} not set"}

    page_candidates = [n for n in scope_env if n.startswith("META_PAGE_ID")]
    if bid == default_bid:
        page_candidates = ["META_PAGE_ID", *page_candidates]
    page_env, page_id = _first_set_env(*page_candidates)
    if not page_id:
        if bid == default_bid:
            page_id = os.environ.get("META_PAGE_ID", "198859063301219")
        else:
            missing = page_candidates[0] if page_candidates else f"META_PAGE_ID_{_brand_safe(bid)}"
            return {"ok": False, "error": f"{missing} not set"}

    ig_candidates = [n for n in scope_env if "META_INSTAGRAM" in n]
    if bid == default_bid:
        ig_candidates = ["META_INSTAGRAM_BUSINESS_ACCOUNT_ID", *ig_candidates]
    ig_env, ig_id = _first_set_env(*ig_candidates)
    if not ig_id:
        if bid == default_bid:
            ig_id = os.environ.get("META_INSTAGRAM_BUSINESS_ACCOUNT_ID", "17841456713897671")
        else:
            missing = ig_candidates[0] if ig_candidates else f"META_INSTAGRAM_BUSINESS_ACCOUNT_ID_{_brand_safe(bid)}"
            return {"ok": False, "error": f"{missing} not set"}

    return {
        "ok": True,
        "access_token": tok,
        "page_id": page_id,
        "instagram_account_id": ig_id,
        "source": f"env:{token_env or 'META_SYSTEM_USER_TOKEN'}",
        "token_kind": "capi_system_user",
    }


def _write_meta_output(name: str, obj: dict, brand: str | None) -> None:
    from _lib.jobs.layer1._io import io_for_job

    io_for_job("meta_refresh", brand).write(name, obj)


def _http(url, timeout=15):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)


def fetch_all(*, brand: str | None = None) -> dict:
    """Pull IG + FB live data + write all 4 JSONs. Returns a summary dict."""
    creds = _load_token(brand)
    if not creds or creds.get("ok") is False:
        return creds if creds else {"ok": False, "error": "no Meta token found"}
    tok = creds["access_token"]
    ig_id = creds["instagram_account_id"]
    page_id = creds["page_id"]

    # 1. Exchange user token for page token
    url = f"https://graph.facebook.com/v19.0/{page_id}?fields=access_token,fan_count,followers_count,name&access_token={tok}"
    body, err = _http(url)
    if err:
        return {"ok": False, "error": f"page token exchange failed: {err}"}
    page_tok = body["access_token"]
    fan_count = body.get("fan_count", 0)
    page_name = body.get("name", "Swing Shack")

    # 2. IG account info
    url = f"https://graph.facebook.com/v19.0/{ig_id}?fields=id,username,biography,followers_count,follows_count,media_count,profile_picture_url&access_token={tok}"
    body, err = _http(url)
    if err:
        return {"ok": False, "error": f"IG account fetch failed: {err}"}
    ig_followers = body.get("followers_count", 0)
    ig_follows = body.get("follows_count", 0)
    ig_media = body.get("media_count", 0)
    ig_bio = body.get("biography", "")
    ig_handle = body.get("username")

    # 3. IG posts + per-post engagement
    metrics = "impressions,reach,replies,saved,likes,comments,shares,total_interactions,profile_visits"
    url = f"https://graph.facebook.com/v19.0/{ig_id}/media?fields=id,caption,media_type,permalink,timestamp,insights.metric({metrics})&limit=30&access_token={tok}"
    body, err = _http(url)
    if err:
        return {"ok": False, "error": f"IG posts fetch failed: {err}"}
    posts = body.get("data", [])

    # 4. Normalize IG posts
    now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    ig_posts = []
    for post in posts:
        cap = post.get("caption") or ""
        ts = post.get("timestamp", "")
        ins = {}
        for m in post.get("insights", {}).get("data", []):
            _m_name = m.get("name")
            if not _m_name:
                continue
            for v in m.get("values", []):
                val = v.get("value", 0)
                if isinstance(val, dict): val = sum(val.values())
                ins[_m_name] = val
        likes = ins.get("likes", 0)
        comments = ins.get("comments", 0)
        saves = ins.get("saved", 0)
        shares = ins.get("shares", 0)
        reach = ins.get("reach", 0) or 0
        er = (likes + comments + saves) / reach * 100 if reach else 0
        fmt = {"VIDEO": "reel", "CAROUSEL_ALBUM": "carousel"}.get(post.get("media_type"), "static")
        hook = cap.split("\n", 1)[0] if cap else ""
        pillar = "unknown"
        cap_low = cap.lower()
        if any(t in cap_low for t in ["sub 70", "fitting", "club", "avoda", "shaft", "t150", "titleist"]): pillar = "equipment"
        elif any(t in cap_low for t in ["lesson", "coach"]): pillar = "coaching"
        ig_posts.append({
            "id": post["id"], "postId": post["id"], "timestamp": ts,
            "captionPreview": cap[:200], "hook_text": hook[:120], "hook_id": post["id"],
            "format_type": fmt, "topic_cluster": pillar, "reach": reach,
            "likes": likes, "comments": comments, "saves": saves, "shares": shares,
            "profile_visits": ins.get("profile_visits", 0), "follows_gained": 0,
            "engagementRate": f"{er:.2f}",
            "saveRate": f"{saves / reach * 100:.2f}" if reach else "0.00",
            "shareRate": f"{shares / reach * 100:.2f}" if reach else "0.00",
            "followConversion": "0.000",
        })

    _write_meta_output("ig-analytics.json", {
        "schema": "https://clawdia.io/agents/instagram-analytics/v1",
        "updated": now_iso,
        "source": "Meta Graph API /v19.0 IG media insights (live fetch 2026-08-20)",
        "total_posts": len(ig_posts),
        "posts": ig_posts,
    }, brand)

    # IG business
    avg_reach = sum(p["reach"] for p in ig_posts) / 30 if ig_posts else 0
    _write_meta_output("ig-business-analytics.json", {
        "schema": "https://clawdia.io/agents/ig-business-analytics/v1",
        "updated": now_iso,
        "source": "Meta Graph API /v19.0 IG account info (live fetch 2026-08-20)",
        "account": {"id": ig_id, "username": ig_handle, "biography": ig_bio,
                   "followers_count": ig_followers, "follows_count": ig_follows,
                   "media_count": ig_media, "profile_picture_url": body.get("profile_picture_url")},
        "daily_reach": [{"date": now_iso[:10], "value": int(avg_reach)}],
        "media": ig_posts[:5],
        "top_post": {"permalink": (ig_posts[0] if ig_posts else {}).get("id")},
        "window_totals": {
            "accounts_engaged": sum(1 for p in ig_posts if p["likes"] + p["comments"] > 0),
            "profile_links_taps": sum(p.get("profile_visits", 0) for p in ig_posts),
            "profile_views": sum(p.get("profile_visits", 0) for p in ig_posts),
            "total_interactions": sum(p["likes"] + p["comments"] + p["saves"] + p["shares"] for p in ig_posts),
        },
    }, brand)

    # 4.5. PAGE-LEVEL engagement metrics.
    # Built 2026-08-21: page-level metrics come from TWO endpoints:
    #   - /v19.0/{page_id}/insights          → page_post_engagements, page_views_total,
    #                                            page_actions_post_reactions_total
    #   - /v19.0/{ad_account_id}/insights    → page_impressions, page_fans, page_fan_adds
    #                                            (these are "App Insights" — only
    #                                            exposed via the ad account endpoint
    #                                            even for read-only fetches)
    # Both are tried. Some may fail with #100 if the bound ad account
    # does not have the page as a child object; in that case the page
    # endpoint version is tried as a fallback.
    page_metrics = {}
    page_metric_errors = {}  # for debugging — surfaced in the response
    if not err and page_tok:
        # Discovery trail: trace which ad-account path the fetcher tried
        discovery = {"tried_page_endpoint": False, "page_endpoint_returned": None,
                     "tried_me_adaccounts": False, "me_adaccounts_returned": None,
                     "final_ad_account_id": None}
        # First try the page endpoint (handles most metrics).
        for metric in ["page_post_engagements", "page_views_total",
                       "page_actions_post_reactions_total"]:
            since_ts = int((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=30)).timestamp())
            url = f"https://graph.facebook.com/v19.0/{page_id}/insights?metric={metric}&period=day&since={since_ts}&access_token={page_tok}"
            body, m_err = _http(url)
            if m_err:
                page_metric_errors[f"page_endpoint.{metric}"] = m_err[:200]
                continue
            for series in (body or {}).get("data", []):
                vals = series.get("values", []) or []
                total = 0
                for v in vals:
                    val = v.get("value", 0) or 0
                    if isinstance(val, dict):
                        val = sum((vv or 0) for vv in val.values())
                    elif isinstance(val, list):
                        val = sum((vv or 0) for vv in val)
                    total += val
                _m = series.get("name")
                if _m:
                    page_metrics[_m] = {
                        "total_30d": total,
                        "points": len(vals),
                        "latest": (vals[-1] if vals else None) or {},
                        "endpoint": f"/{page_id}/insights",
                    }
        # Then discover the ad account bound to this page and try the
        # remaining metrics from there. If no ad account, skip.
        try:
            discovery["tried_page_endpoint"] = True
            url = f"https://graph.facebook.com/v19.0/{page_id}?fields=ads_permitted_roles,adaccounts{{id,name,account_status}}&access_token={page_tok}"
            page_meta, pm_err = _http(url)
            adaccounts = (page_meta or {}).get("adaccounts", {}).get("data", [])
            discovery["page_endpoint_returned"] = len(adaccounts)
            ad_acct_id = None
            if adaccounts:
                # Pick the first active ad account
                for a in adaccounts:
                    if a.get("account_status") == 1:
                        ad_acct_id = a.get("id")
                        break
                if not ad_acct_id and adaccounts:
                    ad_acct_id = adaccounts[0].get("id")
        except Exception:
            ad_acct_id = None
        # If no ad account via the page, try me/adaccounts.
        # IMPORTANT: use the user/system token (tok), NOT the page token
        # (page_tok). The page token is a child of /{page_id} exchange and
        # has only page-level scope — ads_management is missing, so
        # me/adaccounts returns #100 "Tried accessing nonexisting field".
        if not ad_acct_id:
            discovery["tried_me_adaccounts"] = True
            url = f"https://graph.facebook.com/v19.0/me/adaccounts?access_token={tok}"
            me_acct, me_err = _http(url)
            accts = (me_acct or {}).get("data", []) or []
            discovery["me_adaccounts_returned"] = len(accts)
            if me_err:
                page_metric_errors["me_adaccounts"] = m_err[:200] if m_err else me_err
                # Try again with page_tok as a last resort (already did above)
            elif accts:
                ad_acct_id = accts[0].get("id")
        discovery["final_ad_account_id"] = ad_acct_id
        if ad_acct_id:
            # IMPORTANT: use the system token (tok) here, not page_tok.
            # page_impressions / page_fans / page_fan_adds are exposed via
            # the ad-account endpoint, but page-level tokens lack the
            # ads_management scope to hit it.
            for metric in ["page_impressions", "page_fans", "page_fan_adds"]:
                since_ts = int((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=30)).timestamp())
                url = f"https://graph.facebook.com/v19.0/{ad_acct_id}/insights?metric={metric}&period=day&since={since_ts}&access_token={tok}"
                body, m_err = _http(url)
                if m_err:
                    page_metric_errors[f"ad_account.{metric}"] = m_err[:200]
                    # If ad account endpoint also rejects, try the page endpoint
                    url = f"https://graph.facebook.com/v19.0/{page_id}/insights?metric={metric}&period=day&since={since_ts}&access_token={page_tok}"
                    body, m_err = _http(url)
                    if m_err:
                        page_metric_errors[f"page_endpoint.{metric}"] = m_err[:200]
                        continue
                for series in (body or {}).get("data", []):
                    vals = series.get("values", []) or []
                    total = 0
                    for v in vals:
                        val = v.get("value", 0) or 0
                        if isinstance(val, dict):
                            val = sum((vv or 0) for vv in val.values())
                        elif isinstance(val, list):
                            val = sum((vv or 0) for vv in val)
                        total += val
                    _m = series.get("name")
                    if _m:
                        page_metrics[_m] = {
                            "total_30d": total,
                            "points": len(vals),
                            "latest": (vals[-1] if vals else None) or {},
                            "endpoint": f"/{ad_acct_id}/insights",
                        }

    # 4.6. PER-POST engagement metrics.
    # Two strategies:
    #   1. Use /{page_id}/posts?fields=insights.metric(...) — works if the
    #      page token has post-level engagement scopes
    #   2. Use /{post_id}/insights?metric=... per-post — universal, only
    #      requires the post_id (which we get from strategy 1)
    # Strategy 2 always works for ANY token with post-level access.
    per_post_engagement = {}
    fb_posts_with_metrics = []
    if not err and page_tok:
        # Strategy 1: list posts with inline engagement metrics
        url = (f"https://graph.facebook.com/v19.0/{page_id}/posts"
               f"?fields=id,message,permalink_url,created_time,shares&"
               f"limit=20&access_token={page_tok}")
        body, err = _http(url)
        if not err and body:
            posts_list = body.get("data", [])
            for p in posts_list:
                post_id = p.get("id", "")
                ins_summary = {}
                # First try inline insights (strategy 1)
                inline_ins = (p.get("insights") or {}).get("data", [])
                if inline_ins:
                    for m in inline_ins:
                        values = m.get("values", []) or []
                        if values:
                            val = values[0].get("value", 0) or 0
                            if isinstance(val, dict):
                                val = sum((v or 0) for v in val.values())
                            ins_summary[m["name"]] = val
                # Then try per-post insights endpoint (strategy 2) —
                # works for any post_id and only requires basic read access
                if not ins_summary:
                    for metric in ["post_impressions", "post_impressions_unique",
                                   "post_engaged_users", "post_reactions_by_type_total",
                                   "post_clicks"]:
                        # Use the system token (tok) for per-post insights too —
                        # page_tok is restricted to the single page's scope.
                        url2 = f"https://graph.facebook.com/v19.0/{post_id}/insights?metric={metric}&access_token={tok}"
                        body2, e2 = _http(url2)
                        if e2:
                            continue
                        for series in (body2 or {}).get("data", []):
                            vals = series.get("values", []) or []
                            if vals:
                                val = vals[0].get("value", 0) or 0
                                if isinstance(val, dict):
                                    val = sum((v or 0) for v in val.values())
                                _metric_name = series.get("name")
                                if _metric_name:
                                    ins_summary[_metric_name] = val
                per_post_engagement[post_id] = ins_summary
                fb_posts_with_metrics.append({
                    "id": post_id,
                    "postId": post_id,
                    "timestamp": p.get("created_time", ""),
                    "captionPreview": (p.get("message") or "")[:200],
                    "hook_text": ((p.get("message") or "").split("\n", 1)[0])[:120] if p.get("message") else "",
                    "hook_id": post_id,
                    "format_type": "post",
                    "topic_cluster": "unknown",
                    "reach": ins_summary.get("post_impressions_unique"),
                    "likes": sum((ins_summary.get("post_reactions_by_type_total") or {}).values()
                                 if isinstance(ins_summary.get("post_reactions_by_type_total"), dict)
                                 else [ins_summary.get("post_reactions_by_type_total") or 0]),
                    "comments": None,
                    "saves": None,
                    "shares": (p.get("shares") or {}).get("count", 0) if isinstance(p.get("shares"), dict) else 0,
                    "profile_visits": None,
                    "follows_gained": None,
                    "engagementRate": (f"{(ins_summary.get('post_engaged_users', 0) / max(ins_summary.get('post_impressions_unique', 1), 1) * 100):.2f}"
                                       if ins_summary.get('post_impressions_unique') else None),
                    "saveRate": None,
                    "shareRate": None,
                    "followConversion": None,
                })

    # 5. FB posts (always reachable, even without engagement metrics)
    url = f"https://graph.facebook.com/v19.0/{page_id}/posts?fields=id,message,permalink_url,created_time,shares&limit=20&access_token={page_tok}"
    body, err = _http(url)
    if err:
        return {"ok": True, "ig_posts": len(ig_posts), "fb_posts": 0, "fan_count": fan_count,
                "warning": f"FB posts fetch failed: {err}"}
    fb_posts = body.get("data", [])
    fb_normalized = [{
        "id": p["id"], "postId": p["id"], "timestamp": p.get("created_time", ""),
        "captionPreview": (p.get("message") or "")[:200],
        "hook_text": ((p.get("message") or "").split("\n", 1)[0])[:120] if p.get("message") else "",
        "hook_id": p["id"], "format_type": "post", "topic_cluster": "unknown",
        "reach": None, "likes": None, "comments": None, "saves": None,
        "shares": (p.get("shares") or {}).get("count", 0) if isinstance(p.get("shares"), dict) else 0,
        "profile_visits": None, "follows_gained": None,
        "engagementRate": None, "saveRate": None, "shareRate": None, "followConversion": None,
    } for p in fb_posts]
    # When the CAPI System User is live, we have per-post engagement metrics.
    # Use those over the basic fb_normalized (shares only).
    posts_to_save = fb_posts_with_metrics if fb_posts_with_metrics else fb_normalized
    token_kind = creds.get("token_kind", "long_lived_user")
    is_capi = token_kind == "capi_system_user"
    _write_meta_output("facebook-analytics.json", {
        "schema": "https://clawdia.io/agents/facebook-analytics/v1",
        "channel": "facebook",
        "updated": now_iso,
        "generated_by": f"meta_live_fetch.py v2 (live fetch 2026-08-20, token={token_kind})",
        "data_pending": False,
        "posts": posts_to_save,
        "next_fetch_url": f"https://graph.facebook.com/v19.0/{page_id}/posts",
        "source_note": (
            f"Posts fetched live (count={len(posts_to_save)}). Per-post engagement metrics included: {is_capi}."
            if is_capi else
            f"Posts fetched live (count={len(fb_posts)}). Per-post engagement metrics require pages_read_user_content + read_insights on the Clawdia app — app review pending per data/api-connections.json."
        ),
        "total_posts": len(posts_to_save),
    }, brand)

    # FB business — enriched with page-level engagement when CAPI token is live
    token_kind = creds.get("token_kind", "long_lived_user")
    is_capi = token_kind == "capi_system_user"
    _write_meta_output("facebook-business-analytics.json", {
        "schema": "https://clawdia.io/agents/facebook-business-analytics/v1",
        "channel": "facebook",
        "updated": now_iso,
        "generated_by": f"meta_live_fetch.py v2 (live fetch 2026-08-20, token={token_kind})",
        "data_pending": not is_capi,
        "account": {"id": page_id, "handle": "swing-shack", "name": page_name,
                   "biography": None, "followers_count": fan_count, "follows_count": None,
                   "media_count": None, "verified": False},
        "daily_reach": page_metrics.get("page_impressions", {}).get("points", 0) and [
            None
        ],
        "media": [],
        "top_post": {"permalink": None},
        "window_totals": {
            "page_views": page_metrics.get("page_views_total", {}).get("total_30d"),
            "page_likes": fan_count,
            "page_impressions_30d": page_metrics.get("page_impressions", {}).get("total_30d"),
            "page_post_engagements_30d": page_metrics.get("page_post_engagements", {}).get("total_30d"),
            "page_fan_adds_30d": page_metrics.get("page_fan_adds", {}).get("total_30d"),
            "page_actions_post_reactions_total_30d": page_metrics.get("page_actions_post_reactions_total", {}).get("total_30d"),
        },
        "page_metrics_30d": page_metrics,
        "per_post_engagement": per_post_engagement,
        "_meta_pending_reason": (
            "Page-level engagement metrics live via CAPI System User token."
            if is_capi else
            "Page-level engagement metrics blocked by Meta app review (pages_read_user_content + read_insights on Clawdia app). "
            "Generate a CAPI System User token at business.facebook.com/settings/system-users to bypass."
        ),
    }, brand)

    return {
        "ok": True,
        "ig_followers": ig_followers,
        "ig_posts": len(ig_posts),
        "fb_fan_count": fan_count,
        "fb_posts": len(fb_posts),
        "fb_page_metrics_30d": page_metrics,
        "fb_page_metric_errors": page_metric_errors,
        "token_kind": creds.get("token_kind", "long_lived_user"),
        "token_source": creds.get("source", "?"),
        "ad_account_id": ad_acct_id,
        "ad_account_discovery": discovery,
    }


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    result = fetch_all()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("ok") else 1)


# ─── V2.4.1: PAID-MEDIA INGESTION (sibling to fetch_all) ────────────
# Per V2.4.1 §1: extend the existing meta_refresh job to also
# pull paid-media. Read-only — no Meta mutation. Reuses the
# canonical token → brand → ad_account mapping.
# Avoids importing app.py (circular import) by using os.environ
# directly.

_META_ADS_TOKEN_FOR_BRAND = {
    "stick": "META_SYSTEM_USER_TOKEN_STICK",
    "swing-shack": "META_SYSTEM_USER_TOKEN",
}
_META_ADS_ACCOUNT_FOR_BRAND = {
    "stick": "act_2101557317059886",
    "swing-shack": "act_1024882912541604",
}
_META_ADS_ACCOUNT_NAME = {
    "act_2101557317059886": "Stick",
    "act_1024882912541604": "Swing Shack – Ad account",
}
_META_ADS_BRAND_CLASSIFICATION = {
    "act_2101557317059886": "CANONICAL_STICK",
    "act_1024882912541604": "CANONICAL_SWING_SHACK",
}
_META_GRAPH_API_VERSION = "v26.0"


def _pm_get(path, token, params):
    """GET a Meta Graph API endpoint. Returns parsed JSON or
    (None, error). Read-only."""
    import urllib.request as _url_req
    base = "https://graph.facebook.com"
    full = f"{base}{path}"
    sep = "&" if "?" in full else "?"
    qp = "&".join(f"{k}={_url_req.quote(str(v), safe='')}"
                   for k, v in params.items() if v is not None)
    full_with_access = f"{full}{sep}access_token={_url_req.quote(token, safe='')}"
    if qp:
        full_with_access += f"&{qp}"
    try:
        with _url_req.urlopen(full_with_access, timeout=60) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        try:
            return None, f"HTTP {e.code}: {e.read().decode()[:200]}"
        except Exception:
            return None, f"HTTP {e.code}"
    except Exception as e:
        return None, str(e)[:200]


def _pm_insights(act_id, token, time_range, level=None):
    """Read-only /insights call. Same shape as the app.py version."""
    if level and level != "default":
        fields = ("campaign_id,campaign_name,adset_id,adset_name,"
                  "ad_id,ad_name,objective,"
                  "impressions,reach,frequency,clicks,spend,"
                  "cpc,cpm,ctr,actions,conversions,"
                  "cost_per_action_type,cost_per_conversion,"
                  "purchase_roas")
    else:
        fields = ("impressions,reach,frequency,clicks,spend,"
                  "cpc,cpm,ctr,actions,conversions,"
                  "cost_per_action_type,cost_per_conversion,"
                  "purchase_roas")
    path = f"/{_META_GRAPH_API_VERSION}/{act_id}/insights"
    return _pm_get(path, token, {"fields": fields,
                                    "time_range": json.dumps(time_range),
                                    "limit": 1000,
                                    "level": level} if (level and level != "default") else
                                  {"fields": fields,
                                    "time_range": json.dumps(time_range),
                                    "limit": 1000})


def _pm_account_meta(act_id, token):
    """Fetch ad-account metadata (id, name, amount_spent, currency,
    spend_cap, account_status, timezone_name). Retry without
    owner_business on 400."""
    path = f"/{_META_GRAPH_API_VERSION}/{act_id}"
    fields_full = ("id,name,account_status,amount_spent,spend_cap,"
                    "currency,timezone_name,balance,disable_reason,"
                    "owner_business")
    for fields in (fields_full,
                    "id,name,account_status,amount_spent,spend_cap,"
                    "currency,timezone_name,balance,disable_reason"):
        body, err = _pm_get(path, token, {"fields": fields})
        if not err and body and body.get("id"):
            return 200, body
        if err and "owner_business" in err:
            continue
        return (200, body) if not err else (400, {"error_msg": err})
    return 400, {"error_msg": "owner_business fallback exhausted"}


def _pm_campaigns(act_id, token, brand_id):
    """Fetch /campaigns list (id, name, objective, status,
    effective_status, daily_budget, lifetime_budget, start_time,
    stop_time, buying_type, special_ad_category)."""
    path = f"/{_META_GRAPH_API_VERSION}/{act_id}/campaigns"
    body, err = _pm_get(path, token, {"fields": ("id,name,objective,status,"
                                                    "effective_status,"
                                                    "daily_budget,"
                                                    "lifetime_budget,"
                                                    "start_time,stop_time,"
                                                    "buying_type,"
                                                    "special_ad_category,"
                                                    "created_time,updated_time,"
                                                    "budget_remaining,"
                                                    "source_id"),
                                        "limit": 500})
    if err:
        return {"ok": False, "data": [], "error": err}
    return {"ok": True, "data": body.get("data") or []}


def _pm_normalize(rows):
    """Convert Meta insights row → dict with numeric fields."""
    def _i(x):
        try:
            return int(x) if x is not None else None
        except Exception:
            return None
    def _f(x):
        try:
            return float(x) if x is not None else None
        except Exception:
            return None
    out = []
    for row in rows or []:
        actions = [{"action_type": a.get("action_type"),
                     "value": a.get("value")} for a in (row.get("actions") or [])]
        cpas = [{"action_type": c.get("action_type"),
                  "value": c.get("value")} for c in (row.get("cost_per_action_type") or [])]
        convs = [{"action_type": c.get("action_type"),
                   "value": c.get("value")} for c in (row.get("conversions") or [])]
        out.append({
            "campaign_id": row.get("campaign_id"),
            "campaign_name": row.get("campaign_name"),
            "adset_id": row.get("adset_id"),
            "adset_name": row.get("adset_name"),
            "ad_id": row.get("ad_id"),
            "ad_name": row.get("ad_name"),
            "objective": row.get("objective"),
            "impressions": _i(row.get("impressions")),
            "reach": _i(row.get("reach")),
            "frequency": _f(row.get("frequency")),
            "clicks": _i(row.get("clicks")),
            "spend": _f(row.get("spend")),
            "cpc": _f(row.get("cpc")),
            "cpm": _f(row.get("cpm")),
            "ctr": _f(row.get("ctr")),
            "actions": actions,
            "cost_per_action_type": cpas,
            "conversions": convs,
        })
    return out


def fetch_paid_media(brand_id: str | None = None,
                       period_days: int = 31) -> dict:
    """Pull paid-media for one brand (or both if brand_id is None).

    Per V2.4.1 §1: read-only Meta Graph API ingestion.
    Writes cache to DATA_DIR/paid-media/<brand>.json.
    Retains last-known-good cache on failure (caller controls
    via separate write-after-success logic in app.py)."""
    now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    brands = ([brand_id] if brand_id
              else list(_META_ADS_TOKEN_FOR_BRAND.keys()))
    out = {"ok": True, "refreshed_at": now_iso,
            "fetched_at": now_iso, "brands": {}}
    for bid in brands:
        token_label = _META_ADS_TOKEN_FOR_BRAND.get(bid)
        token = os.environ.get(token_label) if token_label else None
        acc = _META_ADS_ACCOUNT_FOR_BRAND.get(bid)
        if not token or not acc:
            out["brands"][bid] = {"ok": False,
                                    "error": "no canonical token or account",
                                    "data_status": "NOT_CONNECTED"}
            out["ok"] = False
            continue
        # Period contract: today excluded, 31d current, 31d previous,
        # YTD since Jan 1 of current year.
        today = _dt.date.today()
        current_end = (today - _dt.timedelta(days=1)).isoformat()
        current_start = (today - _dt.timedelta(days=period_days)).isoformat()
        previous_end = (today - _dt.timedelta(days=period_days + 1)).isoformat()
        previous_start = (today - _dt.timedelta(days=period_days * 2 + 1)).isoformat()
        year_start = f"{today.year}-01-01"
        report_period = {
            "current_start": current_start,
            "current_end": current_end,
            "previous_start": previous_start,
            "previous_end": previous_end,
            "days_per_window": period_days,
            "data_complete_through": current_end,
            "fetched_at": now_iso,
        }
        # Fetch account meta
        sc, aa_meta = _pm_account_meta(acc, token)
        # Fetch campaigns metadata
        cmeta = _pm_campaigns(acc, token, bid)
        # Fetch insights at three windows
        cur = _pm_insights(acc, token,
                            {"since": current_start, "until": current_end},
                            level="campaign")
        prev = _pm_insights(acc, token,
                              {"since": previous_start, "until": previous_end},
                              level="campaign")
        ytd = _pm_insights(acc, token,
                            {"since": year_start, "until": current_end},
                            level="campaign")
        # If any insights call failed, mark the brand with error
        # but DO NOT zero out — let the caller retain last-known-good.
        err_msgs = []
        if not cur[0]: err_msgs.append(f"current: {cur[1]}")
        if not prev[0]: err_msgs.append(f"previous: {prev[1]}")
        if not ytd[0]: err_msgs.append(f"ytd: {ytd[1]}")
        cur_rows = _pm_normalize(cur[0].get("data") if cur[0] else [])
        prev_rows = _pm_normalize(prev[0].get("data") if prev[0] else [])
        ytd_rows = _pm_normalize(ytd[0].get("data") if ytd[0] else [])
        # Campaign-name enrichment
        cid_to_cname = {str(c.get("id")): c.get("name")
                          for c in (cmeta.get("data") or [])}
        for rows in (cur_rows, prev_rows, ytd_rows):
            for r in rows:
                if r.get("campaign_id") and not r.get("campaign_name"):
                    r["campaign_name"] = cid_to_cname.get(
                        str(r.get("campaign_id")))
        # Totals
        def _totals(rows):
            t = {"spend": 0, "impressions": 0, "reach": 0,
                  "clicks": 0}
            for r in rows:
                t["spend"] += (r.get("spend") or 0)
                t["impressions"] += (r.get("impressions") or 0)
                t["reach"] += (r.get("reach") or 0)
                t["clicks"] += (r.get("clicks") or 0)
            if t["clicks"]:
                t["cpc"] = round(t["spend"] / t["clicks"], 4)
            if t["impressions"]:
                t["cpm"] = round(t["spend"] / t["impressions"] * 1000, 2)
            if t["impressions"]:
                t["ctr"] = round(t["clicks"] / t["impressions"] * 100, 2)
            t["campaigns_with_delivery"] = len([r for r in rows if (r.get("spend") or 0) > 0])
            return {k: (round(v, 2) if isinstance(v, float) else v)
                     for k, v in t.items()}
        cache = {
            "schema": "https://campaign-os/paid-media/v2",
            "brand_id": bid,
            "ad_account_id": acc,
            "ad_account_name": _META_ADS_ACCOUNT_NAME.get(acc, "?"),
            "brand_classification": _META_ADS_BRAND_CLASSIFICATION.get(acc, "?"),
            "token_label": token_label,
            "report_period": report_period,
            "fetched_at": now_iso,
            "data_as_of": current_end,
            "ad_account_meta": aa_meta if sc == 200 else {
                "status": sc,
                "error": (aa_meta.get("error_msg") if isinstance(aa_meta, dict) else ""),
            },
            "current_period": {"time_range": {"since": current_start,
                                                 "until": current_end},
                                "level": "campaign",
                                "ok": bool(cur[0]),
                                "rows": cur_rows,
                                "error": (cur[1] or "") if not cur[0] else ""},
            "previous_period": {"time_range": {"since": previous_start,
                                                  "until": previous_end},
                                 "level": "campaign",
                                 "ok": bool(prev[0]),
                                 "rows": prev_rows,
                                 "error": (prev[1] or "") if not prev[0] else ""},
            "ytd": {"time_range": {"since": year_start, "until": current_end},
                     "level": "campaign",
                     "ok": bool(ytd[0]),
                     "rows": ytd_rows,
                     "error": (ytd[1] or "") if not ytd[0] else ""},
            "current_totals": _totals(cur_rows),
            "previous_totals": _totals(prev_rows),
            "ytd_totals": _totals(ytd_rows),
            "campaigns": cmeta.get("data") or [],
            "data_status": "LIVE" if not err_msgs else "PARTIAL",
            "errors": err_msgs,
            "data_source": "meta_graph_api",
            "api_version": _META_GRAPH_API_VERSION,
        }
        # Write to canonical cache file (single root per brand).
        try:
            (DATA_DIR / "paid-media").mkdir(parents=True, exist_ok=True)
            cache_path = DATA_DIR / "paid-media" / f"{bid}.json"
            cache_path.write_text(json.dumps(cache, indent=2))
            cache["cache_path"] = str(cache_path)
        except Exception as e:
            cache["cache_write_error"] = str(e)[:200]
        out["brands"][bid] = {
            "ok": not err_msgs,
            "data_status": cache["data_status"],
            "fetched_at": now_iso,
            "data_as_of": current_end,
            "campaigns_count": len(cmeta.get("data") or []),
            "current_rows": len(cur_rows),
            "previous_rows": len(prev_rows),
            "ytd_rows": len(ytd_rows),
            "ytd_spend": round(_totals(ytd_rows)["spend"] or 0, 2),
            "errors": err_msgs,
        }
        if err_msgs:
            out["ok"] = False
    return out


def fetch_all_with_paid_media(*, brand: str | None = None) -> dict:
    """Combined: existing meta_refresh + paid-media ingestion.

    Per V2.4.1 §1: extend the existing meta_refresh job to also
    pull paid-media. Returns combined summary."""
    base = fetch_all(brand=brand) or {"ok": True, "summary": "no-op"}
    paid = fetch_paid_media(brand_id=brand)
    base["paid_media"] = paid
    base["combined_ok"] = bool(base.get("ok")) and bool(paid.get("ok"))
    base["source"] = "extended meta_refresh job (V2.4.1 §1)"
    return base
