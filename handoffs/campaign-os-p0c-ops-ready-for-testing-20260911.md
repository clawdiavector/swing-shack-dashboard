# Ready for testing: Campaign OS P0c — ops + docs (Gate P0)

**Date:** 2026-09-11  
**Job:** `job-20260911-campaign-os-p0c-ready-for-testing`  
**Verify:** `job-20260911-campaign-os-p0c-verify` on Herdr `w3W:pH` (`campaign-os-p0c-verify`)  
**Verify verdict:** **PASS** t00, t20–t24; **PARTIAL** t18/t19 (code done, live crons blocked on Kyle `COS_JOB_TOKEN`); **Gate P0 — code criteria met, soak open**  
**Plan:** `handoffs/campaign-os-p0c-ops-plan-20260911.md` (§1 Gate P0, §7 manual tests)  
**Mac-ops:** `handoffs/campaign-os-p0c-mac-ops-20260911.md`

## Branches + SHAs

| Repo | Branch | SHA (short) | Full | Worktree |
|---|---|---|---|---|
| swing-shack-dashboard | `feat/campaign-os-p0c-ops` | `5d61405` | `5d61405c0a5c97d3effb4f6663da2a683230bf56` | `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-p0c-ops` |
| agent-control | `feat/campaign-os-p0c-ac` | `d72cd2e` | `d72cd2efb3cae5d0b11d99574e13df91b178ceed` | `/home/kyle/Work/worktrees/agent-control/feat/campaign-os-p0c-ac` |

**Merge target (both):** `integrate/campaign-os-option-c` — do **not** push `main` / `master` / `develop`.

## Push state (checked, not pushed)

Fresh `git ls-remote` / remote inspection on 2026-09-11 (RFT job; **no push attempted**):

| Branch | On origin? | Notes |
|---|---|---|
| `feat/campaign-os-p0c-ops` | **NO** — `git ls-remote origin feat/campaign-os-p0c-ops` empty | Local only at `5d61405`. Range vs `origin/integrate/campaign-os-option-c` still includes P0b workflow edits (`.github/workflows/gbp-daily-cron.yml`, `meta-live-fetch.yml`). Same PAT **workflow-scope** reject as P0b. |
| `feat/campaign-os-p0c-ac` | **NO** — agent-control checkout has **no `origin` remote** | Local only at `d72cd2e`. Cannot `ls-remote` until Kyle adds a remote / push path. |

**Do not force-push. Do not attempt token refresh from agents (Kyle gate).**

Kyle push after `gh auth refresh -s workflow` (swing-shack):

```bash
cd /home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/campaign-os-p0c-ops
git push -u origin feat/campaign-os-p0c-ops
```

Agent-control push (after remote exists):

```bash
cd /home/kyle/Work/worktrees/agent-control/feat/campaign-os-p0c-ac
# add/configure origin if missing, then:
git push -u origin feat/campaign-os-p0c-ac
```

## Gate P0 checklist (plan §1.2)

| # | Criterion | Status at RFT | Detail |
|---|---|---|---|
| 1 | `/api/jobs/status` shows `meta_refresh`, `gbp_tick`, `freshness_scan` green | **Code-met with caveat** | Verify boot port **3260**, scratch `$DATA_DIR`: unauth status → **401**; after runs: `freshness_scan` **OK**, `gbp_tick` **OK**, `meta_refresh` **NEVER** (no Meta token in scratch). Code path proven. Full green needs a **real-token** `meta_refresh` run. |
| 2 | Telegram silent 48h, then shout on deliberate pause | **Soak open** + live half gated | Mechanical halves need live t18/t19. t18/t19 blocked on `COS_JOB_TOKEN` → cannot observe silence/shout on Telegram yet. Kyle closes 48h soak after crons are live. |
| 3 | No automation commits to `data/` | **PASS** | Re-asserted in verify: last 20 `data/` commits human (`Forge V2`); workflows have no live `git commit`/`git push` touching `data/` (comment-only “no git commit dance”). |
| 4 | New agent from root `AGENTS.md` alone gets branch/paths/rules | **PASS (6/6)** | Falsification list (§3.2) all answerable from `AGENTS.md` only. |

**Ticket status (honest, per plan §1.2):** Gate P0 **code criteria met — 48h alerting soak open.**

## Per-task (verify pane)

| Task | Verdict |
|---|---|
| t00 Hermes health | **PASS** (`hermes cron list` exit 0, clean) |
| t18 / t19 crons | **PARTIAL** — scripts + shims done; live crons not created (`TOKEN_MISSING`) |
| t20 legacy + AGENTS + salvage | **PASS** (`legacy/agents/` 225, `agents/` 0, salvage YAML outside `legacy/`) |
| t21 archive | **PASS** |
| t22 workspace map | **PASS** (45 nav / 44 sections) |
| t23 README | **PASS** (no “Client-side only”) |
| t24 ticket profile | **PASS** (`profiles/campaign-os-ticket.yaml` + template, registered) |

## Manual tests (plan §7) — results

Environment cited by verify: review/feat worktrees; verify used port **3260**; RFT job file port **3837** for any later local re-run. Scratch `$DATA_DIR`. Never print secret values.

| # | Plan §7 step | Result | Evidence |
|---|---|---|---|
| 1 | Legacy move clean + app boots | **PASS** | `legacy/agents` = 225; `agents` = 0; no live `agents/` py/workflow refs; implement/verify on `5d61405` |
| 2 | `AGENTS.md` falsification | **PASS** | 6/6; names `meta_refresh` / `gbp_tick` / `freshness_scan`; no “74 agents” |
| 3 | Three jobs via endpoints (Gate P0 #1) | **PARTIAL** | 401 unauth; `freshness_scan` OK; `gbp_tick` OK; `meta_refresh` **NEVER** — needs Meta real-token run |
| 4 | Watchdog silent when healthy | **Deferred / scripts ready** | `bin/watch_campaign_os.py` @ `d72cd2e`. Cannot prove empty stdout while `meta_refresh` is NEVER |
| 5 | Watchdog shouts + `--force` + suppression | **Deferred / scripts ready** | Same script; live half also needs t18 + all-OK baseline |
| 6 | Failure modes legible | **PARTIAL (scripts + smoke)** | AC scripts stdlib-only; mac-ops smoke: missing token → exit 0, misconfigured line, no token material |
| 7 | Hermes crons live + digest fire | **PARTIAL** | Shims installed as **real files** on **Linux desk** host; `hermes cron list` still “No scheduled jobs”; crons pending Kyle `COS_JOB_TOKEN` |
| 8 | Docs truth (t21–t23) + profile (t24) | **PASS** | Both STATUS archives; README Flask; WORKSPACE_MAP 44/45; profile + template present |

## Open Kyle items

1. **`COS_JOB_TOKEN`** → add to `~/.hermes/.env` (mode 600). Then create `campaign-os-watch` (15m) + `campaign-os-digest` (`0 7 * * *`), fire digest once, confirm Telegram (plan §7 step 7 / mac-ops handoff).
2. **`meta_refresh` real-token run** — so Gate P0 criterion 1 can go fully green (verdict leaves NEVER without Meta token).
3. **48h soak close** — after crons live: silence on all-OK, then deliberate pause shout; Kyle ticks Gate P0 #2 from Telegram.
4. **Railway deploy branch names** — point the Railway service at the integrate/feat line in play (`integrate/campaign-os-option-c` after land). `RAILWAY.md` still documents dead `fix/asset-state-engine-deploy` / `feat/asset-state-engine` names; confirm live service branch in the Railway UI.
5. **`gh auth refresh -s workflow`** — required before origin push of swing-shack branches that touch `.github/workflows/gbp-daily-cron.yml` (P0b + anything still carrying those commits, including this feat branch). Same block as P0b; do not agent-refresh tokens.
6. **agent-control remote** — configure `origin` (or push path) for `feat/campaign-os-p0c-ac` @ `d72cd2e`.

## Program note

After land of both feat branches onto `integrate/campaign-os-option-c`, the **P0 program is complete** (code). Remaining Gate P0 soak / token / Railway items above are Kyle ops, not more P0 implement tickets. **P1 queue is manual** — spawn from `profiles/campaign-os-ticket.yaml` / `manifests/template-campaign-os-ticket.yaml` when ready; do not auto-start P1 from this RFT.

## Suggested board / comment draft

Campaign OS P0c ready for testing. swing-shack `feat/campaign-os-p0c-ops` @ `5d61405`; agent-control `feat/campaign-os-p0c-ac` @ `d72cd2e`. Verify PASS t00,t20–t24; PARTIAL t18/t19 (TOKEN_MISSING). Gate P0 code criteria met, soak open; `meta_refresh` NEVER without Meta token. Neither feat branch on origin — swing-shack push blocked on workflow scope; agent-control has no origin remote. Target merge: `integrate/campaign-os-option-c`. Suggested column: **Ready for testing**.

## Land (next job)

Land merges both feat branches → `integrate/campaign-os-option-c` (may push **integrate**, not `main`). Prefer origin presence first; if still blocked on workflow PAT, land locally and hand Kyle the exact push commands.
