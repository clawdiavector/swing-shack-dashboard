"""No module-scope helper may reference a free `io` — regression for 1f95768."""

from __future__ import annotations

import ast
import pathlib

LAYER_ROOT = pathlib.Path(__file__).resolve().parents[2] / "_lib" / "jobs"


def _bound_names(fn: ast.AST) -> set[str]:
    bound = {a.arg for a in fn.args.args + fn.args.kwonlyargs}
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            bound |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            bound.add(node.target.id)
        elif isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            bound.add(node.target.id)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            bound |= {
                i.optional_vars.id
                for i in node.items
                if isinstance(i.optional_vars, ast.Name)
            }
    return bound


def test_no_unbound_io_reads():
    offenders = []
    for path in sorted(LAYER_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if "io" in _bound_names(fn):
                continue
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "io"
                    and node.attr in ("read", "write")
                ):
                    offenders.append(f"{path.name}:{node.lineno} {fn.name} io.{node.attr}")
    assert not offenders, "unbound io in: " + ", ".join(offenders)
