#!/usr/bin/env python3
"""Static AST scan: which `_lib` modules does app.py import that are not on disk?

Never imports those modules. Reports only — does not create, stub, or scaffold.

Dynamic `_lib` loads (string-built import calls) are not counted. If one is
added later, this scanner will not see it.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(3)


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return (REPO_ROOT / p).resolve()


def _display(path: Path, given: str) -> str:
    """Stable, cwd-independent label for reports."""
    given_p = Path(given)
    if not given_p.is_absolute():
        return given.replace("\\", "/")
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def collect_lib_imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "_lib":
                for alias in node.names:
                    if alias.name != "*":
                        names.add(alias.name)
            elif mod.startswith("_lib."):
                first = mod[len("_lib."):].split(".")[0]
                if first:
                    names.add(first)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name.startswith("_lib."):
                    first = name[len("_lib."):].split(".")[0]
                    if first:
                        names.add(first)
    return names


def present_modules(lib_dir: Path) -> set[str]:
    found: set[str] = set()
    if not lib_dir.is_dir():
        return found
    for py in lib_dir.glob("*.py"):
        if py.name == "__init__.py":
            continue
        found.add(py.stem)
    return found


def orphan_pyc_files(campaign_os: Path) -> list[str]:
    orphans: list[str] = []
    if not campaign_os.is_dir():
        return orphans
    for pyc in campaign_os.rglob("__pycache__/*.pyc"):
        stem = pyc.name.split(".")[0]
        source = pyc.parent.parent / f"{stem}.py"
        if not source.is_file():
            try:
                orphans.append(pyc.resolve().relative_to(REPO_ROOT).as_posix())
            except ValueError:
                orphans.append(pyc.as_posix())
    return sorted(orphans)


def scan(
    sources: list[str] | None = None,
    lib_dir: str = "campaign-os/_lib",
) -> dict:
    src_labels = sources if sources else ["campaign-os/app.py"]
    src_paths = [_resolve(s) for s in src_labels]
    lib_path = _resolve(lib_dir)

    imported: set[str] = set()
    for label, path in zip(src_labels, src_paths):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            raise RuntimeError(f"unreadable source: {label}: {e}") from e
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as e:
            raise RuntimeError(f"SyntaxError in {label}: {e}") from e
        imported |= collect_lib_imports(tree)

    present = present_modules(lib_path)
    missing = sorted(imported - present)
    unreferenced = sorted(present - imported)
    campaign_os = lib_path.parent if lib_path.name == "_lib" else REPO_ROOT / "campaign-os"
    orphans = orphan_pyc_files(campaign_os)
    strategy_page = (lib_path / "strategy_page.html").is_file()

    ok = (not missing) and (not orphans)
    return {
        "ok": ok,
        "lib_dir": _display(lib_path, lib_dir),
        "sources": [_display(p, lab) for p, lab in zip(src_paths, src_labels)],
        "imported_count": len(imported),
        "present_count": len(present),
        "missing_count": len(missing),
        "lib_modules_missing": missing,
        "lib_modules_present": sorted(present),
        "unreferenced": unreferenced,
        "orphan_pyc": orphans,
        "strategy_page_present": strategy_page,
    }


def _human_report(report: dict, warn_only: bool) -> str:
    missing = report["lib_modules_missing"]
    orphans = report["orphan_pyc"]
    lines: list[str] = []
    prefix = "WARNING: " if warn_only else ""

    if missing:
        lines.append(
            f"{prefix}{report['missing_count']} imported _lib module(s) missing: "
            + " ".join(missing)
        )
        if not warn_only:
            for name in missing:
                lines.append(f"  {name}")
    else:
        if not warn_only:
            lines.append("imported _lib modules: all present")

    if orphans:
        lines.append(f"{prefix}orphan .pyc (masking hazard): " + " ".join(orphans))
    elif not warn_only:
        lines.append("orphan_pyc: (none)")

    if not report["strategy_page_present"]:
        lines.append(f"{prefix}strategy_page.html is missing")
    elif not warn_only:
        lines.append("strategy_page_present: true")

    if not warn_only:
        lines.append(
            f"imported_count: {report['imported_count']}  "
            f"present_count: {report['present_count']}  "
            f"missing_count: {report['missing_count']}"
        )
        if report["unreferenced"]:
            lines.append("unreferenced: " + " ".join(report["unreferenced"]))
        lines.append(f"strategy_page_present: {str(report['strategy_page_present']).lower()}")

    if warn_only and not lines:
        lines.append("WARNING: no _lib module gaps")

    return "\n".join(lines) + "\n"


def _exit_code(report: dict) -> int:
    if report["lib_modules_missing"]:
        return 1
    if report["orphan_pyc"]:
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(
        description="Report _lib modules imported by app.py that are missing on disk.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a single JSON object to stdout.",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Always exit 0; prefix human findings with WARNING:.",
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        metavar="PATH",
        help="Source file to scan (repeatable). Default: campaign-os/app.py",
    )
    parser.add_argument(
        "--lib-dir",
        default="campaign-os/_lib",
        help="Directory of _lib/*.py files. Default: campaign-os/_lib",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Exit code only, no stdout.",
    )
    args = parser.parse_args(argv)

    try:
        report = scan(sources=args.sources, lib_dir=args.lib_dir)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3

    if not args.quiet:
        if args.json:
            json.dump(report, sys.stdout, indent=2)
            sys.stdout.write("\n")
        else:
            sys.stdout.write(_human_report(report, warn_only=args.warn_only))

    if args.warn_only:
        return 0
    return _exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
