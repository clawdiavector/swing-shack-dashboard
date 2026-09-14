# Phase 2 Wizard + API Test Suite (+ P1a pytest notes)

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

## Running (JS wizard)

```bash
# 1. Start the Flask server (in one terminal)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DATA_DIR=/tmp/campaign-os-test PORT=<job-runtime.ports.web> python3 app.py

# 2. Run the suite (in another terminal)
node tests/test_phase2_wizard.js
```

Expected: `Total: 33, Passed: 33, Failed: 0`

## Pytest (P1a / t25–t27)

From repo root (preferred for CI):

```bash
export DATA_DIR=/tmp/cos-scratch OPENCLAW_CREDENTIALS_DIR=/tmp/cos-creds
mkdir -p "$DATA_DIR" "$OPENCLAW_CREDENTIALS_DIR"
python3 -m pytest -q                    # uses pytest.ini testpaths
xargs -a tests/ci-allowlist.txt python3 -m pytest -q   # CI gate subset
```

From `campaign-os/` (same auth behaviour via `campaign-os/tests/conftest.py`):

```bash
cd campaign-os && python3 -m pytest tests/ -q
```

Auth: `cos_session` / auto-login via `POST /login` (t25). Opt out with
`app.test_client(cos_anon=True)`. Bearer / `COS_JOB_TOKEN` is out of scope
(`t25_scope` → t31).

### Root `tests/` disposition (t26)

- `tests/test_parity.py` is a real pytest test (was a module-scope
  `sys.exit` script that caused `INTERNALERROR` / exit 3). Standalone
  `python3 tests/test_parity.py` still works.
- `scripts/tests/` collects via `pytest.ini` `pythonpath = scripts`
  (avoids editing that tree; its local `SCRIPTS = HERE.parent / "scripts"`
  path is wrong but harmless once `scripts/` is on `sys.path`).
- After any full-suite run, check `git status --porcelain data/` and
  `git checkout -- data/` if tests dirtied tracked seed files (risk 9.7).
  Allowlisted writers are isolated: `test_freshness_sanity_range` restores
  `data/freshness.json`; `test_v2026_08_13_weekly_report_share` redirects
  `intelligence.DATA_DIR` to a temp dir; `test_v2026_08_13_html_export`
  uses `cos_anon=True` so format probes do not persist markdown. Keeps
  CI's `git diff --quiet -- data/` gate green without dropping coverage.

### CI allowlist

`tests/ci-allowlist.txt` is the blocking green subset. It may only grow
(see `allowlist_ratchet` in `.github/workflows/ci.yml`). Removing a path
needs a written reason in the PR body.

## What's NOT covered here
- Browser-runtime wizard flow (Back/Next/Cancel, validation, refresh persistence)
  → covered manually via the `browser_*` tools, reported in the morning report.
- Pillars parsing edge cases (empty lines, no separator, special chars)
  → handled by the JS code, not unit-tested in isolation.
- Residual campaign-os failures after t25 (stale HTML, Mac paths, etc.) —
  named classes + owners in [`RESIDUAL-TRIAGE.md`](./RESIDUAL-TRIAGE.md) (t25-E);
  before/after counts in [`BASELINE.md`](./BASELINE.md) (t25-D).
  Not fixed in P1a except the caption_studio subprocess login follow-up.
