"""Shared archive retention clock (60 days by default, overridable in tests)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

DEFAULT_RETENTION_DAYS = 60
MIN_RETENTION_DAYS = 7


class ArchivePurgeConfigError(ValueError):
    """ARCHIVE_PURGE_DAYS or live-purge settings are invalid for production."""


def _pytest_active() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def retention_days() -> int:
    """Effective retention for purge_at timestamps and eligibility checks."""
    raw = os.environ.get("ARCHIVE_PURGE_DAYS", "")
    if not raw.strip():
        return DEFAULT_RETENTION_DAYS
    try:
        n = int(raw.strip())
    except ValueError:
        return DEFAULT_RETENTION_DAYS
    if n <= 0:
        if _pytest_active() and n == 0:
            return 0
        raise ArchivePurgeConfigError(
            f"ARCHIVE_PURGE_DAYS must be at least {MIN_RETENTION_DAYS} (got {n})"
        )
    if n < MIN_RETENTION_DAYS and not _pytest_active():
        return MIN_RETENTION_DAYS
    return n


def validate_production_purge_config() -> None:
    """Called before any destructive purge (the Archive page button)."""
    if _pytest_active():
        return
    raw = os.environ.get("ARCHIVE_PURGE_DAYS", "").strip()
    if not raw:
        return
    try:
        n = int(raw)
    except ValueError:
        raise ArchivePurgeConfigError(f"ARCHIVE_PURGE_DAYS must be an integer (got {raw!r})")
    if n <= 0:
        raise ArchivePurgeConfigError(
            f"ARCHIVE_PURGE_DAYS must be at least {MIN_RETENTION_DAYS} (got {n})"
        )
    if n < MIN_RETENTION_DAYS:
        raise ArchivePurgeConfigError(
            f"ARCHIVE_PURGE_DAYS must be at least {MIN_RETENTION_DAYS} (got {n})"
        )


def purge_live_enabled() -> bool:
    """Destructive purge is off until explicitly armed (skipped under pytest)."""
    if _pytest_active():
        return True
    flag = os.environ.get("ARCHIVE_PURGE_LIVE", "").strip().lower()
    return flag in ("1", "true", "yes", "on")


def purge_at_iso(archived_at: str, *, days: int | None = None) -> str:
    days = retention_days() if days is None else days
    try:
        base = datetime.fromisoformat(str(archived_at).replace("Z", "+00:00"))
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
    except ValueError:
        base = datetime.now(timezone.utc)
    return (base + timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
