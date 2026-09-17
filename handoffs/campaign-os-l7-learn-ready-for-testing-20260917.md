# Ready for testing: Campaign OS L7 — Learn (outcomes → recipes)

**Date:** 2026-09-17  
**Job:** `job-20260917-campaign-os-l7-learn-ready-for-testing` (Cursor, ready-for-testing)  
**Verify:** `job-20260917-campaign-os-l7-learn-verify` (Pi, read-only)  
**Verify verdict:** **PASS** — `20260917T125123-review-077e38` @ `e6608ed`: 16/16 L7 tests, 47/47 total; 4 jobs registered; `winning-recipes.json` contract frozen; Learn tab operational; no auto-publish  
**Plan:** `agent-control/handoffs/campaign-os-l7-learn-plan-20260917.md` + `agent-control/handoffs/campaign-os-layers/L7-learn.md`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-l7-learn`  
**Merge target:** `integrate/campaign-os-option-c` — **do not** push `main` / `master` / `develop`.  
**Deploy:** **none** (RFT only; no Railway).

## One-line summary

L7 Learn layer: `post_outcomes`, `winner_promotion`, `proposal_outcome`, and `human_edit_signal` jobs turn Meta/GA4 fixtures + L4 human edits into `post-outcomes.json`, `winning-recipes.json`, and related summaries; `GET /api/ops/learn/summary` and `/ops?layer=learn` expose the rollup. Verify **PASS**. Feat branch **on origin**.

## Branches + SHAs

| Item | Value |
|---|---|
| Code-complete SHA | `e6608ed27228b3094d2982ace9ea154bae084290` |
| Short | `e6608ed` |
| Origin tip | `origin/feat/campaign-os-l7-learn` @ `e6608ed`+handoff (pushed by RFT job) |
| Integrate tip at RFT | `origin/integrate/campaign-os-option-c` @ `6bccf87` |
| RFT handoff commit | lands after this file (see git log) |

## Push state

| Branch | On origin? | Notes |
|---|---|---|
| `feat/campaign-os-l7-learn` | **YES** @ `e6608ed`+handoff | RFT pushes code tip then handoff doc. |

## RFT re-verify (this job)

Fresh pytest on scoped L7 suite (verification-before-completion):

```bash
cd campaign-os
python3 -m pytest tests/jobs/test_layer7_learn.py tests/jobs/test_ops_layers_ribbon.py -q
```

**Result:** `33 passed, 0 failed` (2026-09-17, RFT job).

Pi verify reported `16p/0f` on `test_layer7_learn.py` only at the same SHA — ribbon/layers tests included in RFT scope, not a product divergence.

## Done-when (L7-learn.md — product writer scope)

| Criterion | Status | Evidence |
|---|---|---|
| Jobs: `post_outcomes`, `winner_promotion`, `proposal_outcome`, `human_edit_signal` registered | **PASS** | `test_l7_jobs_registered`; `layer7/__init__.py` |
| `GET /api/ops/learn/summary` for ops tab | **PASS** | `test_learn_summary_bearer_and_session`; `app.py` route |
| `winning-recipes.json` contract (v1 schema) | **PASS** | `test_winning_recipes_schema_frozen`; relative ranking, not 0.65 threshold |
| `/ops?layer=learn` tab | **PASS** | `test_ops_learn_tab_renders`; `ops-jobs.html` Learn tab |
| Post outcomes join receipt → IG post | **PASS** | `test_post_outcomes_joins_receipt_to_ig_post` |
| Relative winners (not empty recipes on fixture band) | **PASS** | `test_winner_promotion_relative_ranking` |
| No auto-publish / no auto-approve | **PASS** | Pi verify grep checklist; no publish routes in L7 package |
| L4 edit → `human-edits.jsonl` feeds L7 | **PASS** | `test_human_edit_signal_*`; L4 `previous` capture in `unified_inbox.py` |

**Out of scope (not RFT blockers):**

| Criterion | Status | Notes |
|---|---|---|
| `ab_autospawn` job | **DEFERRED** | Plan §2.6 — needs L5 enqueue normalisation fix first |
| `cos-learn` weekly Mac profile (tL7-4) | **DEFERRED** | mac-bridge; blocked on K8 (Mac awake + Tailscale) |
| L5/L3 consuming `winning-recipes.json` in prompts | **DEFERRED** | File shipped; injection is a separate L5 ticket |
| `test_suggested_checks.py`, `test_v2026_08_07_reference_library.py::TestFlaskRoutes` | **PRE-EXISTING RED** | Red at base `6bccf87`; not in CI allowlist — not attributed to L7 |

## `winning-recipes.json` contract (frozen v1)

Schema: `campaign-os/winning-recipes/v1`. Written by `winner_promotion` from `post-outcomes.json`.

| Field | Meaning |
|---|---|
| `ready` | `true` when `samples >= 8` in the 30-day window |
| `winners` | Count of promoted recipes (top 25% percentile) |
| `score_basis` | `"engagement_only"` when GA4 attribution is zero |
| `recipes[]` | Each row: `recipe_id`, `brand_id`, `rank`, `percentile`, `score`, `evidence`, `join_basis` |

Relative ranking only — **not** the 0.65 image-gen absolute threshold. Empty `recipes[]` with a populated fixture band is a regression.

## Manual tests — `/ops?layer=learn`

Environment: local worktree, scratch `$DATA_DIR`, port from job file **`3880`**. Session login required for ops UI (bearer for job run). Never print secret values.

**Fixture setup** (copy L7 test fixtures into scratch `$DATA_DIR`):

```bash
DATA_DIR=/tmp/cos-l7-manual
FIX=campaign-os/tests/jobs/fixtures/layer7
mkdir -p "$DATA_DIR/proposals" "$DATA_DIR/publish-sandbox"
cp "$FIX/ig-business-analytics.min.json" "$DATA_DIR/ig-business-analytics.json"
cp "$FIX/post-conversion-score.min.json" "$DATA_DIR/post-conversion-score.json"
cp "$FIX/receipts.jsonl" "$DATA_DIR/publish-sandbox/receipts.jsonl"
cp "$FIX/human-edits.jsonl" "$DATA_DIR/human-edits.jsonl"
cp "$FIX/proposals-pending.jsonl" "$DATA_DIR/proposals/pending.jsonl"
```

| # | Step | Expected |
|---|---|---|
| 1 | Start app: `cd campaign-os && DATA_DIR=$DATA_DIR COS_JOB_TOKEN=local-dev PORT=3880 python3 app.py` | Health OK |
| 2 | Log in → open `/ops?layer=learn` | Learn tab loads; rollup chips not stub-only |
| 3 | Bearer `POST /api/jobs/run/post_outcomes?reason=manual` | Job OK; `post-outcomes.json` written |
| 4 | Bearer `POST /api/jobs/run/winner_promotion?reason=manual` | Job OK; `winning-recipes.json` has `winners >= 1` |
| 5 | Bearer `POST /api/jobs/run/human_edit_signal?reason=manual` | `human-edit-summary.json` written |
| 6 | Bearer `POST /api/jobs/run/proposal_outcome?reason=manual` | `proposal-outcomes.json` written |
| 7 | `GET /api/ops/learn/summary` (session or bearer) | `200`, schema `campaign-os/ops-learn-summary/v1` |
| 8 | Re-open `/ops?layer=learn` | Recipe count / last-run metrics updated |
| 9 | Confirm **nothing published** | No Postiz dispatch; no new live receipts |

Optional eyeball URLs (port **3880**):

```bash
# browser: http://127.0.0.1:3880/ops?layer=learn
# API:     http://127.0.0.1:3880/api/ops/learn/summary
```

Automated coverage: `campaign-os/tests/jobs/test_layer7_learn.py` exercises jobs, summary API, auth gate, and Learn tab without a dev server.

## Commits on feat (vs `integrate/campaign-os-option-c`)

1. `e6608ed` feat(l7): learn loop — outcomes, recipes, summary API, Learn tab

## Files touched (product)

| Path | Change |
|---|---|
| `campaign-os/_lib/jobs/layer7/post_outcomes.py` | **new** — Meta + receipts → post outcomes |
| `campaign-os/_lib/jobs/layer7/winner_promotion.py` | **new** — relative ranking → winning recipes |
| `campaign-os/_lib/jobs/layer7/proposal_outcome.py` | **new** — L3 proposal approve/reject gate |
| `campaign-os/_lib/jobs/layer7/human_edit_signal.py` | **new** — aggregate human-edits.jsonl |
| `campaign-os/_lib/jobs/layer7/__init__.py` | **new** — JobSpec registration |
| `campaign-os/_lib/feedback_loop.py` | extend — `rank_outcomes`, `promote_winners` |
| `campaign-os/_lib/ops_layers.py` | L7 rollup + `build_learn_summary()` |
| `campaign-os/_lib/unified_inbox.py` | L4 edit `previous` capture for L7 |
| `campaign-os/app.py` | `GET /api/ops/learn/summary` |
| `campaign-os/ops-jobs.html` | Learn tab |
| `campaign-os/tests/jobs/test_layer7_learn.py` | **new** — 16 tests |
| `campaign-os/tests/jobs/fixtures/layer7/*` | **new** — fixture bundle |
| `campaign-os/tests/jobs/test_ops_layers_ribbon.py` | L7 no longer stub-only |
| `tests/ci-allowlist.txt` | allowlist new test file |

## Jobs registered

| Job | Cadence | Criticality | best_effort | Writes |
|---|---|---|---|---|
| `post_outcomes` | 24h | MEDIUM | yes | `post-outcomes.json` |
| `human_edit_signal` | 24h | LOW | yes | `human-edit-summary.json` |
| `winner_promotion` | 24h | MEDIUM | no | `winning-recipes.json` |
| `proposal_outcome` | 24h | LOW | yes | `proposal-outcomes.json` |

## Open Kyle items

1. **Land** — next job merges `feat/campaign-os-l7-learn` → `integrate/campaign-os-option-c` (integration push OK; not `main`).
2. **L5 injection** — wire `winning-recipes.json` into caption/proposal context (separate ticket).
3. **Mac fleet (tL7-4)** — optional `cos-learn` weekly profile on Kyle Mac (disabled until L3 fleet exists).

## Suggested board / comment draft

Campaign OS L7 Learn ready for testing. `feat/campaign-os-l7-learn` @ `e6608ed` on origin. Pi verify **PASS** (16 new tests, 4 jobs, winning-recipes contract). RFT re-verify **33p/0f**. Manual: `/ops?layer=learn` with fixture bundle. Target merge: `integrate/campaign-os-option-c`. No deploy. Suggested column: **Ready for testing**.

## Land (next job)

`job-20260917-campaign-os-l7-learn-land` — merge feat → integrate locally, push `integrate/campaign-os-option-c` only.
