"""Fetch trending golf posts from Reddit and write reddit-trends.json."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import requests

from ._io import atomic_write, utc_now_iso

OUTPUT = "reddit-trends.json"
USER_AGENT = "linux:SwingShackCampaignOS:v1.0.0 (by /u/swing-shack)"
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


def _fetch_bytes(url: str) -> bytes:
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=FETCH_TIMEOUT,
    )
    if resp.status_code == 429:
        raise requests.HTTPError("rate limited", response=resp)
    resp.raise_for_status()
    return resp.content


def _local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


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


def _parse_reddit_json(data: dict, sub: str) -> list[dict[str, Any]]:
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


def _parse_subreddit_rss(sub: str) -> list[dict[str, Any]]:
    """Reddit blocks anonymous JSON from many hosts; Atom RSS still works."""
    url = f"https://www.reddit.com/r/{sub}/.rss"
    xml_bytes = _fetch_bytes(url)
    root = ET.fromstring(xml_bytes)
    trends: list[dict[str, Any]] = []
    for entry in root.iter():
        if _local_tag(entry.tag) != "entry":
            continue
        fields: dict[str, str] = {}
        link = ""
        for child in entry:
            tag = _local_tag(child.tag)
            if tag == "link" and child.get("href"):
                link = child.get("href") or ""
            elif tag in ("title", "updated", "published", "content"):
                fields[tag] = (child.text or "").strip()
        title = fields.get("title", "")
        if len(title) < 5:
            continue
        title_l = title.lower()
        words = [w for w in title_l.split() if len(w) > 5]
        raw_ts = fields.get("updated") or fields.get("published") or ""
        created = raw_ts
        try:
            if raw_ts:
                created = datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).isoformat()
        except ValueError:
            created = datetime.now(timezone.utc).isoformat()
        trends.append(
            {
                "subreddit": sub,
                "title": title,
                "score": 0,
                "comments_count": 0,
                "url": link,
                "permalink": link,
                "created_utc": created,
                "intent": _classify_intent(title),
                "key_terms": " ".join(words[:5]),
                "is_self": True,
                "selftext_snippet": (fields.get("content") or "")[:200],
                "source_format": "rss",
            }
        )
    return trends


def _parse_subreddit(sub: str) -> list[dict[str, Any]]:
    json_url = f"https://www.reddit.com/r/{sub}/hot.json?limit=20"
    try:
        data = _fetch_json(json_url)
        return _parse_reddit_json(data, sub)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (403, 429):
            return _parse_subreddit_rss(sub)
        raise


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
