#!/usr/bin/env python3
"""Lint bible-visual colour language against palette/brand.json (primary/accent/neutrals only)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HUES = [
    "black",
    "white",
    "grey",
    "gray",
    "navy",
    "blue",
    "teal",
    "cyan",
    "mint",
    "green",
    "lime",
    "yellow",
    "amber",
    "gold",
    "orange",
    "brass",
    "red",
    "crimson",
    "maroon",
    "pink",
    "magenta",
    "purple",
    "violet",
    "brown",
    "beige",
    "cream",
    "charcoal",
    "slate",
]
FIELDS = (
    "visual_philosophy",
    "philosophy",
    "look_and_feel_keywords",
    "composition_rules",
)
SKIP_DIRS = {"_system", "copy-banks"}


def hex_to_hue(h: str) -> set[str]:
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    mx, mn = max(r, g, b), min(r, g, b)
    v = mx / 255
    s = 0 if mx == 0 else (mx - mn) / mx
    if s < 0.12:
        if v < 0.35:
            return {"black", "charcoal", "grey", "gray", "slate"}
        if v > 0.8:
            return {"white", "cream", "beige"}
        return {"grey", "gray", "slate"}
    if mx == r:
        hdeg = (60 * ((g - b) / (mx - mn))) % 360
    elif mx == g:
        hdeg = 60 * (2 + (b - r) / (mx - mn))
    else:
        hdeg = 60 * (4 + (r - g) / (mx - mn))
    hdeg %= 360
    out: set[str] = set()
    if hdeg < 15 or hdeg >= 345:
        out |= {"red", "crimson", "maroon", "pink"}
    elif hdeg < 45:
        out |= {"orange", "brass", "brown", "amber", "gold", "beige"}
    elif hdeg < 70:
        out |= {"yellow", "amber", "gold", "lime"}
    elif hdeg < 100:
        out |= {"lime", "green"}
    elif hdeg < 160:
        out |= {"green", "mint", "teal"}
    elif hdeg < 200:
        out |= {"teal", "cyan", "mint", "blue"}
    elif hdeg < 250:
        out |= {"blue", "navy", "slate"}
    elif hdeg < 290:
        out |= {"purple", "violet"}
    else:
        out |= {"magenta", "pink", "purple"}
    if v < 0.3:
        if 200 <= hdeg < 290:
            out |= {"black", "charcoal", "navy"}
        else:
            out |= {"black", "charcoal"}
    return out


def allowed_hues(brand_dir: Path) -> set[str] | None:
    pal_path = brand_dir / "palette" / "brand.json"
    if not pal_path.is_file():
        return None
    raw = json.loads(pal_path.read_text(encoding="utf-8"))
    allowed: set[str] = set()
    for src in (raw.get("palette") or {}).values():
        if isinstance(src, dict):
            if src.get("hex"):
                allowed |= hex_to_hue(str(src["hex"]))
            for w in re.findall(r"[a-z]+", str(src.get("name", "")).lower()):
                if w in HUES:
                    allowed.add(w)
    return allowed


def lint_brand(brand_dir: Path) -> list[str]:
    bible = brand_dir / "bible-visual.json"
    if not bible.is_file():
        return []
    allowed = allowed_hues(brand_dir)
    if allowed is None:
        return [f"{brand_dir.name}: no palette/brand.json"]
    data = json.loads(bible.read_text(encoding="utf-8"))
    violations: list[str] = []
    found: dict[str, list[str]] = {}
    for field in FIELDS:
        val = data.get(field)
        text = " ".join(val) if isinstance(val, list) else str(val or "")
        for word in re.findall(r"[a-z]+", text.lower()):
            if word in HUES and word not in allowed:
                found.setdefault(word, []).append(field)
    for word, fields in sorted(found.items()):
        violations.append(
            f"{brand_dir.name}: off-palette hue '{word}' in {sorted(set(fields))}"
        )
    return violations


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: lint_brand_visual.py <repo-root> [brand-dir ...]", file=sys.stderr)
        return 2
    root = Path(argv[1])
    brands_root = root / "data" / "brand-directory"
    if len(argv) > 2:
        brand_dirs = [Path(p) for p in argv[2:]]
    else:
        brand_dirs = sorted(
            p
            for p in brands_root.iterdir()
            if p.is_dir() and p.name not in SKIP_DIRS
        )
    rc = 0
    for bd in brand_dirs:
        if bd.name in SKIP_DIRS:
            continue
        for line in lint_brand(bd):
            print(line)
            rc = 1
        if (bd / "bible-visual.json").is_file() and not lint_brand(bd):
            print(f"{bd.name}: ok")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
