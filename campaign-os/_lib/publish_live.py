"""Live publish adapter — Postiz / GBP (only when PUBLISH_MODE=live)."""

from __future__ import annotations

from typing import Any


def dispatch_pending() -> dict[str, Any]:
    """Live dispatch stub — requires credentials + explicit live mode."""
    return {
        "ok": False,
        "mode": "live",
        "error": "live publish_dispatch not enabled in this slice — use sandbox mode",
    }
