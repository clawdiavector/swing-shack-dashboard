# Phase 2 Wizard + API Test Suite

Two-layer test approach:

## 1. HTML structure (`tests/test_phase2_wizard.js`)
Static assertions on the cockpit file:
- Modal, fields, wizard functions exist
- Dev store + dev API adapter present
- Steps 5 (Review Queue) functions present
- No regressions on prior steps

## 2. Live API (same test file)
Runs against a live Flask backend:
- POST wizard payload (new shape) returns 201, persists verbatim
- GET round-trips identity/plan/brief/history
- Duplicate id returns 409
- Legacy shape still works (backward compat)
- Empty name returns 400
- Wizard payload without campaignId returns 400
- Health endpoint returns ok

## Running

```bash
# 1. Start the Flask server (in one terminal)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DATA_DIR=/tmp/campaign-os-test PORT=8765 python3 app.py

# 2. Run the suite (in another terminal)
node tests/test_phase2_wizard.js
```

Expected: `Total: 33, Passed: 33, Failed: 0`

## What's NOT covered here
- Browser-runtime wizard flow (Back/Next/Cancel, validation, refresh persistence)
  → covered manually via the `browser_*` tools, reported in the morning report.
- Pillars parsing edge cases (empty lines, no separator, special chars)
  → handled by the JS code, not unit-tested in isolation.
