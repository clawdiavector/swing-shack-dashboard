# Ready for testing: Campaign OS L5 — visible caption + image drafts

**Date:** 2026-09-21  
**Job:** `job-20260921-cos-l5-draft-visible-ready-for-testing` (Cursor, ready-for-testing)  
**Verify:** `job-20260921-cos-l5-draft-visible-verify` (Hermes MiniMax-M3, read-only)  
**Verify verdict:** **PASS** — `20260921T173152-review-fbe135` @ `eea3ba0`: `28p/0f` on `test_layer5_create.py`; AC-1..AC-6 covered (`agent-control` last-run record, fingerprint `8211e260ed2e`)  
**Plan:** `agent-control/manifests/plan-20260921-cos-l5-draft-visible.yaml`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/cos-l5-draft-visible`  
**Merge target:** `main` — **Kyle gate only**; do **not** push `main` / `master` / `develop` from agents.  
**Deploy:** **none** (RFT only; manual QA on prod/staging after Kyle lands).

## One-line summary

L5 `draft_assets` now surfaces caption **and** image in Review, crash-proofs stick/bag-drop with frame-bearing diagnostics, fans out **sandbox** publish requests per brand `publish_channels` (SS: IG+FB+GBP; Stick: IG+FB), and exposes full caption/image fields in unified inbox payloads. Verify **PASS**. Feat branch **on origin** after this job.

## Branches + SHAs

| Item | Value |
|---|---|
| Code-complete SHA | `eea3ba081800abf0b2e5dc9e570de932a52e6c62` |
| Short | `eea3ba0` |
| Branch | `feat/cos-l5-draft-visible` |
| Origin tip | `origin/feat/cos-l5-draft-visible` @ handoff tip (pushed by RFT job) |
| RFT handoff commit | see `git log -1 -- handoffs/cos-l5-draft-visible-ready-for-testing-20260921.md` |

## Push state

| Branch | On origin? | Notes |
|---|---|---|
| `feat/cos-l5-draft-visible` | **YES** @ tip | RFT pushes code + handoff doc. Never `main`. |

## RFT re-verify (this job)

Fresh pytest on scoped L5 suite (verification-before-completion):

```bash
cd campaign-os
python3 -m pytest tests/jobs/test_layer5_create.py -q
```

**Result:** `28 passed, 0 failed` (2026-09-21, RFT job).

Hermes verify reported identical `28p/0f` at `eea3ba0`.

## Intended publish channels (product data)

| Brand | `publish_channels` |
|---|---|
| **swing-shack** | `instagram`, `facebook`, `gbp` |
| **stick** | `instagram`, `facebook` |
| **bag-drop** | `[]` (no publish fan-out) |

Source: `data/brands.json` on feat tip.

## Manual tests — prod / staging Review (post-land)

**Environment:** Production — https://swing-shack-dashboard-production.up.railway.app (session login required). Staging: same UI if a preview deploy exists; steps identical. Postiz stays **sandbox** — no live HTTP from this slice.

**Precondition:** Slice landed to prod (`main` deploy). `CAMPAIGN_OS_L5_ENQUEUE=1` on Railway. Approve at least one **calendar_candidate** per brand (Stick Term 4 school holidays or any SS calendar row) so L4 → L5 enqueue runs.

| # | Step | Expected |
|---|---|---|
| 1 | Log in → open **Review**: `/?page=review` | Unified inbox loads; type filter pills visible |
| 2 | Click **📝 Drafts** filter (`data-rtype="draft_asset"`) | List narrows to draft rows only |
| 3 | Select brand **stick** in the global brand picker (top nav) | Draft rows scoped to Stick |
| 4 | Find a **draft_asset** row with caption preview in the summary line | Row shows caption snippet + brand pill `stick` |
| 5 | Click **Open** on that draft | Modal shows **Caption** block with text + **Current visual** with image (or reachable URL) |
| 6 | Edit caption inline (✏️ Edit → Save) | Toast OK; reopen shows updated text (iteration path) |
| 7 | Switch brand picker to **swing-shack** | Draft list refreshes for SS |
| 8 | Open an SS **draft_asset** | Caption + image visible same as step 5 |
| 9 | Click **🚀 Publish** filter (`data-rtype="publish_request"`) | Sandbox publish-request rows appear after QC pass |
| 10 | For **stick**: confirm inbox rows (or API) for **instagram** and **facebook** channels | Two publish_request items or matching sandbox receipts |
| 11 | For **swing-shack**: confirm **instagram**, **facebook**, and **gbp** | Three channel artifacts |
| 12 | Optional API spot-check (session cookie): `GET /api/inbox/unified?brand=stick&status=all` | Items with `type: draft_asset` include `meta.caption`, `meta.image_path` or `meta.image_url` |
| 13 | Optional sandbox receipts: while logged in, inspect `$DATA_DIR/publish-sandbox/receipts.jsonl` on volume **or** L6 ops rollup | Each receipt has `"mode": "sandbox"`; one row per intended channel |
| 14 | Confirm **no live Postiz publish** | Connected Accounts still sandbox; no new live post IDs |

**Ops shortcut (optional):** `/ops?layer=create` → **Open Review inbox** link; **Run draft_assets** if queue rows exist but drafts missing.

**Local repro (pre-land):** worktree port **3164** from job file; scratch `$DATA_DIR`; same Review URL paths on `http://127.0.0.1:3164/?page=review`.

## verify_calendar (Kyle — post-merge)

Cannot PASS on verify day per plan. After land, Kyle iterates caption/image from Review (steps 1–8 above) and confirms sandbox receipts per channel (steps 9–13).

## Commits on feat (vs `main`)

1. `eea3ba0` feat(l5): visible caption+image drafts and per-channel sandbox publish
2. *(RFT)* docs: ready-for-testing handoff

## Files touched (product)

| Path | Change |
|---|---|
| `campaign-os/_lib/jobs/layer5/draft_assets.py` | crash-proof + caption/image paths |
| `campaign-os/_lib/jobs/layer5/image_draft_context.py` | **new** — image context helper |
| `campaign-os/_lib/jobs/layer5/asset_qc.py` | sandbox publish enqueue hook |
| `campaign-os/_lib/unified_inbox.py` | expose caption + image in draft payload |
| `campaign-os/_lib/publish_sandbox.py` | per-channel sandbox fan-out |
| `campaign-os/tests/jobs/test_layer5_create.py` | +14 tests (28 total) |
| `data/brands.json` | `publish_channels` per brand |

## Open Kyle items

1. **Land** — merge `feat/cos-l5-draft-visible` → `main` (Kyle gate; next job `job-20260921-cos-l5-draft-visible-land`).
2. **verify_calendar** — manual Review iteration after prod deploy.
3. **Postiz OAuth** — stick IG+FB still unconfirmed in prod UI (`agent-control/context/campaign-os-auth-status.md`).

## Suggested board / comment draft

Campaign OS L5 visible drafts ready for testing. `feat/cos-l5-draft-visible` @ tip on origin. Hermes verify **PASS** (`28p/0f`, AC-1..AC-6). Manual: prod `/?page=review` → Drafts filter → open caption+image for stick and swing-shack → Publish filter for sandbox receipts (SS: IG+FB+GBP; Stick: IG+FB). Target merge: **main** (Kyle gate). No deploy from RFT. Suggested column: **Ready for testing**.

## Land (next job)

`job-20260921-cos-l5-draft-visible-land` — local merge prep feat → main; hand off exact git commands. Do **not** push `main` unless Kyle names and approves in session.
