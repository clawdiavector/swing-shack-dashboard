"""Relative winner promotion → winning-recipes.json."""

from __future__ import annotations

from ..layer1._io import as_dict, as_list, atomic_write, read_json, utc_now_iso
from _lib import feedback_loop as fb

OUTPUT = "winning-recipes.json"
SCHEMA = "campaign-os/winning-recipes/v1"
WINDOW_DAYS = 30
TOP_PCT = 0.25
MIN_SAMPLES = 8


def run() -> dict:
    """Promote top-percentile post outcomes into winning recipes."""
    outcomes_doc = as_dict(read_json("post-outcomes.json"))
    outcomes = as_list(outcomes_doc.get("outcomes"))
    if not outcomes:
        return {"ok": False, "error": "post-outcomes.json missing or empty — run post_outcomes first"}

    ranked = fb.rank_outcomes(outcomes, window_days=WINDOW_DAYS)
    promoted = fb.promote_winners(ranked, top_pct=TOP_PCT, min_samples=MIN_SAMPLES)

    payload = {
        "schema": SCHEMA,
        "generated_at": utc_now_iso(),
        "generated_by": "layer7/winner_promotion.py",
        "window_days": WINDOW_DAYS,
        **promoted,
    }
    atomic_write(OUTPUT, payload)
    return {"ok": True, "rows": promoted.get("winners", 0), "ready": promoted.get("ready")}
