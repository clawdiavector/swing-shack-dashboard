"""Fetch YouTube golf trends via Data API v3 and write youtube-trends.json."""

from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import requests

from ._io import as_dict, atomic_write, read_json, utc_now_iso

OUTPUT = "youtube-trends.json"
API_TIMEOUT = 20
DEFAULT_QUERIES = (
    "golf swing tips",
    "golf lesson tutorial",
    "golf simulator indoor",
    "golf practice drill",
)

THEME_KEYWORDS = {
    "swing_speed": ["swing speed", "club head speed", "mph", "driver distance", "yards off tee"],
    "short_game": ["chip", "pitch", "putt", "around the green", "bunker"],
    "trackman": ["trackman", "launch monitor", "launch angle", "backspin", "spin rate", "data driven"],
    "slice_fix": ["slice", "hook", "ball flight", "aim line", "club path"],
    "practice": ["practice", "drill", "training", "range session", "muscle memory"],
    "indoor": ["indoor", "simulator", "launch monitor", "bad weather", "rain"],
    "lessons": ["lesson", "pro", "coach", "instruction", "golf professional"],
    "fitness": ["fitness", "flexibility", "mobility", "core", "strength"],
}

SA_HOOKS = (
    {"hook": "That slice costing you yards off the tee? TrackMan found it in 3 swings.", "theme": "slice_fix"},
    {"hook": "How fast should your club head speed actually be? Pros average 112 mph.", "theme": "swing_speed"},
    {"hook": "Your launch monitor data is telling you exactly what to fix.", "theme": "trackman"},
    {"hook": "Rain season. Your game doesn't have to stop. Indoor golf in Johannesburg.", "theme": "indoor"},
    {"hook": "Short game practice that actually transfers to the course.", "theme": "short_game"},
    {"hook": "When was the last time a golf pro watched your actual swing on a launch monitor?", "theme": "lessons"},
)


def _keyword_seeds() -> list[str]:
    seeds: list[str] = list(DEFAULT_QUERIES)
    news = as_dict(read_json("golf-news.json"))
    for item in (news.get("news") or [])[:5]:
        title = (item.get("title") or "").strip()
        if len(title) > 10:
            seeds.append(title[:60])

    reddit = as_dict(read_json("reddit-trends.json"))
    for item in (reddit.get("trends") or reddit.get("top_posts") or [])[:5]:
        title = (item.get("title") or "").strip()
        if len(title) > 10:
            seeds.append(title[:60])

    deduped: list[str] = []
    seen: set[str] = set()
    for q in seeds:
        key = q.lower()[:40]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(q)
    return deduped[:8]


def _youtube_search(query: str, api_key: str) -> dict:
    """Call YouTube search API; patch in tests."""
    params = urlencode(
        {
            "q": query,
            "part": "snippet",
            "regionCode": "ZA",
            "type": "video",
            "maxResults": 5,
            "key": api_key,
        }
    )
    url = f"https://www.googleapis.com/youtube/v3/search?{params}"
    resp = requests.get(url, timeout=API_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, dict) else {}


def _extract_themes(items: list[dict[str, Any]]) -> dict[str, bool]:
    text = " ".join(
        f"{i.get('title', '')} {i.get('description', '')}".lower() for i in items
    )
    return {theme: any(kw in text for kw in keywords) for theme, keywords in THEME_KEYWORDS.items()}


def _build_hooks(articles: list[dict[str, Any]], themes: dict[str, bool]) -> list[dict[str, Any]]:
    hooks: list[dict[str, Any]] = []
    seen: set[str] = set()
    stamp = int(time.time() * 1000)

    for i, item in enumerate(articles[:8]):
        text = item.get("title") or item.get("description") or ""
        if len(text) < 15:
            continue
        hook = text if len(text) <= 65 else text[:62] + "..."
        key = hook.lower()[:35]
        if key in seen:
            continue
        seen.add(key)
        published = item.get("publishedAt") or item.get("date")
        days_old = 2
        if published:
            try:
                delta = datetime.now(timezone.utc) - datetime.fromisoformat(
                    str(published).replace("Z", "+00:00")
                ).astimezone(timezone.utc)
                days_old = max(0, delta.days)
            except (ValueError, TypeError):
                pass
        active_themes = [k for k, v in themes.items() if v]
        hooks.append(
            {
                "idea_id": f"yt-hook-{stamp}-{i}",
                "source": item.get("source") or "article",
                "hook_text": hook,
                "description": (item.get("description") or "")[:120],
                "freshness_score": max(5, 10 - days_old),
                "theme_signal": active_themes[0] if active_themes else "general",
            }
        )

    for i, sh in enumerate(SA_HOOKS):
        key = sh["hook"].lower()[:35]
        if key in seen:
            continue
        seen.add(key)
        hooks.append(
            {
                "idea_id": f"yt-sa-{stamp}-{i}",
                "source": "sa_market_always",
                "hook_text": sh["hook"],
                "description": "SA-market hook - always included",
                "freshness_score": 8,
                "theme_signal": sh["theme"],
            }
        )
    return hooks[:15]


def run() -> dict:
    """Fetch YouTube trends and write youtube-trends.json."""
    api_key = (os.environ.get("YOUTUBE_API_KEY") or "").strip()
    if not api_key:
        return {"ok": False, "error": "missing YOUTUBE_API_KEY"}

    queries = _keyword_seeds()
    all_videos: list[dict[str, Any]] = []
    network_errors: list[str] = []

    for query in queries:
        try:
            data = _youtube_search(query, api_key)
            if data.get("error"):
                err = data["error"]
                msg = err.get("message") if isinstance(err, dict) else str(err)
                network_errors.append(msg or "youtube api error")
                continue
            for item in data.get("items") or []:
                vid = (item.get("id") or {}).get("videoId")
                if not vid:
                    continue
                snippet = item.get("snippet") or {}
                all_videos.append(
                    {
                        "title": snippet.get("title") or "",
                        "description": snippet.get("description") or "",
                        "videoId": vid,
                        "channelTitle": snippet.get("channelTitle") or "",
                        "publishedAt": snippet.get("publishedAt"),
                        "source": "youtube_api_v3",
                        "query": query,
                    }
                )
        except Exception as exc:  # noqa: BLE001 — network stubs may raise any type
            network_errors.append(type(exc).__name__)

    seen_ids: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for video in all_videos:
        if video["videoId"] in seen_ids:
            continue
        seen_ids.add(video["videoId"])
        deduped.append(video)

    if not deduped and network_errors:
        return {"ok": False, "error": "youtube fetch failed: " + "; ".join(network_errors[:3])}

    if not deduped:
        return {"ok": False, "error": "youtube fetch failed: no videos"}

    articles = [
        {
            "title": v["title"],
            "description": v["description"],
            "source": v.get("channelTitle") or "youtube",
            "publishedAt": v.get("publishedAt"),
        }
        for v in deduped
    ]
    themes = _extract_themes(articles)
    hooks = _build_hooks(articles, themes)
    active = [k for k, v in themes.items() if v]
    top_theme = active[0].replace("_", " ") if active else "general golf"

    payload = {
        "updated": utc_now_iso(),
        "data_source": "youtube_api_v3",
        "videos_found": len(deduped),
        "top_videos": deduped[:10],
        "articles_sourced": articles[:10],
        "trending_themes": themes,
        "hooks": hooks,
        "summary": {
            "top_theme": top_theme,
            "source": "youtube_api_v3",
            "notes": "Live YouTube trending data for ZA region",
        },
    }
    atomic_write(OUTPUT, payload)
    return {"ok": True, "rows": len(deduped)}
