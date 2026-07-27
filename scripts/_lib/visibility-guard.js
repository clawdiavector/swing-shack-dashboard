// Step 97/98 Visibility Guard — canonical JavaScript implementation.
// Pure function. No I/O, no logging, no persistence. Caller passes
// operatorVisibilityState (defaults to 'unknown'). Disputes are sticky at
// the caller; this module never records state. Mirrored in Python at
// campaign-os/_lib/visibility_guard.py; JS is canonical.

'use strict';

const VALID_OPERATOR_STATES = ['visible', 'not-visible', 'disputed', 'unknown'];
const BLOCKING_STATES = new Set(['VISIBILITY_DISPUTED', 'EXTERNAL_STATE_DISPUTED']);
// "Missing-like" values for apiState / canonicalState: empty/undefined/null + 'missing' + 'absent'.
// All are treated as "not present". Only truthy non-missing values (e.g. 'exists') count as present.
const ABSENT_LIKE = v => v === undefined || v === null || v === '' || v === 'missing' || v === 'absent';

const STATE_CHANGING_ACTIONS = [
  'reconcile',
  'delete',
  'duplicate-skip',
  'mark-live',
  'destructive-state-reconciliation',
];

function assertNoVisibilityDispute(context) {
  if (!context || typeof context !== 'object') {
    return { state: 'NO_OBJECT', allowStateChange: false, reason: 'invalid context' };
  }
  const { apiState, canonicalState, operatorVisibilityState } = context;
  // Operator state: missing-like -> 'unknown' (no opinion). Any other invalid value fails closed.
  if (!ABSENT_LIKE(operatorVisibilityState) && !VALID_OPERATOR_STATES.includes(operatorVisibilityState)) {
    return { state: 'VISIBILITY_DISPUTED', allowStateChange: false, reason: `invalid operator state: ${operatorVisibilityState}` };
  }
  const opState = ABSENT_LIKE(operatorVisibilityState) ? 'unknown' : operatorVisibilityState;
  if (opState === 'not-visible' || opState === 'disputed') {
    return { state: 'VISIBILITY_DISPUTED', allowStateChange: false, reason: `operator reports ${operatorVisibilityState}` };
  }
  // Canonical is the authority. Canonical missing + API missing -> NO_OBJECT.
  const canonicalMissing = ABSENT_LIKE(canonicalState);
  const apiMissing = ABSENT_LIKE(apiState);
  if (canonicalMissing && apiMissing) {
    return { state: 'NO_OBJECT', allowStateChange: false, reason: 'no canonical object' };
  }
  // Canonical exists but API does not -> EXTERNAL_STATE_DISPUTED.
  if (!canonicalMissing && apiMissing) {
    return { state: 'EXTERNAL_STATE_DISPUTED', allowStateChange: false, reason: 'canonical exists but API missing' };
  }
  // Canonical missing but API exists -> API_ONLY (canonical is authority: nothing to change here,
  // but flag the discrepancy). No operator dispute -> do NOT block.
  if (canonicalMissing && !apiMissing) {
    return { state: 'API_ONLY', allowStateChange: true, reason: 'api confirms existence; canonical has no record' };
  }
  return { state: 'OK', allowStateChange: true, reason: 'canonical and API agree' };
}

function blocksAction(guard, action) {
  if (!BLOCKING_STATES.has(guard.state)) return false;
  return STATE_CHANGING_ACTIONS.includes(action);
}

module.exports = {
  assertNoVisibilityDispute,
  blocksAction,
  VALID_OPERATOR_STATES,
  BLOCKING_STATES,
  STATE_CHANGING_ACTIONS,
};