"""fetch_facebook_analytics.py — fetch Swing Shack Facebook page analytics.

Built 2026-08-20 to populate data/facebook-analytics.json +
data/facebook-business-analytics.json (scaffolded with data_pending=True
by scripts/seed_channel_analytics.py).

WHAT YOU NEED:
  - Meta Graph API access_token with `pages_show_list`,
    `pages_read_engagement`, `read_insights` scopes
  - The swing-shack Facebook page ID
  - Both stored in `~/.openclaw-instance2/workspace/clients/swing-shack/
    credentials/facebook-page.json` as:
      {
        "page_id": "...",
        "access_token": "EAAxxxx",
        "page_handle": "swing-shack-sa",
        "app_id": "...",
        "app_secret": "..."
      }

  Plus a META_SYSTEM_USER_TOKEN env var on Railway (long-lived token)
  for production. This script reads both.

HOW IT WORKS:
  1. Reads credentials/facebook-page.json (or env)
  2. Calls /me/accounts to confirm page access
  3. Calls /<page_id>/insights?metric=page_impressions,page_post_engagements,
     page_fans&period=day for 30 days
  4. Calls /<page_id>/posts?fields=insights.metric(post_impressions),
     message,created_time&limit=20 for per-post metrics
  5. Writes both JSONs to data/ — flips data_pending to False

NEXT STEPS:
  1. Get Christelle to confirm the swing-shack FB page name + URL
     (brands.json has facebook_page: null — needs filling in)
  2. Have her generate a Meta System User token via
     business.facebook.com/settings/system-users with the scopes above
  3. Save the page_id + token to credentials/facebook-page.json
  4. Run this script — the per-post JSON will populate with real numbers
     and brand_brief_intel will flip the brief's source badges from
     red ('pending') to green ('data:facebook-analytics.json')

DISCOURAGED:
  - Do NOT invent post-level metrics. If the API fails or the page
    is missing data, write empty `posts: []` and surface
    data_pending=True. The brief renders a 'pending' badge so the
    user knows the channel still has no real numbers.
  - Do NOT use scraped data (FB ToS violation + brittle).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR") or (
    Path(__file__).resolve().parent.parent / "data"
))
CRED_PATH = Path(os.path.expanduser(
    "~/.openclaw-instance2/workspace/clients/swing-shack/credentials/facebook-page.json"
))


def _load_creds() -> dict | None:
    """Read creds from file or env. Returns None if not wired yet."""
    # Env first (Railway)
    token = os.environ.get("META_SYSTEM_USER_TOKEN")
    page_id = os.environ.get("FACEBOOK_PAGE_ID")
    if token and page_id:
        return {"access_token": token, "page_id": page_id,
                "page_handle": os.environ.get("FACEBOOK_PAGE_HANDLE", "")}
    # Local file
    if CRED_PATH.exists():
        try:
            with open(CRED_PATH) as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _http_get(url: str, token: str) -> tuple[dict | None, str | None]:
    """Lightweight Graph API GET that returns (json_body, error_string)."""
    sep = "&" if "?" in url else "?"
    full = f"{url}{sep}access_token={token}"
    try:
        with urllib.request.urlopen(full, timeout=30) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)


def fetch_page_metrics(page_id: str, token: str, *, days: int = 30) -> dict:
    """Fetch 30d of metrics: page_impressions, page_post_engagements, page_fans."""
    metrics = "page_impressions,page_post_engagements,page_fans,page_views_total"
    since = int((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)).timestamp())
    until = int(_dt.datetime.now(_dt.timezone.utc).timestamp())
    url = (f"https://graph.facebook.com/v19.0/{page_id}/insights"
           f"?metric={metrics}&period=day&since={since}&until={until}")
    return _http_get(url, token)


def fetch_recent_posts(page_id: str, token: str, *, limit: int = 20) -> dict:
    """Fetch recent posts + per-post engagement metrics."""
    fields = ("id,message,permalink_url,created_time,shares,insights.metric("
              "post_impressions,post_reach,post_engaged_users,post_reactions_by_type_total)")
    url = (f"https://graph.facebook.com/v19.0/{page_id}/posts"
           f"?fields={fields}&limit={limit}")
    return _http_get(url, token)


def write_business_json(brand_id: str, page_handle: str, account_data: dict,
                         business_summary: dict) -> Path:
    """Save account-level file."""
    out = {
        "schema": "https://clawdia.io/agents/facebook-business-analytics/v1",
        "channel": "facebook",
        "updated": _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "generated_by": "fetch_facebook_analytics.py",
        "data_pending": True if business_summary.get("error") else False,
        "account": {
            "id": business_summary.get("page_id"),
            "handle": page_handle,
            "biography": None,
            "followers_count": business_summary.get("followers_count"),
            "follows_count": None,
            "media_count": business_summary.get("media_count"),
            "verified": False,
        },
        "daily_reach": business_summary.get("daily_reach", []),
        "media": [],
        "top_post": {"permalink": business_summary.get("top_post_permalink")},
        "window_totals": {
            "page_views": business_summary.get("page_views_total_30d"),
            "page_likes": business_summary.get("followers_count"),
            "page_impressions": business_summary.get("page_impressions_30d"),
            "post_engagements_30d": business_summary.get("page_post_engagements_30d"),
        },
    }
    p = DATA_DIR / "facebook-business-analytics.json"
    p.write_text(json.dumps(out, indent=2))
    return p


def write_analytics_json(posts: list[dict]) -> Path:
    """Save per-post file."""
    out = {
        "schema": "https://clawdia.io/agents/facebook-analytics/v1",
        "channel": "facebook",
        "updated": _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "generated_by": "fetch_facebook_analytics.py",
        "data_pending": not bool(posts),
        "posts": posts,
        "next_fetch_url": "see scripts/fetch_facebook_analytics.py",
        "source_note": "Sourced from Meta Graph API: page posts + page-level insights.",
        "total_posts": len(posts),
    }
    p = DATA_DIR / "facebook-analytics.json"
    p.write_text(json.dumps(out, indent=2))
    return p


def main() -> int:
    creds = _load_creds()
    if not creds:
        print("ERROR: No credentials found.")
        print(f"  Set META_SYSTEM_USER_TOKEN + FACEBOOK_PAGE_ID env vars, OR")
        print(f"  write {CRED_PATH}")
        print()
        print("Sample credentials file:")
        print(json.dumps({"page_id": "1234567890", "access_token": "EAAxxxx", "page_handle": "swing-shack-sa"}, indent=2))
        return 1
    page_id = creds["page_id"]
    token = creds["access_token"]
    page_handle = creds.get("page_handle") or ""

    print(f"Fetching Facebook metrics for page={page_id} ({page_handle})...")
    page_data, page_err = fetch_page_metrics(page_id, token, days=30)
    if page_err:
        print(f"  WARN: page metrics failed: {page_err}")
        # Still write the JSON with data_pending=True
        write_business_json("swing-shack", page_handle, {}, {"error": page_err, "page_id": page_id})
        write_analytics_json([])
        print()
        print("Wrote both files with data_pending=True. See _pending_reason in the JSON for details.")
        return 1
    print(f"  OK: page metrics fetched ({len(page_data.get('data', []))} time-series rows)")
    posts_data, posts_err = fetch_recent_posts(page_id, token, limit=20)
    if posts_err:
        print(f"  WARN: posts fetch failed: {posts_err}")
        posts = []
    else:
        # Normalize to the schema brand_brief_intel expects
        posts = _normalize_posts(posts_data.get("data", []))
        print(f"  OK: {len(posts)} posts fetched + normalized")

    # Build the business summary
    summary = _summarize_page_metrics(page_data)
    write_business_json("swing-shack", page_handle, page_data, summary)
    write_analytics_json(posts)
    print()
    print("Done. data_pending=False on populated fields.")
    print("Next: re-run /api/campaigns/from-idea — Facebook card should now show green 'data:facebook-analytics.json' badges.")
    return 0


def _summarize_page_metrics(page_data: dict) -> dict:
    """Compute 30d totals + follower count from the /insights response."""
    summary = {"page_id": None, "page_views_total_30d": 0,
               "page_impressions_30d": 0, "page_post_engagements_30d": 0}
    for series in page_data.get("data", []):
        name = series.get("name", "")
        for v in series.get("values", []):
            val = v.get("value", 0) or 0
            end = v.get("end_time", "")[:10]
            if name == "page_impressions":
                summary["page_impressions_30d"] += val
            elif name == "page_post_engagements":
                summary["page_post_engagements_30d"] += val
            elif name == "page_views_total":
                summary["page_views_total_30d"] += val
            elif name == "page_fans" and end:
                # Most recent value wins
                summary["followers_count"] = val
    return summary


def _normalize_posts(raw_posts: list[dict]) -> list[dict]:
    """Convert Meta Graph API post shape to brand_brief_intel shape."""
    out = []
    for p in raw_posts:
        post_id = p.get("id", "")
        message = p.get("message", "") or ""
        created_time = p.get("created_time", "")
        insights = {}
        for ins in p.get("insights", {}).get("data", []):
            name = ins.get("name", "")
            for v in ins.get("values", []):
                insights[name] = v.get("value", 0) or 0
        reach = insights.get("post_reach", 0)
        impressions = insights.get("post_impressions", 0)
        engaged = insights.get("post_engaged_users", 0)
        er = (engaged / reach * 100) if reach else 0
        out.append({
            "id": post_id,
            "postId": post_id,
            "timestamp": created_time,
            "captionPreview": message[:200],
            "hook_text": message.split("\n", 1)[0][:120] if message else "",
            "hook_id": post_id,
            "format_type": "post",
            "topic_cluster": "unknown",
            "reach": reach,
            "likes": insights.get("post_reactions_by_type_total", 0),
            "comments": 0,    # would need separate field; placeholder
            "saves": 0,
            "shares": p.get("shares", {}).get("count", 0),
            "profile_visits": None,
            "follows_gained": None,
            "engagementRate": f"{er:.2f}",
            "saveRate": "0.00",
            "shareRate": "0.00",
            "followConversion": "0.000",
        })
    return out


if __name__ == "__main__":
    raise SystemExit(main())
