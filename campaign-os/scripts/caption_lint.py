#!/usr/bin/env python3
"""Check a caption against a brand's bible. Deterministic, free, no model.

The brand bibles (`data/brand-directory/<brand>/BRAND-BIBLE.md`) end with a Part 4
block of machine rules. This reads that block, adds the universal rules from
`_system/BRAND-BIBLE-TEMPLATE.md` (Part 1), and reports what a machine can judge:
dashes, banned phrases, names, calls to action, sign-off, emoji, hashtags, caps,
currency, units, hook length, and lines copied from a sister brand.

    python3 campaign-os/scripts/caption_lint.py stick --text "Your caption here"
    python3 campaign-os/scripts/caption_lint.py swing-shack --file caption.txt --lane coaching
    echo "caption" | python3 campaign-os/scripts/caption_lint.py bag-drop
    python3 campaign-os/scripts/caption_lint.py stick --audit            # every real caption
    python3 campaign-os/scripts/caption_lint.py stick --audit --show cta-unlisted
    python3 campaign-os/scripts/caption_lint.py --list-rules

Three levels:
    HARD   a Gate hard fail. Rewrite before it ships.
    WARN   a mechanical slip the Gate scores (spacing, spelling variant, format).
    CHECK  something a human must verify (a figure, a stock claim, a name).

What it cannot judge, and leaves to a person: whether a fact is true, the swap test,
the idea, the tone, whether the humour lands. A clean result means "no mechanical
fault", not "good".

This does NOT replace `_lib/caption_copy_contract.gate_text`, which the generation
pipeline calls today. That gate reads the old `voice/do-say-dont-say.md` files; this
one reads the bibles. `lint()` is importable so the two can be joined once the owners
confirm the bibles.

While a bible sets `list_enforcement: warn`, hashtag, emoji and unlisted call-to-action
hits are warnings. Banned phrases, names, the sign-off, dashes and the other mechanical
bans stay hard fails. Set `list_enforcement: hard` when those lists are confirmed.

Exit status (single caption): 0 no hard fails, 1 hard fails, 2 bad usage.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import yaml

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO = CAMPAIGN_OS.parent
BRAND_DIR = REPO / "data" / "brand-directory"
BRANDS = ("stick", "swing-shack", "bag-drop")

HARD, WARN, CHECK = "HARD", "WARN", "CHECK"

# Words a brand uses for itself, for the "hook is the brand name" check and for
# spotting a mention of a sister brand.
BRAND_NAMES = {
    "stick": ["Stick", "STICK"],
    "swing-shack": ["Swing Shack", "SwingShack"],
    "bag-drop": ["The Bag Drop", "Bag Drop", "Bagdrop", "BagDrop"],
}

# --------------------------------------------------------------------------- #
# Universal rules (template Part 1, L1 to L7). A brand may add, never remove.
# --------------------------------------------------------------------------- #
_AP = r"['’]"

UNIVERSAL_BANNED: list[tuple[str, str, str]] = [
    # (label, regex, level)
    ("unlock", r"\bunlock\w*", HARD),
    ("elevate", r"\belevat(?:e|es|ed|ing)\b", HARD),
    ("level up", r"\blevel(?:s|ed|ing)? up\b", HARD),
    ("next level", r"\bnext level\b", HARD),
    ("game changer", r"\bgame[\s-]?chang\w*", HARD),
    ("seamless", r"\bseamless\w*", HARD),
    ("curated", r"\bcurated\b", HARD),
    ("tailored solutions", r"\btailored solutions?\b", HARD),
    ("state-of-the-art", r"\bstate[\s-]of[\s-]the[\s-]art\b", HARD),
    ("world-class", r"\bworld[\s-]class\b", HARD),
    ("premium experience", r"\bpremium experience\b", HARD),
    ("cutting-edge", r"\bcutting[\s-]edge\b", HARD),
    ("passionate about", r"\bpassionate about\b", HARD),
    ("one-stop", r"\bone[\s-]stop\b", HARD),
    ("look no further", r"\blook no further\b", HARD),
    ("we've got you covered", rf"\bwe(?:{_AP}ve| have)? got (?:you|u) covered\b", HARD),
    ("delve", r"\bdelv(?:e|es|ed|ing)\b", HARD),
    ("dive into", r"\bdiv(?:e|es|ed|ing) into\b", HARD),
    ("in today's fast-paced", rf"\bin today{_AP}?s fast[\s-]paced\b", HARD),
    ("whether you're a ... or a", rf"\bwhether you(?:{_AP}re| are) an? [^.!?\n]{{1,40}} or an? ", HARD),
    ("crushing it", r"\bcrush(?:ing|ed)? it\b", HARD),
    ("beast mode", r"\bbeast mode\b", HARD),
    ("Ready to / Looking to ...?", r"(?:^|[.!?\n]\s*)(?:ready|looking) to [^.!?\n]*\?", HARD),
    ("Imagine ...", r"(?:^|[.!?\n]\s*)imagine\b", HARD),
    ("Picture this", r"\bpicture this\b", HARD),
    ("Calling all golfers", r"\bcalling all \w+", HARD),
    ("Exciting news", r"\bexciting news\b", HARD),
    ("thrilled to announce", rf"\b(?:thrilled|delighted|excited|pleased) to (?:announce|share|introduce)\b", HARD),
    ("Say hello to", r"\bsay hello to\b", HARD),
    ("Introducing", r"(?:^|\n)\s*introducing\b", HARD),
    ("Happy [day]", r"(?:^|\n)\s*happy (?:mon|tues|wednes|thurs|fri|satur|sun)day\b", HARD),
    ("Stay tuned", r"\bstay tuned\b", HARD),
    ("Don't miss out", rf"\bdon{_AP}?t miss out\b", HARD),
    ("Hit us up", r"\bhit us up\b", HARD),
    ("Let that sink in", r"\blet that sink in\b", HARD),
    ("Tag a friend", r"\btag (?:a|your|some|someone|anyone|that)\b[^.!?\n]{0,25}\b(?:friend|mate|buddy|golfer|who|someone)\b|\btag someone\b", HARD),
    ("Comment YES", r"\bcomment (?:yes|below|your|if)\b", HARD),
    ("Like if you agree", r"\blike if you\b|\bdouble[\s-]?tap\b", HARD),
    ("Share with someone who", r"\bshare (?:this )?with (?:someone|a friend|a mate)\b", HARD),
    ("not just X, it's Y", rf"\bnot (?:just|only|merely)\b[^.!?\n]{{0,80}}?(?:,|;|:|—|-)?\s*(?:it{_AP}?s|it is|but)\b", HARD),
    ("bespoke", r"\bbespoke\b", WARN),
    ("journey", r"\bjourney\b", WARN),
]

# Language: text-speak and unambiguous typos (L1.3, L1.4).
TEXT_SPEAK = [
    (r"(?<![\w'’])u(?![\w'’])", "u"),
    (r"\bur\b", "ur"),
    (r"\blil\b", "lil"),
    (r"\bsesh\b", "sesh"),
    (r"\bgonna\b", "gonna"),
    (r"\bwanna\b", "wanna"),
    (r"\blol\b|\blmao\b", "lol"),
    (r"\bw/\s", "w/"),
    (r"\bw us\b", "w us"),
]
KNOWN_TYPOS = [
    (r"\bpreform\b", "preform (perform)"),
    (r"\bsneak peak\b", "sneak peak (peek)"),
    (r"\balot\b", "alot"),
    (r"\brecieve\w*", "recieve"),
    (r"\bseperate\w*", "seperate"),
    (r"\bdefinately\b", "definately"),
    (r"\boccured\b", "occured"),
    (r"\buntill\b", "untill"),
    (r"\b(?:Dont|dont|Doesnt|doesnt|Isnt|isnt|Cant|cant|Wasnt|wasnt|Couldnt|couldnt|Shouldnt|shouldnt|Wouldnt|wouldnt)\b", "missing apostrophe"),
]
US_SPELLING = [
    (r"\bcolor\w*", "colour"), (r"\bcenter\w*", "centre"), (r"\boptimi[sz]ed?\b|\boptimized\b", "optimise"),
    (r"\bmeters?\b", "metre"), (r"\bfavorite\w*", "favourite"), (r"\bgray\b", "grey"),
    (r"\borganize\w*", "organise"), (r"\banalyze\w*", "analyse"), (r"\brealize\w*", "realise"),
    (r"\btraveling\b", "travelling"), (r"\bdefense\b", "defence"),
]

# Initialisms and product codes that are normally written in capitals.
CAPS_OK = {"PGA", "LPGA", "TPI", "GPS", "USA", "USGA", "LED", "MKL", "KBS", "MCA", "LAB", "GTS", "STX", "STZ",
           "STG", "RTX", "AVX", "SIM", "PXG", "RPM", "MPH", "CCJ", "BBF", "FAQ", "VIP"}

RULES_INDEX = {
    "em-dash": ("L2.2", "No em or en dashes"),
    "banned-universal": ("L7", "Universal banned phrases and patterns"),
    "banned-brand": ("L7", "Brand banned phrases"),
    "name-wrong": ("L1.2", "Known wrong spelling of a name"),
    "name-case": ("L1.2", "Name spelled or capitalised differently from the registry"),
    "name-quarantined": ("L4.1", "A quarantined product name"),
    "name-unconfirmed": ("L1.2", "A name whose spelling is not confirmed"),
    "typo": ("L1.3", "A known typo or missing apostrophe"),
    "text-speak": ("L1.4", "Text-speak"),
    "us-spelling": ("L1.1", "US spelling in a British-English brand"),
    "exclamation": ("L2.4", "More exclamation marks than the brand allows"),
    "ellipsis": ("L2.5", "Ellipsis"),
    "caps": ("L2.6", "ALL CAPS beyond the limit"),
    "unicode-styled": ("L5.12", "Unicode styled letters (bold, italic)"),
    "double-space": ("L2.9", "Double or trailing spaces"),
    "markdown": ("L2.9", "Markdown characters that show as text"),
    "apostrophe": ("L2.3", "Apostrophe or quote style"),
    "hook-length": ("L5.1", "Hook longer than the limit"),
    "hook-opener": ("L5.1", "Hook is a greeting, 'We' or the brand name"),
    "hashtag-count": ("L5.8", "Too many hashtags"),
    "hashtag-allowed": ("L5.8", "Hashtag not in the allowed set or not CamelCase"),
    "emoji-count": ("L5.9", "More emoji than allowed"),
    "emoji-allowed": ("L5.9", "Emoji not on the allowed list"),
    "emoji-space": ("L5.9", "No space before an emoji"),
    "cta-multiple": ("L5.6", "More than one call to action"),
    "cta-unlisted": ("L5.6", "Call to action not on the approved list"),
    "cta-missing": ("L5.6", "No call to action where the lane requires one"),
    "signoff-variant": ("L5.7", "Sign-off spelled or punctuated differently"),
    "signoff-place": ("L5.7", "Sign-off is not the last line"),
    "signoff-missing": ("L5.7", "Required sign-off is missing"),
    "credit-format": ("L2.9", "Photo credit line does not match the pattern"),
    "currency": ("L3.2", "Price not in the brand's currency format"),
    "unit": ("L3.3", "Wrong or mixed units"),
    "date-time": ("L3.4", "Date or time format"),
    "link": ("L5.11", "A web address in a caption"),
    "condition-grade": ("L4.1", "A condition that is not on the scale"),
    "cross-brand-line": ("L6.2", "A line also used on a sister brand's feed"),
    "cross-brand-mention": ("L4.5", "Mentions a sister brand"),
    "lane-length": ("L5.3", "Outside the lane's word band"),
    "watch-words": ("L6.1", "More than one watch word"),
    "repeated-word": ("L1.3", "A word repeated twice in a row"),
    "figure": ("L3.5", "A figure that needs a Proof bank row"),
    "price-figure": ("L3.5", "A price that must match the listing"),
    "superlative": ("L4.2", "A superlative that needs evidence"),
    "stock-claim": ("L4.1", "A stock claim that needs a stock check"),
    "only-tags": ("L5", "Caption is only hashtags"),
}


# --------------------------------------------------------------------------- #
# Loading the brand's rules
# --------------------------------------------------------------------------- #
# Allow-lists the owners have not confirmed. While list_enforcement is "warn",
# these still report, but they are not Gate hard fails. Banned phrases, names,
# sign-off, dashes and the other mechanical bans stay hard.
_LIST_CODES = frozenset({
    "hashtag-count", "hashtag-allowed", "emoji-count", "emoji-allowed", "cta-unlisted",
})


def list_level(rules: dict, code: str, level: str) -> str:
    """Downgrade an unconfirmed allow-list hit from HARD to WARN."""
    if level == HARD and code in _LIST_CODES and str(rules.get("list_enforcement", "hard")).lower() == "warn":
        return WARN
    return level


def load_rules(brand: str, bible: Path | None = None) -> dict:
    path = Path(bible) if bible else BRAND_DIR / brand / "BRAND-BIBLE.md"
    if not path.exists():
        raise FileNotFoundError(f"No bible at {path}. Run from a checkout of the branch that has it.")
    text = path.read_text(encoding="utf-8")
    start = text.find("# PART 4")
    if start < 0:
        raise ValueError(f"{path} has no 'PART 4' heading")
    m = re.search(r"```yaml\n(.*?)\n```", text[start:], re.S)
    if not m:
        raise ValueError(f"{path} has no yaml block after PART 4")
    rules = yaml.safe_load(m.group(1)) or {}
    rules.setdefault("brand", brand)
    return rules


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #
_EMOJI_BASE = (
    r"[‼⁉↔-↪⌚-⏿Ⓜ▪-◾☀-➿"
    r"⤴⤵⬅-⭕〰〽㊗㊙\U0001F000-\U0001FAFF]"
)
EMOJI_RE = re.compile(_EMOJI_BASE + r"(?:[️⃣\U0001F3FB-\U0001F3FF]|‍" + _EMOJI_BASE + r")*")
HASHTAG_RE = re.compile(r"(?<![\w])#\w+")
HANDLE_RE = re.compile(r"(?<![\w.])@[\w.]+")
URL_RE = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+\.co\.za\S*", re.I)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
STYLED_RE = re.compile("[\U0001D400-\U0001D7FF]")


def plain_of(text: str) -> str:
    """The caption without hashtags, handles, web addresses and emails."""
    t = EMAIL_RE.sub(" ", text)
    t = URL_RE.sub(" ", t)
    t = HASHTAG_RE.sub(" ", t)
    t = HANDLE_RE.sub(" ", t)
    return t


def nfkc_styled(text: str) -> str:
    """Turn mathematical bold/italic letters back into plain letters for rule matching."""
    return "".join(unicodedata.normalize("NFKC", c) if STYLED_RE.match(c) else c for c in text)


def letters(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", EMOJI_RE.sub("", s).lower())


def snippet(text: str, start: int, end: int, pad: int = 22) -> str:
    a, b = max(0, start - pad), min(len(text), end + pad)
    s = text[a:b].replace("\n", " / ")
    return ("..." if a else "") + s + ("..." if b < len(text) else "")


def word_count(plain: str) -> int:
    return len(EMOJI_RE.sub(" ", plain).split())


_ALL_BRAND_WORDS = {n for names in BRAND_NAMES.values() for n in names} | {"Stick.paarl", "SwingShack"}


def phrase_regex(p: str) -> re.Pattern:
    """A brand banned-list entry as a regex. Plain phrases match whole words, any case.
    A brand's own name matches only as written, so the ordinary word "stick" is left alone."""
    p = str(p)
    flags = 0 if p in _ALL_BRAND_WORDS else re.I
    if p in ("up to", "as many as"):
        # Only a performance claim: "up to 25 meters", "as many as 6 shots". Not "up to 10th place".
        return re.compile(
            re.escape(p) + r"\s+\d[\d.,]*\s?(?:%|percent|m\b|met(?:er|re)s?|shots?|strokes?|yards?|yds|km|mph|rpm|points?)", re.I)
    pat = re.escape(p).replace(r"\ ", r"\s+")
    pat = pat.replace("\\'", _AP).replace("'", _AP)
    if re.match(r"\w", p):
        pat = r"\b" + pat
    if re.search(r"\w$", p):
        pat += r"(?:s|es|ed|ing)?\b" if len(p) >= 6 and " " not in p else r"\b"
    return re.compile(pat, flags)


def _inside_proper_noun(text: str, m: re.Match) -> bool:
    """A Capitalised single word sitting between other Capitalised words, mid-sentence."""
    if " " in m.group(0) or not m.group(0)[:1].isupper():
        return False
    prev = re.search(r"([A-Za-z][\w'-]*)\s+$", text[:m.start()])
    if not prev or not prev.group(1)[:1].isupper():
        return False
    before_prev = text[:prev.start()].rstrip()
    return bool(before_prev) and before_prev[-1] not in ".!?:\n"


# Names that are also ordinary words. A lower-case "stick" is only a misspelt brand name
# where it is plainly used as one ("at stick", "stick is coming", a line on its own).
AMBIGUOUS_NAMES = {"Stick"}


def _used_as_name(text: str, m: re.Match) -> bool:
    before = text[max(0, m.start() - 14):m.start()].lower()
    after = text[m.end():m.end() + 12]
    return bool(
        re.search(r"(?:\bat|@|\bwith|\bfrom|\bthrough|\bto|\bby|\bfor|\bvisit)\s*$", before)
        or re.match(r"\s*(?:[.,!?/:]|is\b|are\b|has\b|have\b|$)", after)
        or re.match(r"\s*\n", after)
    )


class Findings:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, code: str, level: str, msg: str, evidence: str = "") -> None:
        rid = RULES_INDEX.get(code, ("", ""))[0]
        self.items.append({"code": code, "rule": rid, "level": level, "message": msg, "evidence": evidence})


# --------------------------------------------------------------------------- #
# Calls to action
# --------------------------------------------------------------------------- #
_CTA_START = re.compile(
    r"^(?:book|dm|message|shop|view|visit|email|join|enter|call|whatsapp|order|reserve|claim|secure|pre-?order|"
    r"come (?:see|roll|try|test|browse|experience|in|and|down|visit|have|check)|"
    r"tell us|ask us|ask stick|drop us|hit the link|link in bio|find yours|find your fit|get fitted|get in touch|check (?:the|current|out)|"
    r"grab (?:yours|one|it)|swing by|pop (?:in|us)|head (?:down|to|over))\b",
    re.I,
)
_HOW_ONLY = {"link in bio", "hit the link in bio", "link in bio to shop"}


def _norm_cta(s: str) -> str:
    """Lower-case words only: no emoji, no punctuation, single spaces."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9@ ]", " ", EMOJI_RE.sub("", s).lower().replace("’", "'"))).strip()


def _matches_pattern(candidate: str, pattern: str) -> bool:
    """An allowed CTA with '*' in it matches any words in the gap: 'DM us to *.'"""
    parts = [_norm_cta(p) for p in pattern.split("*")]
    if not candidate.startswith(parts[0]):
        return False
    pos = len(parts[0])
    for mid in parts[1:-1]:
        i = candidate.find(mid, pos)
        if i < 0:
            return False
        pos = i + len(mid)
    last = parts[-1]
    return not last or (candidate.endswith(last) and len(candidate) - len(last) >= pos)


def find_ctas(plain: str, allowed: list[str]) -> tuple[list[str], list[str]]:
    """Return (listed, unlisted) call-to-action phrases found in the caption."""
    wild_allowed = [a for a in allowed if "*" in a]
    norm_allowed = {_norm_cta(a): a for a in allowed if "*" not in a}
    sentences = [s.strip() for s in re.split(r"\n+|(?<=[.!?])\s+", plain) if s.strip()]
    listed: list[str] = []
    unlisted: list[str] = []
    i = 0
    while i < len(sentences):
        s = sentences[i]
        body = EMOJI_RE.sub("", s).strip()
        if _CTA_START.match(body):
            cta = body
            # "Book a fitting. Link in bio." is one CTA with its "how".
            if i + 1 < len(sentences) and _norm_cta(sentences[i + 1]) in _HOW_ONLY:
                cta = f"{body} {sentences[i + 1].strip()}"
                i += 1
            n = _norm_cta(cta)
            hit = norm_allowed.get(n)
            if hit is None:
                hit = next((w for w in wild_allowed if _matches_pattern(n, w)), None)
            if hit is None:
                # An allowed phrase may sit inside a longer sentence, or the sentence inside it.
                for k, v in norm_allowed.items():
                    if k and (k in n or n in k) and len(min(k, n, key=len)) > 8:
                        hit = v
                        break
            (listed if hit else unlisted).append(cta)
        elif _norm_cta(s) in _HOW_ONLY:
            unlisted.append(s)
        i += 1
    return listed, unlisted


# --------------------------------------------------------------------------- #
# Cross-brand overlap
# --------------------------------------------------------------------------- #
_OVERLAP_CACHE: dict[str, list[tuple[str, str, str]]] = {}


def _norm_line(s: str) -> str:
    s = HASHTAG_RE.sub("", HANDLE_RE.sub("", s))
    s = re.sub(r"swing\s?shack|stick|the bag drop|bag\s?drop", "X", s, flags=re.I)
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]", "", EMOJI_RE.sub("", s).lower())).strip()


def _other_brand_lines(brand: str) -> list[tuple[str, str, str]]:
    """(normalised line, brand, date) for every caption on the other brands' audits."""
    key = brand
    if key in _OVERLAP_CACHE:
        return _OVERLAP_CACHE[key]
    out: list[tuple[str, str, str]] = []
    for other in BRANDS:
        if other == brand:
            continue
        p = BRAND_DIR / other / "feedback" / "instagram-audit.json"
        if not p.exists():
            continue
        for post in json.loads(p.read_text(encoding="utf-8")).get("posts", []):
            for line in (post.get("caption") or "").split("\n"):
                n = _norm_line(line)
                if len(n) > 20:
                    out.append((n, other, (post.get("timestamp") or "")[:10]))
    _OVERLAP_CACHE[key] = out
    return out


# --------------------------------------------------------------------------- #
# The linter
# --------------------------------------------------------------------------- #
def lint(brand: str, text: str, *, rules: dict | None = None, lane: str | None = None,
         when: dt.date | None = None, cross_brand: bool = True) -> dict:
    """Lint one caption. Returns {"brand", "hard", "warn", "check", "findings": [...]}."""
    rules = rules or load_rules(brand)
    F = Findings()
    raw = text.replace("\r\n", "\n").strip("\n")
    flat = nfkc_styled(raw)               # styled letters read as plain letters for matching
    plain = plain_of(flat)
    lines = [l for l in plain.split("\n")]
    nonblank = [l for l in lines if l.strip()]
    lane_rules = (rules.get("lanes") or {}).get(lane or "", {})

    # --- dashes (L2.2) ---
    for m in re.finditer(r"[—–]", raw):
        F.add("em-dash", HARD, "Em or en dash. Use a full stop, colon, comma or the word 'to'.", snippet(raw, m.start(), m.end()))

    # --- universal and brand banned phrases (L7) ---
    covered: list[tuple[int, int]] = []
    for label, pat, level in UNIVERSAL_BANNED:
        for m in re.finditer(pat, plain, re.I):
            F.add("banned-universal", level, f"Banned phrase: {label}", snippet(plain, m.start(), m.end()))
            covered.append(m.span())
            break
    for p in rules.get("banned_brand") or []:
        m = None
        for cand in phrase_regex(p).finditer(plain):
            if _inside_proper_noun(plain, cand):
                continue   # "BSI Premier Division" is a name, not the banned word
            if p in AMBIGUOUS_NAMES and not _used_as_name(plain, cand):
                continue   # "Stick with the plan" is the verb
            m = cand
            break
        if m and not any(a < m.end() and m.start() < b for a, b in covered):
            F.add("banned-brand", HARD, f"Banned for this brand: '{p}'", snippet(plain, m.start(), m.end()))

    # --- names (L1.2) ---
    so_key = letters(rules.get("signoff") or "")
    for w in rules.get("names_wrong") or []:
        if so_key and letters(w) == so_key:
            continue   # a sign-off variant is reported once, as signoff-variant
        m = re.search(r"(?<![\w])" + re.escape(w) + r"(?![\w])", plain)
        if m:
            F.add("name-wrong", HARD, f"Known wrong spelling: '{w}'", snippet(plain, m.start(), m.end()))
    for q in rules.get("quarantined_names") or []:
        m = re.search(re.escape(q), plain, re.I)
        if m:
            F.add("name-quarantined", HARD, f"Quarantined product name: '{q}'", snippet(plain, m.start(), m.end()))
    wrong = {w.lower() for w in (rules.get("names_wrong") or [])}
    for name in rules.get("names_exact") or []:
        pat = re.compile(r"(?<![\w@#/.-])" + re.escape(name).replace(r"\ ", r"\s+") + r"(?![\w-])", re.I)
        for m in pat.finditer(plain):
            if m.group(0) != name and m.group(0).lower() not in wrong:
                if name in AMBIGUOUS_NAMES and not _used_as_name(plain, m):
                    continue
                F.add("name-case", HARD, f"Write '{name}', not '{m.group(0)}'", snippet(plain, m.start(), m.end()))
                break
    for n in rules.get("unknown_names_block") or []:
        m = re.search(r"\b" + re.escape(n) + r"\b", plain, re.I)
        if m:
            F.add("name-unconfirmed", CHECK, f"'{m.group(0)}': the supplier's spelling is not confirmed", snippet(plain, m.start(), m.end()))
            break
    if rules.get("cross_brand_mention_requires_approval"):
        own = {n.lower() for n in BRAND_NAMES.get(brand, [])}
        for b, names in BRAND_NAMES.items():
            if b == brand:
                continue
            for n in names:
                if n.lower() in own:
                    continue
                m = re.search(r"\b" + re.escape(n) + r"\b", plain, re.I)
                if m:
                    F.add("cross-brand-mention", CHECK, f"Mentions '{n}': needs the approver's yes in the current message", snippet(plain, m.start(), m.end()))
                    break

    # --- language (L1) ---
    for pat, label in TEXT_SPEAK:
        m = re.search(pat, plain)
        if m:
            F.add("text-speak", HARD, f"Text-speak: '{label}'", snippet(plain, m.start(), m.end()))
    for pat, label in KNOWN_TYPOS:
        m = re.search(pat, plain)
        if m:
            F.add("typo", HARD, f"Typo: {label}", snippet(plain, m.start(), m.end()))
    if str(rules.get("language", "")).lower().startswith("en-za"):
        for pat, uk in US_SPELLING:
            m = re.search(pat, plain, re.I)
            if m:
                F.add("us-spelling", WARN, f"US spelling '{m.group(0)}': South African English uses '{uk}'", snippet(plain, m.start(), m.end()))
    m = re.search(r"\b(\w+)\s+\1\b", plain, re.I)
    if m and not m.group(1).isdigit() and m.group(1).lower() not in {"that", "had"}:
        F.add("repeated-word", WARN, f"Repeated word: '{m.group(0)}'", snippet(plain, m.start(), m.end()))

    # --- punctuation and layout (L2) ---
    ex_total = plain.count("!")
    ex_max = int(rules.get("exclamation_max_per_post", 1))
    first = next((l for l in nonblank), "")
    if "!!" in plain:
        F.add("exclamation", HARD, "Two exclamation marks in a row", snippet(plain, plain.index("!!"), plain.index("!!") + 2))
    elif ex_total > ex_max:
        F.add("exclamation", HARD, f"{ex_total} exclamation marks, the limit is {ex_max}", "")
    if first.count("!") > int(rules.get("exclamation_max_in_headline", 0)):
        F.add("exclamation", HARD, "Exclamation mark in the first line (headline)", first[:80])
    if re.search(r"\.\.\.|…", plain):
        m = re.search(r"\.\.\.|…", plain)
        F.add("ellipsis", WARN, "Ellipsis", snippet(plain, m.start(), m.end()))
    if STYLED_RE.search(raw) and rules.get("unicode_styled_letters") == "forbidden":
        m = STYLED_RE.search(raw)
        F.add("unicode-styled", HARD, "Unicode bold or italic letters: unreadable to screen readers and unsearchable", raw[m.start():m.start() + 24])
    if "  " in raw.replace("\n", " ") or any(l != l.rstrip() for l in raw.split("\n")):
        F.add("double-space", WARN, "Double space or trailing space", "")
    m = re.search(r"\*\*[^*]+\*\*|\*[A-Za-z][^*\n]*\*", raw)
    if m:
        F.add("markdown", WARN, "Asterisks show as literal text on Instagram", snippet(raw, m.start(), m.end()))
    if rules.get("apostrophe") == "curly" and re.search(r"(?<=\w)'(?=\w)", plain):
        m = re.search(r"(?<=\w)'(?=\w)", plain)
        F.add("apostrophe", WARN, "Straight apostrophe: use a curly one", snippet(plain, m.start(), m.end()))
    if str(rules.get("quotes", "")).startswith("double") and '"' in plain:
        m = re.search(r'"', plain)
        F.add("apostrophe", WARN, "Straight double quote: use curly quotes", snippet(plain, m.start(), m.end()))

    # --- ALL CAPS (L2.6) ---
    strict = rules.get("all_caps_line_max_words") is not None
    limit = 1 if strict else 3            # a run of this many caps words in a row is allowed
    for ln in nonblank:
        run: list[str] = []
        worst: list[str] = []
        for t in re.findall(r"[A-Za-z][A-Za-z0-9.'\-]*", ln):
            alpha = re.sub(r"[^A-Za-z]", "", t)
            if len(alpha) >= 3 and t.isupper() and not re.search(r"\d", t) and alpha not in CAPS_OK:
                run.append(t)
                if len(run) > len(worst):
                    worst = list(run)
            else:
                run = []
        if len(worst) > limit:
            F.add("caps", HARD, f"ALL CAPS: {' '.join(worst)}", ln.strip()[:80])
            break

    # --- hook (L5.1) ---
    hook_max = rules.get("hook_max_chars")
    if first:
        hook = EMOJI_RE.sub("", first).strip()
        if hook_max and len(hook) > int(hook_max):
            F.add("hook-length", HARD, f"First line is {len(hook)} characters, the limit is {hook_max}", hook[:90])
        opens = re.match(r"(?:happy|hello|hi|hey|good (?:morning|afternoon|evening)|welcome|we\b|we[’']re\b|we[’']ve\b)", hook, re.I)
        names = sorted(BRAND_NAMES.get(brand, []), key=len, reverse=True)
        if opens or any(hook.lower().startswith(n.lower()) for n in names):
            F.add("hook-opener", HARD, "The hook opens with a greeting, 'We' or the brand name", hook[:60])

    # --- hashtags (L5.8) ---
    tags = HASHTAG_RE.findall(raw)
    if tags:
        hmax = rules.get("hashtags_max")
        if hmax is not None and len(tags) > int(hmax):
            F.add("hashtag-count", list_level(rules, "hashtag-count", HARD), f"{len(tags)} hashtags, the limit is {hmax}", " ".join(tags[:8]))
        elif len(tags) > 5:
            F.add("hashtag-count", list_level(rules, "hashtag-count", HARD), f"{len(tags)} hashtags is a wall", " ".join(tags[:8]))
        allowed = {a.lower(): a for a in (rules.get("hashtags_allowed") or [])}
        bad = []
        for t in tags:
            core = t.lstrip("#")
            if allowed and core.lower() not in allowed:
                bad.append(f"{t} (not on the allowed list)")
            elif allowed and rules.get("hashtags_camelcase") and core != allowed[core.lower()]:
                bad.append(f"{t} (write #{allowed[core.lower()]})")
        if bad:
            F.add("hashtag-allowed", list_level(rules, "hashtag-allowed", HARD), "Hashtags: " + "; ".join(bad[:4]), "")
        if not letters(plain):
            F.add("only-tags", WARN, "The caption is only hashtags", "")

    # --- emoji (L5.9) ---
    ems = list(EMOJI_RE.finditer(raw))
    if ems:
        emax = rules.get("emoji_max_per_post")
        allowed_e = {a[0] for a in (rules.get("emoji_allowed") or []) if a}
        stray = [e.group(0) for e in ems if e.group(0)[0] not in allowed_e]
        if emax is not None:
            if int(emax) == 0:
                # None allowed, except the few on the allowed list.
                if stray:
                    F.add("emoji-allowed", list_level(rules, "emoji-allowed", HARD),
                          "No emoji allowed here" + (" except " + "".join(rules["emoji_allowed"]) if allowed_e else ""),
                          "".join(dict.fromkeys(stray)))
            else:
                if len(ems) > int(emax):
                    F.add("emoji-count", list_level(rules, "emoji-count", HARD), f"{len(ems)} emoji, the limit is {emax}", "".join(e.group(0) for e in ems[:6]))
                if stray and allowed_e:
                    F.add("emoji-allowed", list_level(rules, "emoji-allowed", HARD), "Emoji not on the allowed list: " + "".join(dict.fromkeys(stray)), "")
        if rules.get("emoji_requires_space_before"):
            for e in ems:
                if e.start() > 0 and not raw[e.start() - 1].isspace() and not EMOJI_RE.fullmatch(raw[e.start() - 1]):
                    F.add("emoji-space", WARN, "No space before the emoji", snippet(raw, e.start(), e.end()))
                    break

    # --- calls to action (L5.6) ---
    allowed_ctas = rules.get("ctas_allowed") or []
    listed, unlisted = find_ctas(plain, allowed_ctas)
    cta_max = int(rules.get("cta_max", 1))
    n_cta = len(listed) + len(unlisted)
    if n_cta > cta_max:
        F.add("cta-multiple", HARD, f"{n_cta} calls to action, the limit is {cta_max}", " | ".join((listed + unlisted)[:3]))
    for u in unlisted:
        F.add("cta-unlisted", list_level(rules, "cta-unlisted", HARD), "Call to action not on the approved list", u[:90])
    if lane_rules.get("cta_required") and n_cta == 0:
        F.add("cta-missing", WARN, f"The '{lane}' lane needs a call to action", "")

    # --- sign-off (L5.7) ---
    so = rules.get("signoff") or ""
    if so:
        tail = [l for l in raw.split("\n") if l.strip()]
        credit = re.compile(rules.get("credit_line_pattern") or r"$^")
        while tail and (re.fullmatch(r"(?:\s*#\w+)+\s*", tail[-1]) or credit.match(tail[-1].strip())
                        or re.match(r"photo credit", tail[-1].strip(), re.I)):
            if re.match(r"photo credit", tail[-1].strip(), re.I) and not credit.match(tail[-1].strip()):
                F.add("credit-format", WARN, "Photo credit line does not match the pattern", tail[-1].strip()[:60])
            tail.pop()
        want = letters(so)
        found = False
        for idx, ln in enumerate(tail):
            if want and want in letters(ln):
                found = True
                if letters(ln) != want:
                    F.add("signoff-variant", HARD, f"The sign-off sits inside another line. It must be exactly '{so}' on its own line.", ln.strip()[:80])
                elif ln.strip() != so:
                    F.add("signoff-variant", HARD, f"Sign-off must read exactly '{so}'", ln.strip()[:80])
                elif idx != len(tail) - 1:
                    F.add("signoff-place", HARD, "The sign-off must be the last line", ln.strip()[:80])
        need = lane_rules.get("signoff_required", rules.get("signoff_required", False))
        if need and not found:
            F.add("signoff-missing", WARN, f"Missing the sign-off '{so}'", "")

    # --- currency (L3.2) ---
    if rules.get("currency_format"):
        for m in re.finditer(r"\bR\s?\d[\d\s,.]*\d|\bR\s?\d", plain):
            tok = m.group(0).rstrip(" ,.")
            if re.fullmatch(r"R\d{1,3}(?:,\d{3})*", tok):
                continue
            F.add("currency", HARD, f"Price '{tok}' is not in the format {rules['currency_format']}", snippet(plain, m.start(), m.end()))
        m = re.search(r"\b\d{3,}\s?/\s?pm\b", plain, re.I)
        if m:
            F.add("currency", HARD, "A price with no R and no clear period", snippet(plain, m.start(), m.end()))

    # --- units (L3.3) ---
    if re.search(r"\bmph\b", plain, re.I) and re.search(r"km/?h", plain, re.I):
        F.add("unit", WARN, "mph and km/h in the same caption", "")
    if re.search(r"\byards?\b|\byds?\b", plain, re.I) and re.search(r"\bmet(?:er|re)s?\b|\b\d\s?m\b", plain, re.I):
        F.add("unit", WARN, "Yards and metres in the same caption", "")
    if rules.get("unit_system") == "metres" and re.search(r"\byards?\b|\byds?\b", plain, re.I):
        F.add("unit", WARN, "Yards: this brand uses metres", "")
    if rules.get("speed_unit") == "km/h" and re.search(r"\bmph\b", plain, re.I):
        F.add("unit", WARN, "mph: this brand uses km/h", "")

    # --- dates and times (L3.4) ---
    if re.search(r"\b\d{1,2}(?:st|nd|rd|th)\b", plain):
        m = re.search(r"\b\d{1,2}(?:st|nd|rd|th)\b", plain)
        F.add("date-time", WARN, "Date with an ordinal: write '1 May', not '1st May'", snippet(plain, m.start(), m.end()))
    if rules.get("time_format") == "HH:mm" and re.search(r"\b\d{1,2}\s?(?:am|pm)\b", plain, re.I):
        m = re.search(r"\b\d{1,2}\s?(?:am|pm)\b", plain, re.I)
        F.add("date-time", WARN, "Time in 12-hour form: this brand uses 24-hour (15:00)", snippet(plain, m.start(), m.end()))
    if rules.get("time_range_separator") == " to " and re.search(r"\d{1,2}[:h]\d{2}\s?[-–]\s?\d{1,2}[:h]\d{2}", plain):
        m = re.search(r"\d{1,2}[:h]\d{2}\s?[-–]\s?\d{1,2}[:h]\d{2}", plain)
        F.add("date-time", WARN, "Time range with a dash: write '15:00 to 18:00'", snippet(plain, m.start(), m.end()))

    # --- links (L5.11) ---
    if rules.get("links_in_caption") == "forbidden" and URL_RE.search(flat):
        m = URL_RE.search(flat)
        F.add("link", WARN, "A web address in a caption is not clickable: say 'Link in bio'", m.group(0)[:50])

    # --- condition scale (Bag Drop) ---
    grades = rules.get("condition_grades_allowed")
    if grades:
        for m in re.finditer(r"Condition:\s*([A-Za-z]+)", plain):
            if m.group(1) not in grades:
                F.add("condition-grade", HARD, f"Condition '{m.group(1)}' is not on the scale {grades}", snippet(plain, m.start(), m.end()))

    # --- lane length (L5.3) ---
    if lane_rules:
        wc = word_count(plain)
        lo, hi = lane_rules.get("min_words"), lane_rules.get("max_words")
        if lo is not None and wc < int(lo) or hi is not None and wc > int(hi):
            F.add("lane-length", WARN, f"{wc} words, the '{lane}' lane runs {lo} to {hi}", "")

    # --- watch words ---
    ww = rules.get("watch_words_max_one") or []
    hits = [w for w in ww if re.search(r"\b" + re.escape(w) + r"\b", plain, re.I)]
    if len(hits) > 1:
        F.add("watch-words", WARN, "More than one watch word: " + ", ".join(hits), "")

    # --- things a person must verify (L3.5, L4.1, L4.2) ---
    figs = re.findall(r"\d[\d,.]*\s?(?:%|percent|m\b|metres|meters|km/h|mph|rpm|shots|yards|yds|°)", plain, re.I)
    if figs and rules.get("numbers_require_proof_row", True):
        F.add("figure", CHECK, "Every figure needs a row in the Proof bank: " + ", ".join(dict.fromkeys(f.strip() for f in figs))[:80], "")
    prices = re.findall(r"\bR\s?\d[\d,. ]*", plain)
    if prices:
        F.add("price-figure", CHECK, "Check each price against the live listing or price list: " + ", ".join(dict.fromkeys(p.strip() for p in prices))[:80], "")
    m = re.search(r"\b(?:the best|best in|first and only|the first|number one|#1|leading|premier|the only)\b", plain, re.I)
    if m:
        F.add("superlative", CHECK, "A superlative needs evidence a stranger could check", snippet(plain, m.start(), m.end()))
    m = re.search(r"\b(?:in stock|available (?:at|through|for fitting|for pre-?order|now|in[- ]store)|pre-?order|just landed|has landed|in store now|now at)\b", plain, re.I)
    if m:
        F.add("stock-claim", CHECK, "Stock claim: confirm the item is in stock today", snippet(plain, m.start(), m.end()))

    # --- the same line on a sister brand (L6.2) ---
    days = rules.get("sister_brand_line_overlap_days")
    if cross_brand and days:
        ref = when or dt.date.today()
        seen = set()
        for ln in nonblank:
            n = _norm_line(ln)
            if len(n) <= 20 or _CTA_START.match(EMOJI_RE.sub("", ln).strip()):
                continue   # an approved call to action is meant to repeat across brands
            for other_n, other_brand, other_date in _other_brand_lines(brand):
                if other_n == n and (other_brand, n) not in seen:
                    try:
                        gap = abs((ref - dt.date.fromisoformat(other_date)).days)
                    except ValueError:
                        gap = 0
                    if gap <= int(days):
                        seen.add((other_brand, n))
                        F.add("cross-brand-line", HARD, f"Same line on {other_brand} ({other_date}), inside {days} days", ln.strip()[:80])

    # Order: hard, warn, check; stable within a level.
    order = {HARD: 0, WARN: 1, CHECK: 2}
    items = sorted(F.items, key=lambda i: order[i["level"]])
    return {
        "brand": brand,
        "lane": lane,
        "words": word_count(plain),
        "hard": sum(i["level"] == HARD for i in items),
        "warn": sum(i["level"] == WARN for i in items),
        "check": sum(i["level"] == CHECK for i in items),
        "findings": items,
    }


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def print_result(res: dict, text: str) -> None:
    verdict = "FAIL" if res["hard"] else "PASS"
    print(f"{res['brand']}  lane={res['lane'] or '-'}  {res['words']} words")
    print(f"{verdict}: {res['hard']} hard, {res['warn']} warnings, {res['check']} to check\n")
    for i in res["findings"]:
        ev = f'   "{i["evidence"]}"' if i["evidence"] else ""
        print(f"  {i['level']:<5} {i['rule']:<5} {i['code']:<17} {i['message']}")
        if ev:
            print("       " + ev.strip())
    if not res["findings"]:
        print("  No mechanical faults found. A person still has to judge the facts, idea and tone.")
    elif not res["hard"]:
        print("\n  No hard fails. A person still has to judge the facts, idea and tone.")


def audit(brand: str, rules: dict, show: str | None, examples: int, as_json: bool,
          since: str | None = None, until: str | None = None) -> int:
    p = BRAND_DIR / brand / "feedback" / "instagram-audit.json"
    if not p.exists():
        print(f"No audit at {p}. Run /audit-social {brand} first.", file=sys.stderr)
        return 2
    posts = [x for x in json.loads(p.read_text(encoding="utf-8")).get("posts", []) if x.get("caption")]
    posts.sort(key=lambda x: x.get("timestamp", ""))
    if since:
        posts = [x for x in posts if x["timestamp"][:10] >= since]
    if until:
        posts = [x for x in posts if x["timestamp"][:10] <= until]
    if not posts:
        print("No captions in that range.", file=sys.stderr)
        return 2
    per_rule: dict[str, list[tuple[str, dict, str]]] = defaultdict(list)
    results = []
    for post in posts:
        when = dt.date.fromisoformat(post["timestamp"][:10])
        r = lint(brand, post["caption"], rules=rules, when=when)
        results.append((post, r))
        for f in r["findings"]:
            per_rule[f["code"]].append((post["timestamp"][:10], f, str(post.get("id"))))
    n = len(posts)
    hard_posts = sum(1 for _, r in results if r["hard"])
    clean = sum(1 for _, r in results if not r["hard"] and not r["warn"])
    if as_json:
        print(json.dumps({"brand": brand, "captions": n, "with_hard": hard_posts, "clean": clean,
                          "by_rule": {k: len({i for _, _, i in v}) for k, v in per_rule.items()},
                          "results": [{"id": po.get("id"), "date": po["timestamp"][:10], **{k: r[k] for k in ("hard", "warn", "check", "findings")}} for po, r in results]},
                         indent=1, ensure_ascii=False))
        return 0
    if show:
        hits = per_rule.get(show, [])
        print(f"{brand}: rule '{show}' fired on {len(hits)} findings\n")
        for d, f, _ in hits:
            print(f"  {d}  {f['message']}")
            if f["evidence"]:
                print(f"            \"{f['evidence']}\"")
        return 0
    span = f"{posts[0]['timestamp'][:10]} to {posts[-1]['timestamp'][:10]}"
    print(f"{brand}: {n} captions ({span}) linted against {BRAND_DIR.name}/{brand}/BRAND-BIBLE.md")
    print(f"  {hard_posts} ({100 * hard_posts // n}%) have at least one hard fail")
    print(f"  {clean} ({100 * clean // n}%) have no hard fail and no warning")
    print(f"  {sum(r['hard'] for _, r in results)} hard findings in all, {sum(r['warn'] for _, r in results)} warnings, {sum(r['check'] for _, r in results)} to check\n")
    print(f"  {'level':<6}{'rule':<7}{'code':<19}{'captions':>9}  what it caught")
    order = {HARD: 0, WARN: 1, CHECK: 2}
    rows = sorted(per_rule.items(), key=lambda kv: (order[kv[1][0][1]["level"]], -len({i for _, _, i in kv[1]})))
    for code, hits in rows:
        lvl = hits[0][1]["level"]
        count = len({i for _, _, i in hits})
        print(f"  {lvl:<6}{RULES_INDEX.get(code, ('', ''))[0]:<7}{code:<19}{count:>9}  {RULES_INDEX.get(code, ('', ''))[1]}")
        for d, f, _ in hits[:examples]:
            ev = f["evidence"] or f["message"]
            print(f"{'':<34}e.g. {d}: {ev[:70]}")
    print("\n  Use --show <code> to list every hit for a rule and check the linter is right.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Lint a caption against a brand's bible.")
    ap.add_argument("brand", nargs="?", choices=BRANDS)
    ap.add_argument("--text")
    ap.add_argument("--file")
    ap.add_argument("--lane")
    ap.add_argument("--date", help="ISO date the caption will post (for the sister-brand rule)")
    ap.add_argument("--bible", help="path to a BRAND-BIBLE.md (default: the brand's own)")
    ap.add_argument("--audit", action="store_true", help="lint every caption in the brand's feed audit")
    ap.add_argument("--show", help="with --audit: list every hit for one rule code")
    ap.add_argument("--examples", type=int, default=1)
    ap.add_argument("--since", help="with --audit: only captions posted on or after this ISO date")
    ap.add_argument("--until", help="with --audit: only captions posted on or before this ISO date")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--list-rules", action="store_true")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):   # emoji in a Windows console
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if a.list_rules:
        for code, (rid, desc) in RULES_INDEX.items():
            print(f"{code:<20}{rid:<6}{desc}")
        return 0
    if not a.brand:
        ap.error("a brand is required")
    rules = load_rules(a.brand, Path(a.bible) if a.bible else None)
    if a.audit:
        return audit(a.brand, rules, a.show, a.examples, a.json, a.since, a.until)
    if a.text is not None:
        text = a.text
    elif a.file:
        text = Path(a.file).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        ap.error("give --text, --file, stdin or --audit")
    when = dt.date.fromisoformat(a.date) if a.date else None
    res = lint(a.brand, text, rules=rules, lane=a.lane, when=when)
    if a.json:
        print(json.dumps(res, indent=1, ensure_ascii=False))
    else:
        print_result(res, text)
    return 1 if res["hard"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (BrokenPipeError, OSError):   # `| head` closed the pipe
        sys.exit(0)
