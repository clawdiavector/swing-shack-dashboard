"""Finds specific posts worth reposting to Stories, from the pages in story-brands.json.

Reads each page's recent posts through Instagram business_discovery (read-only, the
same call the competitor tracker uses), drops what we should not share, and ranks the
rest. Rules, not a model, so the reasons shown are the real reasons.

Dropped: launches and drops (we may not stock them), giveaways, paid posts, sales,
anything older than two weeks. Preferred: "vibe" posts (short caption, no product,
doing better than the page's usual). Product posts that are not launches stay in,
marked "check we stock it", because a caption cannot tell us what is on our shelves.
"""
from __future__ import annotations

import json
import os
import re
import statistics
import tempfile
import time
import urllib.parse
from datetime import datetime, timezone
from urllib.parse import urlsplit

from . import story_suggestion

CACHE_TTL = 6 * 3600
MAX_AGE_DAYS = 14
PER_BRAND = 6
PER_PAGE = 2

_RELEASE = re.compile(
    r"\b(drops?|dropping|dropped|launch(es|ed|ing)?|pre-?orders?|coming soon|available now|"
    r"just released|now available|new collection|release date|out now|on sale|restock|"
    r"shop now|limited edition|collab(oration)?|collections?|all-new|brand new|introducing|"
    r"is back|is here|meet the|new arrivals?|new additions?|new colou?rways?|new models?|new styles?|"
    r"line-?ups?|just added|now in|first look|sneak peek|unveil(s|ed)?)\b|"
    r"\b\d{1,2}% off\b|\bsale\b|\bdiscount\b|\bcode\b"
)
_NOT_ORGANIC = re.compile(
    r"#ad\b|#sponsored|paid partnership|\bgiveaway\b|\bwin (a|an|your)\b|\btag a friend\b|\benter to win\b"
)
_SENSITIVE = re.compile(
    r"\b(rip|rest in peace|passed away|passing|tribute|remembering|in memory|condolences|"
    r"heartbroken|mourn(ing)?|funeral|accountability|banning|banned|lawsuit|controversy)\b"
)
_PRODUCT = re.compile(
    r"\b(driver|irons?|putter|wedges?|shaft|polo|shirt|hoodie|cap|hat|bag|ball|balls|jacket|"
    r"shorts|trousers|shoes?|glove|tee)\b"
)


def _handle(url: str | None) -> str | None:
    if not url:
        return None
    parts = [p for p in urlsplit(url).path.split("/") if p]
    return parts[0].lower() if parts else None


def classify(caption: str) -> tuple[str | None, str]:
    """Return (kind, why). kind None means do not suggest."""
    text = (caption or "").lower()
    if _NOT_ORGANIC.search(text):
        return None, "paid or giveaway post"
    if _RELEASE.search(text):
        return None, "release, sale or launch: we may not stock it"
    if _SENSITIVE.search(text):
        return None, "sad, legal or divisive news: not for our Stories"
    product = bool(_PRODUCT.search(text))
    if len(text.strip()) <= 140 and not product:
        return "vibe", "vibe post: no product named, short caption"
    if product:
        return "product", "product post, not a launch: check we stock it"
    return "story", "brand or golf story"


def _age_days(ts: str, now: datetime) -> float:
    return (now - datetime.fromisoformat(ts.replace("Z", "+00:00").replace("+0000", "+00:00"))).total_seconds() / 86400


def rank_page(page: dict, posts: list[dict], now: datetime | None = None) -> list[dict]:
    """Score one page's recent posts against that page's own normal."""
    now = now or datetime.now(timezone.utc)
    eng = [(p.get("like_count") or 0) + 3 * (p.get("comments_count") or 0) for p in posts]
    mid = statistics.median(eng) if eng else 0
    norm = mid if mid > 0 else 1
    out = []
    for p, e in zip(posts, eng):
        if not p.get("permalink") or not p.get("timestamp"):
            continue
        age = _age_days(p["timestamp"], now)
        if age > MAX_AGE_DAYS:
            continue
        kind, why = classify(p.get("caption") or "")
        if not kind:
            continue
        score = min(e / norm, 8) * {"vibe": 1.3, "story": 1.1, "product": 0.9}[kind] * (1 - 0.5 * age / MAX_AGE_DAYS)
        video = p.get("media_type") == "VIDEO"
        out.append({
            "page_id": page["id"], "page": page["name"], "kind": kind, "why": why,
            "url": p["permalink"], "likes": p.get("like_count"), "comments": p.get("comments_count"),
            "posted": p["timestamp"][:10], "media_type": p.get("media_type"),
            "image": p.get("thumbnail_url") if video else p.get("media_url"),
            "caption": (p.get("caption") or "")[:140], "score": round(score, 2),
        })
    return out


def pick(cands: list[dict]) -> list[dict]:
    """Best first, at most PER_PAGE from one page so one brand does not take the list."""
    taken: dict[str, int] = {}
    out = []
    for c in sorted(cands, key=lambda c: -c["score"]):
        if taken.get(c["page_id"], 0) >= PER_PAGE:
            continue
        taken[c["page_id"]] = taken.get(c["page_id"], 0) + 1
        out.append(c)
        if len(out) >= PER_BRAND:
            break
    return out


def _fetch(username: str) -> list[dict]:
    """Recent posts for one public business or creator account. Raises on failure."""
    from .jobs.layer1.competitor_tracker import _graph_get, _load_meta_creds

    creds = _load_meta_creds()
    if not creds:
        raise RuntimeError("no Meta credentials")
    fields = (
        f"business_discovery.username({username})"
        "{media.limit(20){caption,timestamp,like_count,comments_count,media_type,permalink,media_url,thumbnail_url}}"
    )
    q = urllib.parse.urlencode({"fields": fields, "access_token": creds["token"]})
    body, err = _graph_get(f"https://graph.facebook.com/v21.0/{creds['ig_id']}?{q}")
    if err or not isinstance(body, dict) or "business_discovery" not in body:
        raise RuntimeError((err or "no business_discovery")[:120])
    return body["business_discovery"]["media"]["data"]


def _cache_path() -> str:
    return os.path.join(os.environ.get("DATA_DIR") or "/data/campaign-os", "story-candidates.json")


def _read_cache() -> dict:
    try:
        with open(_cache_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write_cache(data: dict) -> None:
    path = _cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def candidates(brand: str, refresh: bool = False, now: datetime | None = None) -> dict:
    """Ranked posts for a brand. Cached six hours; a page that fails is reported, not fatal."""
    cache = _read_cache()
    hit = cache.get(brand)
    if hit and not refresh and time.time() - hit["fetched_at"] < CACHE_TTL:
        return hit
    data = story_suggestion._load(brand)
    if not data:
        return {"brand": brand, "posts": [], "errors": ["unknown brand"], "fetched_at": time.time()}
    pages = [p for p in (data.get("retail") or []) + (data.get("moments") or []) if _handle(p.get("instagram"))]
    cands, errors = [], []
    for page in pages:
        try:
            cands += rank_page(page, _fetch(_handle(page["instagram"])), now)
        except Exception as exc:  # one dead page must not blank the list
            errors.append(f"{page['name']}: {exc}")
    best: dict[str, dict] = {}
    for c in sorted(cands, key=lambda c: -c["score"]):
        best.setdefault(c["page_id"], c)
    result = {"brand": brand, "posts": pick(cands), "by_page": best, "errors": errors, "fetched_at": time.time()}
    if result["posts"] or not hit:
        cache[brand] = result
        _write_cache(cache)
        return result
    return hit  # every page failed: keep showing the last good list


_STOCK_STOP = {
    "with", "your", "from", "that", "this", "have", "what", "when", "will", "more", "just", "like",
    "into", "over", "their", "they", "them", "been", "were", "than", "then", "some", "much", "most",
    "every", "about", "ready", "great", "game", "round", "shot", "hole", "play", "plays", "golf",
}


def _stock_names(brand: str) -> list[str]:
    """Product names on the brand's latest saved stock list (empty when none saved)."""
    from . import stock_pulse as sp
    snaps = sp.load_snapshots(brand)
    if not snaps:
        return []
    return sorted({r["name"] for r in snaps[-1].get("rows", []) if r.get("name")})


def stock_check(brand: str, posts: list[dict]) -> list[dict]:
    """Flag each retail-brand post against the stock list. Nothing is hidden.

    stock is "match" (a model in the caption is on our list), "none" (the brand is on
    our list but nothing in the caption is), "brand-unlisted" (we list nothing from
    this maker), or "unknown" (no stock list saved, or a golf-moment page, which is not a shop brand).
    """
    from . import stock_pulse as sp
    data = story_suggestion._load(brand) or {}
    retail = {p["id"]: p for p in data.get("retail") or []}
    names = _stock_names(brand)
    out = []
    for p in posts:
        q = dict(p, stock="unknown", stock_name=None)
        page = retail.get(p.get("page_id"))
        if page and names:
            maker = sp._tokens(page["name"])
            mine = [n for n in names if maker and set(maker) <= set(sp._tokens(n))]
            if not mine:
                q["stock"] = "brand-unlisted"
            else:
                words = {t for t in sp._tokens(p.get("caption") or "") if len(t) >= 4 and t not in _STOCK_STOP}
                words -= set(maker)
                hit = next((n for n in mine if words & set(sp._tokens(n))), None)
                q["stock"], q["stock_name"] = ("match", hit) if hit else ("none", None)
        out.append(q)
    return out
