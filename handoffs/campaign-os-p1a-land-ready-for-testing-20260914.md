# Ready for testing: Campaign OS P1a land — CI gate + conftest (t25–t28)

**Date:** 2026-09-15  
**Job:** `job-20260914-campaign-os-p1a-land-ready-for-testing` (Cursor, ready-for-testing)  
**Implement:** `job-20260914-campaign-os-p1a-land-implement` — **done** @ `ca252a9` (code-complete)  
**Plan:** `plan/campaign-os-p1a-land/handoffs/campaign-os-p1a-land-plan-20260914.md`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-p1a-land`  
**Merge target:** `integrate/campaign-os-option-c` @ `a56a7c6` — **do not** push `main` / `master` / `develop`.  
**Deploy:** **none** (RFT only; land worker merges to integrate).

## One-line summary

P1a CI gate (`ci.yml` + allowlist pytest + `data/` gate + smoke) rebased onto post-P1f integrate; RFT re-verify **PASS** (949P/19S/0F). Feat branch on origin for land.

## Verify

| Source | Verdict | Notes |
|---|---|---|
| Pi job `job-20260914-campaign-os-p1a-land-verify` | **FAIL (stale)** | Checked `review/campaign-os-p1a-land` @ old integrate — artifacts absent. Not a product FAIL. |
| RFT re-verify on `feat/campaign-os-p1a-land` @ `ca252a9` | **PASS** | Plan §3 gates + t25–t28 artifact checks (this job, 2026-09-15) |

### Fresh gate evidence (RFT)

| Gate | Result |
|---|---|
| Artifacts | `ci.yml`, `campaign-os/tests/conftest.py`, `tests/ci-allowlist.txt` (113 lines), `pytest.ini` present |
| `python3 scripts/check_lib_modules.py` | exit 0, `missing_count: 0`, `strategy_page_present: true` |
| `xargs -a tests/ci-allowlist.txt python3 -m pytest -q` | **949 passed, 19 skipped, 0 failed** (exit 0) |
| `data/` gate | `git status --porcelain data/` empty; `git diff --quiet -- data/` exit 0 |
| `STRICT=1 bash tests/smoke_boot.sh` (`PORT=3093`) | exit 0, `PASS: build ok, health 200, ready answered (200)` |
| Workflow YAML | all four `.github/workflows/*.yml` parse |

t28: `lint-brand-copy.yml` targets `main` / `integrate/**` (dead `feat/asset-state-engine` gone).  
t25: `cos_session` / `cos_anon` fixtures in `campaign-os/tests/conftest.py`.

## Branches + push state

| Item | Value |
|---|---|
| Origin tip (RFT) | `origin/feat/campaign-os-p1a-land` — run `git rev-parse origin/feat/campaign-os-p1a-land` |
| Code-complete SHA | `ca252a976fadf93251e56c65608a1031217e4c85` |
| Branch | `feat/campaign-os-p1a-land` |
| Base | `origin/integrate/campaign-os-option-c` @ `a56a7c6d8938ecf4272e5cb2b8c698562f15bff9` |
| On origin? | **YES** — `git push -u origin feat/campaign-os-p1a-land` exit 0 (2026-09-15); no workflow-scope 403 |

```
ca252a9 fix(p1a-land): recognize _lib package dirs in module scanner
a56a7c6 docs(t51): add p1f Pages plan and ready-for-testing handoffs
11b7c7b docs(t51): retire Pages wording in campaign-os/README
0b86873 docs(t51): record the Pages decision in AGENTS.md §11
4bf0b71 chore(t51): retire the GitHub Pages deploy workflow
… (+ prior P1a commits on earlier integrate bases)
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
# expect: 0 failed (≥904 passed; tip measured 949P/19S)

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

Campaign OS P1a land ready for testing. `feat/campaign-os-p1a-land` on origin (code-complete `ca252a9`; RFT re-verify PASS: 949P/19S/0F, check_lib + smoke + data clean). Pi verify job failed only because `review/` was stale at old integrate tip. Target merge: `integrate/campaign-os-option-c`. No deploy. Suggested column: **Ready for testing**.

## Land (next job)

Land merges `feat/campaign-os-p1a-land` → `integrate/campaign-os-option-c` and may push **integrate** (not `main`). Feat already on origin — use `git rev-parse origin/feat/campaign-os-p1a-land`. After integrate tip moves, P1d should rebase onto it so t39 CI “required check” can go PASS.
