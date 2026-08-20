"""seed_channel_analytics.py — build the channel-analytics JSON files.

Built 2026-08-20 to close the 'Facebook / TikTok / X data holes' so the
campaign brief stops baseline-guessing those channels.

Why this script exists separately from a real fetcher:
  - We have live IG tokens (per ig-business-analytics.json) but no live
    Meta Business / TikTok Display / X Analytics tokens yet.
  - The /api/postiz/channels endpoint shows integrations are connected
    but Postiz itself doesn't expose per-platform analytics via API.
  - Brand_brief_intel.py already knows the shape these JSONs need
    (mirrors ig-analytics.json / ig-business-analytics.json).

What this does:
  1. Creates data/facebook-analytics.json (per-post schema)
  2. Creates data/facebook-business-analytics.json (account-level)
  3. Creates data/tiktok-analytics.json + data/tiktok-business-analytics.json
  4. Creates data/x-analytics.json + data/x-business-analytics.json
  5. Each file ships with:
        - the schema (so brand_brief_intel can parse it)
        - an explicit `posts: []` (no fabricated posts)
        - an explicit `data_pending: true` marker (so the brief renders
          a red badge NOT a green one until real data lands)
        - a `next_fetch_url` pointer so the next agent knows exactly
          which endpoint + token they need to populate it

When the real fetcher runs (see scripts/fetch_facebook_analytics.py /
fetch_tiktok_analytics.py / fetch_x_analytics.py in this directory),
it overwrites this file with real numbers and flips data_pending to
false.

Run ONCE after deploy:
  python3 scripts/seed_channel_analytics.py

Doesn't touch RailWay environment, posts, or campaigns.json. Pure
data file creation. Idempotent.
"""

from __future__ import annotations

import json
import os
import datetime as _dt
from pathlib import Path


DATA_DIR = Path(os.environ.get("DATA_DIR") or (
    Path(__file__).resolve().parent.parent / "data"
))
DATA_DIR.mkdir(parents=True, exist_ok=True)

NOW_ISO = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _account_template(channel: str, *, handle: str | None = None,
                       page_id: str | None = None) -> dict:
    """Account-level metadata for any channel.

    handle: facebook_page_id / tiktok_handle / x_handle — populated when
    known, None otherwise (brand_brief_intel reads `None` as 'unknown').
    """
    return {
        "id": page_id or None,
        "handle": handle,
        "biography": None,
        "followers_count": None,    # populated by the fetcher
        "follows_count": None,
        "media_count": None,
        "verified": False,
        "_account_meta_pending": {
            "reason": "no live API token yet",
            "what_we_need": f"Live {channel} insights / display API token in credentials/ + this channel ID.",
            "see_also": f"scripts/fetch_{channel}_analytics.py — fetcher scaffold + endpoint pointers",
        },
    }


def _post_template() -> dict:
    """Per-post row shape — mirrors ig-analytics.json so brand_brief_intel
    can reuse its loader logic for FB / TikTok / X unchanged."""
    return {
        "id": None,
        "postId": None,
        "timestamp": None,
        "captionPreview": "",
        "hook_text": "",
        "hook_id": None,
        "format_type": "post",
        "topic_cluster": "unknown",
        "reach": None,
        "likes": None,
        "comments": None,
        "saves": None,        # X / TikTok may not have saves; set null
        "shares": None,
        "profile_visits": None,
        "follows_gained": None,
        "engagementRate": None,
        "saveRate": None,
        "shareRate": None,
        "followConversion": None,
    }


def _file_template(*, channel: str, schema_uri: str,
                    source_note: str, next_fetch_url: str,
                    business_extra: dict | None = None) -> dict:
    """Skeleton that any per-channel JSON gets on first seed.

    `data_pending: true` is the agreement between this script and the
    brand_brief_intel conf flag — the brief knows to render a red badge
    when data_pending is True even if other fields are populated.
    """
    base = {
        "schema": schema_uri,
        "channel": channel,
        "updated": NOW_ISO,
        "generated_by": "seed_channel_analytics.py (built 2026-08-20)",
        "data_pending": True,           # flips false when fetcher runs
        "posts": [],                    # empty until fetcher populates
        "next_fetch_url": next_fetch_url,
        "source_note": source_note,
    }
    if business_extra:
        base.update(business_extra)
    return base


# ── Per-channel next-fetch URLs ─────────────────────────────────────
# Where the eventual fetcher should hit. Documented here so we don't
# re-derive on every refresh.

_NEXT_FETCH_URLS = {
    "facebook": (
        "https://graph.facebook.com/v19.0/<PAGE_ID>/insights"
        "?metric=page_post_engagements,page_impressions,page_fans"
        "&period=day&access_token=<SYSTEM_USER_TOKEN>"
        "   (see scripts/fetch_facebook_analytics.py for full payload schema)"
    ),
    "tiktok": (
        "https://open.tiktokapis.com/v2/research/user/followers/"
        "?username=<TIKTOK_HANDLE>  (requires TikTok Research Application API approval)"
        "  OR  if Business: https://business-api.tiktok.com/open_api/v1.3/aweme/stats/"
        "   (see scripts/fetch_tiktok_analytics.py)"
    ),
    "x": (
        "https://api.twitter.com/2/users/<USER_ID>/tweets"
        "?tweet.fields=public_metrics,non_public_metrics"
        "&start_time=<ISO_8601>"
        "   OR  https://api.twitter.com/2/users/<USER_ID>/followers/count"
        "   (requires X Basic tier or above; ~$100/mo per agent-budget gate)"
    ),
}


# ── Files to write ──────────────────────────────────────────────────

FILES = [
    {
        "path": "facebook-analytics.json",
        "doc": _file_template(
            channel="facebook",
            schema_uri="https://clawdia.io/agents/facebook-analytics/v1",
            source_note="Per-post metrics for Swing Shack FB page. Empty until scripts/fetch_facebook_analytics.py runs against a live Meta Page token.",
            next_fetch_url=_NEXT_FETCH_URLS["facebook"],
        ),
    },
    {
        "path": "facebook-business-analytics.json",
        "doc": {
            "schema": "https://clawdia.io/agents/facebook-business-analytics/v1",
            "channel": "facebook",
            "updated": NOW_ISO,
            "generated_by": "seed_channel_analytics.py",
            "data_pending": True,
            "account": _account_template("facebook"),
            "daily_reach": [],           # populates: [{"date": "...", "value": int}]
            "media": [],                 # populates with per-post entries
            "top_post": {"permalink": None},
            "window_totals": {
                "page_views": None,
                "page_likes": None,
                "page_impressions": None,
                "post_engagements_30d": None,
            },
            "_pending_reason": "no Meta Page access token yet; see scripts/fetch_facebook_analytics.py",
        },
    },
    {
        "path": "tiktok-analytics.json",
        "doc": _file_template(
            channel="tiktok",
            schema_uri="https://clawdia.io/agents/tiktok-analytics/v1",
            source_note="Per-post metrics for Swing Shack TikTok account. Empty until scripts/fetch_tiktok_analytics.py runs against a live TikTok token.",
            next_fetch_url=_NEXT_FETCH_URLS["tiktok"],
        ),
    },
    {
        "path": "tiktok-business-analytics.json",
        "doc": {
            "schema": "https://clawdia.io/agents/tiktok-business-analytics/v1",
            "channel": "tiktok",
            "updated": NOW_ISO,
            "generated_by": "seed_channel_analytics.py",
            "data_pending": True,
            "account": _account_template("tiktok"),
            "daily_reach": [],
            "media": [],
            "top_post": {"permalink": None},
            "window_totals": {
                "video_views_30d": None,
                "profile_views_30d": None,
                "likes_30d": None,
                "followers_gained_30d": None,
            },
            "_pending_reason": "no TikTok Business API token yet; see scripts/fetch_tiktok_analytics.py",
        },
    },
    {
        "path": "x-analytics.json",
        "doc": _file_template(
            channel="x",
            schema_uri="https://clawdia.io/agents/x-analytics/v1",
            source_note="Per-tweet metrics for Swing Shack X account. Empty until scripts/fetch_x_analytics.py runs against a live X Basic+ token.",
            next_fetch_url=_NEXT_FETCH_URLS["x"],
        ),
    },
    {
        "path": "x-business-analytics.json",
        "doc": {
            "schema": "https://clawdia.io/agents/x-business-analytics/v1",
            "channel": "x",
            "updated": NOW_ISO,
            "generated_by": "seed_channel_analytics.py",
            "data_pending": True,
            "account": _account_template("x"),
            "daily_reach": [],
            "media": [],
            "top_post": {"permalink": None},
            "window_totals": {
                "impressions_30d": None,
                "engagements_30d": None,
                "followers_count": None,
                "tweet_count_30d": None,
            },
            "_pending_reason": "no X API Basic+ token yet ($100/mo per agent-budget gate); see scripts/fetch_x_analytics.py",
        },
    },
]


def main() -> int:
    written = []
    for spec in FILES:
        full = DATA_DIR / spec["path"]
        # Don't overwrite real data — only seed when file is missing
        if full.exists():
            try:
                existing = json.loads(full.read_text())
                if existing.get("data_pending") is False:
                    print(f"  SKIP {spec['path']} (real data already present)")
                    continue
            except Exception:
                pass  # write fresh
        full.write_text(json.dumps(spec["doc"], indent=2, ensure_ascii=False))
        written.append(spec["path"])
        print(f"  SEEDED {spec['path']} ({full.stat().st_size} bytes)")
    print()
    print(f"Written: {len(written)} files. All marked data_pending=True.")
    print("Brief will render these channels with a red badge until")
    print("scripts/fetch_facebook_analytics.py etc. populate real numbers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
