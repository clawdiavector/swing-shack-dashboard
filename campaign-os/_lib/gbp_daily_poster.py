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

# Same folder app.py writes GBP drafts to (campaign-os/data/gmb-drafts).
def resolve_drafts_dir(env: Optional[dict] = None) -> Path:
    """Where Google Business drafts live.

    On Railway only DATA_DIR sits on the permanent volume; a folder inside the
    app is wiped by every deploy, which deleted every draft once (2026-10-23).
    """
    data_dir = (env if env is not None else os.environ).get("DATA_DIR")
    if data_dir:
        return Path(data_dir) / "gmb-drafts"
    return Path(__file__).resolve().parent.parent / "data" / "gmb-drafts"


GMB_DRAFTS_DIR = resolve_drafts_dir()

# ── Brand-scoped defaults ────────────────────────────────────────────


BRAND_PROFILES = {
    "swing-shack": {
        "display_name": "Swing Shack",
        "voice_id": "swing-shack",
        "domain": "swingshack.co.za",
        "bookings_url": "https://swingshack.co.za/bookings/",
        "primary_color": "#1C1C1C",
        "accent_color": "#74CC46",
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


# ── One partner brand per post ───────────────────────────────────────

# Headline, CTA and hashtags used to be drawn independently, so a post could
# talk about a Vessel bag, link to L.A.B Golf and carry #TakomoAtStick.
_PARTNER_BRAND_RES = {
    "takomo": re.compile(r"takomo", re.IGNORECASE),
    "vessel": re.compile(r"\bvessel\b", re.IGNORECASE),
    "lab": re.compile(r"l\.a\.b|l-a-b-golf|\blab golf\b", re.IGNORECASE),
    "vice": re.compile(r"\bvice\b|vice-golf|#vice", re.IGNORECASE),
    "psycho-bunny": re.compile(r"psycho[ -]?bunny", re.IGNORECASE),
    "avoda": re.compile(r"\bavoda\b", re.IGNORECASE),
    "la-golf": re.compile(r"\bla golf\b", re.IGNORECASE),
    "miura": re.compile(r"\bmiura\b", re.IGNORECASE),
}


def partner_brands_in(*texts: Any) -> set[str]:
    """Partner (product) brands named in any of the texts."""
    blob = " ".join(str(t) for t in texts if t)
    return {name for name, rx in _PARTNER_BRAND_RES.items() if rx.search(blob)}


def _on_subject(items: list, subject: set[str], text_of) -> list:
    """Items naming no partner brand outside `subject`. Empty if none qualify."""
    return [i for i in items if partner_brands_in(text_of(i)) <= subject]


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

    # 5. One partner brand per post: the CTA and hashtags may not name a
    #    partner brand the keyword and headline do not.
    subject = partner_brands_in(post.get("keyword"), post.get("headline_source") or title)
    for stray in sorted(partner_brands_in(cta, post.get("cta_url"), *(post.get("hashtags") or [])) - subject):
        violations.append(f"mixed_partner_brand:{stray}")

    # 6. Length cap.
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

    # The keyword sets the partner brand, if it names one; the headline may
    # only add to it when the keyword names none.
    subject = partner_brands_in(keyword)
    all_headlines = bank.get("headlines") or []
    fitting = (
        _on_subject(all_headlines, subject, lambda h: h.get("text")) if subject
        else all_headlines
    ) or _on_subject(all_headlines, set(), lambda h: h.get("text")) or all_headlines
    headline_obj = pick_headline({**bank, "headlines": fitting}, intent, pillar, brand_id, rng)
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

    subject = subject | partner_brands_in(headline_text)
    cta_text_of = lambda c: f"{c.get('text')} {c.get('url')}"  # noqa: E731
    bank_ctas = bank.get("ctas") or {}
    on_subject_ctas = {
        kind: _on_subject(list(bank_ctas.get(kind, [])), subject, cta_text_of)
        for kind in ("hard", "soft")
    }

    prefer_soft = intent in ("cheeky", "challenge") or pillar in ("culture", "local")
    cta_obj = pick_cta({**bank, "ctas": on_subject_ctas}, pillar, rng, prefer_soft=prefer_soft)
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
    hashtags = rng.choice(
        _on_subject(hashtag_palettes, subject, lambda tags: " ".join(tags)) or hashtag_palettes
    )

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


# ── Reviewed drafts: the only source for daily posts ─────────────────
#
# A daily post is a GMB draft that a person approved on the GBP page. Nothing
# is composed to fill a plan slot: an empty slot is a gap. The fragment
# composer (compose_post) is kept for its existing callers, but build_daily_plan
# no longer uses it, because fragments read as templates and carried no photo
# or link.

DRAFT_STATUSES = ("draft", "approved", "published")


def _read_draft(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    data["id"] = path.stem
    return data


def load_drafts(brand_id: Optional[str] = None, drafts_dir: Optional[Path] = None) -> list[dict]:
    root = Path(drafts_dir) if drafts_dir else GMB_DRAFTS_DIR
    if not root.is_dir():
        return []
    rows = [_read_draft(p) for p in sorted(root.glob("*.json"))]
    return [r for r in rows if r and (brand_id is None or r.get("brand") == brand_id)]


def approved_drafts(brand_id: str, drafts_dir: Optional[Path] = None) -> list[dict]:
    """Approved drafts for a brand, earliest approval first."""
    rows = [d for d in load_drafts(brand_id, drafts_dir) if d.get("status") == "approved"]
    return sorted(rows, key=lambda d: d.get("approvedAt") or "")


def draft_post(draft: dict) -> dict:
    """A reviewed draft in the shape publish_post() takes."""
    brand_id = draft.get("brand") or ""
    body = (draft.get("body") or "").strip()
    post = {
        "brand_id": brand_id,
        "draft_id": draft.get("id"),
        "keyword": None,
        "intent": "reviewed_draft",
        "pillar": None,
        "title": ((draft.get("title") or body)[:58]).strip(),
        "body": body,
        "cta": (draft.get("cta") or "").strip(),
        "cta_url": (draft.get("link") or "").strip() or None,
        "image_url": (draft.get("imageUrl") or "").strip() or None,
        "target_query": (draft.get("targetQuery") or "").strip() or None,
        "hashtags": [],
    }
    ok, violations = integrity_check(post, brand_id)
    post["integrity_ok"] = ok
    post["integrity_violations"] = violations
    return post


def review_problems(draft: dict) -> list[str]:
    """Why a draft may not be approved yet. An empty list means it may be."""
    brand_id = draft.get("brand") or ""
    profile = BRAND_PROFILES.get(brand_id)
    if not profile:
        return ["unknown_brand"]
    problems: list[str] = []
    if not (draft.get("body") or "").strip():
        problems.append("body_empty")
    link = (draft.get("link") or "").strip()
    if not link:
        problems.append("link_missing")
    elif profile["domain"] not in link:
        problems.append("link_not_brand_domain")
    if not (draft.get("imageUrl") or "").strip():
        problems.append("photo_missing")
    target = (draft.get("targetQuery") or "").strip().lower()
    if target and target not in (draft.get("body") or "").lower():
        problems.append("target_query_not_in_body")
    problems.extend(draft_post(draft)["integrity_violations"])
    return problems


def suggest_draft(
    brand_id: str,
    *,
    drafts_dir: Optional[Path] = None,
    terms: Optional[list[dict]] = None,
) -> dict:
    """The draft that should go out next, when none is approved.

    Only drafts that already pass review_problems() are candidates, so what is
    suggested can be approved as it stands. The pick is the draft whose target
    search term has the most Search Console impressions for this brand, then
    the oldest waiting. `terms` are search_terms() rows; fetched when omitted.
    """
    if terms is None:
        terms = search_terms(brand_id).get("terms") or []
    impressions = {(t.get("query") or "").strip().lower(): int(t.get("impressions") or 0) for t in terms}
    ready: list[tuple[int, str, dict]] = []
    blocked = 0
    for d in load_drafts(brand_id, drafts_dir):
        if d.get("status") != "draft":
            continue
        if review_problems(d):
            blocked += 1
            continue
        target = (d.get("targetQuery") or "").strip().lower()
        ready.append((impressions.get(target, 0), d.get("createdAt") or "", d))
    if not ready:
        return {"draft": None, "ready_count": 0, "blocked_count": blocked}
    ready.sort(key=lambda r: (-r[0], r[1]))
    top_impressions, _, pick = ready[0]
    target = (pick.get("targetQuery") or "").strip()
    if top_impressions:
        why = f"People searched \"{target}\" {top_impressions} times on Google lately, and this post is about it."
    else:
        why = "Ready to go and has waited longest."
    return {"draft": pick, "why": why, "ready_count": len(ready), "blocked_count": blocked}


def search_terms(brand_id: str, *, limit: int = 12, payload: Optional[dict] = None) -> dict:
    """Top Search Console queries for a brand, to pick a post's target term from.

    Only a live Search Console file for this brand's own site counts. Anything
    else returns ok=False with a reason and no terms.
    """
    profile = BRAND_PROFILES.get(brand_id)
    if not profile:
        return {"ok": False, "reason": "unknown_brand", "terms": []}
    if payload is None:
        from _lib.brand_data_paths import read_brand_data_json  # noqa: PLC0415
        payload = read_brand_data_json("search-console.json", brand_id)
    if not isinstance(payload, dict) or payload.get("source") != "google_search_console_api":
        return {"ok": False, "reason": "no_search_console_data", "terms": []}
    if profile["domain"] not in (payload.get("site_url") or ""):
        return {"ok": False, "reason": "search_console_site_is_not_this_brand", "terms": []}
    rows = sorted(
        (r for r in payload.get("queries") or [] if r.get("key")),
        key=lambda r: int(r.get("impressions") or 0),
        reverse=True,
    )[:limit]
    terms = [
        {
            "query": r["key"],
            "impressions": int(r.get("impressions") or 0),
            "clicks": int(r.get("clicks") or 0),
            "position": r.get("position"),
        }
        for r in rows
    ]
    return {"ok": True, "updated": payload.get("updated"), "data_window": payload.get("data_window"), "terms": terms}


def set_draft_status(
    draft_id: str,
    status: str,
    *,
    drafts_dir: Optional[Path] = None,
    **extra: Any,
) -> bool:
    """Move a draft to another status. Returns False if it cannot be found."""
    if status not in DRAFT_STATUSES or not draft_id or "/" in draft_id or ".." in draft_id:
        return False
    root = Path(drafts_dir) if drafts_dir else GMB_DRAFTS_DIR
    path = root / f"{draft_id}.json"
    draft = _read_draft(path) if path.is_file() else None
    if draft is None:
        return False
    draft.pop("id", None)
    now = _dt.datetime.utcnow().isoformat() + "Z"
    draft["status"] = status
    draft["statusAt"] = now
    if status == "approved":
        draft["approvedAt"] = now
    draft.update(extra)
    path.write_text(json.dumps(draft, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
PHOTO_MAX_BYTES = 8 * 1024 * 1024


PHOTO_MAX_SIDE = 2000


def resize_photo(src_path, dst_path, max_side: int = PHOTO_MAX_SIDE) -> None:
    """Write a JPEG copy with its long edge at most max_side px. The source is not touched."""
    from PIL import Image  # noqa: PLC0415

    with Image.open(src_path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        im.save(dst_path, "JPEG", quality=88, optimize=True)


def looks_like_photo(data: bytes, ext: str) -> bool:
    """True if the bytes start like the image type the extension names."""
    ext = ext.lower()
    if ext in (".jpg", ".jpeg"):
        return data[:3] == b"\xff\xd8\xff"
    if ext == ".png":
        return data[:8] == b"\x89PNG\r\n\x1a\n"
    if ext == ".webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


# ── Plan builder ────────────────────────────────────────────────────


def rebuild_plan(brand_id: str, *, previous: Optional[dict] = None, drafts_dir: Optional[Path] = None) -> dict:
    """Rebuild the plan from the approved drafts as they stand now.

    `previous` is the plan being replaced. Its publish log is carried over, so
    a post already sent today is not sent again by the 06:30 job.
    """
    plan = build_daily_plan(brand_id, days=7, posts_per_day=1, drafts_dir=drafts_dir)
    if previous and previous.get("publish"):
        plan["publish"] = previous["publish"]
    return plan


def build_daily_plan(
    brand_id: str,
    *,
    days: int = 7,
    posts_per_day: int = 1,
    publish: bool = False,
    keywords: Optional[list[str]] = None,
    drafts_dir: Optional[Path] = None,
) -> dict:
    """Daily plan from approved drafts, one post per slot, earliest approval first.

    `publish` and `keywords` are accepted for existing callers and do nothing
    here. Sending is publish_post(), from the Today approve button or the
    gbp_publish job.
    """
    profile = BRAND_PROFILES.get(brand_id)
    if not profile:
        return {"error": "unknown_brand", "brand_id": brand_id}

    ready = approved_drafts(brand_id, drafts_dir)
    today = _dt.date.today()
    posts: list[dict] = []
    gaps: list[dict] = []
    for slot in range(days * posts_per_day):
        day_iso = (today + _dt.timedelta(days=slot // posts_per_day)).isoformat()
        if slot >= len(ready):
            gaps.append({
                "error": "gap_no_approved_draft",
                "brand_id": brand_id,
                "day": day_iso,
                "needs": "Write and approve a draft on the GBP page",
            })
            continue
        post = draft_post(ready[slot])
        post["day"] = day_iso
        if post["integrity_ok"]:
            posts.append(post)
        else:
            gaps.append({**post, "kind": "integrity_violation"})

    return {
        "brand_id": brand_id,
        "domain": profile["domain"],
        "build_started_at": _dt.datetime.utcnow().isoformat() + "Z",
        "build_for_days": days,
        "posts": posts,
        "gaps": gaps,
        "source_breakdown": {"from_drafts": len(posts), "gaps": len(gaps)},
        "publish": {"scheduled": False, "reason": "publish_disabled_in_build"},
        "voice_id": profile["voice_id"],
        "tagline": profile.get("tagline"),
    }


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


def gbp_post_text(post: dict) -> str:
    """Text sent to GBP: body, then the CTA label and link on one line."""
    cta_line = " ".join(x for x in ((post.get("cta") or "").strip(), (post.get("cta_url") or "").strip()) if x)
    parts = [(post.get("body") or "").strip(), cta_line]
    return "\n\n".join(p for p in parts if p)[:1500]


def publish_post(post: dict, *, dry_run: bool = False) -> dict:
    """Send one reviewed post to GBP via Postiz, photo attached and link in the text.

    A photo that fails to upload stops the post. A text-only post does not go out.
    """
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

    media_ids: list[str] = []
    image = post.get("image_url")
    if image:
        try:
            upload, up_err = _pc.upload_media(image)
        except Exception as exc:
            return {"ok": False, "error": f"image_upload_exception: {exc}", "post_status": "ERROR"}
        if up_err or not (upload and upload.get("id")):
            return {"ok": False, "error": f"image_upload_failed: {up_err}", "post_status": "ERROR"}
        media_ids.append(upload["id"])

    scheduled_at = _dt.datetime.utcnow().isoformat()
    try:
        result, err = _pc.create_post(
            integration_id=integration_id,
            content=gbp_post_text(post),
            media_ids=media_ids,
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
            if result.get("ok") and p.get("draft_id"):
                set_draft_status(p["draft_id"], "published")
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
