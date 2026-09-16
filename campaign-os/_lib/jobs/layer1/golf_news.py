"""Fetch golf news from RSS feeds and write golf-news.json."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from ..errors import describe_exception
from ._io import atomic_write, utc_now_iso

OUTPUT = "golf-news.json"
USER_AGENT = "SwingShackCampaignOS/1.0 (golf news; contact ops)"
FETCH_TIMEOUT = 15
MAX_BYTES = 300_000

RSS_FEEDS = (
    {"name": "BBC Sport Golf", "url": "https://feeds.bbci.co.uk/sport/golf/rss.xml"},
    {"name": "Golf.com", "url": "https://www.golf.com/feed/"},
    {"name": "ESPN Golf", "url": "https://www.espn.com/espn/rss/golf/news"},
)


def _fetch_url(url: str) -> bytes:
    """Download *url*; patch in tests."""
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=FETCH_TIMEOUT,
        stream=True,
    )
    resp.raise_for_status()
    chunks: list[bytes] = []
    size = 0
    for chunk in resp.iter_content(chunk_size=8192):
        if not chunk:
            continue
        chunks.append(chunk)
        size += len(chunk)
        if size >= MAX_BYTES:
            break
    return b"".join(chunks)


def _local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return html.unescape(el.text.strip())


def _parse_pub_date(raw: str) -> str:
    if not raw:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        return parsedate_to_datetime(raw).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _absolute_url(link: str, feed_url: str) -> str:
    link = link.strip()
    if not link:
        return ""
    if link.startswith("http://") or link.startswith("https://"):
        return link
    return urljoin(feed_url, link)


def _score_article(title: str, source: str) -> dict[str, Any]:
    title_l = title.lower()
    local_relevance = 6
    if re.search(r"south africa|johannesburg|sa golf|ernest|oudtshoorn|cape town|durban", title_l):
        local_relevance = 9 if "news24" in source.lower() else 8

    content_angle = 7 if re.search(r"golf|swingshack|indoor|trackman|fitting|lesson|simulator", title_l) else 5

    if re.search(r"fitting|equipment|clubs", title_l):
        topic_cluster = "equipment"
    elif re.search(r"lesson|coach|teaching|swing", title_l):
        topic_cluster = "coaching"
    elif re.search(r"liv|pga|tour|tournament|winner|score", title_l):
        topic_cluster = "tournament"
    else:
        topic_cluster = "general"

    return {
        "local_relevance_score": local_relevance,
        "content_angle_score": content_angle,
        "topic_cluster": topic_cluster,
    }


def _parse_rss(xml_bytes: bytes, feed: dict[str, str]) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return articles

    for item in root.iter():
        if _local_tag(item.tag) != "item":
            continue
        fields: dict[str, str] = {}
        for child in item:
            fields[_local_tag(child.tag)] = _text(child)
        title = fields.get("title", "")
        if len(title) < 10:
            continue
        link = _absolute_url(fields.get("link", ""), feed["url"])
        summary = re.sub(r"<[^>]+>", "", fields.get("description", ""))[:150]
        scores = _score_article(title, feed["name"])
        articles.append(
            {
                "title": title,
                "source": feed["name"],
                "url": link,
                "published_date": _parse_pub_date(fields.get("pubDate", "")),
                "summary": summary,
                **scores,
            }
        )
        if len(articles) >= 8:
            break
    return articles


def _build_payload(news: list[dict[str, Any]]) -> dict[str, Any]:
    post_ideas = [
        {
            "headline": n["title"],
            "format": "reel" if re.search(r"video|watch|highlight", n["title"], re.I) else "static",
            "source": "golf-news",
            "reason": f"Breaking: {n['title'][:50]}",
        }
        for n in news
        if n.get("content_angle_score", 0) >= 7
    ][:3]

    return {
        "updated": utc_now_iso(),
        "source": "RSS feeds",
        "news": news[:12],
        "post_ideas": post_ideas,
        "story_today": [n for n in news if n.get("local_relevance_score", 0) >= 8][:2],
        "reel_today": [n for n in news if n.get("topic_cluster") == "tournament"][:2],
    }


def run() -> dict:
    """Fetch golf RSS feeds and write golf-news.json."""
    all_news: list[dict[str, Any]] = []
    network_errors: list[str] = []

    for feed in RSS_FEEDS:
        try:
            xml_bytes = _fetch_url(feed["url"])
            all_news.extend(_parse_rss(xml_bytes, feed))
        except Exception as exc:  # noqa: BLE001 — network stubs may raise any type
            host = urlparse(feed["url"]).netloc or feed["name"]
            network_errors.append(f"{host}: {describe_exception(exc)}")

    if not all_news and network_errors:
        return {"ok": False, "error": "golf news fetch failed: " + "; ".join(network_errors[:3])}

    if not all_news:
        return {"ok": False, "error": "golf news fetch failed: no articles"}

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in all_news:
        key = item["title"][:50]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    payload = _build_payload(unique)
    atomic_write(OUTPUT, payload)
    return {"ok": True, "rows": len(unique)}
