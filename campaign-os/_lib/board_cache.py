"""Read a file once per board build (Scheduled list, This week), not once per post.

unified_inbox._board_reads() turns this on around a read-only board build. Loaders that
were called for every post (brands.json, a brand's archetypes.json) go through cached():
inside a board they share one read, outside one they read as before (6 Nov 2026).
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Hashable, TypeVar

T = TypeVar("T")

_ACTIVE: ContextVar[dict[Hashable, Any] | None] = ContextVar("board_cache", default=None)


@contextmanager
def board_cache():
    """Share loads for everything inside the block; a nested block reuses the outer one."""
    if _ACTIVE.get() is not None:
        yield
        return
    token = _ACTIVE.set({})
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def cached(key: Hashable, load: Callable[[], T]) -> T:
    """load() once per board for this key; every call outside a board loads fresh."""
    store = _ACTIVE.get()
    if store is None:
        return load()
    if key not in store:
        store[key] = load()
    return store[key]
