// Step 97/98 Visibility Guard — compact canonical test suite.
// Same compact fixture table used by parity test in tests/test_parity.py.
// JS implementation is canonical; Python adapter must match every row.

'use strict';

const VG = require('../scripts/_lib/visibility-guard');

const TABLE = [
  // [api, canonical, operator, expected state, expected blocksAction]
  ['exists', 'exists', 'unknown', 'OK', false],
  ['exists', 'exists', 'visible', 'OK', false],
  ['exists', 'exists', 'not-visible', 'VISIBILITY_DISPUTED', true],
  ['exists', 'exists', 'disputed', 'VISIBILITY_DISPUTED', true],
  ['exists', 'missing', 'unknown', 'NO_OBJECT', false],
  ['missing', 'exists', 'unknown', 'EXTERNAL_STATE_DISPUTED', true],
  ['exists', 'missing', 'not-visible', 'VISIBILITY_DISPUTED', true],
  ['', '', 'unknown', 'NO_OBJECT', false],
  ['exists', 'exists', 'garbage', 'VISIBILITY_DISPUTED', true], // invalid input fails closed
  [undefined, undefined, undefined, 'NO_OBJECT', false],
];

let passed = 0;
let failed = 0;
for (const [api, canonical, operator, expectedState, expectedBlocks] of TABLE) {
  const g = VG.assertNoVisibilityDispute({ apiState: api, canonicalState: canonical, operatorVisibilityState: operator });
  const stateOk = g.state === expectedState;
  const blocksAny = VG.blocksAction(g, 'reconcile');
  const blocksOk = blocksAny === expectedBlocks;
  if (stateOk && blocksOk) {
    passed++;
  } else {
    failed++;
    console.error(`FAIL [api=${api},canonical=${canonical},op=${operator}]: got state=${g.state} (want ${expectedState}), blocksAny=${blocksAny} (want ${expectedBlocks})`);
  }
}

// Read-only actions remain allowed during dispute
const disputeGuard = VG.assertNoVisibilityDispute({ apiState: 'exists', canonicalState: 'exists', operatorVisibilityState: 'disputed' });
if (VG.blocksAction(disputeGuard, 'read') === false && VG.blocksAction(disputeGuard, 'analytics') === false && VG.blocksAction(disputeGuard, 'planning') === false && VG.blocksAction(disputeGuard, 'reconcile') === true) {
  passed++;
} else {
  failed++;
  console.error('FAIL: dispute must block reconcile but allow read/analytics/planning');
}

// Determinism: same inputs, same outputs
const a = VG.assertNoVisibilityDispute({ apiState: 'exists', canonicalState: 'exists', operatorVisibilityState: 'not-visible' });
const b = VG.assertNoVisibilityDispute({ apiState: 'exists', canonicalState: 'exists', operatorVisibilityState: 'not-visible' });
if (a.state === b.state && a.allowStateChange === b.allowStateChange && a.reason === b.reason) {
  passed++;
} else {
  failed++;
  console.error('FAIL: same inputs must produce identical outputs');
}

console.log(`Total: ${passed + failed}, Passed: ${passed}, Failed: ${failed}`);
process.exit(failed > 0 ? 1 : 0);