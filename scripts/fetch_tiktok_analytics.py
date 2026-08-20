"""fetch_tiktok_analytics.py — fetch Swing Shack TikTok account analytics.

Built 2026-08-20 to populate data/tiktok-analytics.json +
data/tiktok-business-analytics.json (scaffolded with data_pending=True
by scripts/seed_channel_analytics.py).

WHAT YOU NEED:
  - TikTok Display API access token (sandbox tier) OR
    TikTok Business API access_token (requires TikTok Business Center
    app approval) OR
    TikTok Research Application API access_token (requires separate
    approval — best fit for our use case)
  - The swing-shack TikTok handle (handle field in brands.json is null)
  - Token saved to `~/.openclaw-instance2/workspace/clients/swing-shack/
    credentials/tiktok-business.json` as:
      {
        "handle": "swingshack",
        "access_token": "tt-...",
        "open_id": "..."
      }

  Plus a TIKTOK_ACCESS_TOKEN env var on Railway.

HOW IT WORKS:
  1. Reads credentials/tiktok-business.json (or env)
  2. If using TikTok Business Display API: pulls 30d of video metadata
     + per-video engagement via /v1.3/video/list/ + /v1.3/video/data/
  3. Writes both JSONs to data/ — flips data_pending to False

REAL-WORLD CONSTRAINTS:
  - TikTok Display API is locked behind Business Center app review
    (~3-7 days). Until approved, the brief's TikTok channel will
    keep showing the 'pending' badge and a baseline paid-plan recommendation.
  - TikTok Research Application API is restricted to academic / NGO
    use cases and doesn't expose engagement metrics for most handles.
  - The cheapest path is to keep using Postiz for publishing and
    accept that TikTok engagement will stay 'baseline' until a
    Business API token lands.

NEXT STEPS:
  1. Christelle creates a TikTok Business Center account
  2. Applies for Display API access (this script's endpoints require it)
  3. Saves handle + token to credentials/tiktok-business.json
  4. Runs this script — per-video engagement populates the brief
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
    "~/.openclaw-instance2/workspace/clients/swing-shack/credentials/tiktok-business.json"
))


def _load_creds() -> dict | None:
    tok = os.environ.get("TIKTOK_ACCESS_TOKEN")
    handle = os.environ.get("TIKTOK_HANDLE")
    if tok and handle:
        return {"access_token": tok, "handle": handle}
    if CRED_PATH.exists():
        try:
            with open(CRED_PATH) as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _fetch_videos(handle: str, token: str) -> tuple[dict | None, str | None]:
    """Pull videos via Display API. NOTE: requires Business Center approval."""
    business_account = "YOUR_OPEN_ID"
    url = "https://business-api.tiktok.com/open_api/v1.3/video/list/?" + "business_account=" + business_account + "&access_token=" + token
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as e:
        return None, str(e)


def main() -> int:
    creds = _load_creds()
    if not creds:
        print("ERROR: No credentials found.")
        print(f"  Set TIKTOK_ACCESS_TOKEN + TIKTOK_HANDLE env vars, OR")
        print(f"  write {CRED_PATH}")
        print()
        print("REAL-WORLD STATUS (2026-08-20):")
        print("  TikTok Display API requires Business Center app approval.")
        print("  Until approved, this script leaves the JSON with data_pending=True")
        print("  so the brief surfaces a 'pending' badge for TikTok.")
        print()
        print("  Cheapest unblock: Postiz (we already have its token on Railway).")
        print("  Postiz doesn't expose engagement analytics, but it does schedule")
        print("  the videos. Add Display API access for engagement pull separately.")
        return 0  # not fatal — seed file remains valid
    # Real fetcher path would go here once approved
    print("TODO: complete this once TikTok Business Display API is approved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
