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


# Club business is not a moment: transfers, contracts, coaches, injuries. Golf is exempt (a player
# "joins" a field), and so is a national-team match, which the EVENT words below let through.
_CLUB_BUSINESS_RE = re.compile(
    r"\b(?:signing|signs|signed|transfer|contract|terminated|appointed|appoints|sacked|coach|coaching staff|"
    r"leaves|joins|extends|extension|loan|rumour|rumours|targets|bid)\b", re.I)
# Words that say something is actually being played or decided.
_EVENT_RE = re.compile(
    r"\b(?:vs|v|test|final|semi-final|quarter-final|series|match|tour|wicket|century|hat-trick|try|"
    r"squad|named|beat|beats|defeat|draw|win|wins|world cup|grand slam|champion|champions|leaderboard|day [1-5])\b",
    re.I)
_NATIONAL_RE = re.compile(r"\b(?:springboks?|proteas|bafana|banyana|blitzboks)\b", re.I)
# A search that is only a sport's name is not news.
_GENERIC_TOPICS = {
    "rugby", "rugby union", "cricket", "soccer", "football", "tennis", "golf", "sport", "sports",
    "formula 1", "f1", "olympics", "weather", "holiday", "public holiday",
}


def _is_generic(title: str) -> bool:
    return re.sub(r"[^a-z0-9 ]", "", title.lower()).strip() in _GENERIC_TOPICS


def _display_title(it: dict) -> str:
    """Google Trends names a search ("marco jansen"); its news headline says what happened."""
    ctx = it.get("context") or []
    if it.get("kind") == "trends" and ctx:
        return ctx[0]
    return it["title"]


def _is_act_today(name: str, score: int, age, traffic_pts: int, blob: str) -> bool:
    """A flyover or a golf story is hot for a day. Other sport only when a team is actually playing."""
    if age is not None and age > 24:
        return False
    if name in ("flyover", "golf"):
        return score >= 95
    if name == "big_sport":
        return bool(traffic_pts >= 15 and (age is None or age <= 12)
                    and (_NATIONAL_RE.search(blob) or _EVENT_RE.search(blob)))
    return False


def live(items: list[dict], *, now: _dt.datetime, limit: int = 12) -> dict:
    """Keep what has an angle, drop what is sensitive, old, generic or club business, rank the rest."""
    kept, hidden, seen = [], 0, set()
    for it in items:
        title = _display_title(it)
        key = re.sub(r"\W+", "", title.lower())[:60]
        if key in seen:
            continue
        seen.add(key)
        age = None
        if it.get("published"):
            age = (now - it["published"]).total_seconds() / 3600
            if age > MAX_AGE_HOURS:
                continue
        if _is_generic(it["title"]):
            continue
        blob = " ".join([it["title"], title] + list(it.get("context") or []))
        cat = _category(blob)
        if not cat:
            continue
        if is_sensitive(blob):
            hidden += 1
            continue
        name, base, why, line = cat
        if name != "golf" and _CLUB_BUSINESS_RE.search(blob) and not _EVENT_RE.search(blob):
            continue
        pts = _traffic_points(it.get("traffic"))
        score = base + pts
        if age is not None:
            score += 15 if age <= 6 else 8 if age <= 24 else -10 if age > 48 else 0
        kept.append({
            "title": title, "source": it["source"], "link": it.get("link"), "category": name,
            "score": score, "traffic": it.get("traffic"),
            "age_hours": None if age is None else round(age, 1),
            "act_today": _is_act_today(name, score, age, pts, blob),
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


def build(*, now: _dt.datetime | None = None, get=http_get, calendar: list[dict] | None = None,
          chat=None, previous: dict | None = None) -> dict:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    sast_today = (now + _dt.timedelta(hours=2)).date()
    items, errors = fetch_all(get)
    result = live(items, now=now)
    if chat is not None:
        draft_lines(result["items"], chat=chat, previous=(previous or {}).get("live"))
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


# ---------- voice: the take, drafted per brand ----------

VOICE_SYSTEM = (
    "You write one-line social posts for two South African golf businesses. Voice: Nando's. Quick, cheeky, "
    "says out loud what everyone is already thinking, always on the side of the ordinary person. Dry, never mean. "
    "Punch at the situation, never at a person, a fan base, a victim, a religion, a race, a party or a tragedy. "
    "Never mock or praise an individual by name. If the story involves a death, injury, crime, politics, money "
    "trouble or anything that could hurt someone, answer {\"skip\": true}. "
    "No made-up facts about the business: no prices, offers, opening hours, results or claims. "
    "No hashtags, no links, at most one emoji. Each line is 140 characters or fewer, plain South African English "
    "with a local feel (lekker is fine, sparingly). Do not put the business name in the line. "
    "The line must tie the news to golf, practising, indoor bays or club fitting in a way that makes people smile. "
    "Businesses: swing-shack is indoor golf simulator bays in Johannesburg, social and playful. "
    "stick is a golf club fitting and lessons studio in Paarl, calm and dry, still cheeky. "
    "Also give each business a story headline: 2 to 6 words, 40 characters or fewer, the punchline of its line "
    "(it goes on a story image). "
    "Return only JSON: {\"angle\": \"one short sentence on the take\", \"swing-shack\": \"line\", "
    "\"stick\": \"line\", \"headlines\": {\"swing-shack\": \"headline\", \"stick\": \"headline\"}}"
)
DRAFT_BRANDS = ("swing-shack", "stick")
MAX_LINE = 140
MAX_HEADLINE = 40
_JSON_RE = re.compile(r"\{.*\}", re.S)


def _unquote(text: str) -> str:
    """Drop quote marks wrapped around the whole line, not a quote that belongs to it."""
    t = text.strip()
    if len(t) > 1 and t[0] == t[-1] == '"' and t.count('"') == 2:
        return t[1:-1].strip()
    return t


def parse_draft(text: str | None) -> dict | None:
    """The model's JSON, checked. None when unusable; {"skip": True} when it declined the story."""
    m = _JSON_RE.search(text or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("skip"):
        return {"skip": True}
    lines = {}
    for b in DRAFT_BRANDS:
        line = _unquote(str(data.get(b) or ""))
        if not line or len(line) > MAX_LINE or "#" in line or "http" in line.lower() or is_sensitive(line):
            continue
        lines[b] = line
    if not lines:
        return None
    heads = {}
    raw = data.get("headlines") if isinstance(data.get("headlines"), dict) else {}
    for b in lines:
        h = _unquote(str(raw.get(b) or ""))
        if h and len(h) <= MAX_HEADLINE and "#" not in h and "http" not in h.lower() and not is_sensitive(h):
            heads[b] = h
    return {"skip": False, "lines": lines, "headlines": heads,
            "angle": str(data.get("angle") or "").strip()[:200]}


def draft_lines(items: list[dict], *, chat, previous: list[dict] | None = None, limit: int = 3) -> None:
    """Add ``lines`` (per brand) and ``angle`` to the strongest items, in place.

    ``chat(messages)`` returns (text, error). Lines already drafted for the same headline are reused, so
    a refresh costs nothing and the text does not change under someone's feet. A failure leaves the
    template line in place; it never breaks the page.
    """
    old = {p.get("title"): p for p in (previous or [])
           if (p.get("lines") and "headlines" in p) or p.get("skip_joke")}  # an older draft is redone once
    todo = []
    for it in items[:limit]:
        prev = old.get(it["title"])
        if prev:
            for k in ("lines", "headlines", "angle", "skip_joke"):
                if k in prev:
                    it[k] = prev[k]
        else:
            todo.append(it)

    def one(it):
        user = (f"Headline: {it['title']}\nAlso reported: {' | '.join(it.get('context') or []) or 'n/a'}\n"
                f"Source: {it['source']}\nKind of moment: {it['category']}")
        try:
            text, err = chat([{"role": "system", "content": VOICE_SYSTEM}, {"role": "user", "content": user}])
        except Exception:
            return it, None
        return it, (None if err else parse_draft(text))

    if not todo:
        return
    with ThreadPoolExecutor(max_workers=min(4, len(todo))) as pool:
        for it, draft in pool.map(one, todo):
            if not draft:
                continue
            if draft.get("skip"):
                it["skip_joke"] = True
            else:
                it["lines"], it["angle"] = draft["lines"], draft["angle"]
                it["headlines"] = draft["headlines"]
