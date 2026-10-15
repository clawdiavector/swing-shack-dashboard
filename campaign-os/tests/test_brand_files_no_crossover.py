"""Swing Shack and Stick brand files must not name each other (or Bag Drop).

Christelle, 2026-10-15: "Swing Shack does only Swing Shack, Stick does only
Stick. Bag Drop can run with both. Stick is in Paarl, Swing Shack is in JHB,
Bag Drop is online. All three are run by us but are individual companies, so
even if stuff is connected behind the scenes no one knows about it."

These files feed caption prompts, poster CTAs and image prompts. Ban lines
(a rule telling the writer NOT to name another brand) are allowed. Bag Drop
is not checked: it may name both.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

BRAND_DIR = Path(__file__).resolve().parents[2] / "data" / "brand-directory"

# "stick" is also an ordinary golf word, so only the capitalised brand counts.
OTHER = {
    "swing-shack": re.compile(r"\bStick\b|stickgolf|stick\.paarl|(?i:\bPaarl\b|bag\s*drop)"),
    "stick": re.compile(r"swing\s*shack|swingshack|Johannesburg|\bJHB\b|bag\s*drop", re.I),
}
# Fields whose value is a standard identifier, not copy (Africa/Johannesburg is SA's time zone).
SKIP_KEYS = (".timezone",)
BAN_LINE = re.compile(r"❌|\bnever\b|\bunless\b|\bwithout\b|\bbanned\b|\bdon'?t\b|\bnot\b", re.I)

FILES = [
    "README.md",
    "knowledge.json",
    "calendar_config.json",
    "story-brands.json",
    "visual-spec/platforms.json",
    "voice/tone-rules.md",
    "voice/punctuation-rules.md",
    "voice/do-say-dont-say.md",
    "copy/ctas.md",
    "copy/headlines.md",
]


def _strings(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        def walk(o, where=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    yield from walk(v, f"{where}.{k}")
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    yield from walk(v, f"{where}[{i}]")
            elif isinstance(o, str):
                yield where, o
        yield from walk(json.loads(text))
    else:
        for n, line in enumerate(text.splitlines(), 1):
            yield f"line {n}", line


@pytest.mark.parametrize("brand", list(OTHER))
@pytest.mark.parametrize("rel", FILES)
def test_brand_file_names_no_sister_brand(brand, rel):
    path = BRAND_DIR / brand / rel
    if not path.is_file():
        pytest.skip(f"{brand}/{rel} does not exist")
    leaks = [
        f"{where}: {s[:160]}"
        for where, s in _strings(path)
        if OTHER[brand].search(s) and not BAN_LINE.search(s) and not where.endswith(SKIP_KEYS)
    ]
    assert leaks == []
