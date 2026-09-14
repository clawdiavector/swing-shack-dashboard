# Ready for testing: Campaign OS P1c — delete the legacy Node tree (t33/t34)

**Date:** 2026-09-14  
**Job:** `job-20260911-campaign-os-p1c-legacy-implement` (Cursor, implement)  
**Plan:** `handoffs/campaign-os-p1c-legacy-plan-20260911.md` @ `7b2c0c6` / brought onto feat as `ddf53fe`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-p1c-legacy`  
**Branch:** `feat/campaign-os-p1c-legacy` @ `f9dac891a07419bcdbebded97f6a4b7c4c58e337` (36b12fcaeae44cc8287992b950298f139b09c204)  
**Merge target:** `integrate/campaign-os-option-c` (`69b64e2`) — **do not** push `main` / `master` / `develop`.

## One-line summary

224+ dead Node files and ~26.7k lines deleted; **19** JS survive (every one load-bearing for a passing test or Pages deploy); the only behaviour change is that the freshness refresh button no longer needs node installed.

## Branches + push state

| Item | Value |
|---|---|
| Feature SHA (code complete) | `f9dac891a07419bcdbebded97f6a4b7c4c58e337` |
| Base | `origin/integrate/campaign-os-option-c` @ `69b64e2ad185e4ffd75f4a97d20e39a82ed32180` |
| On origin? | **NO** — `git ls-remote origin feat/campaign-os-p1c-legacy` empty at implement time |
| Push | Not attempted (implement job). Allowed: `git push -u origin feat/campaign-os-p1c-legacy` after Kyle/RFT asks |

## Commit shape (§8)

1. `ddf53fe` docs — plan handoff onto feat  
2. `efe7830` refactor — §4 code before deletions (freshness_scan port, two test retargets, intelligence string)  
3. `334cf58` chore(legacy) — delete `legacy/` (225 agents files + README) + AGENTS.md §1/§9  
4. `a1c857c` chore(scripts) — delete 150 JS + `run_path2_chain.sh` + `gate6-blueprint.py`; Mac-path comment in `postiz-credentials.js`  
5. `f9dac89` chore(t34) — root `app.py`, `fix_syntax.py`, `patch-cockpit.py{,.bak}`, `REBUILD_TRIGGER.txt`; ignore + staged-campaign notes tidies  

## Counts (re-derived after deletions)

| Metric | Before (`69b64e2`) | After |
|---|---|---|
| `git ls-files '*.js' \| wc -l` | **243** | **19** |
| Breakdown | 158 scripts / 74 legacy / 11 tests | **8 scripts / 0 legacy / 11 tests** |
| Master-plan "152 → &lt;20" | stale `scripts/`-only count from 2026-09-09 | Use **243 → 19** as the headline |
| `git ls-files legacy` | 226 | **0** |
| `scripts/*.py` | 54 | **52** (gate6-blueprint.py + deliberate `patch-cockpit.py` delete; plan's "53" assumed only gate6) |
| `data/` diff vs base | — | **empty** |

### Retained 8 `scripts/*.js` (Option A)

`patch-cockpit.js`, `_lib/visibility-guard.js`, `_lib/asset-state-engine.js`, `_lib/campaign-state-engine.js`, `_lib/postiz-credentials.js`, `run_publisher.js`, `generate_publish_queue.js`, `regenerate-publishing-index.js`.

### Option A vs Option B (Kyle follow-up)

- **Default taken: Option A** — retain all **11** root `tests/*.js` (19 total JS). Four of those tests are broken / dirties `data/` (`test_phase2_wizard`, `test_phase_tdz_fix`, `test_step94_*`, `test_step94b_*`); they were **not** deleted because `tests/**` was Option-B-only and Kyle confirmed Option A.
- **Option B (Kyle follow-up):** delete the four broken root JS tests → **15** JS. Same retain set for scripts. Record owner: Kyle / next hygiene ticket. Do not do silently.

## Per-task verdict (implement self-check; verify re-derives)

| Task | Verdict | Notes |
|---|---|---|
| t33 | **PASS (code-met)** | Inventories gone; 19 JS; no live node shell-out to deleted scripts; salvage present; visibility_guard untouched |
| t34 | **PASS (code-met)** | Root `app.py` gone; `fix_syntax.py` gone; no `.bak`; `patch-cockpit.js` retained; deliberate extras below |

### t34 deliberate extensions (beyond literal wording)

| Decision | Action | Why |
|---|---|---|
| `scripts/patch-cockpit.py` | **deleted** (with `.bak`) | Byte-identical dead twin of load-bearing JS; same "which is production?" hazard |
| `REBUILD_TRIGGER.txt` | **deleted** | Single timestamp; no deploy filter; Railway rebuilds on push |
| `regenerate-cockpit.js` | **deleted** (cohort G) | Unreferenced |
| `regenerate-cockpit.py` | **kept** | Pages/spec references; t51-gated with `patch-cockpit.js` |

## §4 fixes (file:line at implement time)

| # | Fix | Where |
|---|---|---|
| 4.1 | Replace node shell-out with `_run_freshness_scan_job()`; prefer `$DATA_DIR` read order | `campaign-os/app.py` `admin_data_freshness` |
| 4.2 | Drop `test_node_available`; retarget regenerate at Python job | `campaign-os/tests/test_freshness_sanity_range.py` |
| 4.3 | Operator string → `meta_refresh` job | `campaign-os/_lib/intelligence.py` (~3258) |
| 4.4 | Permalink assert → `_lib/meta_live_fetch.py`; drop `p.releaseURL` | `campaign-os/tests/test_v2026_08_10_insights_relative_tone.py` |

### History comments deliberately kept (not t33-F failures)

- `intelligence.py:889` — `fetch_ga4.js` provenance  
- `intelligence.py:3558` — `run_conversion_truth_engine.js` provenance  
- `postiz_client.py:5` — `fetch_postiz_analytics.js` provenance  
- Plus docstring mentions in `scripts/fetch_ig_business.py` and conversion-attribution tests  

## §2.1 supersessions (nothing to side-by-side diff)

- `fetch_seo_rankings.js` — superseded by `seo_rankings` → `fetch_ubersuggest.py`  
- `fetch_postiz_analytics.js` — subsumed by `meta_refresh` (and violated §8 by writing tracked `data/`)  
- `sync_ig_analytics.js` — subsumed by `meta_refresh`  

## pytest (V11)

Merge-base plan row: `418 failed, 1123 passed, 16 skipped, 18 errors`.

After deletions (scratch `DATA_DIR`, `-p no:randomly`):

```text
418 failed, 1122 passed, 16 skipped, 142 warnings, 18 errors, 139 subtests passed in 24.90s
```

**Passed −1 is intentional:** deleted standalone `test_node_available` (node PATH probe). Failed/errors/skipped held flat. `data/` cleaned after every run (`git checkout -- data/`).

Targeted green: `test_v2026_08_10_insights_relative_tone.py` + `test_freshness_sanity_range.py` → **11 passed**.

## Manual tests (plan §7.2) — implement worktree, port **3039** (job `runtime.ports.web`)

| # | Step | Result |
|---|---|---|
| 1 | `/api/health` | **PASS** — 200 |
| 2 | `/api/jobs/status` | **PASS** — 11 jobs; unauth 401 |
| 3 | freshness refresh | **PASS** — `_run_freshness_scan_job` + admin `?refresh=1` write `$DATA_DIR/freshness.json`; response `total_files` matches file; `log_path` under `$DATA_DIR` (read-order fix proven) |
| 4 | dangling `scripts/*.js` grep | **PASS** — retained files + sanctioned history comments only |
| 5 | pytest flat | **PASS** — see table (1122/418/18) |
| 6 | 7 retained JS tests | **PASS** — all exit 0; `data/` reverted after publisher tests dirtied queues |
| 7 | `check_lib_modules.py` | **PASS** — `missing_count: 0`. Docker image build **not** run locally |
| 8 | `patch-cockpit.js` Pages path | **PASS** — exit 0; working-tree change reverted |

## visibility_guard (V5 / AGENTS.md §8)

`git diff 69b64e2..HEAD -- scripts/_lib/visibility-guard.js campaign-os/_lib/visibility_guard.py` → **empty**.

## Open items for Kyle (§9)

1. **P1e:** retire/relabel `GET /api/intel/agents` — still renders a 23-agent fleet from `data/agent-runs.json` after the Node tree is gone. t33-C met for the **repo tree**; this surface is the remaining carrier.  
2. **Static seeds:** `data/approval-queue.json` + `data/asset-needs.json` — port a tiny job or remove `app.py` readers.  
3. **Option B:** delete four broken root JS tests (→ 15 JS).  
4. **P1a lander:** blocking allowlist still needs `visibility-guard.js` + Node — deliberate retain, not a licence to finish deleting JS.  
5. Push `feat/campaign-os-p1c-legacy` when ready (not `main`).

## Verify next

Re-derive V1–V21 from plan §7.1 on a clean checkout of this branch. Do not trust counts from this file without re-running the commands.
