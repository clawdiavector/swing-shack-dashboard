# Ready for testing: Campaign OS L5 — Create (draft jobs + ops tab)

**Date:** 2026-09-17  
**Job:** `job-20260917-campaign-os-l5-create-ready-for-testing` (Cursor, ready-for-testing)  
**Verify:** `job-20260917-campaign-os-l5-create-verify` (Pi, read-only)  
**Verify verdict:** **PASS** — `20260917T121057-review-d6283e` @ `eed40a1`: drafts-only, jobs registered, Create tab + spend cap in tests; `14p/0f` new L5 suite, identical failure set vs base (`agent-control` last-run record)  
**Plan:** `agent-control/handoffs/campaign-os-l5-create-plan-20260917.md` + `agent-control/handoffs/campaign-os-layers/L5-create.md`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-l5-create`  
**Merge target:** `integrate/campaign-os-option-c` — **do not** push `main` / `master` / `develop`.  
**Deploy:** **none** (RFT only; no Railway).

## One-line summary

L5 Create layer: `draft_assets` + `asset_qc` JobSpecs turn L4-approved queue rows into `draft_asset` inbox entries (caption / image / GBP dry-run paths); `/ops?layer=create` shows spend pill, draft counts, and manual **Run draft_assets**; L4 approve optionally enqueues via `CAMPAIGN_OS_L5_ENQUEUE`. Verify **PASS**. Feat branch **on origin**.

## Branches + SHAs

| Item | Value |
|---|---|
| Code-complete SHA | `eed40a1dd54e3291a44c9913550704da14a69e07` |
| Short | `eed40a1` |
| Origin tip | `origin/feat/campaign-os-l5-create` @ `eed40a1`+handoff (pushed by RFT job) |
| Integrate tip at RFT | `origin/integrate/campaign-os-option-c` @ `86b8a20` |
| RFT handoff commit | lands after this file (see git log) |

## Push state

| Branch | On origin? | Notes |
|---|---|---|
| `feat/campaign-os-l5-create` | **YES** @ `eed40a1`+handoff | RFT pushes code tip then handoff doc. |

## RFT re-verify (this job)

Fresh pytest on scoped L5 suite (verification-before-completion):

```bash
cd campaign-os
python3 -m pytest tests/jobs/test_layer5_create.py tests/jobs/test_ops_layers_ribbon.py -q
```

**Result:** `31 passed, 0 failed` (2026-09-17, RFT job).

Pi verify reported `14p/0f` on `test_layer5_create.py` only at the same SHA — ribbon/layers tests included in RFT scope, not a product divergence.

## Done-when (L5-create.md — product writer scope)

| Criterion | Status | Evidence |
|---|---|---|
| Jobs: `draft_assets`, `asset_qc` registered | **PASS** | `test_layer5_specs_registered`; `registry.py` + `layer5/` |
| Drafts appear as `draft_asset` in unified inbox | **PASS** | `test_draft_assets_writes_inbox_row`, brand-scoped visibility |
| Missing LLM key → LATE (not crash) | **PASS** | `test_draft_assets_missing_llm_is_late`; `best_effort=True` on `draft_assets` |
| Spend cap respected | **PASS** | `test_draft_assets_respects_cap` |
| `/ops?layer=create` spend pill + last writes | **PASS** | `ops-jobs.html` Create tab; `test_ops_create_layer_rollup` |
| L4 approve → enqueue hook (fixture) | **PASS** | `test_l4_approve_enqueues_when_flag_set` |
| `asset_qc` deterministic checks | **PASS** | `test_asset_qc_*` suite |
| No Postiz / GBP publish HTTP | **PASS** | Pi verify drafts-only checklist; no publish routes in job code |

**Out of scope (not RFT blockers):**

| Criterion | Status | Notes |
|---|---|---|
| Mac profiles `cos-caption` / `cos-image` / `cos-gbp` (tL5-3) | **DEFERRED** | Kyle Mac sheet; queue rows stubbed in tests |
| Live GBP OAuth polish | **DEFERRED** | GBP dry-run planner only (`publish=False`) |
| Christelle end-to-end dry-run | **CHECKLIST BELOW** | Kyle manual after land |

## Manual tests — `/ops?layer=create` with fixture approved item

Environment: local worktree, scratch `$DATA_DIR`, port from job file **`3456`**. Session login required for ops UI (bearer for job run). Never print secret values.

**Fixture setup** (approved proposal → queue row):

```bash
DATA_DIR=/tmp/cos-l5-manual
mkdir -p "$DATA_DIR/proposals"
cat > "$DATA_DIR/brands.json" <<'EOF'
{"brands":{"stick":{"id":"stick","campaign_ids":["camp-stick"]}}}
EOF
cat > "$DATA_DIR/campaign-data.json" <<'EOF'
{"campaigns":{"camp-stick":{"identity":{"name":"Stick drafts","brand":"stick"},"assets":{}}}}
EOF
cat > "$DATA_DIR/proposals/pending.jsonl" <<'EOF'
{"id":"prop-fixture-1","brand_id":"stick","title":"L5 manual fixture","status":"approved","approved_at":"2026-09-17T10:00:00Z"}
EOF
cat > "$DATA_DIR/agent-queue.json" <<'EOF'
{"schema":"campaign-os/agent-queue/v1","generated_at":"2026-09-17T10:00:00Z","rows":[{"id":"manual-stick-cos-caption-draft_caption","layer":"L3","agent":"cos-caption","brand":"stick","action":"draft_caption","payload_ref":"inbox/proposal:stick:prop-fixture-1","status":"pending"}]}
EOF
```

| # | Step | Expected |
|---|---|---|
| 1 | Start app: `cd campaign-os && DATA_DIR=$DATA_DIR COS_JOB_TOKEN=local-dev PORT=3456 python3 app.py` | Health OK |
| 2 | Log in → open `/ops?layer=create` | Create tab: spend pill loads; L5 rollup not `NEVER`-only stub |
| 3 | Confirm spend pill shows cap / remaining | Chip from `GET /api/ops/llm-spend` |
| 4 | Click **Run draft_assets** (or bearer `POST /api/jobs/run/draft_assets?reason=manual`) | Job completes; toast OK or LATE if no LLM key |
| 5 | Open **Review** (`/?page=review`) → filter **Draft** | New `draft_asset` row for stick (if caption path succeeded) |
| 6 | Re-open `/ops?layer=create` | Draft count / last-run metrics updated |
| 7 | Confirm **nothing published** | No new Postiz receipt; no GBP publish HTTP |

Optional eyeball URLs (port **3456**):

```bash
# browser: http://127.0.0.1:3456/ops?layer=create
# review:  http://127.0.0.1:3456/?page=review
```

Automated coverage: `campaign-os/tests/jobs/test_layer5_create.py` exercises registration, cap, inbox write, enqueue hook, and anon 401 without a dev server.

## Commits on feat (vs `integrate/campaign-os-option-c`)

1. `eed40a1` feat(l5): draft_assets, asset_qc jobs, and Create ops tab

## Files touched (product)

| Path | Change |
|---|---|
| `campaign-os/_lib/jobs/layer5/draft_assets.py` | **new** — approved queue → draft inbox + sidecar |
| `campaign-os/_lib/jobs/layer5/asset_qc.py` | **new** — deterministic QC |
| `campaign-os/_lib/jobs/layer5/__init__.py` | **new** — JobSpec registration |
| `campaign-os/_lib/jobs/registry.py` | bootstrap Layer 5 |
| `campaign-os/_lib/unified_inbox.py` | draft write helpers |
| `campaign-os/_lib/ops_layers.py` | L5 rollup (draft counts, spend) |
| `campaign-os/_lib/ops_agents.py` | enqueue on L4 approve when flagged |
| `campaign-os/_lib/intelligence.py` | runtime `brands.json` for brand scope |
| `campaign-os/ops-jobs.html` | Create tab + spend pill + run button |
| `campaign-os/tests/jobs/test_layer5_create.py` | **new** — 14 tests |
| `campaign-os/tests/jobs/test_ops_layers_ribbon.py` | L5 no longer stub-only |
| `tests/ci-allowlist.txt` | allowlist new test file |

## Jobs registered

| Job | Cadence | Criticality | best_effort | Writes |
|---|---|---|---|---|
| `draft_assets` | 24h | MEDIUM | yes (missing key → LATE) | `draft-assets/`, `campaign-data.json` |
| `asset_qc` | 24h | LOW | no | `asset-qc.json` |

## Open Kyle items

1. **Land** — next job merges `feat/campaign-os-l5-create` → `integrate/campaign-os-option-c` (integration push OK; not `main`).
2. **Mac fleet (tL5-3)** — `cos-caption`, `cos-image`, `cos-gbp` profiles on Kyle Mac (separate sheet).
3. **L6** — publish remains sandbox; draft approve still ≠ publish.

## Suggested board / comment draft

Campaign OS L5 Create ready for testing. `feat/campaign-os-l5-create` @ `eed40a1` on origin. Pi verify **PASS** (14 new tests, drafts-only, Create tab). RFT re-verify **31p/0f**. Manual: `/ops?layer=create` with fixture approved proposal. Target merge: `integrate/campaign-os-option-c`. No deploy. Suggested column: **Ready for testing**.

## Land (next job)

`job-20260917-campaign-os-l5-create-land` — merge feat → integrate locally, push `integrate/campaign-os-option-c` only.
