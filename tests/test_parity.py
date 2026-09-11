# Step 97/98 Visibility Guard — JS/Python parity test.
# Uses the same compact fixture table as tests/test_visibility_guard.js.
# JS is canonical; Python adapter must match every row.
#
# t26: was a module-scope script that called sys.exit at import, which
# killed the entire root tests/ collection (INTERNALERROR / exit 3).
# Logic is now a pytest test; `python3 tests/test_parity.py` still works.

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TABLE = [
    # [api, canonical, operator, expected state]
    # ── Locked locked-behaviour matrix ─────────────────────────────────────
    # 1. unknown default does not block normal operations.
    ("exists", "exists", "unknown", "OK"),
    # 2. visible operator does not block.
    ("exists", "exists", "visible", "OK"),
    # 3. not-visible operator blocks.
    ("exists", "exists", "not-visible", "VISIBILITY_DISPUTED"),
    # 4. disputed operator blocks.
    ("exists", "exists", "disputed", "VISIBILITY_DISPUTED"),
    # 5. API says exists, canonical says missing (no operator dispute) -> API_ONLY, do NOT block.
    ("exists", "missing", "unknown", "API_ONLY"),
    # 6. Same but with 'absent' as the canonical value (locked spec from Step 99 audit).
    ("exists", "absent", "unknown", "API_ONLY"),
    # 7. Canonical exists but API is missing -> EXTERNAL_STATE_DISPUTED.
    ("missing", "exists", "unknown", "EXTERNAL_STATE_DISPUTED"),
    # 8. Both canonical and API missing -> NO_OBJECT.
    ("missing", "missing", "unknown", "NO_OBJECT"),
    # 9. Canonical says absent, API missing -> NO_OBJECT.
    ("missing", "absent", "unknown", "NO_OBJECT"),
    # 10. Operator dispute overrides any canonical/API agreement.
    ("exists", "missing", "not-visible", "VISIBILITY_DISPUTED"),
    # 11. Invalid operator value fails closed.
    ("exists", "exists", "garbage", "VISIBILITY_DISPUTED"),
    # 12. All-falsy sentinel -> defaults to unknown, falsy api+canonical -> NO_OBJECT.
    ("", "", "unknown", "NO_OBJECT"),
    # 13. All-falsy everything -> same.
    ("", "", "", "NO_OBJECT"),
]

js_script = """
const VG = require('./scripts/_lib/visibility-guard');
const table = JSON.parse(process.argv[1]);
const out = table.map(row => {
  const [api, canonical, operator] = row;
  const apiVal = api === '' ? '' : (api === 'undefined' ? undefined : api);
  const canonicalVal = canonical === '' ? '' : (canonical === 'undefined' ? undefined : canonical);
  const operatorVal = operator === '' ? '' : (operator === 'undefined' ? undefined : operator);
  const g = VG.assertNoVisibilityDispute({apiState: apiVal, canonicalState: canonicalVal, operatorVisibilityState: operatorVal});
  return g.state;
});
process.stdout.write(JSON.stringify(out));
"""


def _run_parity():
    """Returns a list of mismatch strings. Empty list == parity holds."""
    js_results = json.loads(
        subprocess.check_output(
            ["node", "-e", js_script, json.dumps([list(r[:3]) for r in TABLE])],
            cwd=str(REPO),
        )
    )
    sys.path.insert(0, str(REPO / "campaign-os" / "_lib"))
    from visibility_guard import assert_no_visibility_dispute

    problems = []
    for row, js_state in zip(TABLE, js_results):
        api, canonical, operator, expected = row
        py_state = assert_no_visibility_dispute(
            api or "", canonical or "", operator or ""
        )["state"]
        if py_state != js_state:
            problems.append(
                f"PARITY MISMATCH [{api}/{canonical}/{operator}]: "
                f"js={js_state} py={py_state}"
            )
        elif js_state != expected:
            problems.append(
                f"EXPECTATION MISMATCH [{api}/{canonical}/{operator}]: "
                f"got {js_state} expected {expected}"
            )
    return problems


def test_visibility_guard_js_python_parity():
    if shutil.which("node") is None:
        pytest.skip("node not on PATH; JS/Python visibility-guard parity not checked")
    problems = _run_parity()
    assert not problems, "\n".join(problems)


if __name__ == "__main__":
    probs = _run_parity()
    for p in probs:
        print(p)
    print(f"Total: {len(TABLE)}, Failed: {len(probs)}")
    sys.exit(1 if probs else 0)
