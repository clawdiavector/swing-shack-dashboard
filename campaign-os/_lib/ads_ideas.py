"""Video ideas — what to film for a creative test.

A test card used to say "film a new real-person video" and stop. This turns
that line into something a person can shoot: the first three seconds, what to
say after them, the shots to get and how to end.

The ideas are not written here and not by a model at run time. They live in
each brand's data/brand-directory/<brand>/ads/video-ideas.json, which a person
edits. This module only chooses: the idea that fits the campaign's subject,
opens differently from the ad it will be tested against, and is not already on
another card. Where one of the brand's own ads has already proven itself on
the subject, the card says so, so the new video keeps what worked.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import ads_creative, ads_history

SCHEMA = "https://campaign-os/ads-video-ideas/v1"
KINDS = {"NEW_VIDEO": "video", "ANIMATED_STILL": "animated_still"}
ANGLES = {
    "numbers": "show the numbers",
    "question": "open on a question",
    "walkthrough": "show what happens",
    "myth": "answer the doubt",
    "product": "the product in hand",
    "coach": "the coach to camera",
    "customer": "a customer in their own words",
}
PER_CARD = 2

# How the video ends, by what the ad is bought for.
ENDINGS = {
    "leads": "End on the same offer as the original ad and point at the button. "
             "Say what happens next: they fill in a short form and you call them.",
    "messages": "End by asking them to send a message, and say who will answer.",
    "landing_page_views": "End by saying what they will find when they tap through, "
                          "in one line.",
}
_REQUIRED = ("id", "kind", "themes", "angle", "title", "who", "length", "hook", "points", "shots")


def _bank_path(brand_id: str, base_dir=None):
    roots = [Path(base_dir)] if base_dir else [
        Path(os.environ.get("DATA_DIR", "/data/campaign-os")) / "brand-directory",
        Path(__file__).resolve().parents[2] / "data" / "brand-directory",
    ]
    for root in roots:
        path = root / brand_id / "ads" / "video-ideas.json"
        if path.is_file():
            return path
    return None


def load_bank(brand_id: str, base_dir=None) -> dict:
    """The brand's idea file, or an empty bank. Never raises: a missing or
    broken file means cards fall back to the plain 'film a new video' line."""
    path = _bank_path(brand_id, base_dir)
    if not path:
        return {"ideas": []}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"ideas": []}
    if not isinstance(doc, dict) or problems(doc):
        return {"ideas": []}
    return doc


def problems(doc: dict) -> list:
    """Why a bank cannot be used. Empty when it can."""
    out, seen = [], set()
    known = set(ads_creative.THEMES) | {"any"}
    for i, idea in enumerate(doc.get("ideas") or []):
        name = idea.get("id") or f"idea {i + 1}"
        missing = [k for k in _REQUIRED if not idea.get(k)]
        if missing:
            out.append(f"{name}: missing {', '.join(missing)}")
            continue
        if name in seen:
            out.append(f"{name}: used twice")
        seen.add(name)
        if idea["kind"] not in KINDS.values():
            out.append(f"{name}: kind must be video or animated_still")
        if idea["angle"] not in ANGLES:
            out.append(f"{name}: unknown angle {idea['angle']}")
        unknown = set(idea["themes"]) - known
        if unknown:
            out.append(f"{name}: unknown themes {', '.join(sorted(unknown))}")
        if not all((idea["hook"] or {}).get(k) for k in ("say", "show", "text")):
            out.append(f"{name}: the hook needs say, show and text")
        if "—" in json.dumps(idea, ensure_ascii=False):
            out.append(f"{name}: em dash")
    return out


def _opens_on_question(body) -> bool:
    return (ads_history.opening(body) or "").rstrip().endswith("?")


def choose(bank: dict, kind: str, themes, control_body, used, n: int = PER_CARD,
           skip_angles=()) -> list:
    """Ideas for one challenger, best first. On the campaign's subject before
    general ones, and a different way in from the ad it is tested against."""
    themes = set(themes or ())
    scored = []
    for order, idea in enumerate(bank.get("ideas") or []):
        if idea["kind"] != kind or idea["id"] in used:
            continue
        shared = themes & set(idea["themes"])
        if not shared and "any" not in idea["themes"]:
            continue
        same_way_in = idea["angle"] == "question" and _opens_on_question(control_body)
        scored.append((same_way_in, -len(shared), order, idea))
    scored.sort(key=lambda s: s[:3])
    picked, angles = [], set(skip_angles)
    for _, _, _, idea in scored:
        if idea["angle"] in angles:
            continue  # the second option should be a different kind of video
        picked.append(idea)
        angles.add(idea["angle"])
        if len(picked) == n:
            break
    return picked


def _why(idea: dict, card: dict, proven) -> str:
    label = card["metric"]["label"]
    way_in = ANGLES[idea["angle"]]
    if proven and proven["ad_id"] != card["control"]["ad_id"]:
        return (f"Your cheapest {label} ad on this subject, {proven['ad_name']}, opened with "
                f"“{proven['opening']}” and brought {proven['result']['count']:,} "
                f"{label}s at R{proven['result']['cost']:,.2f} each. This keeps the subject "
                f"and tries a different way in: {way_in}.")
    if proven:
        return (f"The ad this is tested against is already your cheapest {label} ad on this "
                f"subject, so only the way in changes: {way_in}.")
    return (f"No ad on this subject has enough {label}s yet to copy from, so this starts from "
            f"the brand's own facts. Way in: {way_in}.")


def brief(idea: dict, card: dict, bank: dict, proven) -> dict:
    return {
        "id": idea["id"], "title": idea["title"], "angle": idea["angle"],
        "who": idea["who"], "length": idea["length"],
        "hook": dict(idea["hook"]), "points": list(idea["points"]),
        "shots": list(idea["shots"]), "watch_out": idea.get("watch_out"),
        "end": ENDINGS.get(card["metric"]["key"]), "sign_off": bank.get("sign_off"),
        "why": _why(idea, card, proven),
    }


def attach(tests: list, bank: dict, win: dict | None) -> list:
    """Give every proposed card its ideas. A card keeps the ideas it was given,
    so it reads the same tomorrow; their wording is refreshed from the bank so
    an edit to the file shows up on the next brief."""
    by_id = {i["id"]: i for i in bank.get("ideas") or []}
    if not by_id:
        return tests
    # No idea on two open cards at once. Closed tests give theirs back.
    used = {i["id"] for t in tests if t.get("status") in ads_creative.OPEN
            for c in t.get("challengers") or [] for i in c.get("ideas") or []}
    out = [dict(t, challengers=[dict(c) for c in t["challengers"]])
           if t.get("status") == "PROPOSED" else t for t in tests]
    slots = [(t, c, KINDS[c["kind"]]) for t in out if t.get("status") == "PROPOSED"
             for c in t["challengers"] if c.get("kind") in KINDS]
    # What each card is about, read from its ad's text as it is today.
    about = {t["id"]: sorted(_subject(t, win)) for t, _, _ in slots}
    # A card keeps its ideas unless it turns out to be about something else.
    picks = {id(c): [by_id[i["id"]] for i in c.get("ideas") or []
                     if i.get("id") in by_id and c.get("ideas_for") == about[t["id"]]]
             for t, c, _ in slots}
    used -= {i["id"] for _, c, _ in slots for i in c.get("ideas") or []
             if i["id"] not in {p["id"] for p in picks[id(c)]}}
    # Every card gets its best idea before any card gets a second, so the first
    # card cannot take both ideas on a subject two campaigns share.
    for want in range(1, PER_CARD + 1):
        for t, c, kind in slots:
            have = picks[id(c)]
            if len(have) >= want:
                continue
            body = (t.get("control") or {}).get("body")
            angles = {i["angle"] for i in have}
            more = choose(bank, kind, about[t["id"]], body, used, n=1, skip_angles=angles)
            if not more and not have:
                # The file has run out of unused ideas: repeat one rather than
                # leave the card with nothing to film.
                more = choose(bank, kind, about[t["id"]], body, set(), n=1)
            have.extend(more)
            used.update(i["id"] for i in more)
    for t, c, _ in slots:
        c.pop("ideas", None)
        if picks[id(c)]:
            proven = ads_history.proven_for(win, about[t["id"]], t["metric"]["key"])
            c["ideas"] = [brief(i, t, bank, proven) for i in picks[id(c)]]
            c["ideas_for"] = about[t["id"]]
    return out


def _subject(card: dict, win: dict | None) -> set:
    """The history has every ad's full text; the card only its first lines."""
    control = card.get("control") or {}
    known = ((win or {}).get("by_ad") or {}).get(control.get("ad_id"))
    if known:
        return set(known["themes"])
    return ads_creative.subject(card.get("campaign_name"), control.get("ad_name"), None,
                                control.get("body"))
