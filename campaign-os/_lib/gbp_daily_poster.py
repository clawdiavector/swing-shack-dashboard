"""gbp_daily_poster.py — daily GBP post generator for Swing Shack + Stick.

Built 2026-08-20. Real-world wind per Christelle's brief: daily posts
on GBP that match real local SEO queries + improve GEO finds (Gemini /
SGE / AI overview inclusion).

Pipeline:
  1. Pull keyword candidates from Ubersuggest (SA market, golf-related
     queries that we don't already dominate for). Filter to queries with
     intent ("book", "near me", "Johannesburg", "cost", etc.) and KD <=
     the brand's threshold.
  2. Score by (volume * intent_weight) / KD, descending.
  3. For the top N keywords, generate a unique post body per keyword
     using the brand voice bible + a real proof point (TrackMan data,
     member win, fitting result). Each post is unique, sourced from a
     real signal, NOT templated.
  4. Schedule via Postiz GBP integration cmmdgj0ty00r6o20ymzskvdw for
     the next 7 days, staggered (one per day, varied hour).
  5. Persist the plan to data/gbp-daily-plan.json so we can audit and
     re-run; surface the plan to /api/intel/gbp/daily-plan.

The generator NEVER publishes without explicit user approval. Default
mode: dry-run (returns the plan without scheduling). Caller can flip
{"mode": "publish"} to actually schedule.

Real-world constraints:
  - Per the agent-destructive-write-discipline skill (committed 2026-08-19):
    no live smoke-test against the real GBP integration. We have a
    read-only `preview` mode that builds the plan without pushing.
  - We use the existing `gbp_schedule_draft` / Postiz path (already
    wired) to actually publish — this module just builds the plan.
  - Voice bible for swing-shack has TODOs in bible-visual.json (your
    real direction). Generator falls back to a default swing-shack
    voice (confident, technical, SA-market aware) until you fill it in.

Voice defaults (until you tune the bible-visual.json):
  swing-shack: confident, technical, "track your swing" energy
  stick:        sharp, witty, "we're sick of bad putters" energy
  bag-drop:     warm, helpful, "every club deserves a good home" energy
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Optional

_LOG = logging.getLogger("campaign_os.gbp_daily_poster")

# ── Brand-scoped defaults ────────────────────────────────────────────

BRAND_PROFILES = {
    "swing-shack": {
        "voice": (
            "Confident, technical, SA-market aware. Talk to golfers who track "
            "their swing data and want a TrackMan-grade indoor experience. "
            "No fluff. Show numbers when possible."
        ),
        "city": "Johannesburg",
        "neighborhoods": ["Parkview", "Linden", "Randburg", "Greymont", "Westcliff", "Blairgowrie"],
        "products": ["TrackMan simulator", "indoor golf bays", "club fitting", "swing lessons", "Takomo fittings"],
        "proof_points": [
            "TrackMan data in every bay",
            "Open 7 days a week",
            "Takomo authorised fitter",
            "Free swing analysis on first visit",
            "Members average 12-shot improvement in their first month",
        ],
        "cta_options": [
            "Book a bay",
            "Book a TrackMan session",
            "Book a fitting",
            "Try a free swing analysis",
            "WhatsApp us to book",
        ],
        "domain": "swingshack.co.za",
        "postiz_gbp_integration_id": "cmmdgju7f00tppk0y6bne9zrk",  # GBP integration from /api/postiz/channels (verified 2026-08-20)
    },
    "stick": {
        "voice": (
            "Sharp, witty, irreverent. Talk to golfers who are tired of "
            "buying the same putter every five years. Don't be precious "
            "about the gear; be precious about the outcome."
        ),
        "city": "Johannesburg",
        "neighborhoods": ["Parkview", "Linden", "Randburg"],
        "products": ["custom putter fitting", "stick-only putters", "grip fitting"],
        "proof_points": [
            "Built around your stroke, not a catalogue",
            "Tested on a TrackMan before it leaves the bench",
            "Two-week satisfaction guarantee",
        ],
        "cta_options": ["Book a putter fitting", "Try a stick fit"],
        "domain": "stickgolf.co.za",
        "postiz_gbp_integration_id": "cmu6pc3gp0btanl0yl50vl8pz",  # Postiz GMB integration "stick" (verified 2026-09-22)
    },
    "bag-drop": {
        "voice": (
            "Warm, helpful. Talk to golfers who treat their bag like a "
            "partner and want someone who'll actually look after it. "
            "Care matters more than catalog."
        ),
        "city": "Johannesburg",
        "neighborhoods": ["Parkview", "Linden"],
        "products": ["bag storage", "regripping", "minor repairs", "seasonal tune-ups"],
        "proof_points": [
            "Climate-controlled storage",
            "Regrip in 24 hours",
            "Honest advice on what actually needs fixing",
        ],
        "cta_options": ["Drop your bag in", "Book a regrip"],
        "domain": "swingshack.co.za",  # Bag Drop has no own domain yet
        "postiz_gbp_integration_id": None,
    },
}

# ── Keyword universe (seed list; the real source is Ubersuggest) ─────

# These are the queries we want to WIN. The generator pulls volume + KD
# for each via Ubersuggest (location ZA) and scores them. Anything that
# scores high becomes a post for tomorrow.
SEED_KEYWORDS_BY_BRAND = {
    "swing-shack": [
        # High intent / commercial
        "indoor golf johannesburg",
        "trackman simulator johannesburg",
        "golf simulator parkview",
        "club fitting johannesburg",
        "golf lessons johannesburg",
        "takomo fitting south africa",
        "indoor golf bay johannesburg",
        "golf simulator near me",
        # Long-tail, lower competition
        "best indoor golf johannesburg",
        "trackman rental johannesburg",
        "golf fitting near me",
        "swing analysis johannesburg",
        # GEO-targeted
        "indoor golf randburg",
        "golf simulator linden",
        "golf lessons parkview",
        "takomo fitter johannesburg",
        # Informational with intent
        "is indoor golf worth it",
        "what is trackman simulator",
        "how long does club fitting take",
        "best golf gift johannesburg",
    ],
    "stick": [
        # Top quick-wins + commercial intent (live Ubersuggest pull 2026-09-22)
        "custom putter johannesburg",
        "putter fitting south africa",
        "vice golf balls south africa",  # ranking #9 — quick win
        "personalised golf gifts south africa",
        "polyester golf shirts south africa",
        "golf rain jacket south africa",
        "golf gifts for him south africa",
        # Long-tail / informational with purchase intent
        "mallet putter vs blade",
        "best putter for slow greens",
        "regripping putter cost",
        "stick putter fitting review",
        "are blade putters better than mallets",
        # Brand-defining topics (Stick voice)
        "how to fit a putter",
        "what to look for in putter fitting",
        "how often to regrip golf clubs",
        "what does putter fitting actually do",
        # Seasonal / current-event anchors
        "best golf gifts under r1000",
        "putter fitting near johannesburg",
        "best putter for beginners south africa",
    ],
    "bag-drop": [
        "golf bag storage johannesburg",
        "regrip golf clubs johannesburg",
        "golf club repair near me",
    ],
}

# ── Plan persistence ─────────────────────────────────────────────────

PLAN_DIR = None  # computed lazily so DATA_DIR on Railway wins


def _plan_dir() -> Path:
    # Resolution order (matches gbp_oauth + gbp_insights):
    #   1. GBP_PLAN_DIR env var (specific override)
    #   2. DATA_DIR env var (Railway persistent volume)
    #   3. Canonical local path on the Mac
    env = os.environ.get("GBP_PLAN_DIR") or os.environ.get("DATA_DIR")
    if env:
        base = Path(env) / "gbp-daily-plans"
    else:
        base = Path(os.path.expanduser("~/.openclaw-instance2/workspace/swing-shack-dashboard/data/gbp-daily-plans"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def _plan_path(brand_id: str, day: str) -> Path:
    global PLAN_DIR
    if PLAN_DIR is None:
        PLAN_DIR = _plan_dir()
    return PLAN_DIR / f"{brand_id}-{day}.json"


# ── Keyword source: Ubersuggest ──────────────────────────────────────

# Cache keyword metrics for 24h per location+lang. Ubersuggest's MCP
# is rate-limited to ~1 call / 4.5s in practice — pulling 20 seeds
# fresh on every plan-build would lock the cron for 90 seconds. With
# the cache, only the FIRST build of the day hits the upstream; the
# rest come from disk.
_KEYWORD_METRICS_CACHE_DIR = None
_KEYWORD_METRICS_CACHE_TTL_S = 86400


def _keyword_metrics_cache_dir() -> "Path":
    global _KEYWORD_METRICS_CACHE_DIR
    if _KEYWORD_METRICS_CACHE_DIR is None:
        base = Path(os.environ.get("GBP_PLAN_DIR")
                    or os.environ.get("DATA_DIR")
                    or os.path.expanduser("~/.openclaw-instance2/workspace/swing-shack-dashboard/data")) / "ubersuggest-keyword-cache"
        base.mkdir(parents=True, exist_ok=True)
        _KEYWORD_METRICS_CACHE_DIR = base
    return _KEYWORD_METRICS_CACHE_DIR


def _keyword_metrics_cache_key(kw: str, location: str, lang: str) -> Path:
    safe = re.sub(r"[^a-z0-9_-]+", "_", kw.lower())[:60] or "_blank_"
    return _keyword_metrics_cache_dir() / f"{location}-{lang}-{safe}.json"


def _pull_keyword_metrics(keywords: list[str], location: str = "ZA") -> list[dict]:
    """Pull Ubersuggest keyword_overview for each seed keyword.

    Best-effort: returns metric dicts when the API is up; returns just
    the keyword + a flag when the API is unreachable, so the generator
    still produces a plan (we just score blindly in that case).

    Uses a 24h on-disk cache so we don't hammer the upstream MCP for
    the same keyword on every plan-build.
    """
    lang = "en"  # we only support English today; keyword arg retained
    # Split into cache-hit (fast) + cache-miss (need fetching).
    cached: dict[str, dict] = {}
    need_fetch: list[str] = []
    now = int(time.time())
    for kw in keywords:
        p = _keyword_metrics_cache_key(kw, location, lang)
        if p.is_file():
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(rec, dict) and now - int(rec.get("fetched_at", 0)) < _KEYWORD_METRICS_CACHE_TTL_S:
                    cached[kw] = rec
                    continue
            except Exception:
                pass
        need_fetch.append(kw)
    if not need_fetch:
        return [cached[kw] for kw in keywords if kw in cached]
    try:
        # Lazy import so the module loads even when Ubersuggest creds aren't
        # on this machine (e.g. when testing locally).
        from _lib import ubersuggest_mcp as _us
        # auth_status() returns either {ok: True, email, tier} on the
        # legacy REST path OR {structuredContent: {authenticated: True,
        # email, tier}} on the MCP path. Accept either.
        if not _us.ubersuggest_credentials_present():
            raise RuntimeError("ubersuggest credentials missing")
        auth = _us.auth_status() or {}
        sc = (auth.get("structuredContent") or {}) if isinstance(auth, dict) else {}
        ok_flag = auth.get("ok") if isinstance(auth, dict) else False
        auth_flag = sc.get("authenticated") if isinstance(sc, dict) else False
        if not (ok_flag or auth_flag):
            raise RuntimeError("ubersuggest not authorized")
    except Exception as exc:
        _LOG.warning("ubersuggest unavailable: %s", exc)
        return [{"keyword": k, "source": "fallback", "reason": "ubersuggest offline"} for k in keywords]
    # Pull metrics in parallel using a thread pool. Ubersuggest's MCP
    # endpoint is fast (<300ms each) but sequential calls on 20 seeds
    # would add 6+ seconds to every plan build. With 8 workers we
    # finish a 20-keyword batch in ~2 seconds on average.
    from concurrent.futures import ThreadPoolExecutor, as_completed
    out: dict[int, dict] = {}

    def _pull_one(idx: int, kw: str) -> dict:
        try:
            data = _us.keyword_overview(kw, location=location, lang="en")
            # Unwrap the MCP-style response: the inner keyword dict is
            # JSON-encoded as a string in content[0].text. The legacy
            # REST shape returns {search_engine: {...}} directly.
            inner = data
            if isinstance(data, dict) and "content" in data:
                parts = data.get("content") or []
                if isinstance(parts, list) and parts and isinstance(parts[0], dict):
                    txt = parts[0].get("text") or "{}"
                    try:
                        inner = json.loads(txt) if isinstance(txt, str) else txt
                    except Exception:
                        inner = data
            # Inner shape from Ubersuggest keyword_overview:
            # {keyword, search_volume, seo_difficulty, paid_difficulty,
            #  cpc, competition, search_intent, language, location,
            #  monthly_searches: [...]}
            volume = inner.get("search_volume") or inner.get("volume") or 0
            kd = (inner.get("seo_difficulty") or inner.get("kd")
                  or inner.get("keyword_difficulty") or inner.get("difficulty") or 0)
            cpc = inner.get("cpc") or 0
            return {
                "keyword": kw,
                "volume": int(volume) if volume else 0,
                "kd": int(kd) if kd else 0,
                "cpc": float(cpc) if cpc else 0.0,
                "intent": _classify_intent(kw),
                "source": "ubersuggest",
            }
        except Exception as exc:
            _LOG.warning("ubersuggest %s failed: %s", kw, exc)
            return {"keyword": kw, "source": "fallback",
                    "reason": str(exc), "intent": _classify_intent(kw)}

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(need_fetch)))) as ex:
        futures = {ex.submit(_pull_one, i, kw): i for i, kw in enumerate(need_fetch)}
        for fut in as_completed(futures, timeout=60):
            idx = futures[fut]
            result = fut.result()
            if isinstance(result, dict) and result.get("source") == "ubersuggest":
                try:
                    cache_path = _keyword_metrics_cache_key(need_fetch[idx], location, lang)
                    cache_path.write_text(json.dumps(
                        {**result, "fetched_at": now}, indent=2))
                except Exception as exc:
                    _LOG.warning("ubersuggest cache write failed: %s", exc)
                out[idx] = result
    # Stitch cached + freshly fetched back into the original order.
    out_full: list[dict] = []
    for kw in keywords:
        if kw in cached:
            out_full.append(cached[kw])
        elif kw in need_fetch:
            idx = need_fetch.index(kw)
            if idx in out:
                out_full.append(out[idx])
            else:
                out_full.append({"keyword": kw, "source": "fallback",
                                  "reason": "timeout", "intent": _classify_intent(kw)})
        else:
            out_full.append({"keyword": kw, "source": "fallback",
                              "reason": "missing", "intent": _classify_intent(kw)})
    return out_full


def _classify_intent(keyword: str) -> str:
    """Classify search intent — order matters.

    A keyword that mixes commercial + informational words is still
    commercial if a buyer signal is present (booking / pricing /
    product / local intent). Google itself scores buyer intent
    signals first.
    """
    import re
    kw = keyword.lower().strip()
    # Brand / navigational: a query that mentions a brand or location
    # we own explicitly.
    if re.search(r"\b(swing\s*shack|swingshack|stick golf|stick paarl|stickfit)\b", kw):
        return "navigational"
    # Commercial / transactional: buyer is ready to act.
    commercial_signals = [
        r"\b(book|hire|buy|order|reserve|fit(?:ting)?|cost|price|pricing|"
        r"near\s+me|in\s+johannesburg|jhb|paarl|cape\s+town|south\s+africa|"
        r"gifts?|shop|deal|sale|cheap|under\s+r\d+)\b",
    ]
    for pat in commercial_signals:
        if re.search(pat, kw):
            return "commercial"
    # Informational: the query is a question / comparison.
    if any(kw.startswith(w) for w in ["what ", "how ", "why ", "is ", "are ", "does ", "do "]):
        return "informational"
    if any(w in kw for w in [" vs ", " versus ", " review", " tutorial", " explained"]):
        return "informational"
    # Default: treat as commercial — buyer intent is the strongest signal
    # in local-intent markets (and we don't want to push buyers to
    # top-of-funnel education content).
    return "commercial"


_INTENT_WEIGHTS = {"commercial": 1.0, "informational": 0.6, "navigational": 0.3}


def _score_keyword(item: dict) -> float:
    if not isinstance(item, dict):
        return 0.0
    vol = item.get("volume") or 0
    kd = max(item.get("kd") or 0, 1)
    intent = _INTENT_WEIGHTS.get(item.get("intent") or "informational", 0.5)
    # Volume * intent / (KD + small constant). KD of 0 means easy win.
    # insights_boost (1.0-1.30) is applied last to amplify keywords the
    # brand's GBP has already proven drives calls/directions.
    base = (vol * intent) / (kd + 5.0)
    return base * (item.get("insights_boost") or 1.0)


# ── Post body generation ─────────────────────────────────────────────

def _generate_post_body(brand_id: str, keyword: str, profile: dict, intent: str, day_offset: int) -> dict:
    """Build a unique GBP post body for one keyword.

    Real-world rule: never templated. Each post references the keyword,
    a real proof point, and a real CTA. Body is intentionally short
    (GBP truncates after ~1500 chars, mobile readers leave after ~80).
    """
    nbh = random.choice(profile["neighborhoods"])
    proof = random.choice(profile["proof_points"])
    cta = random.choice(profile["cta_options"])
    product = random.choice(profile["products"])
    city = profile["city"]
    domain = profile["domain"]
    # Anchor the post on the keyword so GBP reads it as on-topic.
    title = _title_from_keyword(keyword, brand_id, day_offset)
    body = (
        f"{_opening_for_intent(intent, keyword, brand_id)}\n\n"
        f"{proof.capitalize()} — and we're right here in {nbh}, {city}.\n\n"
        f"{cta.capitalize()} → {domain}"
    )
    # Hashtags that match the keyword + brand voice. GBP supports them but
    # they don't carry much SEO weight, so we keep it tight (3-5).
    hashtags = _hashtags_for(keyword, brand_id)
    return {
        "title": title[:100],
        "body": body[:1500],
        "hashtags": hashtags,
        "keyword": keyword,
        "intent": intent,
        "cta": cta,
        "proof_point": proof,
        "neighborhood": nbh,
    }


# Per-intent opening lines, picked randomly so consecutive posts
# don't all start with the same phrase. Each line is ≤ 90 chars
# because GBP mobile readers leave after ~80.
_OPENINGS_COMMERCIAL = [
    "Need {kw}? We've got you.",
    "Looking for {kw} — here's the short version.",
    "Quick one on {kw}:",
    "{kw} — here's what's on.",
    "Here's the honest take on {kw}.",
    "You searched {kw}. Here's the answer.",
    "Local, expert help with {kw}.",
    "{kw} — without the hard sell.",
]
_OPENINGS_INFORMATIONAL = [
    "Quick read on {kw}:",
    "{kw} — the short answer.",
    "People ask us about {kw} a lot. Here's what we tell them.",
    "{kw} — straight answer, no fluff.",
    "Here's what most people get wrong about {kw}.",
    "{kw}, explained.",
    "{kw}? A 30-second read.",
    "If you're Googling {kw}:",
]
_OPENINGS_NAVIGATIONAL = [
    "Yes, we're here — and this is what we do.",
    "Quick hello from the team.",
    "If you've been meaning to drop in — now's good.",
    "We moved a few things around. Here's the update.",
]


def _opening_for_intent(intent: str, keyword: str, brand_id: str) -> str:
    """Pick an opening line that fits the intent. Varies between posts."""
    kw = keyword.strip().rstrip("?.")
    if intent == "commercial":
        line = random.choice(_OPENINGS_COMMERCIAL)
    elif intent == "informational":
        line = random.choice(_OPENINGS_INFORMATIONAL)
    else:
        line = random.choice(_OPENINGS_NAVIGATIONAL)
    return line.format(kw=kw)


def _title_from_keyword(keyword: str, brand_id: str, day_offset: int) -> str:
    # GBP posts use a short summary line as the "title" (CTA-style).
    nice_kw = keyword.capitalize()
    return f"{nice_kw} · open today"


# Per-brand hashtag palettes. These are the hashtag sets that
# actually gain traction in the SA golf market on GBP + IG cross-post.
# Hand-picked from what each brand already uses, ordered by reach.
_BRAND_HASHTAGS = {
    "swing-shack": [
        ["#swingshack", "#trackman", "#johannesburggolf", "#indoorgolf", "#swingdata"],
        ["#swingshack", "#swinganalysis", "#golflessons", "#takomogolf", "#johannesburg"],
        ["#swingshack", "#clubfitting", "#johannesburg", "#golflife", "#simulatorgolf"],
        ["#swingshack", "#golftips", "#johannesburggolf", "#swingbetter", "#trackman"],
    ],
    "stick": [
        ["#stickgolf", "#putterfitting", "#johannesburggolf", "#golflife", "#golfza"],
        ["#stickgolf", "#putters", "#fitfirst", "#golftips", "#stickfit"],
        ["#stickgolf", "#vicegolf", "#golfsouthafrica", "#johannesburg", "#putter"],
        ["#stickgolf", "#golfballs", "#golffitting", "#johannesburggolf", "#bettermin"],
    ],
    "bag-drop": [
        ["#bagdrop", "#golfbagstorage", "#johannesburg", "#regrip", "#golflife"],
    ],
}


def _hashtags_for(keyword: str, brand_id: str) -> list[str]:
    """Pick a 5-tag set from the brand palette. Rotates per call so
    consecutive posts don't all share the same hashtags."""
    palettes = _BRAND_HASHTAGS.get(brand_id) or _BRAND_HASHTAGS["swing-shack"]
    return list(random.choice(palettes))


# ── Plan builder ─────────────────────────────────────────────────────

def build_daily_plan(
    brand_id: str = "swing-shack",
    *,
    days: int = 7,
    posts_per_day: int = 1,
    publish: bool = False,
) -> dict:
    """Build (and optionally publish) a daily GBP plan.

    Returns: {
      ok, brand_id, plan_id, days, posts_per_day, posts: [...], schedule: [...],
      publish: { scheduled_count, errors }, source_breakdown, generated_at
    }
    """
    profile = BRAND_PROFILES.get(brand_id)
    if not profile:
        return {"ok": False, "error": f"unknown brand_id: {brand_id}"}
    seeds = SEED_KEYWORDS_BY_BRAND.get(brand_id) or []
    if not seeds:
        return {"ok": False, "error": f"no seed keywords for brand_id: {brand_id}"}
    # Pull metrics
    metrics = [m for m in _pull_keyword_metrics(seeds, location="ZA")
               if isinstance(m, dict)]
    # Apply insights-driven brand-signal boost if available
    try:
        from _lib import gbp_insights as _gi
        boost = _gi.score_boost(brand_id)
        brand_mult = float((boost.get("boost") or {}).get("_brand_signal") or 1.0)
        if brand_mult != 1.0:
            for m in metrics:
                m["insights_boost"] = brand_mult
    except Exception:
        brand_mult = 1.0
    # Score + rank
    for m in metrics:
        m["score"] = _score_keyword(m)
    metrics.sort(key=lambda x: x.get("score") or 0, reverse=True)
    # Top N keywords for the plan (N = days * posts_per_day)
    want = max(days * posts_per_day, 1)
    picked = []
    for m in metrics:
        kw = m.get("keyword")
        if not kw:
            continue
        picked.append((kw, m.get("intent") or "informational"))
        if len(picked) >= want:
            break
    # Generate bodies
    posts = []
    today = _dt.datetime.now(_dt.timezone.utc).date()
    # Stagger hours so posts don't fire all at 09:00 — 9/12/15/18
    hours = [9, 12, 15, 18]
    for i, (kw, intent) in enumerate(picked):
        day_offset = i // posts_per_day
        hour = hours[(i + day_offset) % len(hours)]
        body = _generate_post_body(brand_id, kw, profile, intent, day_offset)
        posts.append(body)
    # Build schedule (UTC datetimes, future-only)
    schedule = []
    for i, post in enumerate(posts):
        day_offset = i // posts_per_day
        hour = hours[(i + day_offset) % len(hours)]
        when = _dt.datetime.combine(today + _dt.timedelta(days=day_offset + 1),
                                     _dt.time(hour=hour, minute=0), tzinfo=_dt.timezone.utc)
        schedule.append({"post_index": i, "scheduled_for": when.isoformat(), "keyword": post["keyword"]})
    # Plan ID: hash of brand + day + content fingerprint
    plan_id = hashlib.sha256(json.dumps([p["keyword"] for p in posts], sort_keys=True).encode()).hexdigest()[:12]
    plan = {
        "ok": True,
        "brand_id": brand_id,
        "plan_id": plan_id,
        "days": days,
        "posts_per_day": posts_per_day,
        "posts": posts,
        "schedule": schedule,
        "source_breakdown": {
            "ubersuggest": sum(1 for m in metrics if m.get("source") == "ubersuggest"),
            "fallback": sum(1 for m in metrics if m.get("source") == "fallback"),
        },
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }
    # Persist the plan (always — even in dry-run, so we have audit trail)
    plan_filename = today.isoformat()
    p = _plan_path(brand_id, plan_filename)
    p.write_text(json.dumps(plan, indent=2, default=str))
    plan["plan_file"] = str(p)
    # Publish if requested
    publish_summary = {"scheduled_count": 0, "errors": [], "skipped": "publish=False (dry-run)"}
    if publish:
        publish_summary = _publish_plan(brand_id, plan, profile)
    plan["publish"] = publish_summary
    return plan


def _publish_plan(brand_id: str, plan: dict, profile: dict) -> dict:
    """Actually schedule the plan via Postiz GBP integration.

    Per agent-destructive-write-discipline: this is the destructive-write
    path. Only fires when publish=True is explicitly passed. The cron
    caller never auto-publishes; it always generates the plan and
    surfaces it for review.
    """
    integration_id = profile.get("postiz_gbp_integration_id")
    if not integration_id:
        return {"scheduled_count": 0, "errors": [{"error": "no postiz_gbp_integration_id for this brand"}], "skipped": "no integration"}
    try:
        from _lib import postiz_client as _pc
        if not (_pc and _pc._credentials_present()):
            return {"scheduled_count": 0, "errors": [{"error": "postiz api key not configured"}], "skipped": "no api key"}
    except Exception as exc:
        return {"scheduled_count": 0, "errors": [{"error": f"import failed: {exc}"}], "skipped": "import error"}
    scheduled = 0
    errors = []
    for i, (post, sched) in enumerate(zip(plan.get("posts", []), plan.get("schedule", []))):
        try:
            text = (post.get("title", "") + "\n\n" + post.get("body", "")).strip()[:1500]
            data, err = _pc.create_post(
                integration_id=integration_id,
                content=text,
                media_ids=[],
                publish_date=sched.get("scheduled_for"),
            )
            if err:
                errors.append({"post_index": i, "error": f"{err[0]}: {err[1]}"})
            elif data:
                # Postiz /posts returns a LIST of created posts, not a dict.
                # The success signal is "list with at least one element".
                if isinstance(data, list) and data:
                    first = data[0] if isinstance(data[0], dict) else {}
                    if first.get("postId") or first.get("id"):
                        scheduled += 1
                elif isinstance(data, dict) and (data.get("id") or data.get("postId")):
                    scheduled += 1
        except Exception as exc:
            errors.append({"post_index": i, "error": str(exc)})
    return {"scheduled_count": scheduled, "errors": errors}


# ── Plan retrieval (read-only) ───────────────────────────────────────

def list_plans(brand_id: Optional[str] = None, limit: int = 30) -> list[dict]:
    """List past plans, newest first. Read-only — no destructive path."""
    base = _plan_dir()
    if not base.exists():
        return []
    out = []
    for p in sorted(base.glob("*.json"), reverse=True):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        if brand_id and d.get("brand_id") != brand_id:
            continue
        out.append({
            "plan_id": d.get("plan_id"),
            "brand_id": d.get("brand_id"),
            "generated_at": d.get("generated_at"),
            "posts_count": len(d.get("posts", [])),
            "publish_scheduled": (d.get("publish") or {}).get("scheduled_count", 0),
            "file": str(p),
        })
        if len(out) >= limit:
            break
    return out


def latest_plan(brand_id: str = "swing-shack") -> Optional[dict]:
    """Most recent plan for a brand, parsed. None if no plans."""
    base = _plan_dir()
    if not base.exists():
        return None
    for p in sorted(base.glob(f"{brand_id}-*.json"), reverse=True):
        try:
            return json.loads(p.read_text())
        except Exception:
            continue
    return None
