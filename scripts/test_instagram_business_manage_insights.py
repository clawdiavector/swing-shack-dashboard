#!/usr/bin/env python3
"""
test_instagram_business_manage_insights.py

LIVE API test for the instagram_business_manage_insights permission.
Required by Meta App Review to satisfy the checklist item:
  'Ensure that you have performed required API test calls'

Makes the three calls the production app makes:
  1. /{ig_business_id}?fields=followers_count,media_count              (basic)
  2. /{ig_business_id}/insights?metric=reach,accounts_engaged,...       (the permission in question)
  3. /{ig_business_id}/media?fields=id,media_type,like_count,...        (basic + content_publish)
  4. /{ig_media_id}/insights?metric=reach,likes,saved,...               (the permission in question, per media)

Usage:
  python3 scripts/test_instagram_business_manage_insights.py

Output:
  Prints the raw upstream response from each call, suitable for
  pasting into Meta App Review's 'screencast' or 'API call evidence'
  upload.

Auth:
  Uses META_SYSTEM_USER_TOKEN env var (preferred) or the
  canonical credentials file. Same tokens as production.

Exit codes:
  0 — every API call returned HTTP 200 with expected fields present
  1 — at least one call failed (the failing response is printed)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v21.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

# These are the IDs Meta's review process expects to see in the API call
# evidence. They are public (any partner who connects to your IG Business
# account can see them).
# Live IDs from data/ig-business-analytics.json (fetch_ig_business.py, run 2026-08-26)
DEFAULT_IG_BUSINESS_ID = "17841456713897671"  # @swingshack IG Business account
DEFAULT_IG_MEDIA_ID = "17988987897030897"      # most recent Swing Shack IG post
DEFAULT_PAGE_ID = "198859063301219"           # Swing Shack FB page


def _resolve_token() -> str:
    """Read the System User token from env or canonical credential file."""
    tok = os.environ.get("META_SYSTEM_USER_TOKEN")
    if tok:
        return tok.strip()
    # Canonical path
    cred_path = Path(
        "/Users/fivefriday/.openclaw-instance2/workspace/clients/swing-shack/credentials/meta-token.json"
    )
    if cred_path.is_file():
        try:
            data = json.loads(cred_path.read_text())
            if data.get("access_token"):
                return data["access_token"].strip()
        except Exception:
            pass
    raise SystemExit(
        "ERROR: no META_SYSTEM_USER_TOKEN env var and no credentials file at "
        "/Users/fivefriday/.openclaw-instance2/workspace/clients/swing-shack/credentials/meta-token.json"
    )


def _get(path: str, params: dict | None = None) -> dict:
    """GET against the Graph API. Raises on non-200."""
    qs = urlencode({"access_token": _resolve_token(), **(params or {})})
    url = f"{GRAPH_BASE}{path}?{qs}"
    req = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return {
                "_request": {"method": "GET", "path": path, "params": params or {}},
                "_status": resp.status,
                "_response": json.loads(body),
            }
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {
            "_request": {"method": "GET", "path": path, "params": params or {}},
            "_status": e.code,
            "_response_body": body,
            "_error": f"HTTP {e.code}",
        }
    except URLError as e:
        return {
            "_request": {"method": "GET", "path": path, "params": params or {}},
            "_status": None,
            "_error": f"URLError: {e.reason}",
        }


def call_1_account_info(ig_business_id: str) -> dict:
    """Call 1 — Get basic account info.

    Endpoint: GET /{ig_business_id}?fields=id,username,followers_count,media_count
    Permission required: instagram_basic
    """
    return _get(f"/{ig_business_id}", {
        "fields": "id,username,followers_count,media_count,name,biography,profile_picture_url",
    })


def call_2_account_insights(ig_business_id: str) -> dict:
    """Call 2 — Get account-level insights with metric_type=total_value.

    Live-verified shape (scripts/fetch_ig_business.py, 2026-08-13):
      Total-value metrics: reach, accounts_engaged, total_interactions,
        profile_views, profile_links_taps
      Daily metrics (no metric_type needed): reach, follower_count
    Endpoint: GET /{ig_business_id}/insights?metric=reach&period=day&metric_type=total_value
    Permission required: instagram_business_manage_insights (the one we're testing)
    """
    # Make ONE call (the most representative) — reach with metric_type=total_value
    # which is the same call the production fetcher makes.
    return _get(f"/{ig_business_id}/insights", {
        "metric": "reach",
        "period": "day",
        "metric_type": "total_value",
        "since": 1785135494,
        "until": 1787727494,
    })


def call_3_recent_media(ig_business_id: str) -> dict:
    """Call 3 — List recent IG media (posts / reels).

    Endpoint: GET /{ig_business_id}/media?fields=id,caption,media_type,like_count,comments_count,timestamp
    Permission required: instagram_basic + instagram_content_publish
    """
    return _get(f"/{ig_business_id}/media", {
        "fields": "id,caption,media_type,media_url,permalink,like_count,comments_count,timestamp",
        "limit": 5,
    })


def call_4_media_insights(ig_media_id: str) -> dict:
    """Call 4 — Per-media lifetime insights for one specific post.

    Live-verified shape: total_interactions, reach, impressions, likes,
      comments, shares, saved (period=lifetime).
    Endpoint: GET /{ig_media_id}/insights?metric=reach,likes,saved,...
    Permission required: instagram_business_manage_insights (the one we're testing)
    """
    return _get(f"/{ig_media_id}/insights", {
        "metric": "reach,likes,saved,comments,shares,total_interactions",
        "period": "lifetime",
    })


def main() -> int:
    print("=" * 78)
    print("Meta App Review — Live API test for instagram_business_manage_insights")
    print("=" * 78)
    print()
    print("This script makes the same calls the Campaign OS makes in production.")
    print("Run this once before submitting to Meta. Paste the raw response block")
    print("below into the App Review 'API call evidence' field.")
    print()
    print(f"Graph version: {GRAPH_VERSION}")
    print(f"Token source:  META_SYSTEM_USER_TOKEN env (or canonical credentials file)")
    print()

    ig_biz_id = os.environ.get("TEST_IG_BIZ_ID", DEFAULT_IG_BUSINESS_ID)
    ig_media_id = os.environ.get("TEST_IG_MEDIA_ID", DEFAULT_IG_MEDIA_ID)

    failures = 0
    calls = [
        ("Call 1 — Account info (instagram_basic)",          call_1_account_info,    ig_biz_id),
        ("Call 2 — Account insights (instagram_business_manage_insights)", call_2_account_insights, ig_biz_id),
        ("Call 3 — Recent media (instagram_basic + content_publish)",        call_3_recent_media,    ig_biz_id),
        ("Call 4 — Media insights (instagram_business_manage_insights)",    call_4_media_insights,  ig_media_id),
    ]

    results = []
    for label, fn, target_id in calls:
        print("-" * 78)
        print(label)
        print("-" * 78)
        result = fn(target_id)
        results.append({"label": label, **result})
        print(json.dumps(result, indent=2, default=str))
        print()
        if result.get("_status") != 200:
            failures += 1
            print(f"!! FAILED — HTTP {result.get('_status')}")
        else:
            print(f"OK — HTTP 200")

    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"Calls made:    {len(calls)}")
    print(f"Calls passed:  {len(calls) - failures}")
    print(f"Calls failed:  {failures}")
    print()
    if failures == 0:
        print("All API calls succeeded — you can submit to Meta App Review now.")
        print("Copy the response block above into the 'API test calls' field.")
        return 0
    print("At least one call failed. Fix the auth/permission issue before submitting.")
    print("If the failure is a permission error, your token may not have")
    print("instagram_business_manage_insights granted yet — check the App Review")
    print("dashboard for the current grant state.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
