"""Ask a brand's GEO watchlist questions to an AI model with web search, a few each day.

Each run asks the next questions after the last one it asked and stops starting new ones once
the time budget is spent, so a daily run covers the whole watchlist about once a week without
the synchronous job request timing out. One question takes tens of seconds (web search), which
is why the old weekly all-at-once plan could not run through /api/jobs/run.

Observations are written by geo_runner to the files the GEO page already reads. This job only
keeps its place in the list (geo-observe-cursor.json). Cost: one gpt-4o-mini web-grounded call
per question, about US$0.025 each (geo_runner.cost_estimate).
"""

from __future__ import annotations

import os
import time
from typing import Any

from ..errors import describe_exception
from ._io import io_for_job, utc_now_iso

JOB_NAME = "geo_observe"
CURSOR = "geo-observe-cursor.json"
MODEL = "gpt-4o-mini"
GROUNDING = "WEB_GROUNDED"
MAX_PER_RUN = 4
TIME_BUDGET_SECONDS = 100  # no new question starts after this; one call can still take up to 60s


def _clock() -> float:
    """Seconds, monotonic; patch in tests."""
    return time.monotonic()


def run(*, brand: str | None = None) -> dict[str, Any]:
    """Ask the next few watchlist questions for one brand."""
    if not os.environ.get("OPENAI_API_KEY"):
        return {"ok": False, "error": "OPENAI_API_KEY is not set, so no GEO questions were asked"}

    from ... import geo_runner  # noqa: PLC0415

    io = io_for_job(JOB_NAME, brand)
    watchlist = [w for w in geo_runner._load_watchlist(brand) if str(w.get("query") or "").strip()]
    if not watchlist:
        return {"ok": True, "rows": 0, "asked": [], "failed": [], "note": f"no GEO watchlist for {brand}"}

    cursor = io.read(CURSOR) or {}
    index = int(cursor.get("next_index") or 0) % len(watchlist)
    started = _clock()
    asked: list[str] = []
    failed: list[str] = []
    errors: list[str] = []

    for _ in range(min(MAX_PER_RUN, len(watchlist))):
        if _clock() - started >= TIME_BUDGET_SECONDS:
            break
        item = watchlist[index]
        query = str(item["query"]).strip()
        try:
            result = geo_runner.run_one_query(
                brand=brand,
                query=query,
                model=MODEL,
                grounding=GROUNDING,
                query_id=item.get("id") or item.get("query_id"),
            )
            ok = bool(result.get("ok", True))
        except Exception as exc:  # noqa: BLE001 - one bad call must not stop the rest
            ok = False
            errors.append(f"{query}: {describe_exception(exc)}")
        (asked if ok else failed).append(query)
        index = (index + 1) % len(watchlist)

    io.write(
        CURSOR,
        {
            "next_index": index,
            "watchlist_count": len(watchlist),
            "updated": utc_now_iso(),
            "last_asked": asked,
            "last_failed": failed,
        },
    )
    out: dict[str, Any] = {
        "ok": bool(asked) or not failed,
        "rows": len(asked),
        "asked": asked,
        "failed": failed,
        "next_index": index,
        "watchlist_count": len(watchlist),
    }
    if errors:
        out["errors"] = errors[:3]
    if not out["ok"]:
        out["error"] = "every GEO question failed: " + "; ".join(errors[:2] or failed[:2])
    return out
