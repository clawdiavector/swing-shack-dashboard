"""Template- and brand-aware caption contracts for L5 (P11) generation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Global vague-evidence phrasing (not banned in voice markdown yet).
GLOBAL_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "data shows",
    "research shows",
    "studies show",
    "the data proves",
    "statistics show",
    "studies have shown",
    "research has shown",
)

# Extra brand phrases (merged into P11 banned list + contract checks).
BRAND_FORBIDDEN_PHRASES: dict[str, tuple[str, ...]] = {
    "stick": (
        "join our membership",
        "join our fitting membership",
        "fitting membership",
        "join the club",
        "join the stick club",
        "become a member",
    ),
    "swing-shack": (),
}

# Per-template / post_type focus (forbidden terms allowed only if in lodge title + brief).
TEMPLATE_COPY_CONTRACTS: dict[str, dict[str, Any]] = {
    "ss-fitting-headline": {
        "brief_subject_override": "iron fitting",
        "focus": "iron fitting and approach play — not putting or short game",
        "preferred_terms": ("club fitting", "iron fitting"),
        "forbidden_unless_in_brief": (
            "putter",
            "putting",
            "stroke type",
            "eye position",
            "grip size",
            "short game",
        ),
        "required_families": ("iron",),
    },
    "fitting_headline": {
        "brief_subject_override": "iron fitting",
        "focus": "iron fitting",
        "preferred_terms": ("club fitting", "iron fitting"),
        "forbidden_unless_in_brief": ("putter", "putting", "short game"),
        "required_families": ("iron",),
    },
    "ss-did-you-know": {
        "focus": "one honest fitting insight — no invented statistics",
        "forbidden_unless_in_brief": ("membership", "tpi assessment"),
        "preferred_terms": ("club fitting", "fitting"),
    },
    "did_you_know": {
        "focus": "fitting insight without fake stats",
        "forbidden_unless_in_brief": ("membership",),
    },
    "ss-service-promo": {
        "focus": "club fitting service — book a session",
        "preferred_terms": ("club fitting", "fitting session"),
        "forbidden_unless_in_brief": ("putter", "tpi", "membership", "tpr"),
    },
    "service_promo": {
        "focus": "club fitting promo",
        "preferred_terms": ("club fitting",),
        "forbidden_unless_in_brief": ("putter", "membership"),
    },
    "stick-service-start": {
        "brief_subject_override": "coaching",
        "focus": "coaching / service start — not generic off-rack memes",
        "forbidden_unless_in_brief": ("putter", "membership", "putting"),
        "preferred_terms": ("coaching", "service"),
    },
    "service_start": {
        "brief_subject_override": "coaching",
        "focus": "coaching or service start",
        "forbidden_unless_in_brief": ("putter", "membership"),
    },
    "stick-coach-profile": {
        "brief_subject_override": "coaching",
        "focus": "coach / team profile",
        "forbidden_unless_in_brief": ("putter", "membership", "iron fitting"),
    },
    "staff_profile": {
        "brief_subject_override": "coaching",
        "focus": "staff or coach profile",
        "forbidden_unless_in_brief": ("membership",),
    },
    "stick-service-square": {
        "focus": "fitting service callout",
        "preferred_terms": ("club fitting", "fitting"),
        "forbidden_unless_in_brief": ("putter", "membership"),
    },
    "service_square": {
        "focus": "fitting service",
        "preferred_terms": ("club fitting",),
        "forbidden_unless_in_brief": ("putter", "membership"),
    },
    "stick-service-frame": {
        "focus": "club assessment / fitting service",
        "preferred_terms": ("club fitting", "club assessment", "fitting"),
        "forbidden_unless_in_brief": ("putter", "membership"),
    },
    "stick-brand-statement": {
        "focus": "brand philosophy — equipment fitted to the player",
        "forbidden_unless_in_brief": ("putter", "membership", "tpi"),
    },
    "brand_statement": {
        "focus": "brand statement",
        "forbidden_unless_in_brief": ("membership",),
    },
}

EQUIPMENT_FAMILIES: dict[str, tuple[str, ...]] = {
    "iron": ("iron", "irons", "7-iron", "approach shot", "approach shots", "approaches"),
    "putter": (
        "putter",
        "putting",
        "short game",
        "stroke type",
        "eye position",
        "grip size",
        "on the greens",
    ),
    "coaching": ("coaching", "coach", "lesson", "trackman session", "trackman"),
    "membership": ("membership", "join our membership", "member benefits"),
    "fitting_generic": ("club fitting", "fitting session", "fitted", "fitting"),
}


def bible_banned_phrases(brand_id: str) -> tuple[str, ...]:
    from _lib.brand_bible import bible_copy_slice  # noqa: PLC0415

    cs = (bible_copy_slice(brand_id, "caption") or {}).get("copy_system") or {}
    return tuple(
        p for p in (cs.get("banned_phrases") or [])
        if isinstance(p, str) and p.strip()
    )


def parse_dont_say_markdown(text: str) -> list[str]:
    """Extract phrase gates from do-say-dont-say markdown (quoted or pre-rationale)."""
    if not text:
        return []
    banned: list[str] = []
    section: str | None = None

    def _phrases_from_line(line: str) -> list[str]:
        raw = line.strip()
        if not raw.startswith("❌") and not raw.startswith("- ❌"):
            return []
        quoted = re.findall(r'"([^"]{2,60})"', raw)
        if quoted:
            return [q.strip().lower() for q in quoted if q.strip() and "—" not in q]
        clean = re.sub(r"^[-\s❌]+", "", raw).strip()
        for sep in (" — ", " – ", " ("):
            if sep in clean:
                clean = clean.split(sep, 1)[0].strip()
        clean = clean.strip('"').strip("'").strip().lower()
        if clean and "—" not in clean:
            return [clean]
        return []

    for line in text.split("\n"):
        if "## Don't say" in line or "## Banned" in line:
            section = "dont"
            continue
        if "## Numbers discipline" in line:
            section = "numbers"
            continue
        if "## Say with care" in line:
            section = "care"
            continue
        if line.startswith("## "):
            if section == "dont":
                section = None
            elif section in ("numbers", "care") and "## " in line:
                section = None
        if section in ("dont", "numbers", "care"):
            banned.extend(_phrases_from_line(line))

    seen: set[str] = set()
    out: list[str] = []
    for p in banned:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def merged_banned_terms(brand_id: str, markdown_banned: list[str]) -> list[str]:
    out = list(markdown_banned) + list(GLOBAL_FORBIDDEN_PHRASES)
    out.extend(BRAND_FORBIDDEN_PHRASES.get(brand_id, ()))
    out.extend(bible_banned_phrases(brand_id))
    # Dedupe preserve order
    seen: set[str] = set()
    unique: list[str] = []
    for term in out:
        key = term.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(term)
    return unique


def build_copy_contract(
    *,
    brand_id: str,
    template_id: str | None = None,
    post_type: str | None = None,
    lodge_title: str | None = None,
    user_brief: str | None = None,
) -> dict[str, Any]:
    tid = str(template_id or "").strip().lower()
    pt = str(post_type or "").strip().lower()
    spec = (
        TEMPLATE_COPY_CONTRACTS.get(tid)
        or TEMPLATE_COPY_CONTRACTS.get(pt)
        or {}
    )
    forbidden_phrases = list(GLOBAL_FORBIDDEN_PHRASES) + list(
        BRAND_FORBIDDEN_PHRASES.get(brand_id, ())
    )
    contract: dict[str, Any] = {
        "template_id": tid or None,
        "post_type": pt or None,
        "lodge_title": (lodge_title or "").strip() or None,
        "focus": spec.get("focus"),
        "preferred_terms": list(spec.get("preferred_terms") or ()),
        "forbidden_unless_in_brief": list(spec.get("forbidden_unless_in_brief") or ()),
        "required_families": list(spec.get("required_families") or ()),
        "forbidden_phrases": forbidden_phrases,
        "brief_subject_override": spec.get("brief_subject_override"),
    }
    if brand_id == "stick":
        contract["membership_offered"] = False
    else:
        contract["membership_offered"] = brand_id == "swing-shack"
    contract["brief_blob"] = " ".join(
        x for x in ((user_brief or ""), (lodge_title or "")) if x
    ).strip()
    return contract


def _families_in_text(text: str) -> set[str]:
    low = (text or "").lower()
    found: set[str] = set()
    for family, needles in EQUIPMENT_FAMILIES.items():
        for needle in needles:
            if needle in low:
                found.add(family)
                break
    return found


def check_copy_contract(candidate: str, ctx: dict[str, Any]) -> dict[str, Any]:
    contract = ctx.get("copy_contract") if isinstance(ctx.get("copy_contract"), dict) else {}
    if not contract:
        return {"passed": True, "reason": "no_contract"}
    cl = (candidate or "").lower()
    brief_blob = str(contract.get("brief_blob") or ctx.get("user_brief") or "").lower()

    for phrase in contract.get("forbidden_phrases") or []:
        if phrase.lower() in cl:
            return {"passed": False, "reason": f"forbidden_phrase:{phrase[:40]}"}

    if contract.get("membership_offered") is False:
        if re.search(r"\b(membership|join our membership|member benefits)\b", cl):
            if "membership" not in brief_blob and "member" not in brief_blob:
                return {"passed": False, "reason": "membership_not_offered"}

    for term in contract.get("forbidden_unless_in_brief") or []:
        t = str(term).lower()
        if t and t in cl and t not in brief_blob:
            return {"passed": False, "reason": f"off_topic:{term[:32]}"}

    required = contract.get("required_families") or []
    cap_f = _families_in_text(candidate)
    if "iron" in required and "putter" in cap_f and "putter" not in brief_blob:
        return {"passed": False, "reason": "off_topic:putter"}

    return {"passed": True, "reason": "ok"}


def check_poster_caption_alignment(
    candidate: str,
    ctx: dict[str, Any],
    copy_package: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(copy_package, dict):
        return {"passed": True, "reason": "no_copy_package"}
    hook = str(copy_package.get("poster_hook") or "").strip()
    if not hook:
        return {"passed": True, "reason": "no_poster_hook"}

    contract = ctx.get("copy_contract") if isinstance(ctx.get("copy_contract"), dict) else {}
    brief_blob = str(contract.get("brief_blob") or ctx.get("user_brief") or "")
    title = str(contract.get("lodge_title") or "")
    poster_context = f"{hook} {title} {brief_blob}"
    hook_f = _families_in_text(poster_context)
    cap_f = _families_in_text(candidate)
    brief_f = _families_in_text(brief_blob)

    if "iron" in hook_f or "iron" in brief_f or "iron" in (
        contract.get("required_families") or []
    ):
        if "putter" in cap_f and "putter" not in brief_f and "putter" not in hook_f:
            return {"passed": False, "reason": "iron_brief_putter_caption"}

    if "coaching" in hook_f and "putter" in cap_f and "coaching" not in cap_f:
        if "putter" not in brief_f:
            return {"passed": False, "reason": "coaching_hook_putter_caption"}

    from _lib.poster_copy import hook_grounded_in_caption  # noqa: PLC0415

    if not hook_grounded_in_caption(hook, candidate):
        # Only fail alignment when families clearly diverge
        if hook_f and cap_f and not (hook_f & cap_f) and "fitting_generic" not in cap_f:
            return {"passed": False, "reason": "hook_caption_topic_drift"}
    return {"passed": True, "reason": "ok"}


def vague_data_claim_in_text(text: str) -> str | None:
    low = (text or "").lower()
    for phrase in GLOBAL_FORBIDDEN_PHRASES:
        if phrase in low:
            return phrase
    return None


def allow_signature_line(brand_id: str, text: str) -> bool:
    from _lib.brand_bible import bible_copy_slice  # noqa: PLC0415

    cs = (bible_copy_slice(brand_id, "caption") or {}).get("copy_system") or {}
    low = (text or "").lower()
    for line in cs.get("signature_lines") or []:
        if isinstance(line, str) and line.strip().lower() in low:
            return True
    return False


def _dont_say_path(brand_id: str) -> Path:
    from os import environ

    runtime = Path(environ.get("DATA_DIR") or "/data/campaign-os") / "brand-directory" / brand_id
    repo = Path(__file__).resolve().parents[2] / "data" / "brand-directory" / brand_id
    base = runtime if runtime.exists() else repo
    return base / "voice" / "do-say-dont-say.md"


def gate_text(brand_id: str, text: str, *, ctx: dict | None = None) -> dict[str, Any]:
    """Phrase gate on arbitrary copy (caption or poster field). Substring phrase bans only."""
    candidate = text or ""
    if not candidate.strip():
        return {"passed": True, "reason": "empty_ok"}
    if "—" in candidate:
        return {"passed": False, "reason": "em_dash_banned"}
    cl = candidate.lower()
    md_path = _dont_say_path(brand_id)
    md_banned: list[str] = []
    if md_path.exists():
        md_banned = parse_dont_say_markdown(md_path.read_text(encoding="utf-8"))
    for phrase in merged_banned_terms(brand_id, md_banned):
        if phrase.lower() in cl:
            return {"passed": False, "reason": f"forbidden_phrase:{phrase[:40]}"}
    contract_ctx = ctx or {}
    contract = contract_ctx.get("copy_contract")
    if not isinstance(contract, dict):
        contract = build_copy_contract(brand_id=brand_id)
    if contract.get("membership_offered") is False:
        brief = str(contract.get("brief_blob") or contract_ctx.get("user_brief") or "").lower()
        if re.search(r"\b(membership|join our membership|member benefits|become a member)\b", cl):
            if "membership" not in brief and "member" not in brief:
                return {"passed": False, "reason": "membership_not_offered"}
    return {"passed": True, "reason": "ok"}


def gate_copy_package(
    brand_id: str,
    copy_package: dict[str, Any] | None,
    *,
    ctx: dict | None = None,
) -> dict[str, Any]:
    if not isinstance(copy_package, dict):
        return {"passed": True, "reason": "no_copy_package", "field": None}
    fields = (
        ("caption_body", copy_package.get("caption_body") or copy_package.get("body")),
        ("poster_hook", copy_package.get("poster_hook")),
        ("cta_line", copy_package.get("cta_line")),
    )
    for name, val in fields:
        if val:
            r = gate_text(brand_id, str(val), ctx=ctx)
            if not r["passed"]:
                return {"passed": False, "reason": r["reason"], "field": name}
    return {"passed": True, "reason": "ok", "field": None}
