"""Shared archive retention clock (30 days by default, overridable in tests)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

DEFAULT_RETENTION_DAYS = 30


def retention_days() -> int:
    raw = os.environ.get("ARCHIVE_PURGE_DAYS", "")
    if raw.strip():
        try:
            return max(0, int(raw.strip()))
        except ValueError:
            pass
    return DEFAULT_RETENTION_DAYS


def purge_at_iso(archived_at: str, *, days: int | None = None) -> str:
    days = retention_days() if days is None else days
    try:
        base = datetime.fromisoformat(str(archived_at).replace("Z", "+00:00"))
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
    except ValueError:
        base = datetime.now(timezone.utc)
    return (base + timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
