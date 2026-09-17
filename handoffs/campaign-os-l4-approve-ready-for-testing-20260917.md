# Ready for testing: Campaign OS L4 — Approve (unified inbox)

**Date:** 2026-09-17  
**Job:** `job-20260917-campaign-os-l4-approve-ready-for-testing` (Cursor, ready-for-testing)  
**Verify:** `job-20260917-campaign-os-l4-approve-verify` (Pi, read-only)  
**Verify verdict:** **PASS** — `20260917T104639-review-f790e9` @ `05a5d03`: unified inbox API (4 item types), review UI with type filters, calendar transitions reused, ops Approve counts, `#sec-agents` hidden, stubs 501, anon 401, approve ≠ publish (`23p/0f`, checklist `6/6`)  
**Plan:** `agent-control/handoffs/campaign-os-l4-approve-plan-20260917.md` + `agent-control/handoffs/campaign-os-layers/L4-approve.md`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-l4-approve`  
**Merge target:** `integrate/campaign-os-option-c` — **do not** push `main` / `master` / `develop`.  
**Deploy:** **none** (RFT only; no Railway).

## One-line summary

L4 Approve layer: session-gated unified inbox API + Review tab UI (approve / edit / reject) for calendar candidates, proposals, draft assets, and publish requests; `/ops?layer=approve` counts-only tab with deep link to product inbox; `#sec-agents` hidden. Verify **PASS**. Feat branch **on origin**.

## Branches + SHAs

| Item | Value |
|---|---|
| Code-complete SHA | `05a5d03177cbe3465829e9d81a4da6d1b5bbb9d3` |
| Short | `05a5d03` |
| Origin tip | `origin/feat/campaign-os-l4-approve` @ `05a5d03`+handoff (pushed by RFT job) |
| Integrate tip at RFT | `origin/integrate/campaign-os-option-c` @ `0384916` |
| RFT handoff commit | lands after this file (see git log) |

## Push state

| Branch | On origin? | Notes |
|---|---|---|
| `feat/campaign-os-l4-approve` | **YES** @ `05a5d03`+handoff | RFT pushes code tip then handoff doc. |

## RFT re-verify (this job)

Fresh pytest on scoped L4 suite (verification-before-completion):

```bash
cd campaign-os
python3 -m pytest tests/jobs/test_unified_inbox_l4.py tests/jobs/test_ops_layers_ribbon.py -q
```

**Result:** `23 passed, 0 failed` (2026-09-17, RFT job).

Pi verify reported `23p/0f` on the review worktree at the same SHA — counts match.

## Done-when (L4-approve.md — product writer scope)

| Criterion | Status | Evidence |
|---|---|---|
| Unified inbox API lists `calendar_candidate`, `proposal`, `draft_asset`, `publish_request` | **PASS** | `test_unified_list_schema`, verify checklist |
| Product UI: one queue, filters by brand + type, approve / edit / reject | **PASS** | `campaign-os.html` unified inbox render + type filter pills |
| Calendar candidate approve → existing calendar transition (no duplicate) | **PASS** | verify checklist; calendar path reuses `/api/calendar/transition` |
| `/ops?layer=approve` pending / stale / approved-today + deep link | **PASS** | `test_layers_l4_counts`, `ops-jobs.html` Approve tab |
| `#sec-agents` hidden or retired | **PASS** | `sec-agents` section + nav `hidden`; `/ops?layer=agents` is live replacement |
| Stubs: Postiz reschedule, drag-reorder → 501 JSON | **PASS** | `test_unified_stubs_501` |
| Approve draft ≠ publish; publish_request approve does not dispatch | **PASS** | verify checklist |
| Anon → 401 on inbox routes | **PASS** | `test_unified_list_anon_401` |
| Edit writes `human-edits.jsonl` for L7 | **PASS** | `test_unified_approve_reject_edit_draft` |

**Out of scope (K12 / post-land — not RFT blockers):**

| Criterion | Status | Notes |
|---|---|---|
| Christelle live 15-min dry-run recorded | **CHECKLIST BELOW** | Kyle K12 gate; do not block land |

## Manual tests — Review tab + `/ops?layer=approve`

Environment: local worktree, scratch `$DATA_DIR`, port from job file **`3478`**. Session login required (anon → `/login`). Never print secret values.

| # | Step | Expected |
|---|---|---|
| 1 | `GET /api/inbox/unified` without session | `401` |
| 2 | Log in → open **Review** (`/?page=review` or nav **Review**) | Unified summary line; type filter pills (All / Calendar / Proposal / Draft / Publish) |
| 3 | Pick brand (if multi-brand data present) | List scopes to brand; pending rows show Approve / Edit / Reject |
| 4 | Filter **Calendar** | Only `calendar_candidate` rows |
| 5 | Approve one calendar candidate | Row leaves pending; status updates; no publish side-effect |
| 6 | Open `/ops?layer=approve` | Counts: pending, stale, approved_today; link to product inbox (`inbox_href`) |
| 7 | Reject one draft asset with reason | Row moves to rejected; reason persisted |
| 8 | Edit one caption | `$DATA_DIR/human-edits.jsonl` gains one line |
| 9 | `POST /api/inbox/unified/postiz-reschedule` | `501` stub JSON |
| 10 | `#sec-agents` nav / section | Hidden; `/ops?layer=agents` still works |

Automated coverage: `campaign-os/tests/jobs/test_unified_inbox_l4.py` exercises steps 1, 7–9 without a dev server.

Optional eyeball (port **3478**):

```bash
cd /home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-l4-approve/campaign-os
DATA_DIR=/tmp/cos-l4-manual COS_JOB_TOKEN=local-dev PORT=3478 python3 app.py
# browser: http://127.0.0.1:3478/?page=review
# ops:     http://127.0.0.1:3478/ops?layer=approve
```

## Christelle 15-min dry-run checklist (K12 — post-integrate)

**Target:** under 15 minutes end-to-end. **Do not block land** — Kyle runs this after merge to integrate (or on a preview URL). Agents never click approve.

| # | Step | Pass? | Notes |
|---|---|---|---|
| 1 | Log in to Campaign OS (session) | ☐ | Railway prod or local port **3478** with real `$DATA_DIR` |
| 2 | Pick brand (e.g. **stick** or **swing-shack**) | ☐ | Brand selector matches your daily workflow |
| 3 | Open **Review** tab | ☐ | Unified inbox loads; summary shows pending + stale counts |
| 4 | Filter to **Calendar** | ☐ | Only calendar candidates visible |
| 5 | Approve **one** calendar candidate | ☐ | Row leaves pending queue within one refresh |
| 6 | Open `/ops?layer=approve` in a second tab | ☐ | **Pending** count dropped by 1 vs step 3 snapshot |
| 7 | Return to Review; filter **Draft** (or All) | ☐ | Pick one draft asset |
| 8 | **Reject** with a short reason | ☐ | Row moves to rejected; reason visible on re-open |
| 9 | Pick another draft; **Edit** caption | ☐ | Saved caption visible; confirm `$DATA_DIR/human-edits.jsonl` grew by one line (Kyle/admin check) |
| 10 | Confirm **nothing published** | ☐ | `GET /api/publish/sandbox/summary` → `receipt_count` unchanged; no new Postiz receipt |
| 11 | Optional: approve a **proposal** row | ☐ | Exactly one lane content-item; double-approve does not duplicate |
| 12 | Optional: `#sec-agents` nav | ☐ | Hidden in SPA; use `/ops?layer=agents` for roster instead |

**Stop the clock at step 10** if time-boxed — steps 11–12 are bonus coverage.

Record outcome in a follow-up note (date, URL, pass/fail per row, blockers). This handoff supplies the checklist only; Christelle does not need to run before land.

## Commits on feat (vs `integrate/campaign-os-option-c`)

1. `05a5d03` feat(l4): unified inbox API, review UI, and ops Approve counts

## Files touched (product)

| Path | Change |
|---|---|
| `campaign-os/_lib/unified_inbox.py` | **new** — adapter, actions, counts |
| `campaign-os/app.py` | five inbox routes + stubs |
| `campaign-os/campaign-os.html` | unified Review UI, type filters, `#sec-agents` hidden |
| `campaign-os/ops-jobs.html` | Approve tab counts + inbox link |
| `campaign-os/_lib/ops_layers.py` | L4 rollup from inbox counts |
| `campaign-os/tests/jobs/test_unified_inbox_l4.py` | **new** — 6 tests |
| `campaign-os/tests/jobs/test_ops_layers_ribbon.py` | L4 no longer stub `NEVER` only |
| `tests/ci-allowlist.txt` | allowlist new test file |

## API surface (session-gated unless noted)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/inbox/unified?brand=&status=` | List unified items |
| POST | `/api/inbox/unified/<id>/approve` | Approve without publishing |
| POST | `/api/inbox/unified/<id>/reject` | Reject with reason |
| POST | `/api/inbox/unified/<id>/edit` | Edit + `human-edits.jsonl` signal |
| POST | `/api/inbox/unified/postiz-reschedule` | Stub → 501 until L6 |
| POST | `/api/inbox/unified/reorder` | Stub → 501 until L6 |

## Open Kyle items

1. **Land** — next job merges `feat/campaign-os-l4-approve` → `integrate/campaign-os-option-c` (integration push OK; not `main`).
2. **Christelle K12 dry-run** — use checklist § above after land (or on preview).
3. **L5 / L6** — publish_request items appear in inbox; full publish flow remains L6.

## Suggested board / comment draft

Campaign OS L4 Approve ready for testing. `feat/campaign-os-l4-approve` @ `05a5d03` on origin. Pi verify **PASS** (unified inbox 4 types, Review UI, ops Approve counts, approve ≠ publish). RFT re-verify **23p/0f**. Christelle 15-min checklist in handoff (K12 post-land). Target merge: `integrate/campaign-os-option-c`. No deploy. Suggested column: **Ready for testing**.

## Land (next job)

`job-20260917-campaign-os-l4-approve-land` — merge feat → integrate locally, push `integrate/campaign-os-option-c` only.
