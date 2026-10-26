"""Railway/Docker COPY fails when tracked symlinks point at missing targets."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SKIP_PREFIXES = (".git/", "node_modules/")


def _is_skipped(rel_posix: str) -> bool:
    return any(
        rel_posix.startswith(prefix) or f"/{prefix}" in rel_posix for prefix in _SKIP_PREFIXES
    )


def test_no_dangling_symlinks_in_repo():
    """Matches: find . -xtype l -not -path './.git/*' -not -path './node_modules/*'."""
    dangling: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_symlink():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if _is_skipped(rel):
            continue
        if not path.exists():
            dangling.append(rel)
    assert dangling == [], f"dangling symlinks: {sorted(dangling)}"
