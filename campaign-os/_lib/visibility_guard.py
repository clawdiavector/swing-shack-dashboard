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
    # Treat None / '' as "no value supplied" -> default to 'unknown'.
    # Treat any other non-valid state as invalid input -> fail closed.
    op_provided = operatorVisibilityState is not None and operatorVisibilityState != ''
    if op_provided and operatorVisibilityState not in VALID_OPERATOR_STATES:
        return {'state': 'VISIBILITY_DISPUTED', 'allowStateChange': False,
                'reason': f'invalid operator state: {operatorVisibilityState}'}
    op_state = operatorVisibilityState if op_provided and operatorVisibilityState in VALID_OPERATOR_STATES else 'unknown'
    if op_state in ('not-visible', 'disputed'):
        return {'state': 'VISIBILITY_DISPUTED', 'allowStateChange': False,
                'reason': f'operator reports {operatorVisibilityState}'}
    if not canonicalState or canonicalState == 'missing':
        return {'state': 'NO_OBJECT', 'allowStateChange': False,
                'reason': 'no canonical object'}
    if not apiState or apiState == 'missing':
        return {'state': 'EXTERNAL_STATE_DISPUTED', 'allowStateChange': False,
                'reason': 'canonical exists but API missing'}
    return {'state': 'OK', 'allowStateChange': True,
            'reason': 'canonical and API agree'}


def blocks_action(guard, action):
    return guard['state'] in BLOCKING_STATES and action in STATE_CHANGING_ACTIONS