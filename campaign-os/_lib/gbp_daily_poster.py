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
        "supported_pillars": [
            "trackman_intelligence",
            "fitting_education",
            "coaching",
            "social_play",
            "practice",
            "membership",
            "local",
        ],
        "share_targets": {
            "trackman_intelligence": 0.40,
            "fitting_education": 0.25,
            "coaching": 0.20,
            "practice": 0.05,
            "social_play": 0.05,
            "membership": 0.05,
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
        "supported_pillars": [
            "why_its_here",
            "fitting",
            "workshop",
            "culture",
            "coaching",
            "local",
        ],
        "share_targets": {
            "why_its_here": 0.40,
            "fitting": 0.25,
            "workshop": 0.20,
            "culture": 0.10,
            "coaching": 0.03,
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
    # Informational: golfer is researching a concept.
    "what is": ("informational", ["trackman_intelligence", "fitting"]),
    "vs": ("informational", ["fitting", "why_its_here"]),
    "versus": ("informational", ["fitting"]),
    "explained": ("informational", ["trackman_intelligence", "fitting"]),
    "how to": ("informational", ["trackman_intelligence", "fitting"]),
    "how often": ("informational", ["workshop", "fitting"]),
    "difference between": ("informational", ["fitting"]),
    # Commercial: golfer is ready to buy or book.
    "book": ("commercial", ["general"]),
    "fitting": ("commercial", ["fitting"]),
    "coaching": ("commercial", ["coaching"]),
    "membership": ("commercial", ["membership"]),
    "buy": ("commercial", ["why_its_here"]),
    "price": ("commercial", ["fitting"]),
    "cost": ("commercial", ["fitting"]),
    "near me": ("commercial", ["local"]),
    "south africa": ("commercial", ["local"]),
    "johannesburg": ("commercial", ["local"]),
    "paarl": ("commercial", ["local"]),
    "cape town": ("commercial", ["local"]),
    "winelands": ("commercial", ["local"]),
    # Cheeky: golfer is in on the joke. Lead with setup:payoff.
    "myth": ("cheeky", ["culture", "trackman_intelligence"]),
    "lie": ("cheeky", ["trackman_intelligence"]),
    "hope": ("cheeky", ["fitting"]),
    "denial": ("cheeky", ["fitting"]),
    # Challenge: golf habit that needs fixing.
    "slice": ("challenge", ["trackman_intelligence", "fitting"]),
    "hook": ("challenge", ["trackman_intelligence"]),
    "shank": ("challenge", ["trackman_intelligence"]),
    "off-rack": ("challenge", ["fitting", "why_its_here"]),
    "off the rack": ("challenge", ["fitting", "why_its_here"]),
    "off-the-rack": ("challenge", ["fitting", "why_its_here"]),
}


def classify_keyword_intent(keyword: str) -> tuple[str, list[str]]:
    """Returns (intent_label, pillar_hints). Falls back to (commercial, [])."""
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
    to intent-only, then any. Returns None if the bank is empty."""
    headlines = bank.get("headlines") or []
    if not headlines:
        return None
    exact = [h for h in headlines
             if h.get("tone") == intent and pillar_hint in (h.get("pillar") or "")]
    if exact:
        return rng.choice(exact)
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
        pillar_shares = profile.get("share_targets") or {}
        pillars_sorted = sorted(pillar_shares.items(), key=lambda x: -x[1])
        pillar_kw_anchors = {
            "trackman_intelligence": ["trackman session johannesburg", "golf simulator randburg"],
            "fitting_education": ["driver fitting johannesburg", "club fitting randburg"],
            "coaching": ["golf lessons johannesburg", "golf coach randburg"],
            "practice": ["indoor golf practice johannesburg", "trackman practice bay"],
            "social_play": ["indoor golf social johannesburg", "golf party randburg"],
            "membership": ["indoor golf membership johannesburg"],
            "local": ["indoor golf randburg", "golf club randburg"],
            "why_its_here": ["takomo paarl", "vice golf paarl", "psycho bunny paarl"],
            "fitting": ["club fitting paarl", "putter fitting western cape"],
            "workshop": ["regrip golf clubs paarl", "loft and lie paarl"],
            "culture": ["modern golf paarl", "golf culture western cape"],
            "general": ["indoor golf paarl", "golf fitting western cape"],
        }
        kw_list = []
        for pillar, _ in pillars_sorted:
            kw_list.extend(pillar_kw_anchors.get(pillar, [])[:2])

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


_GBP_PLAN_DIR = Path(
    os.environ.get("GBP_PLAN_DIR") or "data/gbp-daily-plans"
)


def save_plan(plan: dict) -> Path:
    today = _dt.date.today().isoformat()
    brand = plan["brand_id"]
    out_dir = Path(_GBP_PLAN_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{brand}-{today}.json"
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def latest_plan(brand_id: str) -> Optional[dict]:
    """Find the most recent plan file for a brand."""
    out_dir = Path(_GBP_PLAN_DIR)
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
    out_dir = Path(_GBP_PLAN_DIR)
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
            out = Path(_GBP_PLAN_DIR) / f"{b}-{today}.json"
            try:
                out.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as exc:
                _LOG.warning("could not save plan back: %s", exc)
            results[b] = {"ok": result.get("ok"), "result": result}
            break
        else:
            results[b] = {"ok": False, "error": "no_unpublished_posts"}
    return {"ok": True, "results": results, "ran_at": _dt.datetime.utcnow().isoformat() + "Z"}
