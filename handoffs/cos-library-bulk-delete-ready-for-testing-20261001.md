# Library bulk archive/delete — ready for testing

**Date:** 2026-10-01  
**Job:** `job-20261001-cos-library-bulk-delete-ready-for-testing`  
**Run:** `20261001T223715-ready-for-testing-4e1d23`  
**Branch:** `feat/cos-library-bulk-delete`  
**Base:** `integrate/campaign-os-brand-lanes-v1`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/cos-library-bulk-delete`

## Commit under test

| Item | SHA |
|---|---|
| Branch tip (product) | `0412d349265761d39961797b30f7a49e1b26a76b` |
| Short | `0412d349` |
| Origin tip | `origin/feat/cos-library-bulk-delete` @ tip after RFT push (includes this handoff) |

**Feature commits (2 ahead of base):**

- `0412d349` — `feat(library): bulk archive and delete on drafts and sandbox`
- `aa80108a` — `feat(library): read-only brand shelf with drafts, sandbox, and templates`

## Verification (worker)

From `campaign-os/` with bundled seed / scratch `DATA_DIR`:

```bash
WT=/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/cos-library-bulk-delete
cd "$WT/campaign-os"
python3 -m pytest tests/test_library_bulk.py tests/test_library_shelf.py -q
cd "$WT/web" && npm ci && npm run build
```

**Result (2026-10-01 RFT):** `13 passed` library pytest; web `build` OK.

Local smoke (job port **3077**):

```bash
export DATA_DIR=$(mktemp -d) BUNDLED_DATA_DIR="$WT/data" COS_JOB_TOKEN=dev-token PORT=3077
cd "$WT/campaign-os" && python3 app.py
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3077/api/health
```

## Scope

- **`/app/library`** (Heroes nav **Library**) — per-brand Drafts, Sandbox posts, Templates tabs.
- **Bulk toolbar** on Drafts and Sandbox: **Select visible**, **Clear**, **Archive**, **Delete** with confirm modal.
- **`POST /api/brands/<brand>/library/bulk`** — archive/delete drafts (sets `approvalStatus` or removes asset + sidecar); delete sandbox queue rows (skips receipt-only unless forced).
- **Draft delete** does **not** remove calendar moments on Planning.

## Manual QA — Kyle

**URL:** `http://127.0.0.1:3077/app/library` (port from job file; Railway `/app/library` after land). Pick **one brand** (not “All brands”). Session login on prod as usual.

| # | Step | Expected |
|---|---|---|
| 1 | Open **Library** for a brand with sandbox rows | **Sandbox posts** tab lists queue rows; toolbar shows selection counts |
| 2 | On **Sandbox posts**, click **Select visible** | All selectable rows checked; receipt-only rows stay unselectable |
| 3 | Select a **no-image** (or caption-only) sandbox row, click **Delete**, confirm | Row disappears from sandbox list; no error toast |
| 4 | Switch to **Drafts**, select a **pending** draft, click **Archive**, confirm | Draft moves to **Archived only** filter / `approvalStatus` archived |
| 5 | Note a draft that still has a **Planning** calendar slot (same brand), **Delete** that draft, confirm | Draft gone from Library |
| 6 | Open **Planning** (week/month view for same brand) | Original calendar slot/moment **still present** — only the draft asset was removed |

## Push

Branch `feat/cos-library-bulk-delete` pushed to `origin` after verify PASS and this handoff commit. Do **not** push `main` / `develop` / `master`.
