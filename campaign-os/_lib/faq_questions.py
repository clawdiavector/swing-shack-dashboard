"""Questions people really ask Google, per brand: post ideas for Plan > Ideas.

Google's search suggestions (the list under the search box) are public and show what
people type. For each brand we ask for suggestions on its own topics, then keep a
suggestion only when it is question-shaped (how much, is it worth it, what is, prices)
and about this brand: not another shop, another sport, another city or buying a
simulator for home. Topics, area and words to drop are in
data/brand-directory/<brand>/faq-seeds.json, so they can be changed without code.

The list is kept for a week, so opening Ideas makes no requests most days. Nothing is
answered here: the answers come from the person making the post, with sources.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[2]
BRAND_DIR = REPO / "data" / "brand-directory"
SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
MAX_AGE_S = 7 * 24 * 3600
PAUSE_S = 0.4  # between suggestion requests, to stay polite
PER_SEARCH = 4  # Google lists ten near-copies; the first few are the most searched
CACHE_DIR_OVERRIDE: Optional[Path] = None

Getter = Callable[[str], Tuple[int, bytes]]

_QUESTION_START = re.compile(
    r"^(how|what|whats|what's|is|are|do|does|can|should|why|when|which|where|who|will|best way)\b", re.I)
_QUESTION_WORDS = re.compile(r"\b(worth it|cost|costs|price|prices|how much)\b", re.I)

# Never about our brands: other shops, other sports, forums and other countries.
_ALWAYS_DROP = (
    "golf galaxy", "pga superstore", "club champion", "roger dunn", "golftec", "dick's", "dicks",
    "topgolf", "baseball", "cricket", "tennis", "railway", "reddit", "uk", "usa", "australia",
    "canada", "nz", "ireland", "america", "in india",
    # seen live on 13 Nov 2026
    "edwin watts", "scheels", "cool clubs", "disc golf", "top golf", "golf now", "golfnow",
    "golf pass", "future golf", "make regripping", "can you make",
)

# South African places. A question naming one outside the brand's area is not for it.
_SA_PLACES = (
    "johannesburg", "joburg", "jhb", "sandton", "randburg", "fourways", "midrand", "pretoria",
    "centurion", "soweto", "durban", "umhlanga", "cape town", "paarl", "stellenbosch",
    "somerset west", "wellington", "franschhoek", "western cape", "gauteng", "kzn",
    "port elizabeth", "gqeberha", "east london", "bloemfontein", "george", "polokwane",
    "nelspruit", "mbombela", "sun city", "kimberley", "rustenburg",
)


def _get(url: str) -> Tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; CampaignOS/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 (fixed public https URL)
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def _sleep(s: float) -> None:
    time.sleep(s)


def _has(text: str, word: str) -> bool:
    return re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", text) is not None


def is_question(text: str) -> bool:
    t = (text or "").strip().lower()
    return bool(_QUESTION_START.search(t) or _QUESTION_WORDS.search(t))


def keep(text: str, seeds: Dict[str, Any]) -> bool:
    """True when a suggestion is a question this brand could answer."""
    t = (text or "").strip().lower()
    if not is_question(t):
        return False
    if any(_has(t, w) for w in _ALWAYS_DROP):
        return False
    if any(_has(t, w.lower()) for w in seeds.get("drop_words") or []):
        return False
    area = [a.lower() for a in seeds.get("area") or []]
    if area and "any" not in area:
        for place in _SA_PLACES:
            if _has(t, place) and place not in area:
                return False
    return True


def tidy(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = t[:1].upper() + t[1:]
    if _QUESTION_START.search(t) and not t.endswith("?"):
        t += "?"
    return t


def load_seeds(brand: str) -> Dict[str, Any]:
    try:
        return json.loads((BRAND_DIR / brand / "faq-seeds.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"queries": [], "area": [], "drop_words": []}


def suggest(query: str, get: Getter = _get) -> List[str]:
    url = SUGGEST_URL + "?" + urllib.parse.urlencode({"client": "firefox", "hl": "en", "gl": "za", "q": query})
    status, body = get(url)
    if status != 200:
        raise RuntimeError(f"HTTP {status}")
    data = json.loads(body.decode("utf-8", "replace"))
    return [s for s in (data[1] if isinstance(data, list) and len(data) > 1 else []) if isinstance(s, str)]


def find_questions(brand: str, *, get: Getter = _get, sleep: Callable[[float], Any] = _sleep) -> Dict[str, Any]:
    seeds = load_seeds(brand)
    questions: List[Dict[str, str]] = []
    seen: set = set()
    errors: List[str] = []
    for i, q in enumerate(seeds.get("queries") or []):
        if i:
            sleep(PAUSE_S)
        try:
            found = suggest(q, get)
        except Exception as e:  # noqa: BLE001 (any failure means "could not read")
            errors.append(f"Google suggestions could not be read for '{q}': {e}")
            continue
        kept = 0
        for s in found:
            key = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
            key = re.sub(r"\s+", " ", key).strip()
            if kept >= PER_SEARCH or key in seen or not keep(s, seeds):
                continue
            seen.add(key)
            kept += 1
            questions.append({"question": tidy(re.sub(r"(?<=[a-z])\.(?=[a-z])", " ", s)), "from": q})
    # One from each search first, then the second from each, so the top of the list
    # covers every topic instead of ten ways to ask about club fitting.
    by_search: Dict[str, List[Dict[str, str]]] = {}
    for item in questions:
        by_search.setdefault(item["from"], []).append(item)
    questions = [lst[i] for i in range(PER_SEARCH) for lst in by_search.values() if i < len(lst)]
    if errors and not questions:
        errors = errors[:1]
    return {"brand": brand, "questions": questions, "errors": errors if not questions else [], "generated_at": time.time()}


def _cache_dir(cache_dir: Optional[Path]) -> Path:
    if cache_dir:
        return Path(cache_dir)
    if CACHE_DIR_OVERRIDE:
        return Path(CACHE_DIR_OVERRIDE)
    data = os.environ.get("DATA_DIR")
    if data and os.path.isdir(data):
        return Path(data) / "faq"
    return Path(tempfile.gettempdir()) / "campaign-os-faq"


def questions_for(brand: str, *, get: Optional[Getter] = None, sleep: Optional[Callable[[float], Any]] = None,
                  cache_dir: Optional[Path] = None, refresh: bool = False,
                  now: Callable[[], float] = time.time) -> Dict[str, Any]:
    """This week's questions for a brand, read from Google at most once a week."""
    get = get or _get
    sleep = sleep or _sleep
    cache = _cache_dir(cache_dir) / f"questions-{brand}.json"
    if not refresh:
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            if now() - float(cached.get("generated_at") or 0) < MAX_AGE_S and cached.get("questions"):
                return cached
        except (OSError, ValueError):
            pass
    res = find_questions(brand, get=get, sleep=sleep)
    if res["questions"]:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return res
