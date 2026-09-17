"""Publish mode — sandbox (default) vs live."""

from __future__ import annotations

import os

_VALID = frozenset({"sandbox", "live"})


def get_publish_mode() -> str:
    """Return ``sandbox`` or ``live``. Default sandbox when unset or invalid."""
    raw = (os.environ.get("PUBLISH_MODE") or "sandbox").strip().lower()
    return raw if raw in _VALID else "sandbox"


def is_sandbox_mode() -> bool:
    return get_publish_mode() == "sandbox"


def is_live_mode() -> bool:
    return get_publish_mode() == "live"
