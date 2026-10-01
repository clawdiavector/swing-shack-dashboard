"""Meme Lord — local meme knowledge, scoring, and caption apply (no network)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_MEME_KNOWLEDGE_CACHE: dict[str, Any] = {"path": None, "mtime": None, "data": None}


def _repo_data_dir() -> str:
    return os.environ.get("DATA_DIR") or "/data/campaign-os"


def _meme_knowledge_path() -> str | None:
    candidate = os.path.join(_repo_data_dir(), "meme_knowledge.json")
    if os.path.exists(candidate):
        return candidate
    bundled = Path(__file__).resolve().parents[2] / "data" / "meme_knowledge.json"
    if bundled.is_file():
        return str(bundled)
    return None


def load_meme_knowledge(_cache_key: int = 0) -> dict[str, Any]:
    """Load meme_knowledge.json with mtime-invalidated cache."""
    path = _meme_knowledge_path()
    mtime = None
    if path:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
    cache = _MEME_KNOWLEDGE_CACHE
    if (
        _cache_key == 0
        and cache["data"] is not None
        and cache["path"] == path
        and cache["mtime"] == mtime
    ):
        return cache["data"]
    empty: dict[str, Any] = {
        "memes": [],
        "taxonomy": {"eras": [], "formats": [], "mechanisms": []},
        "voice_bible": {},
        "stats": {},
    }
    data = empty
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            data = empty
    cache["path"] = path
    cache["mtime"] = mtime
    cache["data"] = data
    return data


def load_meme_knowledge_cache_clear() -> None:
    _MEME_KNOWLEDGE_CACHE["path"] = None
    _MEME_KNOWLEDGE_CACHE["mtime"] = None
    _MEME_KNOWLEDGE_CACHE["data"] = None


load_meme_knowledge.cache_clear = load_meme_knowledge_cache_clear  # type: ignore[attr-defined]


def score_meme_brand_fit(
    meme: dict[str, Any],
    voice: str = "swing-shack",
    pillar: str = "education",
    platform: str = "instagram",
) -> tuple[int, list[str]]:
    """Compute brand-fit score 0..100 for a meme given voice/pillar/platform."""
    score = 0
    reasons: list[str] = []
    if voice and voice in (meme.get("voice_fit") or []):
        score += 20
        reasons.append(f"voice={voice} match (+20)")
    if pillar and pillar in (meme.get("pillar_fit") or []):
        score += 15
        reasons.append(f"pillar={pillar} match (+15)")
    if platform and platform in (meme.get("platform_fit") or []):
        score += 10
        reasons.append(f"platform={platform} match (+10)")
    if meme.get("still_works") is True:
        score += 10
        reasons.append("still_works=True (+10)")
    elif meme.get("still_works") is False:
        score -= 10
        reasons.append("still_works=False (−10)")
    fr = meme.get("fatigue_risk")
    if fr == "low":
        score += 8
        reasons.append("fatigue_risk=low (+8)")
    elif fr == "medium":
        score -= 5
        reasons.append("fatigue_risk=medium (−5)")
    elif fr == "high":
        score -= 15
        reasons.append("fatigue_risk=high (−15)")
    era = (meme.get("era") or "").lower()
    if era in ("current", "recent"):
        score += 5
        reasons.append(f"era={era} (fresh, +5)")
    elif era == "mid":
        score -= 10
        reasons.append("era=mid (2018-2020, overused, −10)")
    elif era == "classic":
        score -= 5
        reasons.append("era=classic (2014-2017, expected, −5)")
    peak = meme.get("peak_year")
    if isinstance(peak, int) and peak < 2026:
        age = 2026 - peak
        if age > 8:
            score -= min(15, age - 5)
            reasons.append(f"peak_year {peak} (aged −{min(15, age - 5)})")
    seeds = meme.get("swingshack_fit_seeds") or []
    n_seeds = min(len(seeds), 3)
    if n_seeds:
        bonus = min(4, n_seeds)
        score += bonus
        reasons.append(f"{n_seeds} fit-seeds (+{bonus})")
    score = max(0, min(100, score))
    return score, reasons


def filter_memes(
    memes: list[dict[str, Any]],
    *,
    era: str | None = None,
    fmt: str | None = None,
    mechanism: str | None = None,
    voice: str | None = None,
    pillar: str | None = None,
    platform: str | None = None,
    only_still_works: bool = False,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """Apply faceted filters to the meme list."""
    out = list(memes)
    if era:
        out = [m for m in out if m.get("era") == era]
    if fmt:
        out = [m for m in out if m.get("format") == fmt]
    if mechanism:
        out = [m for m in out if m.get("mechanism") == mechanism]
    if voice:
        out = [m for m in out if voice in (m.get("voice_fit") or [])]
    if pillar:
        out = [m for m in out if pillar in (m.get("pillar_fit") or [])]
    if platform:
        out = [m for m in out if platform in (m.get("platform_fit") or [])]
    if only_still_works:
        out = [m for m in out if m.get("still_works") is True]
    if search:
        s = search.lower().strip()

        def _hit(m: dict[str, Any]) -> bool:
            hay = " ".join(
                [
                    m.get("name", ""),
                    m.get("why_it_works", ""),
                    m.get("origin", ""),
                    " ".join(m.get("tags") or []),
                    " ".join(m.get("swingshack_fit_seeds") or []),
                    m.get("format_hint", ""),
                ],
            ).lower()
            return s in hay

        out = [m for m in out if _hit(m)]
    return out


def recommend_memes(
    *,
    voice: str = "swing-shack",
    pillar: str = "education",
    platform: str = "instagram",
    limit: int = 10,
    era: str | None = None,
    fmt: str | None = None,
    mechanism: str | None = None,
    only_still_works: bool = False,
    **facets: Any,
) -> list[dict[str, Any]]:
    """Top-N meme picks sorted by brand_fit (deterministic for equal scores)."""
    del facets
    kb = load_meme_knowledge()
    memes = kb.get("memes", []) or []
    limit = max(1, min(int(limit), 50))
    filtered = filter_memes(
        memes,
        era=era,
        fmt=fmt,
        mechanism=mechanism,
        voice=voice,
        pillar=pillar,
        platform=platform,
        only_still_works=only_still_works,
    )
    scored: list[dict[str, Any]] = []
    for m in filtered:
        bf, reasons = score_meme_brand_fit(m, voice=voice, pillar=pillar, platform=platform)
        scored.append({**m, "brand_fit": bf, "brand_fit_reasons": reasons})
    scored.sort(
        key=lambda x: (x.get("brand_fit", 0), x.get("id") or ""),
        reverse=True,
    )
    return scored[:limit]


def apply_meme(
    *,
    meme_id: str,
    voice: str = "swing-shack",
    pillar: str = "education",
    platform: str = "instagram",
    hook: str | None = None,
    pick_seed_index: int = 0,
) -> dict[str, Any]:
    """Return caption templates and metadata for one meme (no HTTP)."""
    kb = load_meme_knowledge()
    memes = kb.get("memes", []) or []
    target = next((m for m in memes if m.get("id") == meme_id), None)
    if not target:
        raise ValueError(f"Unknown meme_id: {meme_id}")

    hook = (hook or "").strip()
    try:
        pick_seed_index = int(pick_seed_index)
    except (TypeError, ValueError):
        pick_seed_index = 0
    seeds = target.get("swingshack_fit_seeds") or []
    seed = seeds[pick_seed_index % len(seeds)] if seeds else ""

    bf, reasons = score_meme_brand_fit(target, voice=voice, pillar=pillar, platform=platform)

    sarcastic_hook = hook or f"{seed}? Deal with it. 🏌️"
    wholesome_hook = hook or f"PSA: {seed.lower()} 💚"
    hard_truth_hook = hook or f"Hard truth: {seed.lower()}."

    voice_bible = (kb.get("voice_bible") or {}).get(voice, {})
    voice_rules = voice_bible.get("do", []) if isinstance(voice_bible, dict) else []

    return {
        "meme": target,
        "applied": {
            "voice": voice,
            "pillar": pillar,
            "platform": platform,
            "fit_seed_used": seed,
            "user_hook": hook or None,
        },
        "brand_fit": {
            "score": bf,
            "reasons": reasons,
            "voice_bible": voice_bible,
            "voice_rules": voice_rules,
        },
        "captions": [
            {"flavour": "sarcastic", "text": sarcastic_hook, "platform_fit": platform},
            {"flavour": "wholesome", "text": wholesome_hook, "platform_fit": platform},
            {"flavour": "hard-truth", "text": hard_truth_hook, "platform_fit": platform},
        ],
        "format_hint": target.get("format_hint"),
        "why_it_works": target.get("why_it_works"),
    }
