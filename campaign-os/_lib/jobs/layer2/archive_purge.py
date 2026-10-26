"""Daily purge of brand content archived past retention."""

from __future__ import annotations

from typing import Any

from _lib.archive_retention import ArchivePurgeConfigError, purge_live_enabled, validate_production_purge_config
from _lib.content_archive import purge_expired


def run(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    try:
        validate_production_purge_config()
    except ArchivePurgeConfigError as exc:
        return {"ok": False, "error": str(exc)}
    live = purge_live_enabled()
    out = purge_expired(dry_run=not live)
    out["live"] = live
    return out
