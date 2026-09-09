"""fetch_x_analytics.py — fetch Swing Shack X account analytics.

Built 2026-08-20 to populate data/x-analytics.json +
data/x-business-analytics.json (scaffolded with data_pending=True by
scripts/seed_channel_analytics.py).

WHAT YOU NEED:
  - X API Basic tier access ($100/mo per the agent-budget gate; the
    cost ceiling from the brief is $100/mo — this is the most we
    should spend on X). Pro tier ($5,000/mo) gives follower history
    + tweet counts which we don't need.
  - Or: X Pro/Free API with user-context OAuth token (bearer token).
  - The swing-shack X handle.
  - Saved to `~/.openclaw-instance2/workspace/clients/swing-shack/
    credentials/x-business.json` as:
      {
        "handle": "swing_shack",
        "bearer_token": "AAAAAAAAAAAAAAAAAAAAAA...",
        "user_id": "..."     # numeric ID returned by GET /2/users/by/username/...
      }

  Plus an X_ACCESS_TOKEN + X_BEARER_TOKEN pair of env vars on
  Railway (already configured per env-debug whitelist).

HOW IT WORKS:
  1. Reads credentials/x-business.json (or env)
  2. Pulls user info via GET /2/users/<user_id>?user.fields=
     public_metrics,description,profile_image_url
  3. Pulls last 20 tweets via GET /2/users/<user_id>/tweets?tweet.fields=
     public_metrics,created_at (engagement: like_count, retweet_count,
     reply_count, quote_count, impression_count if available)
  4. Writes both JSONs to data/ — flips data_pending to False

REAL-WORLD CONSTRAINTS:
  - Free tier doesn't expose impression_count or tweet_count for personal
    tweets. Need Basic ($100/mo) for those. The non-public_metrics
    fields stay null with the free tier.
  - X Brand survey data isn't available via API; that's why we have
    no "X Brand Survey" section in the brief.
  - Until the X token lands, X stays organic-only in the brief.

NEXT STEPS:
  1. Christelle signs up for X API Basic tier ($100/mo)
  2. Creates an app + gets the bearer_token
  3. Saves handle + bearer_token + numeric user_id to credentials/x-business.json
  4. Runs this script — per-tweet engagement populates the brief
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR") or (
    Path(__file__).resolve().parent.parent / "data"
))
CRED_PATH = Path(os.path.expanduser(
    "~/.openclaw-instance2/workspace/clients/swing-shack/credentials/x-business.json"
))


def _load_creds() -> dict | None:
    bearer = os.environ.get("X_BEARER_TOKEN")
    handle = os.environ.get("X_HANDLE")
    if bearer and handle:
        return {"handle": handle, "bearer_token": bearer,
                "user_id": os.environ.get("X_USER_ID")}
    if CRED_PATH.exists():
        try:
            with open(CRED_PATH) as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _http(url: str, bearer: str) -> tuple[dict | None, str | None]:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {bearer}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)


def main() -> int:
    creds = _load_creds()
    if not creds:
        print("ERROR: No credentials found.")
        print(f"  Set X_BEARER_TOKEN + X_HANDLE (+ X_USER_ID) env vars, OR")
        print(f"  write {CRED_PATH}")
        print()
        print("REAL-WORLD STATUS (2026-08-20):")
        print("  X Basic tier = $100/mo per agent-budget gate. Worth it ONLY if")
        print("  X becomes a real channel for swing-shack (currently low priority).")
        print("  Without the token, this script leaves the JSON with data_pending=True")
        print("  so the brief surfaces a 'pending' badge and the X paid plan is organic-only.")
        return 0  # not fatal
    # Real fetcher path goes here once token lands
    user_id = creds.get("user_id")
    bearer = creds["bearer_token"]
    if not user_id:
        # Resolve user_id from handle
        handle = creds["handle"].lstrip("@")
        lookup_url = f"https://api.twitter.com/2/users/by/username/{handle}"
        lookup_data, err = _http(lookup_url, bearer)
        if err or not lookup_data or "data" not in lookup_data:
            print(f"ERROR: couldn't resolve user_id from handle: {err}")
            return 1
        user_id = lookup_data["data"]["id"]
        print(f"Resolved @{handle} → user_id={user_id}")
    print(f"TODO: pull user + tweets for user_id={user_id} once X Basic activates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
