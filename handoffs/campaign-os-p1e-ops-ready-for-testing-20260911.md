# Ready for testing: Campaign OS P1e — ops surface, bootstrap, docs, budget

**Date:** 2026-09-14  
**Job:** `job-20260911-campaign-os-p1e-ops-ready-for-testing`  
**Verify:** `job-20260911-campaign-os-p1e-ops-verify` → **PASS** (`t42 t43 t44 t47 t48 t49 t50`; p1e suite 11/11)  
**Plan:** `handoffs/campaign-os-p1e-ops-plan-20260911.md`  
**Deploy:** none

## Branches + SHAs

| | |
|---|---|
| **Branch** | `feat/campaign-os-p1e-ops` |
| **Tip** | `c27ed64` (`c27ed643c61c49c6ec2aca559a64c8d35212ee4e`) |
| **Parent / planned base** | `f183d3c` (`f183d3cf9d5e5aaec79d4996e28d1b663f107197`) |
| **Merge target** | `integrate/campaign-os-option-c` (do **not** push `main` / `master` / `develop`) |
| **Worktree** | `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-p1e-ops` |
| **Web port** | **3870** (`runtime.ports.web`) |

**Commits on feat:**

| SHA | Message |
|---|---|
| `b2a09f2` | `feat(campaign-os-p1e): /ops/jobs UI, runbook, LLM spend cap` |
| `c27ed64` | `fix(campaign-os-p1e): pass human_approved in meme auto-compose tests` |

**Push:** `origin/feat/campaign-os-p1e-ops` @ `c27ed64` (fresh `git ls-remote` 2026-09-14). No `.github/workflows/**` in tip range — workflow-scope refresh not required for this push.

**Note for land:** `origin/integrate/campaign-os-option-c` has moved to `c568898` (p1d RFT docs merge). Feat is based on `f183d3c`, which is still an ancestor of that tip; land should merge cleanly with integrate ahead by docs-only commits.

## One-line summary

The ops surface a human is paged into now exists behind the session gate, the app stopped shelling out to git on every request, the runbook and the two Meta docs describe the system that actually runs, and image generation can no longer spend past a daily cap.

## Per-task verdicts

| Task | Verdict | Notes |
|---|---|---|
| **t42** `/ops/jobs` | **PASS** | Anon **302** → `/login?next=/ops/jobs`; session **200**; bearer **302**; 11 rows from `/api/jobs/status`; no external `.js`/`.css`; `PUBLIC_ROUTE_PREFIXES` assignment unchanged; routes **619** (= 617 + `/ops/jobs` + `/api/ops/llm-spend`) |
| **t43** failure drawer | **PASS** | Drawer sources status + diagnostics (not failures-only); technical detail fetched on toggle. Page JS mentions `traceback_tail` as a property name (not a shipped stack) — Pi verify accepted |
| **t44** Run now | **PASS** | `POST …?reason=manual` → ledger `triggered_by=manual`; cooldown **`min(every_seconds, 300)`** in `_lib/jobs/cooldown.py`; second manual → **429** + `Retry-After` with `CAMPAIGN_OS_PRODUCTION` **unset**; per-job (other job not locked) |
| **t47** `init_repo` once | **PASS** | **Option A** — module `_boot_git_sync()` + `threading.Lock` + `_GIT_SYNC_DONE`; `g._booted` gone; 5 health GETs → **0** extra `init_repo` calls. Behaviour change: git pull/clone is **once per process**, not per request |
| **t48** runbook | **PASS** (docs) / **PARTIAL** (live Telegram) | `RAILWAY.md` §6 phone-first runbook; dead deploy-branch instruction removed (names only appear as “do not use”); “only on the developer” gone; `/ops/jobs` named. Crons still not live — see open items |
| **t49** Meta doc truth | **PASS** | Live path = `meta_refresh` / `meta_live_fetch`; uncopyable `campaign-os.truth_collector` gone; Postiz section states standing rule (**Do not enable auto-publish**); `truth_collector` import for publish-event ingest intact |
| **t50** spend cap | **PASS** | Hard daily cap from env (`CAMPAIGN_OS_DAILY_LLM_CAP_USD`, default **5.00**); `$DATA_DIR/llm-spend/<day>.json`; fail-closed; modelled OpenAI cost (t50-I); spend chip on `/ops/jobs`; **dedicated** approval gate (`human_approved` + `$DATA_DIR/receipts/…`, not `governance.py` — brand_id gap); **blueprint §8.4 option A** — no live HTTP blueprint route; CLI unwired |
| **t45 / t46** | **not attempted** | deferred `security_hardening` — four public ops pages still anon **200** by design |

## Verify evidence (fresh, this RFT job)

**CI allowlist (blocking):**

```text
$ unset CAMPAIGN_OS_DAILY_LLM_CAP_USD
$ DATA_DIR=… OPENCLAW_CREDENTIALS_DIR=… \
    xargs -a tests/ci-allowlist.txt python3 -m pytest -q -p no:randomly
952 passed, 16 skipped, 157 warnings, 178 subtests passed
```

Exit **0**. Allowlist **112 → 113** (+ `campaign-os/tests/jobs/test_ops_jobs_p1e.py`); **no removals**.

**P1e suite:** `campaign-os/tests/jobs/test_ops_jobs_p1e.py` — **11 passed** (verify + local).

**Full suite (informational V28):** `171 failed, 1472 passed, 16 skipped, 18 errors` — failed count **above** plan baseline 160 by ~11, mostly non-allowlisted image-route tests that now need `human_approved` (t50 collateral). Allowlist gate holds; land does not require full-suite green.

**Other gates:** `data/` clean; `visibility_guard` untouched; `check_lib_modules.py` still exits **1** on package name `jobs` — **pre-existing on `f183d3c`**, not a P1e regression; tracked `_lib/*.py` = **75** (was 73 + `cooldown.py` + `llm_spend.py`).

**Gate matrix (test client, port N/A):**

| Path | Anon | Notes |
|---|---|---|
| `/ops/jobs` | **302** `/login?next=/ops/jobs` | same before/after (page did not exist as gated HTML before; catch-all previously also 302) |
| `/ops/jobs` + bearer | **302** | t42-H |
| `/ops/jobs` + session | **200** `text/html` | |
| `/secrets-sync` `/meta-portal` `/cockpit-operational` `/weekly-report` | **200** | t45 untouched |

## Design choices recorded

| Topic | Choice |
|---|---|
| t47 placement | **Option A** — import-time `_boot_git_sync()` under lock |
| t44 window | **`min(every_seconds, 300)`** seconds; in-memory (resets on process restart) |
| t50 approval | **Dedicated gate** (not `governance.py`) — receipts under `$DATA_DIR/receipts/` |
| t50 blueprint | **§8.4-A** — image gated now; `scripts/generate-blueprint.py` unwired CLI, out of scope |
| Page path | `campaign-os/ops-jobs.html` (not `_ops_jobs.html`) |
| `AGENTS.md` §6 | Still says **three** registered jobs; page renders **eleven**. Not updated in this ticket (plan §11.1) |

## Manual test steps (copy/paste)

```bash
cd /home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-p1e-ops/campaign-os
export DATA_DIR="$(mktemp -d /tmp/cos-p1e-rft-XXXX)"
export COS_JOB_TOKEN=test-token-not-a-secret
unset CAMPAIGN_OS_DAILY_LLM_CAP_USD   # do not leave at 0.00 — pollutes allowlist image tests
PORT=3870 python3 app.py
```

1. **Gate.** Anon `/ops/jobs` → 302; four public ops pages → 200; bearer `/ops/jobs` → 302; login → `/ops/jobs` 200 with 11 job cards + LLM spend chip.
2. **Status.** `GET /api/jobs/status` (bearer) → 11 jobs; fields include `last_duration_s`, `last_run_id`, `best_effort`, `every_seconds`.
3. **Run now.** `POST /api/jobs/run/freshness_scan?reason=manual` → ok; ledger finished row `triggered_by=manual` + `duration_s`; immediate second POST → **429** + `Retry-After`; `golf_news` still allowed.
4. **Drawer.** Force a failure (or use an existing non-OK row); open Failure detail — checklist + freshness; expand technical detail (fetches `/api/jobs/diagnostics/<run_id>`). Repeat on a `best_effort` job (`site_audit`) — drawer still opens though `/api/jobs/failures` omits it.
5. **Budget.** `CAMPAIGN_OS_DAILY_LLM_CAP_USD=0.00`, restart; `POST` image routes with `human_approved=true` → **402** `spend_cap` (or fail-closed). Corrupt `$DATA_DIR/llm-spend/<today>.json` → still refuses. Spend chip on `/ops/jobs` reflects cap.
6. **Allowlist.** Re-run allowlist command above → 0 failed.

## Manual test 7 — 07:00 falsification (from `RAILWAY.md` alone)

| # | Question | Answer from `RAILWAY.md` |
|---|---|---|
| 1 | `site_audit FAILED` — open first? | `/ops/jobs` (session login); tap Failure detail on the row |
| 2 | LATE vs FAILED — which wakes me? | `FAILED` = non–best_effort bad finish; `LATE` = stale success or best_effort soft fail. Severity order: FAILED → STUCK → NEVER → LATE. Watch shouts on any non-OK |
| 3 | `meta_refresh` succeeded 20h ago? | Yes problem — LATE at **18h** (`43200×1.5`) |
| 4 | Have `run_id`, see why without secrets? | `GET /api/jobs/diagnostics/<run_id>` (redacted bundle) or drawer technical detail |
| 5 | No 07:00 digest? | Watchdog/cron host down — **not** all clear |

**5/5** answerable from `RAILWAY.md` §6.

## Open items (named owners)

1. **Telegram crons still not live** — `COS_JOB_TOKEN` in `~/.hermes/.env`, then `campaign-os-watch` / `campaign-os-digest`. t48-C PARTIAL until then. *Owner: Kyle*
2. **Railway service branch unconfirmed** in UI (doc now says `integrate/campaign-os-option-c`). *Owner: Kyle*
3. **Daily cap number** — default `5.00` is a placeholder. *Owner: Kyle*
4. **Approval threshold** — every generate currently needs `human_approved=true` (no soft per-call USD threshold). *Owner: Kyle*
5. **t45** — `/secrets-sync` still anon 200 (credential form). Most visible deferred gap. *Owner: Kyle / security_hardening*
6. **`/api/ops/*` session-only vs `/api/jobs/*` dual-auth** — documented asymmetry. Change = new ticket. *Owner: Kyle*
7. **`AGENTS.md` §6 still says three jobs** — page shows eleven. *Owner: implementer follow-up / Kyle nod*
8. **Non-allowlisted image tests** — several expect pre-t50 200 without `human_approved`; full-suite failed count rose. Optional cleanup ticket. *Owner: follow-up*
9. **`check_lib_modules` false-positive on package `jobs`** — pre-existing. *Owner: follow-up*

## Suggested board / comment draft

Campaign OS P1e ready for testing on `feat/campaign-os-p1e-ops` (`c27ed64`). Verify **PASS** t42–t44,t47–t50; t45/t46 not attempted. Allowlist **952 passed**. Target merge: `integrate/campaign-os-option-c`. No deploy. Suggested column: **Ready for testing**.

## Land (next job)

`job-20260911-campaign-os-p1e-ops-land` merges `feat/campaign-os-p1e-ops` → `integrate/campaign-os-option-c` and may push **integrate** (not `main`). Feature branch already on origin @ `c27ed64`.
