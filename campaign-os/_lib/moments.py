"""Moments desk — what is happening now that a golf brand can join in, and what is coming.

Two halves, both read-only and with no posting:

    upcoming()   dates worth planning around (data/moments-calendar.json), each with
                 a "prepare by" date so the work starts before the day.
    live()       what South Africa is talking about today, from Google Trends (SA)
                 and a few SA news feeds, kept only when there is a golf, sport or
                 "something to do" angle and hidden when it is a sensitive story.

Nothing here writes a post. A person decides. The starter lines are templates,
marked as such, to edit before use.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from pathlib import Path

FEEDS = (
    {"name": "Google Trends SA", "url": "https://trends.google.com/trending/rss?geo=ZA", "kind": "trends"},
    {"name": "IOL Sport", "url": "https://www.iol.co.za/rss/iol/sport", "kind": "news"},
    {"name": "IOL News", "url": "https://www.iol.co.za/rss/iol/news", "kind": "news"},
    {"name": "The Citizen", "url": "https://www.citizen.co.za/feed/", "kind": "news"},
)
USER_AGENT = "SwingShackCampaignOS/1.0 (moments desk; contact ops)"
MAX_BYTES = 1_500_000
MAX_AGE_HOURS = 72

# Stories a brand should not joke about. Phrases, not single words, so golf talk
# ("what a shot", "on court", "dead heat") is not caught.
SENSITIVE = (
    "killed", "murder", "murdered", "shot dead", "shooting", "gunman", "stabbed", "attacked", "hijack",
    "kidnap", "rape", "assault", "abuse", "found dead", "dead body", "deadly", "dies", "died", "death",
    "funeral", "tragedy", "tragic", "plane crash", "car crash", "crash", "collision", "drown", "suicide",
    "protest", "riot", "national strike", "wage strike", "strike action", "election", "anc", "democratic alliance",
    "eff", "mk party", "parliament", "high court", "court case", "constitutional court", "magistrate",
    "arrest", "arrested", "police", "bomb", "petrol bomb", "explosion", "veld fire", "wildfire", "house fire",
    "flood", "floods", "disaster", "war", "gaza", "ukraine", "israel", "hamas", "terror", "cancer",
    "scandal", "corruption", "fraud", "thugs", "gang", "load shedding", "eskom",
    "injury", "injured", "hospital", "tribute", "mourn", "mourning", "passed away", "passes away",
    "condolences", "rallies around",
)
_SENSITIVE_RE = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in SENSITIVE) + r")\b", re.I)

# (category, base score, keywords, why it matters, starter line). {brand} is filled by the page.
CATEGORIES = (
    ("flyover", 100, ("flyover", "fly-over", "flypast", "fly-past", "air show", "airshow", "air force"),
     "Low and loud, and everyone is looking up. A low-score joke writes itself.",
     "Get your score as low as that flyover. {brand}."),
    ("golf", 90, ("golf", "golfer", "masters", "pga", "birdie", "bogey", "dp world", "sunshine tour",
                  "ryder cup", "presidents cup", "ernie els", "rory mcilroy", "scottie scheffler", "tiger woods",
                  "oosthuizen", "schwartzel", "tee shot", "fairway"),
     "Golf is already the story. React with a fitting, a drill or a hot take in the brand's voice.",
     "Everyone is talking golf. Come and see what your swing says. {brand}."),
    ("big_sport", 70, ("springbok", "springboks", "rugby", "proteas", "cricket", "bafana", "sundowns",
                       "kaizer chiefs", "orlando pirates", "tennis", "formula 1", "olympic", "world cup",
                       "t20", "test match", "grand slam"),
     "The whole country is watching. Borrow the talk: pressure, accuracy, the scoreboard.",
     "Pressure putts hit different when the whole country is watching. Beat the clock in the bay. {brand}."),
    ("weather", 55, ("heatwave", "heat wave", "cold front", "thunderstorm", "rainy", "heavy rain", "snow", "hailstorm"),
     "Weather ruins outdoor plans, and the bays are indoors.",
     "Rain, wind or heat, the bay is ready. {brand}."),
    ("long_weekend", 50, ("long weekend", "public holiday", "school holidays"),
     "People are looking for something to do.",
     "Long weekend sorted. Book a bay. {brand}."),
)


# ---------- fetching ----------

def http_get(url: str, timeout: int = 12) -> bytes:
    import requests
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout, stream=True)
    resp.raise_for_status()
    data = resp.raw.read(MAX_BYTES, decode_content=True)
    return data


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_feed(xml_bytes: bytes, source: str, kind: str) -> list[dict]:
    """RSS items as {source, kind, title, link, published, traffic}. Bad XML gives []."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    out = []
    for item in root.iter("item"):
        fields = {}
        for child in item:
            fields.setdefault(_local(child.tag), (child.text or "").strip())
        title = fields.get("title")
        if not title:
            continue
        published = None
        if fields.get("pubDate"):
            try:
                published = parsedate_to_datetime(fields["pubDate"]).astimezone(_dt.timezone.utc)
            except (TypeError, ValueError):
                published = None
        extra = []
        for child in item.iter():
            if _local(child.tag) == "news_item_title" and child.text:
                extra.append(child.text.strip())
        out.append({"source": source, "kind": kind, "title": title, "link": fields.get("link") or None,
                    "published": published, "traffic": fields.get("approx_traffic"),
                    "context": extra[:2]})
    return out


def fetch_all(get=http_get) -> tuple[list[dict], list[str]]:
    errors: list[str] = []

    def one(feed):
        try:
            return parse_feed(get(feed["url"]), feed["name"], feed["kind"]), None
        except Exception as exc:  # one dead feed must not blank the page
            return [], f"{feed['name']}: {type(exc).__name__}"

    with ThreadPoolExecutor(max_workers=len(FEEDS)) as pool:
        results = list(pool.map(one, FEEDS))
    items = []
    for rows, err in results:
        items.extend(rows)
        if err:
            errors.append(err)
    return items, errors


# ---------- scoring ----------

def is_sensitive(*texts: str) -> bool:
    return any(_SENSITIVE_RE.search(t) for t in texts if t)


def _traffic_points(traffic: str | None) -> int:
    digits = re.sub(r"[^\d]", "", traffic or "")
    if not digits:
        return 0
    return min(20, int(math.log10(max(int(digits), 1)) * 5))


def _category(text: str):
    low = text.lower()
    for name, base, words, why, line in CATEGORIES:
        for w in words:
            if re.search(r"\b" + re.escape(w) + r"\b", low):
                return name, base, why, line
    return None


def live(items: list[dict], *, now: _dt.datetime, limit: int = 12) -> dict:
    """Keep what has an angle, drop what is sensitive or old, rank by angle, buzz and freshness."""
    kept, hidden, seen = [], 0, set()
    for it in items:
        title = it["title"]
        key = re.sub(r"\W+", "", title.lower())[:60]
        if key in seen:
            continue
        seen.add(key)
        age = None
        if it.get("published"):
            age = (now - it["published"]).total_seconds() / 3600
            if age > MAX_AGE_HOURS:
                continue
        blob = " ".join([title] + list(it.get("context") or []))
        cat = _category(blob)
        if not cat:
            continue
        if is_sensitive(blob):
            hidden += 1
            continue
        name, base, why, line = cat
        score = base + _traffic_points(it.get("traffic"))
        if age is not None:
            score += 15 if age <= 6 else 8 if age <= 24 else -10 if age > 48 else 0
        kept.append({
            "title": title, "source": it["source"], "link": it.get("link"), "category": name,
            "score": score, "traffic": it.get("traffic"),
            "age_hours": None if age is None else round(age, 1),
            "act_today": bool(score >= 90 and (age is None or age <= 24)),
            "why": why, "starter_line": line, "context": it.get("context") or [],
        })
    kept.sort(key=lambda r: -r["score"])
    return {"items": kept[:limit], "hidden_sensitive": hidden}


# ---------- calendar ----------

def calendar_path() -> Path:
    from _lib.jobs.layer1._io import repo_root
    return repo_root() / "data" / "moments-calendar.json"


def load_calendar(path: Path | None = None) -> list[dict]:
    try:
        with open(path or calendar_path(), encoding="utf-8") as f:
            return json.load(f).get("events") or []
    except (OSError, ValueError):
        return []


def upcoming(events: list[dict], *, today: _dt.date, horizon_days: int = 60) -> list[dict]:
    out = []
    for e in events:
        try:
            start = _dt.date.fromisoformat(e["date"])
            end = _dt.date.fromisoformat(e.get("end") or e["date"])
        except (KeyError, ValueError):
            continue
        if end < today:
            continue
        days_to = (start - today).days
        if days_to > horizon_days:
            continue
        prep_by = start - _dt.timedelta(days=int(e.get("lead_days") or 7))
        if days_to < 0:
            status = "on now"
        elif prep_by <= today:
            status = "prepare now"
        else:
            status = "coming"
        out.append({"date": e["date"], "end": e.get("end"), "title": e["title"], "kind": e.get("kind"),
                    "angle": e.get("angle"), "days_to": max(days_to, 0), "prep_by": prep_by.isoformat(),
                    "status": status})
    out.sort(key=lambda r: r["date"])
    return out


def build(*, now: _dt.datetime | None = None, get=http_get, calendar: list[dict] | None = None) -> dict:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    sast_today = (now + _dt.timedelta(hours=2)).date()
    items, errors = fetch_all(get)
    result = live(items, now=now)
    events = calendar if calendar is not None else load_calendar()
    return {
        "schema": "https://campaign-os/moments/v1",
        "generated_at": now.isoformat(timespec="seconds"),
        "upcoming": upcoming(events, today=sast_today),
        "live": result["items"],
        "hidden_sensitive": result["hidden_sensitive"],
        "feeds_read": len(items),
        "errors": errors,
    }
