"""Daily purge of brand content archived past retention."""

from __future__ import annotations

from typing import Any

from _lib.content_archive import purge_expired


def run(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return purge_expired()
