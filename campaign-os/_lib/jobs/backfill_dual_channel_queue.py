"""One-shot: ensure IG + FB publish-sandbox rows for existing composed drafts."""

from __future__ import annotations

from typing import Any


def run(brand: str | None = None) -> dict[str, Any]:
    from _lib import publish_sandbox

    return publish_sandbox.backfill_dual_channel_queue(brand=brand)
