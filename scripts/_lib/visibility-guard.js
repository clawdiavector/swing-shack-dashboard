// Step 97/98 Visibility Guard — canonical JavaScript implementation.
// Pure function. No I/O, no logging, no persistence. Caller passes
// operatorVisibilityState (defaults to 'unknown'). Disputes are sticky at
// the caller; this module never records state. Mirrored in Python at
// campaign-os/_lib/visibility_guard.py; JS is canonical.

'use strict';

const VALID_OPERATOR_STATES = ['visible', 'not-visible', 'disputed', 'unknown'];
const BLOCKING_STATES = new Set(['VISIBILITY_DISPUTED', 'EXTERNAL_STATE_DISPUTED']);

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
  // Treat undefined / null / empty string as "no value supplied" -> default to 'unknown'.
  // Treat any other non-valid state as invalid input -> fail closed.
  const opProvided = operatorVisibilityState !== undefined && operatorVisibilityState !== null && operatorVisibilityState !== '';
  if (opProvided && !VALID_OPERATOR_STATES.includes(operatorVisibilityState)) {
    return { state: 'VISIBILITY_DISPUTED', allowStateChange: false, reason: `invalid operator state: ${operatorVisibilityState}` };
  }
  const opState = opProvided ? operatorVisibilityState : 'unknown';
  if (opState === 'not-visible' || opState === 'disputed') {
    return { state: 'VISIBILITY_DISPUTED', allowStateChange: false, reason: `operator reports ${operatorVisibilityState}` };
  }
  if (!canonicalState || canonicalState === 'missing') {
    return { state: 'NO_OBJECT', allowStateChange: false, reason: 'no canonical object' };
  }
  if (!apiState || apiState === 'missing') {
    return { state: 'EXTERNAL_STATE_DISPUTED', allowStateChange: false, reason: 'canonical exists but API missing' };
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