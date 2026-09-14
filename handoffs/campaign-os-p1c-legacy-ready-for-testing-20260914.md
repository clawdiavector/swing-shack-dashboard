# Ready for testing: Campaign OS P1c — delete the legacy Node tree (t33/t34)

**Date:** 2026-09-14  
**Job:** `job-20260911-campaign-os-p1c-legacy-ready-for-testing` (Cursor, ready-for-testing)  
**Verify:** `job-20260911-campaign-os-p1c-legacy-verify` on Herdr `w4W:p6` (`campaign-os-p1c-legacy-verify`)  
**Verify verdict:** **PASS** t33+t34 — `19JS pytest418/1122/18 flat 7node-green guards-frozen dataclean` (finished `2026-09-14T11:57:15Z`)  
**Plan:** `handoffs/campaign-os-p1c-legacy-plan-20260911.md` @ `7b2c0c6` / on feat as `ddf53fe`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-p1c-legacy`  
**Merge target:** `integrate/campaign-os-option-c` (`69b64e2`) — **do not** push `main` / `master` / `develop`.  
**Deploy:** **none** (RFT only; land worker merges).

## One-line summary

224+ dead Node files deleted; **19** JS survive (load-bearing for tests / Pages); only behaviour change is freshness refresh no longer needs node. Verify **PASS**. Feat branch **on origin**.

## Branches + push state

| Item | Value |
|---|---|
| Feature tip SHA | `008035181af9b1ea3b22d6c713ed56d33c57f482` |
| Code-complete SHA (pre-RFT docs) | `f9dac891a07419bcdbebded97f6a4b7c4c58e337` |
| Base | `origin/integrate/campaign-os-option-c` @ `69b64e2ad185e4ffd75f4a97d20e39a82ed32180` |
| On origin? | **YES** — `origin/feat/campaign-os-p1c-legacy` @ `0080351` (pushed 2026-09-14 by RFT job) |
| Push command used | `git push -u origin feat/campaign-os-p1c-legacy` — **exit 0** (no workflow-scope 403; this range does not touch `.github/workflows`) |

## Commit shape (§8)

1. `ddf53fe` docs — plan handoff onto feat  
2. `efe7830` refactor — §4 code before deletions (freshness_scan port, two test retargets, intelligence string)  
3. `334cf58` chore(legacy) — delete `legacy/` (225 agents files + README) + AGENTS.md §1/§9  
4. `a1c857c` chore(scripts) — delete 150 JS + `run_path2_chain.sh` + `gate6-blueprint.py`  
5. `f9dac89` chore(t34) — root `app.py`, `fix_syntax.py`, `patch-cockpit.py{,.bak}`, `REBUILD_TRIGGER.txt`  
6. `36b12fc` / `64f3be7` / `0080351` docs — RFT handoff + SHA pins  

## Counts (verify-aligned)

| Metric | Before (`69b64e2`) | After |
|---|---|---|
| `git ls-files '*.js' \| wc -l` | **243** | **19** |
| Breakdown | 158 scripts / 74 legacy / 11 tests | **8 scripts / 0 legacy / 11 tests** |
| `git ls-files legacy` | 226 | **0** |
| `data/` diff vs base | — | **empty** |

### Retained 8 `scripts/*.js` (Option A)

`patch-cockpit.js`, `_lib/visibility-guard.js`, `_lib/asset-state-engine.js`, `_lib/campaign-state-engine.js`, `_lib/postiz-credentials.js`, `run_publisher.js`, `generate_publish_queue.js`, `regenerate-publishing-index.js`.

## Per-task (verify)

| Task | Verdict | Notes |
|---|---|---|
| t33 | **PASS** | Inventories gone; 19 JS; no live node shell-out to deleted scripts; salvage present; visibility_guard untouched |
| t34 | **PASS** | Root `app.py` / `fix_syntax.py` / `.bak` / `REBUILD_TRIGGER.txt` / `patch-cockpit.py` gone; `patch-cockpit.js` retained |

## pytest (V11) — verify flat

```text
418 failed, 1122 passed, 16 skipped, 18 errors
```

Passed −1 vs pre-delete baseline is intentional (`test_node_available` removed). Failed/errors flat. `data/` clean after runs. Seven retained JS node tests green.

## visibility_guard

`git diff 69b64e2..HEAD -- scripts/_lib/visibility-guard.js campaign-os/_lib/visibility_guard.py` → **empty** (re-checked at RFT).

## Open items for Kyle (§9)

1. **P1e:** retire/relabel `GET /api/intel/agents` — still renders a 23-agent fleet from `data/agent-runs.json`.  
2. **Static seeds:** `data/approval-queue.json` + `data/asset-needs.json` — port a tiny job or remove `app.py` readers.  
3. **Option B:** delete four broken root JS tests (→ 15 JS).  
4. **P1a lander:** blocking allowlist still needs `visibility-guard.js` + Node — deliberate retain.

## Suggested board / comment draft

Campaign OS P1c ready for testing. `feat/campaign-os-p1c-legacy` @ `0080351` on origin. Verify PASS t33+t34 (19 JS; pytest 418/1122/18 flat; guards frozen). Target merge: `integrate/campaign-os-option-c`. No deploy from this ticket. Suggested column: **Ready for testing**.

## Land (next job)

Land merges `feat/campaign-os-p1c-legacy` → `integrate/campaign-os-option-c` (may push **integrate**, not `main`). Feat already on origin @ `0080351`. No Railway deploy from RFT.
