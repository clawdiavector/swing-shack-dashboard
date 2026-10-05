# ClubLab pull lab — ready for testing

**Date:** 2026-10-05  
**Job:** `job-20261005-cos-clublab-pull-ready-for-testing`  
**Run:** `20261005T190524-ready-for-testing-bebfcd`  
**Verify:** `job-20261005-cos-clublab-pull-verify` — **PASS** (`20261005T183851-review-f2a38c`, merge-gate `pass`, slice @ `a7146b90`)  
**Branch:** `feat/cos-clublab-pull`  
**Base:** `integrate/campaign-os-brand-lanes-v1`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/cos-clublab-pull`

## Commit under test

- **Feature tip (product code):** `a7146b90cd9b23540f3f902451562ea2028a5bcf` — `fix(campaign-os): ClubLab pull API paths and envelope unwrap`
- **Pushed branch tip:** update after this handoff commit (`git rev-parse origin/feat/cos-clublab-pull`)

## Page path

**Lab URL path:** `/clublab-pull`  
(Flask route in `campaign-os/_lib/clublab_pull_routes.py`; static shell `campaign-os/clublab-pull.html`.)

## ClubLab repo

**ClubLab was not modified.** All work is in Campaign OS (`swing-shack-dashboard-main`) only.

## Verify merge-gate (confirmed)

| Source | Verdict | Notes |
|---|---|---|
| `job-20261005-cos-clublab-pull-verify` last-run | **PASS** | 7/7 mocked tests; live snapshot PII-clean; GET-only pull |
| Manifest `verify_policy.merge_gate` | **pass** | RFT proceeds only after verify PASS |

## RFT re-verify (this job)

From `campaign-os/` with bundled seed data and scratch runtime dir:

```bash
WT=/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/cos-clublab-pull
export BUNDLED_DATA_DIR="$WT/data" DATA_DIR=$(mktemp -d) COS_JOB_TOKEN=dev-token
cd "$WT/campaign-os"
python3 -m pytest tests/test_clublab_pull.py -q --tb=short
```

**Result:** `7 passed, 0 failed` (exit 0, 2026-10-05 RFT).

## Push state

| Branch | On origin? | Notes |
|---|---|---|
| `feat/cos-clublab-pull` | **YES** @ `a7146b90` before handoff commit | RFT pushes again after handoff doc commit. Never `main` / `master` / `develop`. |

## Manual test steps (local)

Job web port: **3315** (from `.agent-job.json` `runtime.ports.web`).

1. **Start Campaign OS** (scratch data dir; any non-empty `COS_JOB_TOKEN` — do not print the value):

   ```bash
   WT=/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/cos-clublab-pull
   export BUNDLED_DATA_DIR="$WT/data"
   export DATA_DIR=$(mktemp -d)
   export COS_JOB_TOKEN=dev-token
   export PORT=3315
   cd "$WT/campaign-os"
   python3 app.py
   ```

2. **Load a snapshot** — either:
   - Click **Run live pull** on the lab page (requires `CLUBLAB_EMAIL` or `CLUBLAB_TOKEN` plus password in the environment; same rules as implement/verify), **or**
   - Copy a verified live snapshot into `$DATA_DIR` as `clublab-snapshot.json` (verify run used `/tmp/cos-clublab-live-pull/clublab-snapshot.json`).

3. **Open the lab page:** `http://127.0.0.1:3315/clublab-pull`

4. **Pick a facility** in the left **Facilities** list (page groups by facility id from the pull; do not hardcode ids).

5. **CRM counts:** In the **CRM** section, confirm KPI tiles (Active, At risk, Dormant, Follow-ups open, New today, Period paid) and the segment table; footer shows snapshot time and facility count.

6. **Sold products (OrderMe):** In **OrderMe**, confirm a table of product name, category, quantity, order count, and first/last order dates (top sellers by quantity).

7. **Fitting mix (FitMe):** In **FitMe**, confirm KPIs (Completed, In progress, In build, Cancelled) and the equipment table (top shafts/heads with selection counts).

8. **CoachMe (optional):** **CoachMe** shows session/player KPIs and tag-frequency counts without player ids.

9. **Ops link:** Header **Ops jobs** goes to `/ops?layer=jobs` where `clublab_pull` is listed as a Layer 2 job.

## Manual test steps (Railway, after land)

1. Log in to Campaign OS (session auth).
2. Open **`/clublab-pull`** on the deployed host.
3. Repeat steps 4–8 above after a live pull or deployed `$DATA_DIR` snapshot.

## Product commits on feat (vs base)

1. `a2538490` — feat(cos): clublab read-only pull (lab page + layer-2 job)  
2. `e8c03118` — fix(campaign-os): read ClubLab token from data.accessToken  
3. `a7146b90` — fix(campaign-os): ClubLab pull API paths and envelope unwrap  
4. *(RFT)* — docs: ready-for-testing handoff  
