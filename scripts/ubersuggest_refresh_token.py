#!/usr/bin/env python3
"""
ubersuggest_refresh_token.py — weekly Ubersuggest OAuth token refresh.

Pattern: fire-weekly, only-burn-a-refresh-inside-the-expiry-window.

Ubersuggest's long-lived tokens (60 days from a successful OAuth dance).
Naive refresh-every-hour wastes 99% of quota. Smarter: fire weekly, only
actually burn a refresh when the saved token expires within 7 days. When
the token is healthy, exits 0 with "no refresh needed". When inside the
window, refresh + verify + atomic-write the credentials file. When the
refresh fails, exits non-zero so a future ops alert can fire.

Exit codes:
  0 = success (either no refresh needed OR refresh succeeded)
  1 = refresh failed (network/upstream, will retry next week)
  2 = token file missing (run scripts/ubersuggest_oauth.py)
  3 = token already past expiry by >30 days (full re-OAuth needed)

Schedule: every Tuesday at 04:30 SAST (after the daily 04:00 cron) via
launchd com.swing-shack.ubersuggest-token-refresh.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Reuse the wrapper module — single source of truth for OAuth helpers.
# Add campaign-os AND its parent so `from _lib import ubersuggest_mcp` works
# regardless of how the launchd context resolves things.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "campaign-os"))

from _lib.ubersuggest_mcp import (
    DEFAULT_CLIENT_ID,
    refresh_access_token,
    write_token_file,
    _normalize_token_response,
    _read_token_path,
    _read_token_meta,
    UbersuggestAuthError,
    UbersuggestUpstreamError,
    UbersuggestNetworkError,
)

# 7-day window: if token expires >7 days from now, skip.
REFRESH_WINDOW_DAYS = 7
# Token is considered "dead" (full re-OAuth required) if past expiry by this many days.
TOKEN_HARD_EXPIRY_DAYS = 30

_log_path = Path(
    "/Users/fivefriday/.openclaw-instance2/workspace/logs/ubersuggest-refresh.log"
)
_log_path.parent.mkdir(parents=True, exist_ok=True)


def _log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S SAST", time.localtime())
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with _log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # logging is best-effort


def main() -> int:
    token_file = _read_token_path()
    if not token_file or not Path(token_file).exists():
        _log("[skip] no token file at "
             f"{token_file} — run scripts/ubersuggest_oauth.py")
        return 2

    meta = _read_token_meta()
    expires_at = meta.get("expires_at")
    if not isinstance(expires_at, (int, float)):
        _log("[refresh] token file missing/garbled expires_at — refreshing defensively")
        return _do_refresh()

    now = time.time()
    days_to_expiry = (expires_at - now) / 86400.0

    if days_to_expiry > REFRESH_WINDOW_DAYS:
        _log(f"[skip] token healthy for {days_to_expiry:.1f} more days "
             f"(window is {REFRESH_WINDOW_DAYS}); no refresh burned")
        return 0

    if days_to_expiry < -TOKEN_HARD_EXPIRY_DAYS:
        _log(f"[hard-expired] token dead for {-days_to_expiry:.1f} days; "
             "manual re-OAuth required")
        return 3

    _log(f"[refresh] inside the window ({days_to_expiry:+.1f} days) — refreshing")
    return _do_refresh()


def _do_refresh() -> int:
    """Refresh + verify + atomic-write. Returns 0 on success."""
    try:
        resp = refresh_access_token()
    except UbersuggestAuthError as e:
        _log(f"[error] refresh failed (auth): {e}")
        return 1
    except UbersuggestNetworkError as e:
        _log(f"[error] refresh failed (network): {e}")
        return 1
    except UbersuggestUpstreamError as e:
        _log(f"[error] refresh failed (upstream {getattr(e, 'code', '?')}): {e}")
        return 1

    if "access_token" not in resp:
        _log(f"[error] token response missing access_token: {resp}")
        return 1

    # Atomic write
    try:
        write_token_file(**_normalize_token_response(resp))
    except Exception as e:
        _log(f"[error] write_token_file failed: {e}")
        return 1

    # Verify by calling auth_status
    try:
        from _lib import ubersuggest_mcp as _us
        result = _us.auth_status()
        new_expires_at = _read_token_meta().get("expires_at", 0)
        new_expires_in_days = (new_expires_at - time.time()) / 86400.0
        _log(f"[ok] refreshed + verified; expires in {new_expires_in_days:.1f} days")
        _log(f"[trace] auth_status response: {json.dumps(result)[:200]}")
    except UbersuggestAuthError as e:
        _log(f"[warn] refresh saved but auth_status fails: {e}")
        return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        _log("[interrupted]")
        sys.exit(130)
