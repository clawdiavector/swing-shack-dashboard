# Campaign OS P1f — Pages decision (t51): ready for testing

**Date:** 2026-09-14  
**Job:** `job-20260911-campaign-os-p1f-pages-implement`  
**Branch:** `feat/campaign-os-p1f-pages`  
**Base:** `origin/integrate/campaign-os-option-c` @ `3c8e5cf`  
**Decision:** **RETIRE**, shape **A2b** (Kyle, 2026-09-14)

## What landed

Four planned commits (+ one README V7 follow-up):

1. `chore(t51): delete the dead cockpit generator chain` — C1–C5  
2. `docs(t51): correct the Pages story in the specs` — C6–C10  
3. `chore(t51): retire the GitHub Pages deploy workflow` — A1 + A2b `_config.yml`  
4. `docs(t51): record the Pages decision in AGENTS.md §11` — C11  
5. `docs(t51): retire Pages wording in campaign-os/README` — V7 leftover

## §1 deviation (AC-R12) — state explicitly

**`campaign-os/cockpit-operational.html` is deliberately retained against t51's literal wording because `app.py:13789` routes it** (`/cockpit-operational`, `/cockpit-operational.html`, `/cockpit.html`), it is on the public-route allowlist (`app.py:54`), and the SPA nav links to it. It is a live Railway product surface, not a Pages artefact. Deleting it was never in scope under RETIRE or KEEP.

## Acceptance (RETIRE / A2b) — implement-time

| # | Result | Evidence |
|---|---|---|
| AC-R1 | PASS | `AGENTS.md` §11 names t51, dated 2026-09-14, RETIRE/A2b substance |
| AC-R2 | PASS | `git ls-files .github/workflows` = ci, gbp-daily-cron, lint-brand-copy, meta-live-fetch (no deploy.yml) |
| AC-R3 | PASS | five generator scripts gone from tree |
| AC-R4 | PASS | `git diff base..HEAD -- campaign-os/cockpit-operational.html` empty |
| AC-R5 | PASS | M1: `localhost:3929/cockpit-operational` → **200**; allowlist intact |
| AC-R6 | PASS* | deleted script names remain only as "Deleted t51" / §11 record (and history logs) |
| AC-R7 | PASS | specs + README no longer assert live Pages regenerate |
| AC-R8 | PASS | `_config.yml` `include: [media/**]` only |
| AC-R9 | PASS | `git ls-files '*.js' \| wc -l` = **18** |
| AC-R10 | PASS | `git diff --stat base..HEAD -- data/` empty |
| AC-R11 | PASS | pytest failure set **identical** to base: `158 failed, 1356 passed, 18 errors` — zero cockpit-named fails; only_head=0 |
| AC-R12 | PASS | this handoff |

\* Intentional naming in §11 / "Deleted t51" strike-throughs matches the plan's prescribed §11 text.

## Manual (job port **3929**)

| # | Result |
|---|---|
| M1 | PASS — HTTP 200 |
| M2 | PASS — `cmp` identical to repo file |
| M3 | PARTIAL — page public; sample `/api/schedule` and `/api/campaigns` return 401 without session (auth gate). `/api/health` 200. Not a Pages-slice regression. |
| M4 | not run (no browser in this job) |
| M5 | PASS for deleted set; unrelated `regenerate-dashboards.py` / `regenerate-publishing-index.js` remain |
| M6 | PASS — app.py / campaign-os.html / cockpit-operational.html untouched |
| M7 | PASS — `data/` porcelain empty |

## Verify tier notes

| # | Status |
|---|---|
| V12 `check_lib_modules` | **Pre-existing on base** — reports `jobs` package missing because checker only globs `*.py`. Not introduced by this slice; out of scope to fix here. |
| V15–V17 | **code-met, live-unverified** — need land push + eventually `main` for Jekyll. Under A2b, cockpit github.io 404 only after `_config.yml` reaches the Pages source branch (`main`). |

## Kyle manual (cannot be done by agent)

- Leave Pages **enabled** (A2b). Do **not** disable Pages unless moving to A2a later.
- After `integrate → main`: confirm cockpit URL 404s and media inbound PNG still 200 (V16/V17).

## Diff scope

```
AGENTS.md
_config.yml
.github/workflows/deploy.yml (deleted)
campaign-data-staged.json
campaign-os/{CAMPAIGN-OS-FULL-SPEC,SPEC,V2-WRITE-BACK-SPEC,README}.md
docs/CAMPAIGN-MOTHERSHIP-V2.md
scripts/{patch-cockpit.js,regenerate-cockpit.py,patch-cockpit-local.py,regen_local.py,gate7-verify.py} (deleted)
```

No `data/` writes. No push to main/master/develop.
