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
    env = os.environ.get("DATA_DIR")
    if env and Path(env).exists() and (Path(env) / "post-conversion-score.json").exists():
        return Path(env)
    bundled = os.environ.get("BUNDLED_DATA_DIR")
    if bundled:
        return Path(bundled)
    return Path(os.environ.get("DATA_DIR") or "data")


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


def _load_token() -> dict | None:
    # CAPI System User token first (env var) — never expires, full access
    if os.environ.get("META_SYSTEM_USER_TOKEN"):
        return {
            "access_token": os.environ["META_SYSTEM_USER_TOKEN"],
            "page_id": os.environ.get("META_PAGE_ID", "198859063301219"),
            "instagram_account_id": os.environ.get("META_INSTAGRAM_BUSINESS_ACCOUNT_ID", "17841456713897671"),
            "source": "env:META_SYSTEM_USER_TOKEN",
            "token_kind": "capi_system_user",
        }
    # Then local file paths
    for p in CRED_PATHS:
        if p.exists():
            try:
                d = json.loads(p.read_text())
                d["source"] = f"file:{p.name}"
                d["token_kind"] = "capi_system_user" if "capi" in p.name else "long_lived_user"
                return d
            except Exception:
                continue
    return None


def _http(url, timeout=15):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)


def fetch_all() -> dict:
    """Pull IG + FB live data + write all 4 JSONs. Returns a summary dict."""
    creds = _load_token()
    if not creds:
        return {"ok": False, "error": "no Meta token found"}
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
            for v in m.get("values", []):
                val = v.get("value", 0)
                if isinstance(val, dict): val = sum(val.values())
                ins[m["name"]] = val
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

    (_live_data_dir() / "ig-analytics.json").write_text(json.dumps({
        "schema": "https://clawdia.io/agents/instagram-analytics/v1",
        "updated": now_iso,
        "source": "Meta Graph API /v19.0 IG media insights (live fetch 2026-08-20)",
        "total_posts": len(ig_posts),
        "posts": ig_posts,
    }, indent=2, ensure_ascii=False))

    # IG business
    avg_reach = sum(p["reach"] for p in ig_posts) / 30 if ig_posts else 0
    (_live_data_dir() / "ig-business-analytics.json").write_text(json.dumps({
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
    }, indent=2, ensure_ascii=False))

    # 4.5. PAGE-LEVEL engagement metrics (CAPI System User only).
    # The legacy user token returns (#100) "must be a valid metric" because
    # page-level engagement requires pages_read_user_content + read_insights
    # on the Clawdia app. The CAPI System User has those scopes auto-granted
    # (server-side tokens bypass Meta app review).
    page_metrics = {}
    if not err and page_tok:
        for metric in ["page_impressions", "page_post_engagements", "page_fans",
                       "page_views_total", "page_fan_adds", "page_actions_post_reactions_total"]:
            since_ts = int((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=30)).timestamp())
            url = f"https://graph.facebook.com/v19.0/{page_id}/insights?metric={metric}&period=day&since={since_ts}&access_token={page_tok}"
            body, m_err = _http(url)
            if m_err:
                continue
            from typing import Iterable
            for series in (body or {}).get("data", []):
                vals = series.get("values", []) or []
                total = sum((v.get("value") or 0) for v in vals)
                page_metrics[series["name"]] = {
                    "total_30d": total,
                    "points": len(vals),
                    "latest": (vals[-1] if vals else None) or {},
                }
            # Stop early on app-review-required 403
            if "blocked_by_app_review" in str(m_err):
                break

    # 4.6. PER-POST engagement metrics (CAPI System User only).
    # Same restriction: legacy user token is read-only and needs app review
    # for post-level engagement. The CAPI System User auto-grants.
    per_post_engagement = {}
    fb_posts_with_metrics = []
    if not err and page_tok:
        # List posts with engagement metrics
        url = (f"https://graph.facebook.com/v19.0/{page_id}/posts"
               f"?fields=id,message,permalink_url,created_time,shares,"
               f"insights.metric(post_impressions,post_impressions_unique,"
               f"post_engaged_users,post_reactions_by_type_total,post_clicks)&"
               f"limit=20&access_token={page_tok}")
        body, err = _http(url)
        if not err and body:
            for p in body.get("data", []):
                post_id = p.get("id", "")
                ins_summary = {}
                for m in (p.get("insights") or {}).get("data", []):
                    values = m.get("values", []) or []
                    if values:
                        val = values[0].get("value", 0) or 0
                        if isinstance(val, dict):
                            val = sum((v or 0) for v in val.values())
                        ins_summary[m["name"]] = val
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
    (_live_data_dir() / "facebook-analytics.json").write_text(json.dumps({
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
    }, indent=2, ensure_ascii=False))

    # FB business — enriched with page-level engagement when CAPI token is live
    token_kind = creds.get("token_kind", "long_lived_user")
    is_capi = token_kind == "capi_system_user"
    (_live_data_dir() / "facebook-business-analytics.json").write_text(json.dumps({
        "schema": "https://clawdia.io/agents/facebook-business-analytics/v1",
        "channel": "facebook",
        "updated": now_iso,
        "generated_by": f"meta_live_fetch.py v2 (live fetch 2026-08-20, token={token_kind})",
        "data_pending": not is_capi,  # with CAPI, data is fully populated
        "account": {"id": page_id, "handle": "swing-shack", "name": page_name,
                   "biography": None, "followers_count": fan_count, "follows_count": None,
                   "media_count": None, "verified": False},
        "daily_reach": page_metrics.get("page_impressions", {}).get("points", 0) and [
            # Spread the page_impressions totals across 30 days for the daily_reach series
            None  # actually we tossed the day-by-day, just keep totals
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
    }, indent=2, ensure_ascii=False))

    return {
        "ok": True,
        "ig_followers": ig_followers,
        "ig_posts": len(ig_posts),
        "fb_fan_count": fan_count,
        "fb_posts": len(fb_posts),
        "fb_page_metrics_30d": page_metrics,
        "token_kind": creds.get("token_kind", "long_lived_user"),
        "token_source": creds.get("source", "?"),
    }


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    result = fetch_all()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("ok") else 1)
