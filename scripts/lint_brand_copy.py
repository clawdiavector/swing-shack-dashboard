#!/usr/bin/env python3
"""
lint_brand_copy.py — fail-fast lint for the brand-directory published-copy lane.

Standing rule (Campaign OS MEMORY.md / PROMPT.md rule 4):
    "Em dash banned. Use pipes `|` / commas `,` / full stops / colons `:` in
    published copy."

This script enforces that rule for the published-copy scope:
    data/brand-directory/*/copy/*.md
    data/brand-directory/*/examples/*.md

(Plus the README headline/heading only — em-dashes in `voice/` meta-prose and
README headings are out-of-scope by design; if you want to expand the rule
to those directories, edit SCOPES below. See the "Open next-tick ideas"
section of the latest nightshift report for the wider discussion.)

Usage:
    .venv/bin/python scripts/lint_brand_copy.py              # scan all
    .venv/bin/python scripts/lint_brand_copy.py <path> ...    # scan specific
    .venv/bin/python scripts/lint_brand_copy.py --strict      # fail on en-dash + NBSP too

Exit codes:
    0  clean
    1  found at least one em-dash (or any banned char with --strict)
    2  bad CLI args

Other banned characters:
    U+2013 EN DASH –   often typos where em-dash was intended
    U+00A0 NO-BREAK SPACE   sneaks in from Word/PowerPoint pastes

Recipe refs:
    - Campaign OS nightshift pitfall #71 (lint your own files before pushing)
    - Campaign OS nightshift pitfall #74 (scan recurring violations
      cross-brand, not just the one file flagged)

Verified on 2026-07-31:
    stick/copy/headlines.md (2 em), stick/copy/ctas.md (1)
    bag-drop/copy/headlines.md (3), bag-drop/copy/ctas.md (1)
    bag-drop/examples/good.md (1), bag-drop/examples/bad.md (16)
    swing-shack/copy/headlines.md (2), swing-shack/copy/ctas.md (1)
    swing-shack/examples/good.md (5)
    takomo/copy/ctas.md (4)
    Total: 36 em-dashes across 10 files (the bug class is alive and well).
"""

from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent

# Banned characters and their names (for error message clarity)
EM_DASH = ("\u2014", "em-dash")
EN_DASH = ("\u2013", "en-dash")
NBSP = ("\u00a0", "non-breaking space")

# Scope: only published-copy paths in the brand-directory tree.
# Each (directory-segments, file-glob) tuple is OR'd together.
SCOPES = [
    ("copy", "*.md"),
    ("examples", "*.md"),
]


def _is_in_scope(path: Path) -> bool:
    """True iff path lives under data/brand-directory/<brand>/<scope-dir>/<file>."""
    parts = path.parts
    try:
        # require "data/brand-directory" prefix and "copy" or "examples"
        bd_idx = parts.index("brand-directory")
    except ValueError:
        return False
    # Need at least brand + <scope-dir>/file after brand-directory
    if len(parts) - bd_idx < 3:
        return False
    scope_dir = parts[bd_idx + 2]
    return scope_dir in ("copy", "examples")


def _iter_files(paths: Iterable[Path]) -> Iterable[Path]:
    for p in paths:
        if p.is_file() and p.suffix == ".md":
            if _is_in_scope(p):
                yield p
        elif p.is_dir():
            for sub in p.rglob("*.md"):
                if _is_in_scope(sub):
                    yield sub


def _scan_file(path: Path, banned: list[tuple[str, str]]) -> list[tuple[int, str, str, str]]:
    """Return list of (line_no, char_name, char_hex, line_text) violations."""
    violations = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return violations
    for i, line in enumerate(text.splitlines(), 1):
        for ch, name in banned:
            if ch in line:
                violations.append((i, name, f"U+{ord(ch):04X}", line.rstrip()))
    return violations


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Lint published brand-directory copy for banned characters "
                    "(em-dash always; en-dash + NBSP with --strict)."
    )
    parser.add_argument(
        "paths", nargs="*", type=Path,
        help="Files or directories to scan. Default: scan the entire repo."
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Also fail on en-dash (U+2013) and non-breaking space (U+00A0). "
             "Default: em-dash only, since the standing rule names em-dash "
             "specifically."
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Print only summary (no per-line violations)."
    )
    args = parser.parse_args(argv)

    banned = [EM_DASH]
    if args.strict:
        banned.extend([EN_DASH, NBSP])

    # Resolve scan paths
    if args.paths:
        scan_roots = [p.resolve() for p in args.paths]
    else:
        scan_roots = [ROOT]

    files = list(_iter_files(scan_roots))
    if not files:
        print("lint_brand_copy: no in-scope markdown files found.", file=sys.stderr)
        return 2

    total_violations = 0
    files_with_violations = 0
    for f in sorted(files):
        v = _scan_file(f, banned)
        if not v:
            continue
        files_with_violations += 1
        total_violations += len(v)
        if not args.quiet:
            try:
                rel = f.relative_to(ROOT)
            except ValueError:
                rel = f
            print(f"\n{rel}:")
            for line_no, name, hex_code, text in v:
                excerpt = text.strip()[:90]
                print(f"  L{line_no}: {name} ({hex_code})  {excerpt}")

    # Summary (always)
    print(
        f"\nlint_brand_copy: scanned {len(files)} files, "
        f"{total_violations} violation(s) in {files_with_violations} file(s)."
    )
    if args.strict:
        print("  (strict mode: em-dash + en-dash + NBSP)")
    else:
        print("  (default: em-dash only — re-run with --strict for wider scope)")

    return 1 if total_violations > 0 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
