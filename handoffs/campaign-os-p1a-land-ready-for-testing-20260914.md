# Ready for testing: Campaign OS P1a land — CI gate + conftest (t25–t28)

**Date:** 2026-09-14  
**Job:** `job-20260914-campaign-os-p1a-land-ready-for-testing` (Cursor, ready-for-testing)  
**Implement:** `job-20260914-campaign-os-p1a-land-implement` — **done** @ `736473b` (code-complete)  
**Plan:** `plan/campaign-os-p1a-land/handoffs/campaign-os-p1a-land-plan-20260914.md`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-p1a-land`  
**Merge target:** `integrate/campaign-os-option-c` @ `9683b16` — **do not** push `main` / `master` / `develop`.  
**Deploy:** **none** (RFT only; land worker merges to integrate).

## One-line summary

P1a CI gate (`ci.yml` + allowlist pytest + `data/` gate + smoke) rebased onto post-P1b/P1c integrate; RFT re-verify **PASS** (935P/16S/0F). Feat branch pushed for land.

## Verify

| Source | Verdict | Notes |
|---|---|---|
| Pi job `job-20260914-campaign-os-p1a-land-verify` | **FAIL (stale)** | Checked `review/campaign-os-p1a-land` still @ integrate `9683b16` — artifacts absent. Not a product FAIL. |
| RFT re-verify on `feat/campaign-os-p1a-land` @ `736473b` (pre-handoff tip) | **PASS** | Plan §3 gates + t25–t28 artifact checks (this job, 2026-09-14) |

### Fresh gate evidence (RFT)

| Gate | Result |
|---|---|
| Artifacts | `ci.yml`, `campaign-os/tests/conftest.py`, `tests/ci-allowlist.txt` (111 lines), `pytest.ini` present |
| `python3 scripts/check_lib_modules.py` | exit 0, `missing_count: 0`, `strategy_page_present: true` |
| `xargs -a tests/ci-allowlist.txt python3 -m pytest -q` | **935 passed, 16 skipped, 0 failed** (exit 0) |
| `data/` gate | `git status --porcelain data/` empty; `git diff --quiet -- data/` exit 0 |
| `STRICT=1 bash tests/smoke_boot.sh` (`PORT=3093`) | exit 0, `PASS: build ok, health 200, ready answered (200)` |
| Workflow YAML | all five `.github/workflows/*.yml` parse |

t28: `lint-brand-copy.yml` targets `main` / `integrate/**` (dead `feat/asset-state-engine` gone).  
t25: `cos_session` / `cos_anon` fixtures in `campaign-os/tests/conftest.py`.

## Branches + push state

| Item | Value |
|---|---|
| Origin tip (RFT) | `origin/feat/campaign-os-p1a-land` — run `git rev-parse origin/feat/campaign-os-p1a-land` (first push `13c4730`; finalize may add +1) |
| Code-complete SHA | `736473b2a73445246efab602a6914a35a22a0e1c` |
| Branch | `feat/campaign-os-p1a-land` |
| Base | `origin/integrate/campaign-os-option-c` @ `9683b16ca1d90dfe1d33d16afb2781ea0094e1ef` |
| On origin? | **YES** — `git push -u origin feat/campaign-os-p1a-land` exit 0 (2026-09-14); no workflow-scope 403 |

```
13c4730 docs(p1a-land): pin RFT handoff tip SHA
889ad63 docs(p1a-land): ready-for-testing handoff after verify PASS
736473b fix(p1a-land): Layer1 allowlist + bearer tests under cos_anon
fa8d4e5 docs(p1a): finalize BASELINE.md SHA line
5761d62 docs(p1a): pin BASELINE.md to measurement SHA
c56953e fix(p1a): caption scratch DATA_DIR + t25 baseline doc
563727f fix(p1a): gate caption_studio on CI allowlist
92c1ac6 fix(p1a): isolate allowlist writers so CI data/ gate passes
775df72 fix(p1a): caption_studio subprocess login + residual triage
bf2c817 feat(p1a): cos_session auth fixture, root tests fix, CI gate
```

Allowlist append (P1b Layer1 / P1d prep): `test_layer1_contracts`, `test_jobs_bearer_auth`, `test_layer1_io`, `test_insights_hooks`, `test_insights_reco`.

## Manual CI check steps

Local mirror of `.github/workflows/ci.yml` (from feat worktree):

```bash
cd /home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-p1a-land
export DATA_DIR="$(mktemp -d /tmp/cos-p1a-rft-XXXX)"
export OPENCLAW_CREDENTIALS_DIR="$(mktemp -d /tmp/cos-p1a-creds-XXXX)"
export PORT=3093   # job runtime.ports.web
# COS_JOB_TOKEN: any non-empty string; presence only — do not print value

python3 scripts/check_lib_modules.py
# expect: missing_count: 0

test -s tests/ci-allowlist.txt
xargs -a tests/ci-allowlist.txt python3 -m pytest -q --tb=short
# expect: 0 failed (≥904 passed; tip measured 935P/16S)

git diff --quiet -- data/
git status --porcelain data/   # must be empty

STRICT=1 bash tests/smoke_boot.sh
# expect: PASS: build ok, health 200, ready answered (200)
```

### After push — GitHub Actions (manual)

1. Open the branch / PR against **`integrate/campaign-os-option-c`** (not `main`).
2. Confirm workflow **`ci`** runs on the PR (or on `integrate/**` push after land).
3. Required green jobs: **`check_lib_modules`**, **`pytest`** (allowlist + `data/` gate step).
4. Informational: **`pytest_full`** is `continue-on-error: true` — do not block land on it.
5. On PR: **`allowlist_ratchet`** must pass (allowlist append-only vs base).
6. Spot-check Actions logs: no secret values echoed; scratch `DATA_DIR` only.

If push hits **workflow-scope 403** (PAT missing `workflow`): Kyle runs `gh auth refresh -s workflow` then re-push — same class as P0c.

## Suggested board / comment draft

Campaign OS P1a land ready for testing. `feat/campaign-os-p1a-land` on origin (code-complete `736473b`; RFT re-verify PASS: 935P/16S/0F, check_lib + smoke + data clean). Pi verify job failed only because `review/` was stale at integrate tip. Target merge: `integrate/campaign-os-option-c`. No deploy. Suggested column: **Ready for testing**.

## Land (next job)

Land merges `feat/campaign-os-p1a-land` → `integrate/campaign-os-option-c` and may push **integrate** (not `main`). Feat already on origin — use `git rev-parse origin/feat/campaign-os-p1a-land`. After integrate tip moves, P1d should rebase onto it so t39 CI “required check” can go PASS.
