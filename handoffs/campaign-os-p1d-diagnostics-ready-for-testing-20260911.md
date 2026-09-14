# Ready for testing: Campaign OS P1d — retry, classifier, diagnostic bundle (t35–t41)

**Date:** 2026-09-14  
**Job:** `job-20260911-campaign-os-p1d-diagnostics-ready-for-testing` (Cursor, ready-for-testing)  
**Verify:** `job-20260911-campaign-os-p1d-diagnostics-verify` on Herdr `w51:p4` (`campaign-os-p1d-diagnostics-veri`)  
**Verify verdict:** **PASS** t35–t40; **PARTIAL** t41 (watch patch handed over, not live on agent-control / Hermes shims) — worker finished `2026-09-14T14:49:42Z`: `t35-40 PASS t41 FAIL (watch patch unmerged) 70 tests green` (plan §1.7 maps unmerged t41 → PARTIAL)  
**Plan:** `plan/campaign-os-p1d-diagnostics/handoffs/campaign-os-p1d-diagnostics-plan-20260911.md`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-p1d-diagnostics`  
**Merge target:** `integrate/campaign-os-option-c` — **do not** push `main` / `master` / `develop`.  
**Deploy:** **none** (RFT only; no Railway).

## One-line summary

Tier-0 retry + 10-class classifier + suggested_checks + diagnostic bundles (schema v1, redacted) + `/api/jobs/failures` + `/api/jobs/diagnostics/<run_id>`. Verify **PASS** t35–t40 (70/70 jobs tests). t41 patch only. Feat branch **on origin**.

## Branches + push state

| Item | Value |
|---|---|
| Code-complete SHA | `931244bc2392e7a8abade0825261f0eeb993ee7a` |
| Origin tip (incl. this handoff) | `origin/feat/campaign-os-p1d-diagnostics` @ `560a81fe7bcd5d6be0586cda8bfbd27bbe284744` |
| Base (feat branched from) | `9683b16ca1d90dfe1d33d16afb2781ea0094e1ef` (`merge(p1c-legacy)`) |
| Integrate tip at RFT | `origin/integrate/campaign-os-option-c` @ `f183d3cf9d5e5aaec79d4996e28d1b663f107197` |
| On origin? | **YES** — `git push -u origin feat/campaign-os-p1d-diagnostics` |
| Deploy | none |

### Integrate already contains this slice

A prior land already merged the feat range into integrate (`41f972a merge(p1d-diagnostics)`), then P1a landed, then two follow-up commits on integrate (not on feat tip):

| SHA | Note |
|---|---|
| `1fa603a` | `fix(p1d): add test_redaction.py to CI allowlist (t39 gate)` — needs P1a `tests/ci-allowlist.txt` |
| `f183d3c` | `fix(p1d): cos_anon on diagnostics auth-negative test (t40)` — needs P1a `cos_anon` test_client kwarg |

Feat tip stays at implement `931244b` (self-contained without P1a fixtures). RFT re-ran `campaign-os/tests/jobs/`: **70 passed**.

## Commit shape (feat vs `9683b16`)

1. `0ac660d` feat(jobs): error classifier + stable fingerprint (t36)  
2. `e98104a` fix(jobs): keep HTTP status in Layer 1 failure strings (t36)  
3. `02799c3` feat(jobs): suggested_checks lookup, 110 pairs covered (t37)  
4. `cde78a8` feat(jobs): redaction + planted-secret test (t39)  
5. `d7752c9` feat(jobs): diagnostic bundle writer, schema v1 + retention (t38)  
6. `a5b9194` feat(jobs): Tier-0 retry for transient classes (t35)  
7. `931244b` feat(api): /api/jobs/failures + diagnostics endpoints (t40)  

Plus handoff docs on feat: `handoffs/campaign-os-p1d-diagnostics-t41-notes.md`, `…-t41-watch.patch`, and this RFT file.

## Per-task (verify)

| Task | Verdict | Notes |
|---|---|---|
| t35 Tier-0 retry | **PASS** | backoff; `RETRYABLE={http_5xx, rate_limit}` only; timeout not retried (plan §3.1 / Kyle nod) |
| t36 classifier | **PASS** | 10 classes; stable sha1 fingerprint |
| t37 suggested_checks | **PASS** | 110 (class, job) pairs |
| t38 diagnostic bundle | **PASS** | schema `campaign-os/diagnostic-bundle/v1`; credentials presence booleans; retention 30d/200 |
| t39 redaction | **PASS** | planted-secret test green; CI allowlist line on integrate via `1fa603a` (after P1a) |
| t40 endpoints | **PASS** | bearer/session dual-auth; failures excludes `best_effort`; bundle refs |
| t41 watch upgrade | **PARTIAL** | patch + notes in `handoffs/`; agent-control merge + Hermes shim repoint still Kyle/ops |

## Guards (RFT re-check)

| Check | Result |
|---|---|
| `git diff 9683b16..HEAD -- data/` | **empty** |
| `visibility_guard` (py + js) | **empty** |
| `campaign-os.html` | **empty** |
| `campaign-os/tests/jobs/` (feat tip) | **70 passed** |

## Empty-by-design bundle fields (plan §2)

`stderr_tail`, `recent_errors`, and often `upstream` may be empty — correct for this runner model; not misses.

## Open items for Kyle

1. **t41 live:** merge `feat/campaign-os-p0c-ac` → agent-control `main` (if not already), apply `handoffs/campaign-os-p1d-diagnostics-t41-watch.patch`, repoint `~/.hermes/scripts/watch_campaign_os.py` (+ digest if needed) to `/home/kyle/finder-workspace/repos/work/agent-control/bin/…`, then `python3 ~/.hermes/scripts/watch_campaign_os.py --force`.  
2. **timeout not retried** — deliberate plan deviation (§3.1); confirm nod.  
3. **Land job:** integrate already has the slice + follow-ups; land worker should no-op or only reconcile if feat tip drifts.

## Suggested board / comment draft

Campaign OS P1d ready for testing. `feat/campaign-os-p1d-diagnostics` @ `931244b` on origin. Verify PASS t35–t40 (70 jobs tests); t41 PARTIAL (watch patch unmerged). Target merge: `integrate/campaign-os-option-c` (already contains land + allowlist/cos_anon follow-ups). No deploy. Suggested column: **Ready for testing**.

## Land (next job)

Land merges `feat/campaign-os-p1d-diagnostics` → `integrate/campaign-os-option-c` (may push **integrate**, not `main`). Feat is on origin. Prefer fast-forward / already-merged check before re-merging. No Railway deploy from RFT.
