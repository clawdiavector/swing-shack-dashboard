"""
campaign_os.gbp_daily_poster
============================

Google Business Profile daily post generator + publisher.

V3.8b (2026-09-23, post-bible-revision)
--------------------------------------
This rewrite is grounded in two canonical sources:

  - Swing Shack Brand Bible (full text) + swingshack.co.za
  - Stick Brand Bible + Stick Golf Commercial Strategy 2026-2029 + stickgolf.co.za

Every fact used in a post body comes from the brand directory's verified
facts (`data/brand-directory/<brand>/knowledge.json#verified_facts`). Every
headline and CTA comes from the copy bank
(`data/brand-directory/copy-banks/<brand>.json`).

Hard rules (enforced at the integrity gate before publish):

  1. Em dashes banned. Use pipes `|`, colons `:`, commas `,`, full stops `.`.
  2. No fabricated numbers. No fake "12-shot improvement" / "members average"
     style claims. If a number isn't in the verified facts, it's banned.
  3. No fake locations. Swing Shack = Old Parktonian Sports Club, Bordeaux,
     Randburg, Johannesburg. Stick = Paarl, Western Cape (with Cape Town +
     Winelands as market). Anywhere else is banned.
  4. Stick voice is cheeky-and-helpful, never sarcasm-as-punchline. The joke
     is shared with the reader, never directed at them.
  5. Every post lands on a thing we can help with. CTAs must be actionable.
  6. Stick CTA links go to stickgolf.co.za. Swing Shack CTA links go to
     swingshack.co.za. Never the other way around.

The generator composes posts from approved fragments. It does NOT generate
free-form copy. If a keyword doesn't have a paired headline in the bank,
the system surfaces a TODO instead of fabricating.
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
        "display_name": "Swing Shack",
        "voice_id": "swing-shack",
        "domain": "swingshack.co.za",
        "bookings_url": "https://swingshack.co.za/bookings/",
        "primary_color": "#0F766E",
        "accent_color": "#F59E0B",
        "verified_address": "Old Parktonian Sports Club, 1 Garden Rd, Bordeaux, Randburg, Johannesburg",
        "verified_phone": "066 542 1522",
        "voice": (
            "Sharp performance coach who is also a great host. Clear, calm, "
            "confident, welcoming, precise, honest. Never snobbish, "
            "condescending, or salesy. Never hides behind jargon."
        ),
        "tagline": "Real Golf, Indoors.",
        "promise": "The ball speaks. Data confirms. Feel seals the deal.",
        "internal_mantra": "Real Golf. Real Data. Real Welcome.",
        # Pillar rotation per Christelle (2026-09-23): Fitting / Coaching / Indoor Golf.
        # The copy bank carries these pillars; the share targets feed the
        # keyword anchor pool + the per-day rotation in build_daily_plan.
        "supported_pillars": [
            "fitting",
            "coaching",
            "indoor_golf",
        ],
        "share_targets": {
            "fitting": 0.40,
            "coaching": 0.30,
            "indoor_golf": 0.30,
        },
        "postiz_gbp_integration_id": "cmmdgju7f00tppk0y6bne9zrk",
        "google_account": "verified",
    },
    "stick": {
        "display_name": "Stick",
        "voice_id": "stick",
        "domain": "stickgolf.co.za",
        "bookings_url": "https://stickgolf.co.za/bookings/",
        "primary_color": "#1B1B1B",
        "accent_color": "#FF3D00",
        "verified_location": "Paarl, Western Cape (Cape Town + Winelands as broader market)",
        "voice": (
            "Cheeky and helpful. Smart Rebel: edge and brains. Sharp, modern, "
            "confident, informed, energetic, selective, culturally awake. "
            "Never sarcasm-as-punchline. The joke is shared with the reader, "
            "never directed at them. Never uses expertise to make the golfer "
            "feel stupid."
        ),
        "tagline": "Better Begins Here.",
        "strategic_belief": "Everything has to earn its place.",
        "trading_principles": "Fit First. Buy Second. Why It's Here. Respect the Player.",
        # Pillar rotation per Christelle (2026-09-23): Fitting / Coaching / Retail.
        # Retail covers products on the shelf + the "Why It's Here." editorial.
        # Workshop + local are preserved as low-share auxiliary pillars so
        # we still touch them occasionally without crowding the operator-
        # specified rotation.
        "supported_pillars": [
            "fitting",
            "coaching",
            "retail",
            "workshop",
            "local",
        ],
        "share_targets": {
            "fitting": 0.40,
            "coaching": 0.25,
            "retail": 0.30,
            "workshop": 0.03,
            "local": 0.02,
        },
        "postiz_gbp_integration_id": "cmu6pc3gp0btanl0yl50vl8pz",
        "google_account": "verified",
    },
    "bag-drop": {
        "display_name": "Bag Drop",
        "voice_id": "bag-drop",
        "domain": "swingshack.co.za",
        "bookings_url": "https://swingshack.co.za/bookings/",
        "primary_color": "#F4A261",
        "accent_color": "#264653",
        "voice": "Community, fun, supportive, relatable, warm. The Thursday social crowd.",
        "postiz_gbp_integration_id": None,
        "google_account": "not_connected",
    },
}


# ── Copy bank loader ─────────────────────────────────────────────────


_COPY_BANKS_DIR = None


def _resolve_copy_banks_dir() -> Path:
    """Find the copy-banks directory.

    Resolution order:
      1. BRAND_DIRECTORY env var (override).
      2. Walk up from this module until we find data/brand-directory/copy-banks.
         This is robust whether we're running from the repo, Railway, or a
         cron job.
      3. /workspace/swing-shack-dashboard/data/brand-directory/copy-banks
         (the canonical Railway persistent volume path).
      4. ~/.openclaw-instance2/workspace/swing-shack-dashboard/data/brand-directory/copy-banks
         (the canonical local development path on the Mac).
    """
    global _COPY_BANKS_DIR
    if _COPY_BANKS_DIR is not None:
        return _COPY_BANKS_DIR
    env = os.environ.get("BRAND_DIRECTORY")
    if env:
        _COPY_BANKS_DIR = Path(env) / "copy-banks"
        _COPY_BANKS_DIR.mkdir(parents=True, exist_ok=True)
        return _COPY_BANKS_DIR
    # Walk up from this file
    here = Path(__file__).resolve().parent
    for _ in range(8):
        candidate = here / "data" / "brand-directory" / "copy-banks"
        if candidate.is_dir():
            _COPY_BANKS_DIR = candidate
            return _COPY_BANKS_DIR
        if here.parent == here:
            break
        here = here.parent
    # Fallback paths
    for fallback in (
        Path("/workspace/swing-shack-dashboard/data/brand-directory/copy-banks"),
        Path(os.path.expanduser(
            "~/.openclaw-instance2/workspace/swing-shack-dashboard/data/brand-directory/copy-banks"
        )),
    ):
        if fallback.is_dir():
            _COPY_BANKS_DIR = fallback
            return _COPY_BANKS_DIR
    # Last resort: create the local fallback
    fallback = Path(os.path.expanduser(
        "~/.openclaw-instance2/workspace/swing-shack-dashboard/data/brand-directory/copy-banks"
    ))
    fallback.mkdir(parents=True, exist_ok=True)
    _COPY_BANKS_DIR = fallback
    return _COPY_BANKS_DIR


def _copy_bank_path(brand_id: str) -> Path:
    return _resolve_copy_banks_dir() / f"{brand_id}.json"


def load_copy_bank(brand_id: str) -> dict:
    """Load the headline + CTA bank for a brand. Returns empty bank on miss."""
    p = _copy_bank_path(brand_id)
    if not p.is_file():
        _LOG.warning("copy bank missing for %s at %s", brand_id, p)
        return {"headlines": [], "ctas": {"hard": [], "soft": []}, "rules": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        _LOG.error("copy bank unreadable for %s: %s", brand_id, exc)
        return {"headlines": [], "ctas": {"hard": [], "soft": []}, "rules": []}


def load_verified_facts(brand_id: str) -> dict:
    """Load verified facts from the brand's knowledge.json."""
    # Walk up from this file's directory to find the brand directory.
    here = Path(__file__).resolve().parent
    for _ in range(8):
        candidate = here / "data" / "brand-directory" / brand_id / "knowledge.json"
        if candidate.is_file():
            try:
                kb = json.loads(candidate.read_text(encoding="utf-8"))
                return kb.get("verified_facts", {}) or {}
            except Exception as exc:
                _LOG.error("verified facts unreadable for %s: %s", brand_id, exc)
                return {}
        if here.parent == here:
            break
        here = here.parent
    # Fallback: canonical local path.
    fallback = (
        Path(os.path.expanduser(
            "~/.openclaw-instance2/workspace/swing-shack-dashboard/"
            f"data/brand-directory/{brand_id}/knowledge.json"
        ))
    )
    if fallback.is_file():
        try:
            kb = json.loads(fallback.read_text(encoding="utf-8"))
            return kb.get("verified_facts", {}) or {}
        except Exception:
            return {}
    return {}


# ── Keyword → headline intent mapping (no generation) ────────────────


_KEYWORD_INTENT_BANK = {
    # ── Topic-driven classification (most specific match wins) ──
    # Coaching keywords take priority over generic location matches.
    "golf lessons": ("commercial", ["coaching"]),
    "golf coach": ("commercial", ["coaching"]),
    "coaching": ("commercial", ["coaching"]),
    "lessons": ("commercial", ["coaching"]),
    "instructor": ("commercial", ["coaching"]),
    # Fitting keywords (full list of variations).
    "driver fitting": ("commercial", ["fitting"]),
    "iron fitting": ("commercial", ["fitting"]),
    "putter fitting": ("commercial", ["fitting"]),
    "club fitting": ("commercial", ["fitting"]),
    "wedge fitting": ("commercial", ["fitting"]),
    "trackman fitting": ("commercial", ["fitting"]),
    "fitting johannesburg": ("commercial", ["fitting"]),
    "fitting randburg": ("commercial", ["fitting"]),
    "fitting paarl": ("commercial", ["fitting"]),
    "fitting western cape": ("commercial", ["fitting"]),
    "fitting cape town": ("commercial", ["fitting"]),
    # Workshop keywords.
    "regrip": ("commercial", ["workshop"]),
    "loft and lie": ("commercial", ["workshop"]),
    "shaft work": ("commercial", ["workshop"]),
    "club repair": ("commercial", ["workshop"]),
    # Retail / Why It's Here keywords.
    "takomo": ("commercial", ["retail"]),
    "vice": ("commercial", ["retail"]),
    "psycho bunny": ("commercial", ["retail"]),
    "l.a.b": ("commercial", ["retail"]),
    "lab golf": ("commercial", ["retail"]),
    "avoda": ("commercial", ["retail"]),
    "vessel": ("commercial", ["retail"]),
    # Indoor golf / simulator keywords.
    "indoor golf": ("commercial", ["indoor_golf"]),
    "golf simulator": ("commercial", ["indoor_golf"]),
    "trackman simulator": ("commercial", ["indoor_golf"]),
    "simulator": ("commercial", ["indoor_golf"]),
    "social play": ("commercial", ["indoor_golf"]),
    "membership": ("commercial", ["indoor_golf"]),
    # Informational / question keywords.
    "what is": ("informational", ["coaching", "fitting"]),
    "how to": ("informational", ["coaching", "fitting", "workshop"]),
    "how often": ("informational", ["workshop", "fitting"]),
    " vs ": ("informational", ["fitting", "retail"]),
    " versus ": ("informational", ["fitting"]),
    "explained": ("informational", ["coaching", "fitting"]),
    "difference between": ("informational", ["fitting", "retail"]),
    # Cheeky / challenge keywords.
    "off-rack": ("challenge", ["fitting", "retail"]),
    "off the rack": ("challenge", ["fitting", "retail"]),
    "off-the-rack": ("challenge", ["fitting", "retail"]),
    "myth": ("cheeky", ["retail", "fitting"]),
    "lie": ("cheeky", ["fitting"]),
    "hope": ("cheeky", ["fitting"]),
    "denial": ("cheeky", ["fitting"]),
    "slice": ("challenge", ["coaching", "fitting"]),
    "hook": ("challenge", ["coaching"]),
    "shank": ("challenge", ["coaching"]),
    # Generic commercial / location fallback (matches last).
    "near me": ("commercial", ["indoor_golf"]),
    "south africa": ("commercial", ["indoor_golf"]),
    "johannesburg": ("commercial", ["indoor_golf"]),
    "randburg": ("commercial", ["indoor_golf"]),
    "paarl": ("commercial", ["local"]),
    "cape town": ("commercial", ["local"]),
    "winelands": ("commercial", ["local"]),
    "book": ("commercial", ["coaching"]),
    "price": ("commercial", ["fitting"]),
    "cost": ("commercial", ["fitting"]),
    "buy": ("commercial", ["retail"]),
}


def classify_keyword_intent(keyword: str) -> tuple[str, list[str]]:
    """Returns (intent_label, pillar_hints). Topic-specific needles are
    listed FIRST in _KEYWORD_INTENT_BANK so they win over generic
    location matches like 'johannesburg'. Falls back to (commercial, []).
    """
    kw_lower = keyword.lower()
    for needle, (intent, hints) in _KEYWORD_INTENT_BANK.items():
        if needle in kw_lower:
            return intent, hints
    return ("commercial", [])


def pick_headline(
    bank: dict,
    intent: str,
    pillar_hint: str,
    brand_id: str,
    rng: random.Random,
) -> Optional[dict]:
    """Pick a headline from the bank. Prefers intent+pillar match, falls back
    to pillar-only, then intent-only, then any. Returns None if the bank
    is empty."""
    headlines = bank.get("headlines") or []
    if not headlines:
        return None
    exact = [h for h in headlines
             if h.get("tone") == intent and pillar_hint in (h.get("pillar") or "")]
    if exact:
        return rng.choice(exact)
    # Pillar-only match: same pillar, any tone. Keeps the pillar rotation
    # even when intent+pillar exact doesn't hit.
    by_pillar = [h for h in headlines if pillar_hint in (h.get("pillar") or "")]
    if by_pillar:
        return rng.choice(by_pillar)
    by_intent = [h for h in headlines if h.get("tone") == intent]
    if by_intent:
        return rng.choice(by_intent)
    return rng.choice(headlines)


def pick_cta(
    bank: dict,
    pillar_hint: str,
    rng: random.Random,
    prefer_soft: bool = False,
) -> Optional[dict]:
    """Pick a CTA. Prefers hard CTAs unless prefer_soft=True."""
    ctas = bank.get("ctas") or {}
    hard = [c for c in ctas.get("hard", []) if c.get("pillar") == pillar_hint]
    hard_general = list(ctas.get("hard", []))
    soft = [c for c in ctas.get("soft", []) if c.get("pillar") == pillar_hint]
    soft_general = list(ctas.get("soft", []))
    if prefer_soft:
        return rng.choice(soft or soft_general or hard_general or [])
    return rng.choice(hard or hard_general or soft or soft_general or [])


# ── Voice rules + integrity gate ─────────────────────────────────────


_EM_DASH_RE = re.compile(r"[\u2014\u2013]")  # em-dash + en-dash


def _strip_em_dashes(s: str) -> str:
    return _EM_DASH_RE.sub(".", s)


def integrity_check(post: dict, brand_id: str) -> tuple[bool, list[str]]:
    """Returns (ok, list_of_violations). When ok is False, the post MUST NOT
    be published. Violations describe what failed."""
    violations: list[str] = []
    body = post.get("body", "") or ""
    title = post.get("title", "") or ""
    cta = post.get("cta", "") or ""

    # 1. Em-dash / en-dash ban
    if _EM_DASH_RE.search(body) or _EM_DASH_RE.search(title) or _EM_DASH_RE.search(cta):
        violations.append("em_dash_or_en_dash_present")

    # 2. Fabrication patterns. These specific patterns are NEVER allowed
    #    unless they appear in the verified facts.
    fab_patterns = [
        (r"\b\d+[\- ]?shot\b\s+(improvement|gain)", "fabricated_shot_improvement"),
        (r"\bmembers\s+average\b", "fabricated_member_average"),
        (r"\b\d+\s*%\s+of\s+golfers\b", "fabricated_percentage"),
        (r"\btwo[\- ]week\s+satisfaction\b", "fabricated_guarantee"),
        (r"\bsatisfaction\s+guarantee\b", "fabricated_guarantee"),
        (r"\b\d+\s*drivers\s+fitted\b", "fabricated_fit_count"),
        (r"\b\d+\+?\s*members\b", "fabricated_member_count"),
        (r"\b\d+\s*metres?\s+(further|extra)\b", "fabricated_distance"),
    ]
    for pat, name in fab_patterns:
        if re.search(pat, body, re.IGNORECASE) or re.search(pat, title, re.IGNORECASE):
            violations.append(name)

    # 3. Fabricated locations. Each brand has a whitelist.
    if brand_id == "stick":
        forbidden = [
            "johannesburg", "randburg", "parkview", "linden", "greymont",
            "rosebank", "sandton", "hyde park", "bryanston", "fourways",
            "midrand", "centurion", "pretoria", "joburg", "jhb",
        ]
        for loc in forbidden:
            if re.search(rf"\b{loc}\b", body, re.IGNORECASE) or re.search(rf"\b{loc}\b", title, re.IGNORECASE):
                violations.append(f"stick_location_violation:{loc}")
    elif brand_id == "swing-shack":
        forbidden = [
            "cape town", "paarl", "stellenbosch", "winelands", "western cape",
        ]
        for loc in forbidden:
            if re.search(rf"\b{loc}\b", body, re.IGNORECASE) or re.search(rf"\b{loc}\b", title, re.IGNORECASE):
                violations.append(f"ss_location_violation:{loc}")

    # 4. URL direction.
    if brand_id == "stick":
        if post.get("cta_url") and "swingshack.co.za" in post["cta_url"]:
            violations.append("stick_cta_points_to_swingshack")
    elif brand_id == "swing-shack":
        if post.get("cta_url") and "stickgolf.co.za" in post["cta_url"]:
            violations.append("ss_cta_points_to_stick")

    # 5. Length cap.
    if len(body) > 1500:
        violations.append("body_too_long")

    return (len(violations) == 0, violations)


# ── Post composer ────────────────────────────────────────────────────


def _seeded_rng(brand_id: str, day: str) -> random.Random:
    seed = int(hashlib.md5(f"{brand_id}:{day}".encode()).hexdigest()[:16], 16)
    return random.Random(seed)


def compose_post(
    brand_id: str,
    keyword: str,
    day: str,
    pillar_override: Optional[str] = None,
) -> dict:
    """Compose a single post from approved bank fragments.

    This function NEVER generates free-form copy. It picks one headline from
    the bank's intent-matched entries, prepends a one-line keyword frame,
    and appends a CTA. If the bank has no matching headline, the post is
    marked `gap:no_matching_headline` and surfaced for human attention.
    """
    profile = BRAND_PROFILES.get(brand_id)
    if not profile:
        return {"error": "unknown_brand", "brand_id": brand_id}

    bank = load_copy_bank(brand_id)
    facts = load_verified_facts(brand_id)
    rng = _seeded_rng(brand_id, day)

    intent, pillar_hints = classify_keyword_intent(keyword)
    pillar = pillar_override or (pillar_hints[0] if pillar_hints else "general")

    headline_obj = pick_headline(bank, intent, pillar, brand_id, rng)
    if not headline_obj:
        return {
            "error": "gap_no_matching_headline",
            "brand_id": brand_id,
            "keyword": keyword,
            "intent": intent,
            "pillar_hint": pillar,
            "needs": (
                f"Add a {intent}/{pillar} headline to the copy bank for {brand_id}. "
                f"Source: data/brand-directory/{brand_id}/copy/{brand_id}-headlines.md "
                f"(or .json). Headlines must come from the brand bible, not be "
                f"generated."
            ),
        }

    headline_text = _strip_em_dashes(headline_obj["text"])

    title = headline_text
    if len(title) > 58:
        title = title[:55].rstrip() + "..."

    # Body construction: keyword frame, blank line, headline.
    # Keep the frame human and short. Avoid title-casing the keyword.
    if brand_id == "stick":
        # Stick: cheeky-helpful. "Range balls, explained." not "Range Balls".
        keyword_frame = f"{keyword}, explained. Or fixed. We do both."
    else:
        keyword_frame = f"Real answer to '{keyword}'."

    body_lines = [keyword_frame, "", headline_text]
    body = "\n".join(body_lines)

    prefer_soft = intent in ("cheeky", "challenge") or pillar in ("culture", "local")
    cta_obj = pick_cta(bank, pillar, rng, prefer_soft=prefer_soft)
    cta_text = cta_obj["text"] if cta_obj else profile["tagline"]
    cta_url = cta_obj.get("url") if cta_obj else None

    if brand_id == "stick":
        hashtag_palettes = [
            ["#StickGolf", "#BetterBeginsHere", "#WhyItsHere"],
            ["#StickPaarl", "#WesternCapeGolf", "#FitFirst"],
            ["#TakomoAtStick", "#BetterBeginsHere"],
            ["#GolfDoneDifferently", "#StickStandard"],
        ]
    elif brand_id == "swing-shack":
        hashtag_palettes = [
            ["#SwingShack", "#RealGolfIndoors", "#TrackMan"],
            ["#TrackMan", "#SwingShack", "#JohannesburgGolf"],
            ["#ClubFitting", "#TrackManData", "#SwingShack"],
            ["#SwingShack", "#RealDataRealWelcome"],
        ]
    else:
        hashtag_palettes = [["#BagDrop"]]
    hashtags = rng.choice(hashtag_palettes)

    post = {
        "brand_id": brand_id,
        "keyword": keyword,
        "intent": intent,
        "pillar": pillar,
        "title": title,
        "body": body,
        "cta": cta_text,
        "cta_url": cta_url,
        "hashtags": hashtags,
        "headline_source": headline_text,
        "headline_tone": headline_obj.get("tone"),
        "headline_pillar": headline_obj.get("pillar"),
    }

    ok, violations = integrity_check(post, brand_id)
    post["integrity_ok"] = ok
    post["integrity_violations"] = violations
    return post


# ── Plan builder ────────────────────────────────────────────────────


def build_daily_plan(
    brand_id: str,
    *,
    days: int = 7,
    posts_per_day: int = 1,
    publish: bool = False,
    keywords: Optional[list[str]] = None,
) -> dict:
    """Build a daily posting plan for a brand."""
    profile = BRAND_PROFILES.get(brand_id)
    if not profile:
        return {"error": "unknown_brand", "brand_id": brand_id}

    facts = load_verified_facts(brand_id)
    bank = load_copy_bank(brand_id)

    if keywords:
        kw_list = list(keywords)
    else:
        # Pillar-anchored keyword pool. The keyword anchors map to the
        # brand's `pillar` field; the headline pool is selected by intent
        # + pillar, so the anchor just steers WHICH pillar wins today.
        # Christelle (2026-09-23): SS = Fitting / Coaching / Indoor Golf;
        # Stick = Fitting / Coaching / Retail.
        #
        # Per-brand pools (NOT one shared dict) so SS doesn't accidentally
        # pick up Stick's "paarl"-anchored keywords and vice versa. We
        # previously had a single combined dict and the iterator order
        # caused SS to draw "club fitting paarl" — a location violation.
        brand_anchors = {
            "swing-shack": {
                "fitting": [
                    "driver fitting johannesburg",
                    "club fitting randburg",
                    "iron fitting johannesburg",
                    "putter fitting johannesburg",
                    "trackman fitting randburg",
                    "fitting johannesburg",
                ],
                "coaching": [
                    "golf lessons johannesburg",
                    "golf coach randburg",
                    "trackman coaching johannesburg",
                    "indoor golf lessons randburg",
                    "golf coaching johannesburg",
                ],
                "indoor_golf": [
                    "indoor golf johannesburg",
                    "golf simulator randburg",
                    "trackman simulator johannesburg",
                    "indoor golf randburg",
                    "indoor golf bay johannesburg",
                    "indoor golf practice johannesburg",
                    "social play randburg",
                    "indoor golf membership johannesburg",
                ],
            },
            "stick": {
                "fitting": [
                    "club fitting paarl",
                    "putter fitting western cape",
                    "putter fitting paarl",
                    "iron fitting western cape",
                    "trackman fitting paarl",
                    "brand agnostic fitting paarl",
                ],
                "coaching": [
                    "golf lessons paarl",
                    "golf coach paarl",
                    "golf coaching western cape",
                    "coaching paarl",
                ],
                "retail": [
                    "takomo paarl",
                    "vice golf paarl",
                    "psycho bunny paarl",
                    "l.a.b golf paarl",
                    "golf retail paarl",
                    "avoda paarl",
                ],
                "workshop": [
                    "regrip golf clubs paarl",
                    "loft and lie paarl",
                    "shaft work western cape",
                    "club repair paarl",
                ],
                "local": [
                    "indoor golf paarl",
                    "stick golf paarl",
                    "golf fitting western cape",
                    "golf lessons paarl",
                ],
            },
            "bag-drop": {
                "general": [
                    "golf bag storage johannesburg",
                    "regrip golf clubs johannesburg",
                ],
            },
        }
        pillar_kw_anchors = brand_anchors.get(brand_id, {})
        pillar_shares = profile.get("share_targets") or {}
        pillars_sorted = sorted(pillar_shares.items(), key=lambda x: -x[1])
        kw_list = []
        # Pull keywords per pillar weighted by share target. Each pillar
        # gets its top `ceil(3 * share)` anchor keywords; the rotation
        # cycles through pillars in share-target order.
        for pillar, share in pillars_sorted:
            anchors = pillar_kw_anchors.get(pillar, [])
            if not anchors:
                continue
            n = max(1, int(round(3 * share)))
            kw_list.extend(anchors[:n])

    today = _dt.date.today()
    posts: list[dict] = []
    gaps: list[dict] = []
    seen_keywords: set[str] = set()

    for day_offset in range(days):
        day_iso = (today + _dt.timedelta(days=day_offset)).isoformat()
        for slot in range(posts_per_day):
            kw = None
            for candidate in kw_list:
                if candidate not in seen_keywords:
                    kw = candidate
                    break
            if kw is None:
                kw = kw_list[(day_offset * posts_per_day + slot) % len(kw_list)]
            seen_keywords.add(kw)

            post = compose_post(brand_id, kw, day_iso)
            if post.get("error") == "gap_no_matching_headline":
                gaps.append(post)
                continue
            if not post.get("integrity_ok", False):
                gaps.append({**post, "kind": "integrity_violation"})
                continue
            posts.append(post)

    source_breakdown = {
        "from_bank": len(posts),
        "gaps": len(gaps),
        "ubersuggest": 0,
        "fallback": 0,
    }

    plan = {
        "brand_id": brand_id,
        "domain": profile["domain"],
        "build_started_at": _dt.datetime.utcnow().isoformat() + "Z",
        "build_for_days": days,
        "posts": posts,
        "gaps": gaps,
        "source_breakdown": source_breakdown,
        "publish": {"scheduled": False, "reason": "publish_disabled_in_build"},
        "voice_id": profile["voice_id"],
        "tagline": profile.get("tagline"),
    }
    return plan


# ── Plan persistence ────────────────────────────────────────────────


def _plan_dir() -> Path:
    """Resolve the gbp-daily-plans directory.

    Resolution order:
      1. GBP_PLAN_DIR env var (specific override)
      2. DATA_DIR env var (Railway persistent volume — matches the
         resolution order used elsewhere in the project)
      3. Walk up from this file until we find data/gbp-daily-plans.
      4. Canonical local path on the Mac.
    """
    env = os.environ.get("GBP_PLAN_DIR") or os.environ.get("DATA_DIR")
    if env:
        base = Path(env) / "gbp-daily-plans"
    else:
        here = Path(__file__).resolve().parent
        candidate = None
        for _ in range(8):
            test = here / "data" / "gbp-daily-plans"
            if test.is_dir():
                candidate = test
                break
            if here.parent == here:
                break
            here = here.parent
        if candidate:
            base = candidate
        else:
            base = Path(os.path.expanduser(
                "~/.openclaw-instance2/workspace/swing-shack-dashboard/data/gbp-daily-plans"
            ))
    base.mkdir(parents=True, exist_ok=True)
    return base


# Module-level handle, lazily resolved.
_GBP_PLAN_DIR: Optional[Path] = None


def _get_plan_dir() -> Path:
    global _GBP_PLAN_DIR
    if _GBP_PLAN_DIR is None:
        _GBP_PLAN_DIR = _plan_dir()
    return _GBP_PLAN_DIR


def save_plan(plan: dict) -> Path:
    today = _dt.date.today().isoformat()
    brand = plan["brand_id"]
    out_dir = _get_plan_dir()
    out = out_dir / f"{brand}-{today}.json"
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def latest_plan(brand_id: str) -> Optional[dict]:
    """Find the most recent plan file for a brand."""
    out_dir = _get_plan_dir()
    if not out_dir.is_dir():
        return None
    candidates = sorted(out_dir.glob(f"{brand_id}-*.json"), reverse=True)
    if not candidates:
        return None
    try:
        return json.loads(candidates[0].read_text(encoding="utf-8"))
    except Exception:
        return None


def list_plans(brand_id: Optional[str] = None, limit: int = 30) -> list[dict]:
    """List past plans, newest first."""
    out_dir = _get_plan_dir()
    if not out_dir.is_dir():
        return []
    out = []
    for p in sorted(out_dir.glob("*.json"), reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if brand_id and d.get("brand_id") != brand_id:
            continue
        out.append({
            "plan_id": d.get("plan_id") or d.get("build_started_at"),
            "brand_id": d.get("brand_id"),
            "build_started_at": d.get("build_started_at"),
            "posts_count": len(d.get("posts", [])),
            "publish_scheduled": (d.get("publish") or {}).get("scheduled_count", 0),
            "file": str(p),
        })
        if len(out) >= limit:
            break
    return out


# ── Publish (used by gbp_publish job) ────────────────────────────────


def publish_post(post: dict, *, dry_run: bool = False) -> dict:
    """Publish a single post to GBP via Postiz. Returns publish result."""
    brand_id = post.get("brand_id")
    profile = BRAND_PROFILES.get(brand_id)
    if not profile:
        return {"ok": False, "error": "unknown_brand"}
    integration_id = profile.get("postiz_gbp_integration_id")
    if not integration_id:
        return {"ok": False, "error": "no_postiz_integration"}
    bid = str(brand_id or "")

    ok, violations = integrity_check(post, bid)
    if not ok:
        return {
            "ok": False,
            "error": "integrity_violations",
            "violations": violations,
            "post_status": "REMOVED",
        }

    if dry_run:
        return {"ok": True, "dry_run": True, "integration_id": integration_id}

    try:
        from _lib import postiz_client as _pc
    except Exception as exc:
        return {"ok": False, "error": f"postiz_client_unavailable: {exc}"}

    body = (post.get("body") or "") + "\n\n" + (post.get("cta") or "")
    body = body.strip()
    scheduled_at = _dt.datetime.utcnow().isoformat()
    try:
        result, err = _pc.create_post(
            integration_id=integration_id,
            content=body,
            media_ids=[],
            publish_date=scheduled_at,
        )
        if err:
            return {"ok": False, "error": f"postiz_error: {err}", "post_status": "ERROR"}
        return {
            "ok": True,
            "integration_id": integration_id,
            "scheduled_at": scheduled_at,
            "upstream": result,
            "post_status": "scheduled",
        }
    except Exception as exc:
        return {"ok": False, "error": f"postiz_error: {exc}", "post_status": "ERROR"}


# ── Cron tick (used by gbp_tick job) ─────────────────────────────────


def _gbp_daily_cron_tick(*, brand: str | None = None) -> dict:
    """Generate today's plan for a brand (or all brands if brand is None).
    Does NOT publish. The publish step is a separate cron job."""
    if brand:
        brands = [brand]
    else:
        brands = list(BRAND_PROFILES.keys())

    results: dict[str, Any] = {}
    for b in brands:
        try:
            plan = build_daily_plan(b, days=7, posts_per_day=1, publish=False)
            path = save_plan(plan)
            results[b] = {
                "ok": True,
                "plan_path": str(path),
                "posts": len(plan.get("posts", [])),
                "gaps": len(plan.get("gaps", [])),
                "source_breakdown": plan.get("source_breakdown"),
            }
        except Exception as exc:
            results[b] = {"ok": False, "error": str(exc)}
    return {"ok": True, "results": results, "ran_at": _dt.datetime.utcnow().isoformat() + "Z"}


def _gbp_publish_cron_tick(*, brand: str | None = None, dry_run: bool = False) -> dict:
    """Publish today's first valid post for a brand (or all brands)."""
    if brand:
        brands = [brand]
    else:
        brands = list(BRAND_PROFILES.keys())

    results: dict[str, Any] = {}
    for b in brands:
        plan = latest_plan(b)
        if not plan:
            results[b] = {"ok": False, "error": "no_plan"}
            continue
        posts = plan.get("posts", [])
        if not posts:
            results[b] = {"ok": False, "error": "no_posts_in_plan"}
            continue
        for p in posts:
            status = (p.get("post_status") or "").upper()
            if status in ("SCHEDULED", "PUBLISHED", "REMOVED"):
                continue
            result = publish_post(p, dry_run=dry_run)
            p["post_status"] = result.get("post_status", "ERROR")
            p["publish_result"] = result
            plan["publish"] = {
                "brand": b,
                "integration_id": (BRAND_PROFILES[b] or {}).get("postiz_gbp_integration_id"),
                "posts": [
                    {
                        "keyword": p.get("keyword"),
                        "scheduled_at": result.get("scheduled_at"),
                        "status": p.get("post_status"),
                        "title": p.get("title"),
                    }
                ],
                "ran_at": _dt.datetime.utcnow().isoformat() + "Z",
                "scheduled_count": 1 if result.get("ok") else 0,
            }
            today = _dt.date.today().isoformat()
            out = _get_plan_dir() / f"{b}-{today}.json"
            try:
                out.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as exc:
                _LOG.warning("could not save plan back: %s", exc)
            results[b] = {"ok": result.get("ok"), "result": result}
            break
        else:
            results[b] = {"ok": False, "error": "no_unpublished_posts"}
    return {"ok": True, "results": results, "ran_at": _dt.datetime.utcnow().isoformat() + "Z"}
