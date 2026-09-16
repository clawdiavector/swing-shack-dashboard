"""Daily refresh of content-ideas.json from trends, hooks, and missed opps."""

from __future__ import annotations

import re
from typing import Any

from ._io import as_dict, as_list, atomic_write, read_json, utc_date, utc_now_iso

OUTPUT = "content-ideas.json"


def _idea_id(prefix: str, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]
    return f"{prefix}-{utc_date()}-{slug or 'idea'}"


def _mine_missed() -> list[dict]:
    missed = as_dict(read_json("missed-opportunities.json"))
    ideas: list[dict] = []
    for opp in as_list(missed.get("opportunities"))[:15]:
        if not isinstance(opp, dict):
            continue
        title = (opp.get("title") or opp.get("name") or "").strip()
        if not title:
            continue
        sev = (opp.get("severity") or "medium").lower()
        score = {"high": 9, "medium": 7, "low": 5}.get(sev, 7)
        ideas.append({
            "idea_id": _idea_id("missed", title),
            "title": title[:120],
            "hook": (opp.get("hook") or opp.get("suggestion") or title)[:120],
            "format": "reel" if "reel" in title.lower() else "static",
            "source_reason": f"Missed opportunity ({opp.get('category', 'gap')})",
            "best_cta": opp.get("cta") or "Book your session · TrackMan from R250",
            "freshness_score": score,
            "difficulty": "easy" if score >= 8 else "medium",
            "topic_cluster": opp.get("category") or "general",
            "used": False,
            "priority": "today" if score >= 8 else "this-week",
        })
    return ideas


def _mine_reddit() -> list[dict]:
    reddit = as_dict(read_json("reddit-trends.json"))
    ideas: list[dict] = []
    for item in as_list(reddit.get("hot_pain_points"))[:10]:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or item.get("pain_point") or "").strip()
        if not title:
            continue
        ideas.append({
            "idea_id": _idea_id("reddit", title),
            "title": title[:120],
            "hook": title[:120],
            "format": "reel",
            "source_reason": "Reddit pain point — answer with a lesson post",
            "best_cta": "Save this · Share with a golfer",
            "freshness_score": 8,
            "difficulty": "medium",
            "topic_cluster": "community",
            "used": False,
            "priority": "this-week",
        })
    return ideas


def _mine_hooks() -> list[dict]:
    hooks = as_dict(read_json("hook-bank.json"))
    ideas: list[dict] = []
    for bucket in ("proven_and_trending", "trending_to_test"):
        for h in as_list((hooks.get("output_buckets") or {}).get(bucket))[:8]:
            if not isinstance(h, dict):
                continue
            hook_text = (h.get("hook") or h.get("text") or "").strip()
            if not hook_text:
                continue
            ideas.append({
                "idea_id": _idea_id("hook", hook_text),
                "title": hook_text[:80].upper(),
                "hook": hook_text[:120],
                "format": "static",
                "source_reason": f"Hook bank ({bucket})",
                "best_cta": h.get("cta") or "TrackMan your swing · Book from R250",
                "freshness_score": 9 if bucket == "proven_and_trending" else 7,
                "difficulty": "easy",
                "topic_cluster": h.get("pillar") or "general",
                "used": False,
                "priority": "today" if bucket == "proven_and_trending" else "this-week",
            })
    return ideas


def _mine_competitor() -> list[dict]:
    comp = as_dict(read_json("competitor-tracker.json"))
    ideas: list[dict] = []
    for change in as_list(comp.get("changes"))[:5]:
        if not isinstance(change, dict):
            continue
        title = f"Counter-move: {change.get('competitor', 'competitor')}"
        ideas.append({
            "idea_id": _idea_id("comp", title),
            "title": title[:120],
            "hook": (change.get("response") or change.get("detail") or title)[:120],
            "format": "reel",
            "source_reason": "Competitor change signal",
            "best_cta": "Book your fitting · Own the educational angle",
            "freshness_score": 8,
            "difficulty": "medium",
            "topic_cluster": "events",
            "used": False,
            "priority": "this-week",
        })
    return ideas


def _dedupe(ideas: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for idea in ideas:
        key = re.sub(r"\s+", " ", (idea.get("title") or "").lower())[:80]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(idea)
    out.sort(key=lambda i: i.get("freshness_score", 0), reverse=True)
    return out


def run() -> dict:
    """Merge mined ideas into content-ideas.json (preserve billboards + used)."""
    existing = as_dict(read_json(OUTPUT))
    preserved_used = [
        i for i in as_list(existing.get("ideas"))
        if isinstance(i, dict) and i.get("used")
    ]
    billboards = existing.get("billboards") if isinstance(existing.get("billboards"), list) else []
    memes = existing.get("memes") if isinstance(existing.get("memes"), list) else []

    mined = _dedupe(
        _mine_hooks()
        + _mine_missed()
        + _mine_reddit()
        + _mine_competitor()
    )

    # Keep unused existing ideas that aren't duplicated
    existing_unused = [
        i for i in as_list(existing.get("ideas"))
        if isinstance(i, dict) and not i.get("used")
    ]
    merged = _dedupe(preserved_used + mined + existing_unused)

    post_today = [i for i in merged if not i.get("used") and i.get("priority") == "today"][:10]
    this_week = [i for i in merged if not i.get("used") and i.get("priority") == "this-week"][:10]
    ideas = merged[:30]

    payload = {
        "updated": utc_now_iso(),
        "generated_by": "layer1/content_ideas_refresh.py",
        "total": len(ideas),
        "ideas": ideas,
        "post_today": post_today,
        "this_week": this_week,
        "billboards": billboards,
        "memes": memes,
    }
    atomic_write(OUTPUT, payload)
    return {"ok": True, "rows": len(ideas), "post_today": len(post_today)}
