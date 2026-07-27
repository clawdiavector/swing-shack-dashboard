# Step 97/98 Visibility Guard — JS/Python parity test.
# Uses the same compact fixture table as tests/test_visibility_guard.js.
# JS is canonical; Python adapter must match every row.

import subprocess
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TABLE = [
    # [api, canonical, operator, expected state]
    # ── Locked locked-behaviour matrix ─────────────────────────────────────
    # 1. unknown default does not block normal operations.
    ('exists', 'exists', 'unknown', 'OK'),
    # 2. visible operator does not block.
    ('exists', 'exists', 'visible', 'OK'),
    # 3. not-visible operator blocks.
    ('exists', 'exists', 'not-visible', 'VISIBILITY_DISPUTED'),
    # 4. disputed operator blocks.
    ('exists', 'exists', 'disputed', 'VISIBILITY_DISPUTED'),
    # 5. API says exists, canonical says missing (no operator dispute) -> API_ONLY, do NOT block.
    ('exists', 'missing', 'unknown', 'API_ONLY'),
    # 6. Same but with 'absent' as the canonical value (locked spec from Step 99 audit).
    ('exists', 'absent', 'unknown', 'API_ONLY'),
    # 7. Canonical exists but API is missing -> EXTERNAL_STATE_DISPUTED.
    ('missing', 'exists', 'unknown', 'EXTERNAL_STATE_DISPUTED'),
    # 8. Both canonical and API missing -> NO_OBJECT.
    ('missing', 'missing', 'unknown', 'NO_OBJECT'),
    # 9. Canonical says absent, API missing -> NO_OBJECT.
    ('missing', 'absent', 'unknown', 'NO_OBJECT'),
    # 10. Operator dispute overrides any canonical/API agreement.
    ('exists', 'missing', 'not-visible', 'VISIBILITY_DISPUTED'),
    # 11. Invalid operator value fails closed.
    ('exists', 'exists', 'garbage', 'VISIBILITY_DISPUTED'),
    # 12. All-falsy sentinel -> defaults to unknown, falsy api+canonical -> NO_OBJECT.
    ('', '', 'unknown', 'NO_OBJECT'),
    # 13. All-falsy everything -> same.
    ('', '', '', 'NO_OBJECT'),
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

js_results = json.loads(subprocess.check_output(['node', '-e', js_script, json.dumps([list(r[:3]) for r in TABLE])], cwd=str(REPO)))

sys.path.insert(0, str(REPO / 'campaign-os' / '_lib'))
from visibility_guard import assert_no_visibility_dispute

failed = 0
for (row, js_state) in zip(TABLE, js_results):
    api, canonical, operator, expected = row
    # Use the sentinel '' literally for both runtimes; the guard treats '' as 'unknown'.
    api_val = api if api else ''
    canonical_val = canonical if canonical else ''
    operator_val = operator if operator else ''
    py_state = assert_no_visibility_dispute(api_val, canonical_val, operator_val)['state']
    if py_state != js_state:
        print(f'PARITY MISMATCH [{api}/{canonical}/{operator}]: js={js_state} py={py_state}')
        failed += 1
    elif js_state != expected:
        print(f'EXPECTATION MISMATCH [{api}/{canonical}/{operator}]: got {js_state} expected {expected}')
        failed += 1

print(f'Total: {len(TABLE)}, Failed: {failed}')
sys.exit(1 if failed > 0 else 0)