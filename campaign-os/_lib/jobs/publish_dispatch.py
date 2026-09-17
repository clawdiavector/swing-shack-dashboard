"""publish_dispatch job — sandbox by default; live gated behind PUBLISH_MODE=live."""

from __future__ import annotations

from _lib.publish_mode import get_publish_mode, is_sandbox_mode


def run() -> dict:
    if is_sandbox_mode():
        from _lib.publish_sandbox import dispatch_pending

        return dispatch_pending()

    from _lib.publish_live import dispatch_pending as live_dispatch

    return live_dispatch()
