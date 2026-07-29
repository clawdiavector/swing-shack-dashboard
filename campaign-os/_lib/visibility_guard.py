# Step 97/98 Visibility Guard — Python language adapter.
# Mirrors scripts/_lib/visibility-guard.js. JS is canonical. Same inputs,
# same outputs, same locked behaviour. No I/O, no persistence, no subprocess.

VALID_OPERATOR_STATES = ('visible', 'not-visible', 'disputed', 'unknown')
BLOCKING_STATES = {'VISIBILITY_DISPUTED', 'EXTERNAL_STATE_DISPUTED'}
STATE_CHANGING_ACTIONS = frozenset({
    'reconcile', 'delete', 'duplicate-skip',
    'mark-live', 'destructive-state-reconciliation',
})


def assert_no_visibility_dispute(apiState, canonicalState, operatorVisibilityState):
    def absent_like(v): return v is None or v in ('', 'missing', 'absent')
    if not absent_like(operatorVisibilityState) and operatorVisibilityState not in VALID_OPERATOR_STATES:
        return {'state': 'VISIBILITY_DISPUTED', 'allowStateChange': False,
                'reason': f'invalid operator state: {operatorVisibilityState}'}
    op_state = 'unknown' if absent_like(operatorVisibilityState) else operatorVisibilityState
    if op_state in ('not-visible', 'disputed'):
        return {'state': 'VISIBILITY_DISPUTED', 'allowStateChange': False,
                'reason': f'operator reports {operatorVisibilityState}'}
    canonical_missing = absent_like(canonicalState)
    api_missing = absent_like(apiState)
    if canonical_missing and api_missing:
        return {'state': 'NO_OBJECT', 'allowStateChange': False, 'reason': 'no canonical object'}
    if not canonical_missing and api_missing:
        return {'state': 'EXTERNAL_STATE_DISPUTED', 'allowStateChange': False, 'reason': 'canonical exists but API missing'}
    if canonical_missing and not api_missing:
        # API_ONLY: canonical is authority, no object to manage; flag discrepancy, do not block.
        return {'state': 'API_ONLY', 'allowStateChange': True, 'reason': 'api confirms existence; canonical has no record'}
    return {'state': 'OK', 'allowStateChange': True, 'reason': 'canonical and API agree'}


def blocks_action(guard, action):
    return guard['state'] in BLOCKING_STATES and action in STATE_CHANGING_ACTIONS