"""Fetch trending golf posts from Reddit and write reddit-trends.json."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import requests

from ._io import atomic_write, utc_now_iso

OUTPUT = "reddit-trends.json"
USER_AGENT = "SwingShackCampaignOS/1.0 (golf trends; contact ops)"
SUBREDDITS = ("golf", "golftips")
FETCH_TIMEOUT = 15


def _fetch_json(url: str) -> dict:
    """GET JSON from *url*; patch in tests."""
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=FETCH_TIMEOUT,
    )
    if resp.status_code == 429:
        raise requests.HTTPError("rate limited", response=resp)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {}


def _classify_intent(title: str) -> list[str]:
    title_l = title.lower()
    intent: list[str] = []
    if re.search(r"slice|hook|swing.?problem|fix|help", title_l):
        intent.append("fix_intent")
    if re.search(r"beginner|start|first.?time|new.?to", title_l):
        intent.append("beginner_help")
    if re.search(r"buy|which|should.?i|recommend|best", title_l):
        intent.append("buying_intent")
    if re.search(r"fitting|club.?fit|driver|irons|wedges", title_l):
        intent.append("fitting_intent")
    if re.search(r"simulator|indoor|launch.?monitor|trackman", title_l):
        intent.append("simulator_interest")
    if re.search(r"distance|yard|driver|speed", title_l):
        intent.append("distance_problem")
    if re.search(r"humor|funny|laugh|i.?don't|cart.?girl", title_l):
        intent.append("humor")
    if re.search(r"couple|friends|group|social|party", title_l):
        intent.append("social_golf")
    if not intent:
        intent.append("general")
    return intent


def _parse_subreddit(sub: str) -> list[dict[str, Any]]:
    url = f"https://www.reddit.com/r/{sub}/hot.json?limit=20"
    data = _fetch_json(url)
    posts = (data.get("data") or {}).get("children") or []
    trends: list[dict[str, Any]] = []
    for post in posts:
        d = (post or {}).get("data") or {}
        if d.get("over_18"):
            continue
        title = d.get("title") or ""
        title_l = title.lower()
        words = [w for w in title_l.split() if len(w) > 5]
        trends.append(
            {
                "subreddit": sub,
                "title": title,
                "score": d.get("score") or 0,
                "comments_count": d.get("num_comments") or 0,
                "url": d.get("url") or "",
                "permalink": f"https://reddit.com{d.get('permalink', '')}",
                "created_utc": datetime.fromtimestamp(
                    d.get("created_utc") or 0, tz=timezone.utc
                ).isoformat(),
                "intent": _classify_intent(title),
                "key_terms": " ".join(words[:5]),
                "is_self": bool(d.get("is_self")),
                "selftext_snippet": (d.get("selftext") or "")[:200],
            }
        )
    return trends


def _build_clusters(trends: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: dict[str, int] = {}
    for trend in trends:
        for term in (trend.get("key_terms") or "").split():
            if len(term) > 5:
                clusters[term] = clusters.get(term, 0) + (trend.get("score") or 0)
    ranked = sorted(clusters.items(), key=lambda kv: kv[1], reverse=True)
    return [{"term": term, "score": score} for term, score in ranked[:20]]


def run() -> dict:
    """Fetch Reddit hot posts and write reddit-trends.json."""
    all_trends: list[dict[str, Any]] = []
    network_errors: list[str] = []

    for sub in SUBREDDITS:
        try:
            all_trends.extend(_parse_subreddit(sub))
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 429:
                return {"ok": False, "error": "reddit rate limited (429)"}
            network_errors.append(f"r/{sub}: HTTPError")
        except Exception:  # noqa: BLE001 — network stubs may raise any type
            network_errors.append(f"r/{sub}: network error")

    if not all_trends and network_errors:
        return {"ok": False, "error": "reddit fetch failed: " + "; ".join(network_errors)}

    if not all_trends:
        return {"ok": False, "error": "reddit fetch failed: no trends"}

    all_trends.sort(key=lambda t: t.get("score") or 0, reverse=True)
    pain_points = [
        t["title"]
        for t in all_trends
        if (t.get("score") or 0) > 100
        and ("fix_intent" in t.get("intent", []) or "distance_problem" in t.get("intent", []))
    ][:5]

    payload = {
        "updated": utc_now_iso(),
        "total_trends": len(all_trends),
        "trends": all_trends[:30],
        "trend_clusters": _build_clusters(all_trends),
        "hot_pain_points": pain_points,
        "top_posts": all_trends[:5],
    }
    atomic_write(OUTPUT, payload)
    return {"ok": True, "rows": len(all_trends)}
