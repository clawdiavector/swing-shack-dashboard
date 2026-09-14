# Campaign OS P1f — the GitHub Pages decision (t51): implementation plan

**Date:** 2026-09-14
**Job:** `job-20260911-campaign-os-p1f-pages-plan` (Claude, plan tier, **read-only**)
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/plan/campaign-os-p1f-pages`
**Branch:** `plan/campaign-os-p1f-pages` @ `3c8e5cf` (= `origin/integrate/campaign-os-option-c`, byte-identical — `git diff --stat` empty)
**Ticket:** `ticket-20260911-campaign-os-p1f-pages` — queue row 9, the last P1 slice
**Task:** t51 (`manifests/campaign-os-master-plan-20260910.yaml`, sequence 51, owner **human**)
**Inputs:** master plan t51 + `gate-p1`, `manifests/plan-20260911-campaign-os-p1f-pages.yaml`, `handoffs/campaign-os-p1-ticket-split-20260911.md`, `handoffs/campaign-os-p1c-legacy-plan-20260911.md` §6.4, `handoffs/campaign-os-p1c-legacy-ready-for-testing-20260914.md`, `campaign-os-audit-{20260909,code-20260909,doc-20260909}.md`, root `AGENTS.md`

**No product code edits were made by this job.** `git status --porcelain` shows only the untracked job files (`.agent-job.json`, `.agent-job/`) and this handoff.

> **✅ DECISION RECORDED (2026-09-14):** Kyle chose **RETIRE**, shape **A2b**. Implement may proceed per §9.

---

## 0. Grounding — everything below was measured today against `3c8e5cf`

Nothing here is quoted from the 2026-09-09 audits. Three of their Pages claims are now **wrong**; §0.4 says which.

### 0.1 The Pages deploy workflow has never succeeded

```
gh run list --workflow=deploy.yml -L 500 --json conclusion
```

| Measurement | Value |
|---|---|
| Runs returned | **500** |
| `success` | **0** |
| `failure` | **500** |
| Oldest run in that window | `2026-07-13T17:55:22Z` — also a failure |
| Most recent run | `34848708658`, `2026-09-14T13:21:08Z`, failure, 17s |

Failure is deterministic, always the same step:

```
=== Cockpit Verification (V2) ===
File size: 18950 bytes
V2 schema: MISSING
##[error]Process completed with exit code 1.
```

It fires on **every push to `main` plus a 4×-daily cron** (`deploy.yml:12-13`). It has been
red for at least two months and nobody noticed, which is the strongest single datum in this plan.

### 0.2 …and the Pages site is not served by that workflow at all

```
gh api repos/:owner/:repo/pages
→ {"build_type":"legacy","source":{"branch":"main","path":"/"},"status":"built"}
```

`build_type: legacy` means **GitHub's own Jekyll branch build** from `main` at `/`, driven by
root `_config.yml`. That path publishes on every push to `main` and is completely independent of
`deploy.yml`. `deploy.yml` never reaches its `upload-pages-artifact` / `deploy-pages` steps.

So the live site is real even though the workflow is dead:

| URL | HTTP |
|---|---|
| `…/swing-shack-dashboard/` | **404** (no root `index.html`; root has `dashboard.html`) |
| `…/campaign-os/cockpit-operational.html` | **200** |
| `…/campaign-os/campaign-os.html` | **200** |
| `…/dashboard.html` | **200** |
| `…/campaign-os/campaign-data.json` | **200** (2.9 MB) |
| `…/campaign-data-staged.json` | **200** |
| `…/campaign-os/SPEC.md` | **200** |
| `…/AGENTS.md`, `…/docs/layer1-salvage-20260911.yaml`, `…/data/` | 404 |

The served cockpit is **byte-identical** to the repo copy (`cmp` → identical, 18 950 bytes).

### 0.3 The page Pages serves cannot work on Pages

Today's `campaign-os/cockpit-operational.html` is a **live-API client**, not a static render.
It fetches, with relative URLs:

`/api/intel/brand-context` · `/api/health` · `/api/schedule` · `/api/campaigns` · `/api/intel/review_inbox`
(`cockpit-operational.html:219,228,252,260-263`)

On `clawdiavector.github.io` those are static 404s — verified:

| Pages URL | HTTP |
|---|---|
| `…/api/health` | 404 |
| `…/api/campaigns` | 404 |
| `…/api/schedule` | 404 |

**The Pages cockpit is a dead shell.** Anyone landing on the bookmarked URL gets chrome with
every data fetch failing. Same for `campaign-os/campaign-os.html` on Pages — the SPA needs the
Flask API too.

### 0.4 Three audit claims from 2026-09-09 are now falsified

| Audit line | 2026-09-09 claim | Measured 2026-09-14 |
|---|---|---|
| `audit-0909:158` | "GitHub Pages — `deploy.yml` patches + publishes `cockpit-operational.html` … **Alive**" | **FALSE.** 0/500 workflow successes. Publishing is the legacy Jekyll branch build. |
| `audit-code:536` | "`deploy.yml` … Cockpit file **exists**; path is alive" | **Half true.** File exists and is routed — by Flask, not by this workflow. |
| `audit-code:477` | "`cockpit-operational.html` … not dead — routed + **Pages-deployed**" | Routed: yes (Railway). Pages-deployed: yes, but by Jekyll and non-functional there. |

Do not re-quote the audits on this topic. Re-derive from §0.1–0.3.

---

## 1. The single most important thing in this plan

**t51's done-criterion as literally written is wrong and must not be executed verbatim.**

> t51: *"If retired: deploy.yml, cockpit-operational.html, patch-cockpit.js and regenerate-cockpit.\* all go together"*

`campaign-os/cockpit-operational.html` is **live Railway product**, not a Pages artefact:

| Binding | Location |
|---|---|
| Flask route ×3 | `campaign-os/app.py:13789-13794` — `/cockpit-operational`, `/cockpit-operational.html`, `/cockpit.html` |
| Public-route allowlist | `campaign-os/app.py:54` — `'/cockpit-operational'`, `'/cockpit'` |
| SPA nav link ×2 | `campaign-os/campaign-os.html:1572` (in-app), `:1617` (external-marked) |
| Node test | `tests/test_step94b_event_semantics_and_recovery.js:568` reads `REPO_ROOT/cockpit-operational.html` |
| Smoke test | `tests/test_v2026_08_08_welcome_nav.py:146` asserts `/cockpit-operational` is reachable |

Deleting it takes out a routed product surface, two nav entries and two tests, to solve a
GitHub Pages problem. **Under both options in §3 the page stays.** This deviation from t51's
wording is deliberate and must be stated explicitly in the RFT handoff so the Pi verifier does
not fail the slice for "not deleting cockpit-operational.html".

**t51 is really a decision about the Pages *lane*, not about the cockpit page.** Three surfaces,
kept apart for the rest of this document:

| # | Surface | State |
|---|---|---|
| **S1** | `.github/workflows/deploy.yml` | Dead. 0/500. Publishes nothing. |
| **S2** | GitHub Pages site (legacy Jekyll branch build + `_config.yml` + repo Pages setting) | Live, auto-publishing `main`, serving a non-functional cockpit |
| **S3** | `campaign-os/cockpit-operational.html` + routes + nav | **Live Railway product. Out of scope for deletion.** |

---

## 2. The generator scripts — all five are dead, two are hazardous

### 2.1 `scripts/patch-cockpit.js` — silent no-op

`deploy.yml:51` runs it. It rewrites four things that no longer exist:

| Marker it targets | Occurrences in today's cockpit |
|---|---|
| `panel-production` | **0** |
| `panel-queue` | **0** |
| `cc-num` | **0** |
| `window.campaignData` | **0** |
| `card-title` | **0** |

It also reads `D.assets` (`patch-cockpit.js:11`). `campaign-os/campaign-data.json` root keys are
`portfolioMetadata`, `activeCampaignId`, `campaigns`, `updatedAt` — **no `assets`**. So
`assetKeys` is `[]`, every `String.replace` misses, the file is written back unchanged, and it
**exits 0 printing `Patched OK`**. A green step that does nothing. Last touched `e02b2cd`, 2026-06-02.

### 2.2 `scripts/regenerate-cockpit.py` — actively destructive ⚠

`DST = campaign-os/cockpit-operational.html` (`:8`) — it **overwrites the live cockpit**. Its
output is the pre-July static cockpit (`window.campaignData` ×10, `showView` ×5,
`selectCampaign` ×3). Running it replaces the working Railway page with a dead static one.

It is still advertised as the thing to run:

- `campaign-os/CAMPAIGN-OS-FULL-SPEC.md:436,599`
- `docs/CAMPAIGN-MOTHERSHIP-V2.md:597`
- `campaign-data-staged.json:51` ("regenerate via `scripts/regenerate-cockpit.py` + `scripts/patch-cockpit.js` (Pages lane, t51-gated)")

Last touched `a3ec01e`, 2026-06-30. The cockpit moved on at `a60ef9a` (2026-07-27) and
`5fc8cb2` (2026-08-17). **P1c §6.4 recommended keeping it as "t51-gated". t51 now says: delete.**

### 2.3 Three more, unreferenced

| File | Why dead |
|---|---|
| `scripts/patch-cockpit-local.py` | Hardcodes `/Users/fivefriday/.openclaw-instance2/…` — the dead Mac path **AGENTS.md §3 explicitly bans**. Zero references. |
| `scripts/regen_local.py` | `import regenerate_cockpit` (`:9`). No such module — the file is `regenerate-cockpit.py`, hyphenated. `ImportError` on every run. Zero references. |
| `scripts/gate7-verify.py` | Polls the Pages URL for M4 markers (`id="btn-create"`, `id="createModal"`) absent from today's cockpit. Zero references. `gate2`–`gate5` do **not** touch Pages and stay. |

**None of these five is decision-gated.** They are broken under RETIRE *and* under KEEP. The only
reason they survived P1c is that P1c deferred to t51. §3 puts them in both option's delete list.

---

## 3. The decision — two options, complete file lists

### Common to both options (not decision-gated)

| # | Action | Path |
|---|---|---|
| C1 | delete | `scripts/patch-cockpit.js` — §2.1 |
| C2 | delete | `scripts/regenerate-cockpit.py` — §2.2 |
| C3 | delete | `scripts/patch-cockpit-local.py` — §2.3, violates AGENTS.md §3 |
| C4 | delete | `scripts/regen_local.py` — §2.3, `ImportError` |
| C5 | delete | `scripts/gate7-verify.py` — §2.3 |
| C6 | edit | `campaign-data-staged.json:51` — drop the "regenerate via … (Pages lane, t51-gated)" sentence; replace with the t51 outcome |
| C7 | edit | `campaign-os/CAMPAIGN-OS-FULL-SPEC.md:31,84,99,105,436,569,596,599,610,639` — the "lives in GitHub Pages / regenerates on push" story |
| C8 | edit | `campaign-os/SPEC.md:417` — the github.io URL as "the user-facing dashboard" |
| C9 | edit | `campaign-os/V2-WRITE-BACK-SPEC.md:603-638` — §7 "How the Cockpit Updates After the Write" describes the Pages regeneration loop |
| C10 | edit | `docs/CAMPAIGN-MOTHERSHIP-V2.md:597-598` — "Update `regenerate-cockpit.py` / `patch-cockpit.js`" |
| C11 | edit | **`AGENTS.md` §11** — rewrite to the recorded decision. This is t51 done-criterion #1 |
| C12 | **keep, untouched** | `campaign-os/cockpit-operational.html`, `campaign-os/app.py:54,13789-13794`, `campaign-os/campaign-os.html:1572,1617` — §1 |
| C13 | **keep, untouched** | `scripts/gate2-form.py`, `gate3-pipeline.py`, `gate4-wire.py`, `gate5-portfolio.py` — none reference Pages |
| C14 | **keep, untouched** | `data/**` — AGENTS.md §8. Zero `data/` changes in this slice |

C7–C10 are doc surgery, not rewrites: strike the false claim, point at Railway, keep the file.

---

### Option A — **RETIRE** (recommended)

Everything in "Common", plus:

| # | Action | Path | Note |
|---|---|---|---|
| A1 | **delete** | `.github/workflows/deploy.yml` | S1. 0/500 successes. Stops 4 red cron runs/day |
| A2 | edit or delete | `_config.yml` | S2 — see the A2a/A2b sub-decision below |
| A3 | Kyle, manual, GitHub UI | Repo → Settings → Pages | see A2a/A2b |

**Sub-decision A2a vs A2b — the only real cost of retiring.**

`media/overlaid/**.html` uses Pages as an **image CDN**. Nine files hotlink **two** URLs:

```
https://clawdiavector.github.io/swing-shack-dashboard/media/inbound/6cc971f6-fe07-4db0-9030-3353a4cd1a24.png
https://clawdiavector.github.io/swing-shack-dashboard/media/inbound/b00af764-4d4f-4ce6-91ea-7c0803e38a46.jpg
```

Both return **200** today. Both files exist in-repo (`media/inbound/`, 5 062 B and 212 991 B).
Files: `media/overlaid/{club-fitting,coaching,membership,practice,social}-graphic.html`,
`media/overlaid/v2/{club-fitting-1,club-fitting-2,club-fitting-3,coaching-1}.html`.
They are standalone graphic templates — **no product code references them**
(`grep -rn overlaid campaign-os/ scripts/` returns only unrelated prose).

| | **A2a — full retirement** | **A2b — media-only mirror** |
|---|---|---|
| `_config.yml` | delete | keep, reduced to `include: [media/**]` + `exclude` everything else |
| Pages setting | **Kyle disables Pages** in repo Settings | leave enabled (legacy branch build) |
| `media/overlaid/*.html` | rewrite 9 files to relative `../inbound/<file>` paths (both files are in-repo) | untouched |
| Result | github.io is gone. One dead bookmark → GitHub 404 | github.io serves only `media/`. Cockpit URL → 404. Overlays keep working |
| Risk | 9 files to edit; a stale external embed of those 2 images elsewhere would break | Pages stays on; someone could re-add files to the include list later |

**Recommend A2b**, then A2a as an optional follow-up. A2b kills the dead cockpit URL and the
red cron with zero edits to files outside the Pages lane; A2a is a tidier end state but touches
nine media templates for no functional gain today.

**AGENTS.md §11 under Option A** — replace the current two lines with, in substance:

> **§11 — Pages is retired (t51, 2026-09-14).** Railway is the only product surface.
> `.github/workflows/deploy.yml` is deleted; it had 0 successes in its last 500 runs. GitHub
> Pages is [disabled / reduced to a `media/` mirror]. `campaign-os/cockpit-operational.html`
> **is kept** — it is a live Railway route (`app.py:13789`) linked from the SPA nav, not a Pages
> artefact. There is no cockpit regeneration pipeline any more; `patch-cockpit.js`,
> `regenerate-cockpit.py`, `patch-cockpit-local.py`, `regen_local.py` and `gate7-verify.py` are
> deleted. Any doc describing "agent writes → Git → Pages regenerates the cockpit" is drift.

---

### Option B — **KEEP**

Everything in "Common", plus:

| # | Action | Path | Note |
|---|---|---|---|
| B1 | **rewrite** | `.github/workflows/deploy.yml` | The patch step (`:49-51`) and the whole V2 verification block (`:53-90`) must go — they assert a schema the cockpit shed in July. What remains is checkout + `upload-pages-artifact` + `deploy-pages`. |
| B2 | **Kyle, manual** | Repo → Settings → Pages → build type | `deploy-pages@v4` **cannot** publish while `build_type` is `legacy`. Switching to `workflow` is required for B1 to mean anything — and it changes what the site serves. If Kyle does not want that, B1 collapses to "delete deploy.yml and keep the Jekyll build", which is Option A2b wearing a different hat. |
| B3 | edit | `_config.yml` | Decide the publish set deliberately instead of inheriting it |
| B4 | edit | `AGENTS.md` §11 | Name it legacy **and state the drift as accepted** — t51 done-criterion #3 |

**What "accepted drift" means under B, stated honestly in AGENTS.md:** the Pages cockpit's five
API fetches 404 (§0.3). Keeping it means publishing a page that is known not to work. §11 must
say that in those words, or the criterion "its drift from the SPA is stated as accepted" is not met.

Option B costs a workflow rewrite plus a repo-settings change and still leaves a broken public
page. It is defensible only if the github.io URL has a consumer this plan did not find — the
sweep in §0.2/A2a found exactly one, the two media images, and A2b serves that more cheaply.

---

## 4. Recommendation

**RETIRE, shape A2b.** The evidence:

1. The workflow has published nothing in ≥2 months and fails 4×/day on cron — it is pure noise.
2. What Pages actually serves is a cockpit whose every data call 404s. Keeping it means keeping a
   broken public page.
3. The generator chain it exists to feed is dead (§2.1) and one member of it silently overwrites
   the live cockpit (§2.2). Deleting removes a live footgun.
4. Railway is already the product (AGENTS.md §11, RAILWAY.md, `railway.json`). Two deploy stories
   have cost this program repeated rediscovery across three audits.
5. The only real dependency is two image hotlinks, and A2b preserves them untouched.

**Not a reason to retire:** exposure. The repo is **public** (`gh api repos/:owner/:repo` →
`"private": false`), so everything Pages serves — `campaign-data.json`, `SPEC.md`,
`campaign-data-staged.json` — is already public in the repo. Retiring Pages changes nothing
about confidentiality. Do not sell it as a security fix.

---

## 5. Acceptance criteria

### 5.1 Under **RETIRE**

| # | Criterion |
|---|---|
| AC-R1 | `AGENTS.md` §11 records the decision, dated, naming t51, in the substance of §3 Option A |
| AC-R2 | `.github/workflows/deploy.yml` is gone; `git ls-files .github/workflows` = `ci.yml`, `gbp-daily-cron.yml`, `lint-brand-copy.yml`, `meta-live-fetch.yml` |
| AC-R3 | All five scripts from C1–C5 are gone |
| AC-R4 | `campaign-os/cockpit-operational.html` is **byte-identical to the base** — `git diff base..HEAD -- campaign-os/cockpit-operational.html` is empty |
| AC-R5 | `/cockpit-operational` still serves 200 locally, and `app.py:54` still allowlists it |
| AC-R6 | No repo file names a deleted script — `grep -rn 'patch-cockpit\|regenerate-cockpit\|regen_local\|gate7-verify'` hits only history prose in `report-log.md` / `docs/nightshift-log.md` / `handoffs/` |
| AC-R7 | C6–C10 doc edits landed; no surviving doc asserts the cockpit is regenerated to Pages |
| AC-R8 | A2b: `_config.yml` publishes `media/**` only. A2a: `_config.yml` gone **and** the 9 `media/overlaid` files use relative paths |
| AC-R9 | `git ls-files '*.js' \| wc -l` = **18** (19 today, minus `patch-cockpit.js`) — gate-p1 "<20 JS files" keeps headroom |
| AC-R10 | `git diff --stat base..HEAD -- data/` **empty** (AGENTS.md §8) |
| AC-R11 | pytest has not regressed vs the base run (§6 V10) |
| AC-R12 | The §1 deviation is stated in the RFT handoff in so many words: *"cockpit-operational.html is deliberately retained against t51's literal wording because app.py:13789 routes it."* |

### 5.2 Under **KEEP**

| # | Criterion |
|---|---|
| AC-K1 | `AGENTS.md` §11 names Pages **legacy**, dated, naming t51, **and** states the accepted drift including the fact that the Pages cockpit's API calls 404 |
| AC-K2 | `deploy.yml` no longer runs `patch-cockpit.js` and no longer asserts the V2 schema |
| AC-K3 | The next `deploy.yml` run on `main` is **green** — a KEEP that still fails 4×/day is not a KEEP. Kyle's repo-settings change (B2) is part of this criterion |
| AC-K4 | C1–C5 deletions landed anyway (they are dead under KEEP too) |
| AC-K5 | AC-R4, AC-R5, AC-R6, AC-R7, AC-R10, AC-R11 apply unchanged |
| AC-K6 | `_config.yml` publish set is explicit, not inherited |

---

## 6. Verify tier

Read-only, from a clean checkout of `feat/campaign-os-p1f-pages`. Re-derive every number; do not
read them out of the RFT handoff. Verdict vocabulary matching P0c/P1b/P1c: **PASS / PARTIAL /
FAIL** per criterion, plus *code-met, live-unverified* for anything needing the branch on origin.
`base` = the merge-base with `origin/integrate/campaign-os-option-c` (`3c8e5cf` at plan time).

| # | Check | Command | Pass condition |
|---|---|---|---|
| V1 | **Decision is recorded** (t51 #1) | `grep -n -A12 '^## 11' AGENTS.md` | §11 names t51, carries a date, and matches the §8 token. **A §11 that still says "if still wired" is an instant FAIL** |
| V2 | Workflow set | `git ls-files .github/workflows` | RETIRE: 4 files, no `deploy.yml`. KEEP: 5, and `deploy.yml` names no `.js` |
| V3 | Generators gone | `git ls-files \| grep -E 'patch-cockpit\|regenerate-cockpit\|regen_local\|gate7-verify'` | no output, **both options** |
| V4 | **Cockpit page untouched** | `git diff base..HEAD -- campaign-os/cockpit-operational.html` | **empty**. Any diff = FAIL (§1) |
| V5 | **Cockpit route intact** | `grep -n "cockpit-operational" campaign-os/app.py campaign-os/campaign-os.html` | `app.py:54` + the 3 routes + both nav links still present |
| V6 | No dangling script reference | `grep -rn 'patch-cockpit\|regenerate-cockpit\|regen_local\|gate7-verify' --include='*.py' --include='*.js' --include='*.yml' --include='*.json' --include='*.html' .` | zero hits outside `report-log.md`, `docs/nightshift-log.md`, `handoffs/`. **Account for each surviving hit individually — a bare count is not a verification** |
| V7 | Docs no longer assert the Pages pipeline | `grep -rn -i 'github pages' --include='*.md' . \| grep -v report-log \| grep -v nightshift-log \| grep -v handoffs/` | every remaining hit is the new §11 wording or an explicit "legacy / retired" statement |
| V8 | JS count | `git ls-files '*.js' \| wc -l` | **18** |
| V9 | `data/` untouched | `git diff --stat base..HEAD -- data/`; `git status --porcelain data/` | both empty (AGENTS.md §8) |
| V10 | pytest not regressed | `cd campaign-os && DATA_DIR=$(mktemp -d) python3 -m pytest tests -q -p no:randomly` | re-derive the `base` baseline first, then compare. Collection today: **1545 tests**. A new failure naming `cockpit` = FAIL |
| V11 | Node tests not regressed | `for f in tests/*.js; do echo "== $f"; node "$f"; done` | same pass/fail set as `base`. `test_phase2_wizard.js` was **already** failing `ENOENT` on root `cockpit-operational.html` before this slice (P1c plan §, line 181) — it must not get *worse* |
| V12 | Image still builds | `python3 scripts/check_lib_modules.py --source campaign-os/app.py --lib-dir campaign-os/_lib; echo $?` | exit 0, `missing_count: 0` — this is `Dockerfile:33` |
| V13 | RETIRE/A2b: Pages publish set | `cat _config.yml` | `include` is `media/**` only; no `campaign-os/**`, no `"*.json"` |
| V14 | RETIRE/A2a: overlays are self-contained | `grep -rc 'github.io' media/` | **0** |
| V15 | **Post-land, live** | `gh run list --workflow=deploy.yml -L 3` after the integrate push | RETIRE: no new runs. KEEP: newest run `success` (AC-K3) |
| V16 | **Post-land, live** | `curl -s -o /dev/null -w '%{http_code}' https://clawdiavector.github.io/swing-shack-dashboard/campaign-os/cockpit-operational.html` | RETIRE: **404**. KEEP: 200 (and §11 already admits its APIs 404) |
| V17 | RETIRE/A2b: media CDN survives | `curl -s -o /dev/null -w '%{http_code}' https://clawdiavector.github.io/swing-shack-dashboard/media/inbound/6cc971f6-fe07-4db0-9030-3353a4cd1a24.png` | **200** |
| V18 | Diff is the decided set and nothing else | `git diff --stat base..HEAD` | only: `AGENTS.md`, `.github/workflows/deploy.yml`, `_config.yml`, the 5 script deletions, the C6–C10 docs, and (A2a only) `media/overlaid/**` |

**V15–V17 run after the land job pushes `integrate/campaign-os-option-c`. They cannot be
satisfied on the feat branch — mark them *code-met, live-unverified* in the RFT handoff and
hand them to the land job.** Note that under RETIRE/A2b the cockpit only 404s once `main`
receives the merge; `integrate` alone does not change what the Jekyll branch build serves.
If Kyle has not yet gated `integrate → main`, V16 is expected to still read 200 — record it as
**deferred to the main gate**, not FAIL.

---

## 7. Manual test plan — 7 steps

Run in the **implement** worktree. Job-file port: **3912** (`runtime.ports.web`) — never 8765,
never 8080. `DATA_DIR` to a scratch dir. Never print a secret value.

```bash
export DATA_DIR=$(mktemp -d /tmp/cos-p1f-manual-XXXX)
export COS_JOB_TOKEN=manual-test-token
cd campaign-os && python3 app.py &   # binds 3912 via the job file
```

| # | Step | Expected |
|---|---|---|
| M1 | `curl -s -o /dev/null -w '%{http_code}\n' localhost:3912/cockpit-operational` | **200** — the page survived the slice |
| M2 | `curl -s localhost:3912/cockpit-operational \| cmp - campaign-os/cockpit-operational.html` | no output — served file is the unmodified repo file |
| M3 | Open `localhost:3912/cockpit-operational` in a browser, DevTools → Network | `/api/health`, `/api/schedule`, `/api/campaigns`, `/api/intel/review_inbox`, `/api/intel/brand-context` all **200**. This is the contrast with §0.3 and the whole reason the page is kept |
| M4 | Open `localhost:3912/` → SPA, click the **🛩️ Cockpit** nav item | navigates to the cockpit, renders data, no console error |
| M5 | `ls scripts/ \| grep -Ei 'cockpit\|regen\|gate7'` | no output (both options) |
| M6 | `git diff base..HEAD -- campaign-os/cockpit-operational.html campaign-os/app.py campaign-os/campaign-os.html` | **empty** — this slice is a Pages/doc slice; it must not touch the app |
| M7 | `git status --porcelain data/` after M1–M6 | **empty** (AGENTS.md §8) |

Kill the server when done. Do not commit anything `DATA_DIR` produced.

---

## 8. ⛔ Kyle's decision — implement is blocked until this is filled in

Write **one** token on the DECISION line, plus the sub-shape if RETIRE, then re-run the implement
job. The implementer must treat an empty or ambiguous line as "still blocked" and stop.

```
DECISION:        RETIRE
SHAPE:           A2b (media-only mirror)
DECIDED BY:      Kyle
DATE:            2026-09-14
NOTES:           Chat foreman session; see handoffs/pipeline-v2-p1f-gate-20260914.md
```

**Plan recommendation: `RETIRE`, shape `A2b`.** Reasons in §4.

Two things need Kyle's hands directly and cannot be done by any agent — flag them in the RFT handoff:

- **RETIRE/A2a:** disable Pages in repo Settings → Pages.
- **KEEP:** switch Pages build type from `legacy` to `workflow`, or AC-K3 is unreachable.

---

## 9. Sequencing for the implement job

1. Rebase on `origin/integrate/campaign-os-option-c`. Never push `main` / `master` / `develop`.
2. **Read §8. If it is empty, stop and report blocked.** Do not guess the decision.
3. Commit in this order, one concern each — a `KEEP` decision drops only commit 3:
   1. `chore(t51): delete the dead cockpit generator chain` — C1–C5
   2. `docs(t51): correct the Pages story in the specs` — C6–C10
   3. `chore(t51): retire the GitHub Pages deploy workflow` — A1, A2 *(RETIRE only)* / `fix(t51): make the Pages workflow publishable` — B1, B3 *(KEEP only)*
   4. `docs(t51): record the Pages decision in AGENTS.md §11` — C11. **Last**, so §11 describes what actually landed
4. Run §7 M1–M7 before declaring done. `verification-before-completion` applies: no success claim without the command output.
5. The manifest's `paths:` list names `campaign-os/cockpit-operational.html` and
   `scripts/patch-cockpit.js`. Per §1, **`cockpit-operational.html` is read-only in this slice** —
   it is on the list so the implementer can *verify* it, not edit it.

## 10. Gate-p1 interaction

t51 is the last item before `gate-p1` (`after_sequence: 51`). Two of its five criteria touch this slice:

- *"Node is gone from the repo (<20 JS files)"* — 19 today, **18** after RETIRE. Already met; this widens the margin.
- *"pytest is trustworthy enough to gate a merge"* — untouched here. V10 only proves no regression.

The other three (Layer 1 jobs green, diagnostic bundle, redaction test) are P1b/P1d business and
are not this slice's to claim. Do not assert gate-p1 PASS from this ticket.

---

## Appendix — commands that produced every number above

```bash
# §0.1
gh run list --workflow=deploy.yml -L 500 --json conclusion -q '[.[]|select(.conclusion=="success")]|length'   # 0
gh run list --workflow=deploy.yml -L 500 --json createdAt  -q '.[-1].createdAt'                               # 2026-07-13T17:55:22Z
gh run view "$(gh run list --workflow=deploy.yml -L1 --json databaseId -q '.[0].databaseId')" --log-failed

# §0.2
gh api repos/:owner/:repo/pages -q '{build_type,source,status}'
gh api repos/:owner/:repo       -q '{private,visibility}'
for p in "" campaign-os/cockpit-operational.html campaign-os/campaign-os.html dashboard.html \
         campaign-os/campaign-data.json campaign-data-staged.json campaign-os/SPEC.md AGENTS.md; do
  printf '%-45s ' "$p"
  curl -s -o /dev/null -w '%{http_code}\n' "https://clawdiavector.github.io/swing-shack-dashboard/$p"
done
curl -s https://clawdiavector.github.io/swing-shack-dashboard/campaign-os/cockpit-operational.html -o /tmp/live.html
cmp /tmp/live.html campaign-os/cockpit-operational.html   # identical

# §0.3
grep -n 'fetch(\|/api/' campaign-os/cockpit-operational.html
for p in api/health api/campaigns api/schedule; do
  curl -s -o /dev/null -w "$p %{http_code}\n" "https://clawdiavector.github.io/swing-shack-dashboard/$p"
done

# §1
grep -n 'cockpit-operational' campaign-os/app.py campaign-os/campaign-os.html
sed -n '13789,13794p' campaign-os/app.py

# §2.1
for m in panel-production panel-queue cc-num window.campaignData card-title; do
  printf '%-22s %s\n' "$m" "$(grep -c "$m" campaign-os/cockpit-operational.html)"
done
python3 -c "import json;print(list(json.load(open('campaign-os/campaign-data.json')).keys()))"

# §2.2
sed -n '1,12p' scripts/regenerate-cockpit.py
for m in window.campaignData showView selectCampaign; do printf '%-20s %s\n' "$m" "$(grep -c "$m" scripts/regenerate-cockpit.py)"; done

# §3 A2a
grep -rhoE 'https://clawdiavector\.github\.io/swing-shack-dashboard/media/[A-Za-z0-9._/-]+' media/ | sort -u
grep -rl 'github.io' media/

# §6
git ls-files '*.js' | wc -l                                      # 19
cd campaign-os && python3 -m pytest --collect-only -q | tail -1   # 1545 tests collected
```
