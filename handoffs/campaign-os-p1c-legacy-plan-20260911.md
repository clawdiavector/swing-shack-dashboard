# Campaign OS P1c — delete the legacy Node tree: implementation plan

**Date:** 2026-09-14
**Job:** `job-20260911-campaign-os-p1c-legacy-plan` (Claude, plan tier, **read-only**)
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/plan/campaign-os-p1c-legacy`
**Branch:** `plan/campaign-os-p1c-legacy` @ `69b64e2` (= `origin/integrate/campaign-os-option-c`, byte-identical)
**Ticket:** `ticket-20260911-campaign-os-p1c-legacy` — queue `handoffs/campaign-os-p0-ticket-queue.yaml` seq 6
**Tasks:** t33, t34
**Inputs:** `manifests/campaign-os-master-plan-20260910.yaml` (t33, t34), `manifests/plan-20260911-campaign-os-p1c-legacy.yaml`, `handoffs/campaign-os-p1-ticket-split-20260911.md`, `handoffs/campaign-os-p1b-port-ready-for-testing-20260914.md`, `handoffs/campaign-os-p1b-port-verify-20260914.md`, `plan/campaign-os-p1b-port/handoffs/campaign-os-p1b-port-plan-20260911.md`, root `AGENTS.md`, `legacy/README.md`

**No product code edits were made by this job.** Two test runs dirtied tracked `data/` (§0.4); both were reverted and `git status --porcelain data/` is empty.

---

## 0. Grounding — measured on this worktree today

Every count below was produced by running the commands in the Appendix against `69b64e2` on 2026-09-14. Nothing is quoted from the 2026-09-09 audit. Runner: node **v26.7.0**, Python **3.14.7** (mise), pytest **9.1.1**.

### 0.1 The master plan's "152 JS files" is stale

| Claim | Measured today | Status |
|---|---|---|
| t33: "152 JS files reduced to <20" | **243 tracked `.js`** — 158 `scripts/`, 74 `legacy/agents/`, 11 `tests/` | drifted; 152 was a `scripts/`-only count from 2026-09-09 |
| t33: "74 manifests / registry.json / README" | `legacy/agents/` holds **225 tracked files**: 74 `run.js`, 74 `manifest.json`, 75 `README.md`, `registry.json`, `SCHEMA.md` | CONFIRMED |
| t34: "root app.py (326-line legacy twin)" | `app.py` = **326 lines**, 9 Flask routes | CONFIRMED |
| t34: "scripts/patch-cockpit.py.bak" | exists, and is **byte-identical** to `scripts/patch-cockpit.py`; *neither* is referenced anywhere | CONFIRMED + refined |
| t34: "fix_syntax.py" | 46 lines, **zero references** repo-wide | CONFIRMED |

**Use 243 → 19 as the headline, not 152 → <20.** Re-derive it in the RFT handoff rather than copying this number.

### 0.2 The prerequisite chain is not what the queue assumes

P1b **did** land (`7d68a7c merge(p1b-port)`): the eight Layer 1 JobSpecs are registered at `campaign-os/_lib/jobs/layer1/`.

**P1a did not land.** `land/campaign-os-p1a-tests` sits at `f0ad184`, the *pre-P1a* integrate base. On `69b64e2` there is no `conftest.py`, no `pytest.ini`, no `.github/workflows/ci.yml`, no `tests/ci-allowlist.txt`, and `lint-brand-copy.yml:16,22` still names `feat/asset-state-engine`. `feat/campaign-os-p1a-tests` @ `24c4792` carries all of it, unmerged.

Two consequences the implementer must hold:

1. **"Nothing in CI references the deleted tree" is measured against four workflows**, not five: `deploy.yml`, `gbp-daily-cron.yml`, `lint-brand-copy.yml`, `meta-live-fetch.yml`. Only `deploy.yml:51` names a `.js`.
2. **The unlanded P1a CI is already Node-dependent** and depends on a file this slice must retain. `feat/campaign-os-p1a-tests:.github/workflows/ci.yml` runs `actions/setup-node@v4` in both pytest jobs, solely because `tests/test_parity.py` — line 104 of the 106-line blocking allowlist — shells `node -e "require('./scripts/_lib/visibility-guard')"`. Deleting `scripts/_lib/visibility-guard.js` would red P1a's blocking CI job the moment P1a lands. It is retained (§3), which settles this — but say so in the RFT handoff so the P1a lander does not have to rediscover it.

### 0.3 pytest baseline to hold flat

```text
$ cd campaign-os && DATA_DIR=/tmp/cos-p1c-probe python3 -m pytest tests -q -p no:randomly
418 failed, 1123 passed, 16 skipped, 142 warnings, 18 errors, 139 subtests passed in 23.93s
```

```text
$ DATA_DIR=/tmp/cos-p1c-probe python3 -m pytest tests/ scripts/tests/ -q
INTERNALERROR ... SystemExit: 0   # no tests ran — t26 unlanded, expected
```

P1c is a **delete-only** slice. Its pass condition on the campaign-os suite is **no regression**, not improvement: `418 / 1123 / 16 / 18` before and after, modulo the two deliberate test edits in §4. Re-measure the baseline at the merge-base yourself; do not trust this row after a rebase.

### 0.4 Two tests write into tracked `data/` — deleting their JS fixes it

Running the campaign-os suite dirtied `data/freshness.json` and `data/weekly-report.md`. Running the root `tests/*.js` tree dirtied `data/publish-failures.json`, `data/publish-queue.json`, `data/published-items.json`, `data/scheduled-items.json` and created three untracked files under `data/events/postiz/` and `data/live-publish-runs/`.

The first is `campaign-os/tests/test_freshness_sanity_range.py::test_freshness_regenerates`, which runs `node scripts/data_freshness_check.js` with `cwd=REPO` — the JS writes `data/freshness.json` directly. That is a standing **AGENTS.md §8 violation** ("No automation commits to `data/` — not a test fixture, not 'just this once'"). Deleting the JS and retargeting the test (§4.2) ends it.

**After every suite run on the desk: `git status --porcelain data/ && git checkout -- data/`.** Never commit the churn.

---

## 1. Acceptance criteria

Master-plan `done_criteria` first, then the checkable form.

### 1.1 t33 — delete the Node tree

Master plan: *152 JS files reduced to <20; nothing in CI or the app references the deleted tree; the three contradictory agent inventories (74 manifests / registry.json / README) are down to zero.*

| # | Acceptance criterion | How it is checked |
|---|---|---|
| t33-A | `git ls-files '*.js' \| wc -l` → **19** (8 `scripts/`, 11 `tests/`, 0 `legacy/`) | Run it. §2 gives the exact cohorts; §3 justifies each of the 19 |
| t33-B | `legacy/` no longer exists | `git ls-files legacy \| wc -l` → **0** |
| t33-C | The three inventories are gone | `git ls-files \| grep -cE 'legacy/agents/(registry\.json\|README\.md)\|legacy/agents/.*/manifest\.json'` → **0** |
| t33-D | No workflow names a deleted file | `grep -rnE '\.js\b' .github/workflows/ \| grep -v '\.json'` → exactly one hit, `deploy.yml:51` (`patch-cockpit.js`, retained) |
| t33-E | **No live app code path executes a deleted script** | `grep -rn "'node'\|\"node\"" campaign-os/app.py campaign-os/_lib/` → no hit that reaches a deleted file. See §4.1 — this is the one real code change in t33 |
| t33-F | No live code, test, or workflow resolves a deleted path | `grep -rnE "scripts/[a-zA-Z0-9_.-]+\.js" --include='*.py' --include='*.yml' --include='*.html' --include='*.sh' campaign-os/ tests/ scripts/ .github/` → every surviving hit names a **retained** file (§3) or is a historical comment (§4.5) |
| t33-G | The JS-only shell/py orchestrators go with their scripts | `scripts/run_path2_chain.sh` (14 `node scripts/*.js` calls) and `scripts/gate6-blueprint.py` (runs `create-campaign.js` / `generate-blueprint.js` off hardcoded `/Users/fivefriday` paths) are deleted. Both are unreferenced |
| t33-H | `docs/layer1-salvage-20260911.yaml` **survives** | `test -f docs/layer1-salvage-20260911.yaml`. AGENTS.md Appendix A: it exists precisely to survive t33 |
| t33-I | The 54 `scripts/*.py` fetchers survive, minus `gate6-blueprint.py` | `git ls-files 'scripts/*.py' \| wc -l` → **53**. `Dockerfile:29` copies `scripts/` into the image and `Dockerfile:33` runs `scripts/check_lib_modules.py` — an over-broad `git rm scripts/*` breaks the build |
| t33-J | `visibility_guard` is untouched on both sides | `git diff <base>..HEAD -- scripts/_lib/visibility-guard.js campaign-os/_lib/visibility_guard.py` → **empty**. AGENTS.md §8: FROZEN |
| t33-K | Doc truth follows the deletion | `AGENTS.md` §1/§9 and Appendix A no longer point at a `legacy/agents/` that does not exist; `legacy/README.md` is gone with its directory (§5.2) |

**Not** t33: porting anything. Every deletion in §2 is either already ported (§2.B), already superseded (§2.B), or knowingly unported and unreferenced (§2.E/F/G).

### 1.2 t34 — delete dead code

Master plan: *no second app.py to confuse a reader about which one is production; `scripts/patch-cockpit.js` retained — it is load-bearing for `deploy.yml:51` until t51 decides otherwise.*

| # | Acceptance criterion | How it is checked |
|---|---|---|
| t34-A | Root `app.py` is gone | `test ! -f app.py`. Production is `campaign-os/app.py` — the image never copies the root twin (§6.1) |
| t34-B | `fix_syntax.py` is gone | `test ! -f fix_syntax.py`. Zero references repo-wide |
| t34-C | `scripts/patch-cockpit.py.bak` is gone | `git ls-files \| grep -c '\.bak$'` → **0** |
| t34-D | **`scripts/patch-cockpit.js` is retained** | `test -f scripts/patch-cockpit.js`; `deploy.yml:51` still resolves. Do not touch it before t51 |
| t34-E | The `REBUILD_TRIGGER.txt` decision is recorded | §6.3. Recommendation: **delete** |
| t34-F | The `regenerate-cockpit.{js,py}` decision is recorded | §6.4. Recommendation: delete the `.js`, **keep** `regenerate-cockpit.py` |
| t34-G | The `patch-cockpit.py` decision is recorded | §6.2. Recommendation: **delete** — exceeds t34's literal wording, so it needs an explicit line in the RFT handoff and a verify acknowledgement |
| t34-H | Root-`app.py` deletion does not silently break a root test | §4.4 — one root test currently imports the *wrong* app and must be handled |

### 1.3 Explicitly out of scope for P1c

- Porting `taskmaster` (13 scripts), `approval_queue` or `asset_needs`. The p1b plan §4 already recommended dropping them; this slice deletes the JS and records `data/approval-queue.json` + `data/asset-needs.json` as permanently-static seed (§9.2).
- Retiring the `GET /api/intel/agents` fleet surface, which still reads `data/agent-runs.json` (§9.1). That is a live product surface, not a file deletion.
- Landing P1a. Do not merge `feat/campaign-os-p1a-tests` from this ticket.
- Any Railway deploy, any `main` push, any `data/` commit.
- `t45` / `t46` (`security_hardening`) — deferred by the ticket split.

---

## 2. The delete inventory

`legacy/agents/` — **225 files**, `git rm -r legacy/`. Deleting it also removes all three inventories in one move (t33-C) and drops ~920 KB from the Docker build context (`legacy/` is absent from `.dockerignore` / `.railwayignore`, so it ships today).

`scripts/` — **150 of 158 `.js`** (24,778 lines, 1.6 MB), plus `run_path2_chain.sh` and `gate6-blueprint.py`. The deterministic way to produce the list, and the way verify should re-derive it:

```bash
git ls-files '*.js' | grep '^scripts/' | grep -vE \
  'patch-cockpit|_lib/(visibility-guard|asset-state-engine|campaign-state-engine|postiz-credentials)|run_publisher|generate_publish_queue|regenerate-publishing-index'
# -> 150 lines
```

Evidence the 150 are dead: **71 of them hardcode `/Users/fivefriday`**, and the only non-builtin `require()`s in the whole set are `googleapis` and `google-auth-library` — neither installed, because **the repo has no `package.json` at all**. None of the 150 can run on this box or in the image.

| Cohort | Count | What it is | Why it goes |
|---|---|---|---|
| **B — ported / superseded** | 20 | `fetch_golf_news`, `fetch_reddit_trends`, `fetch_youtube_trends`, `fetch_ga4`, `run_seo_audit`, `run_geo_audit`, `analyse_hooks`, `extract_youtube_signals`, `fetch_website_insights`, `generate_anomaly_alerts`, `detect_missed_opportunities`, `generate_funnel_leaks`, `generate_conversion_attribution`, `generate_retargeting_recommendations`, `generate_recommendation_scores`, `generate_recommendation_outcomes`, `fetch_seo_rankings`, `sync_ig_analytics`, `fetch_postiz_analytics`, `data_freshness_check` | Replaced by the eight Layer 1 JobSpecs plus `meta_refresh` / `freshness_scan`. Three are supersessions rather than ports and must be recorded as such (§2.1) |
| **C — orchestrators** | 2 | `run_agent.js`, `master_pipeline.js` | Named by t33. The job runner replaces both |
| **D — memory + pulse keeper** | 3 | `retrieve_memory.js`, `store_daily_learnings.js`, `generate_pulse_keeper.js` | Named by t33: "the platform replaces them" |
| **E — taskmaster** | 13 | the 13 `generate_*.js` listed in `legacy/agents/taskmaster/manifest.json` | Unported by decision (p1b plan §4). 11 of their 12 outputs have no reader |
| **F — agent runners** | 74 | `scripts/run_<agent>.js`, one per `legacy/agents/<agent>/` | The Layer 2–9 fleet. Dies with the tree it drives |
| **G — other dead** | 38 | cockpit/dashboard generators, campaign CRUD, discord, publishing helpers, `validator.js`, `route_task.js`, … | Unported, unreferenced by live code, CI or a passing test |
| | **150** | | |

### 2.1 Three supersessions to record, not diff

t30's done-criteria asked for a side-by-side diff before deletion. Three of cohort B have **nothing to diff** and the RFT handoff must say so explicitly, or t32's verdict will be read as missing:

- **`fetch_seo_rankings.js`** — never ported. `seo_rankings` wraps `scripts/fetch_ubersuggest.py` instead; the JS produces a Google-SERP shape (`rising_keywords`/`falling_keywords`) that matches nothing on disk and has no reader. Superseded, not ported (p1b plan §0 #1).
- **`fetch_postiz_analytics.js`** — writes `data/ig-analytics.json` (line 10 + 124), which `meta_refresh` now owns. Subsumed, and its write into tracked `data/` is a §8 violation in its own right.
- **`sync_ig_analytics.js`** — subsumed by `meta_refresh` per the p1b job table.

---

## 3. The retain list — 19 files, each load-bearing

Nothing here is kept "just in case". Every entry has a named consumer.

### 3.1 `scripts/` — 8 files

| File | Kept because | Authority |
|---|---|---|
| `patch-cockpit.js` | `.github/workflows/deploy.yml:51` runs it on every Pages deploy | **t34 done-criteria, explicit — until t51** |
| `_lib/visibility-guard.js` | `campaign-os/_lib/visibility_guard.py:2` mirrors it, JS canonical; `tests/test_parity.py:42` shells node into it; `tests/test_visibility_guard.js` covers it (**16/16 pass**); P1a's blocking CI allowlist includes `test_parity.py` (§0.2) | **AGENTS.md §8 — FROZEN** |
| `_lib/asset-state-engine.js` | `require`d by `tests/test_asset_state_engine.js` (**79/79 pass**), `tests/test_engine_convergence.js` (**18/18 pass**), `tests/test_step94b...js`. Itself `require`s `./visibility-guard` | transitive closure |
| `_lib/campaign-state-engine.js` | `require`d by `tests/test_campaign_state_engine.js` (**0 failed**) | transitive closure |
| `_lib/postiz-credentials.js` | `require`d by `run_publisher.js` | transitive closure |
| `run_publisher.js` | `require`d/read by 5 root JS tests, two of which pass (`test_publisher_writeback.js` 31 passed, `test_step100_runtime_proof.js` exit 0) | transitive closure |
| `generate_publish_queue.js` | `require`d by `tests/test_generate_publish_queue.js` (**43/43 pass**) | transitive closure |
| `regenerate-publishing-index.js` | `require`d by `run_publisher.js`; `campaign-os/truth_collector.py:1101` prints "Run scripts/regenerate-publishing-index.js to rebuild" as an operator hint | live user-facing string |

`truth_collector.py:1101` is worth a beat: it is the one operator-facing string naming a JS file that **stays true** after this slice, because the script it names is retained. Its sibling at `_lib/intelligence.py:3258` does not (§4.3).

### 3.2 `tests/` — 11 root JS tests, measured

I ran all eleven. They are not in pytest and no workflow invokes them, so this is the first recorded state of that tree:

| Test | Exit | Result |
|---|---|---|
| `test_visibility_guard.js` | 0 | 16 passed |
| `test_asset_state_engine.js` | 0 | 79 passed |
| `test_campaign_state_engine.js` | 0 | 0 failed |
| `test_engine_convergence.js` | 0 | 18 passed |
| `test_generate_publish_queue.js` | 0 | 43 passed |
| `test_publisher_writeback.js` | 0 | 31 passed |
| `test_step100_runtime_proof.js` | 0 | proof emitted |
| `test_phase2_wizard.js` | **1** | `ENOENT` — wants root `cockpit-operational.html`, which lives at `campaign-os/` |
| `test_phase_tdz_fix.js` | **1** | `ENOENT /Users/fivefriday/.../campaign-data.json` |
| `test_step94_payload_and_upload.js` | **1** | "expected at least 1 failure, got 0" — **and dirties tracked `data/`** |
| `test_step94b_event_semantics_and_recovery.js` | **1** | 34 passed, **2 failed** — **and dirties tracked `data/`** |

**Default (Option A, in scope): retain all 11.** Total = 8 + 11 = **19** < 20. t33-A met.

**Option B, recommended but out of the manifest's `paths`:** also delete the four broken tests. They prove nothing, two of them violate AGENTS.md §8 on every run, and two carry the same dead-Mac-path rot t34 exists to remove. That gives **15** JS, and the §3.1 retain set does not shrink (every retained script still has a passing consumer). `tests/**` is not in the implement job's `paths`, so **this needs the extension in §5.1 or a Kyle call.** Do not do it silently.

---

## 4. The four live references — this is where t33 stops being `git rm`

t33's second done-criterion is the whole risk of this slice. I grepped every `.py`, `.html`, `.yml`, `.sh` and the `Dockerfile` outside `scripts/` and `legacy/` for `scripts/*.js`, in both the literal and the `os.path.join(..., 'scripts', ...)` split form. Four hits need work. Everything else resolves to a retained file or is a historical comment.

### 4.1 `campaign-os/app.py` executes `data_freshness_check.js` — the only real code change

`campaign-os/app.py:27763` `admin_data_freshness()`, on `?refresh=1`, probes three paths for `data_freshness_check.js` and runs `subprocess.run(['node', sp], ...)` (lines 27777–27787). Docstrings at `:14117`, `:14469` and `:27765` also name it.

**The replacement already exists and is already registered.** `_run_freshness_scan_job()` at `app.py:14320` performs the same walk in Python — `_build_freshness_on_demand()` was written against "the same heuristic as `scripts/data_freshness_check.js`" (comment at `:14116`) — and is registered as the `freshness_scan` JobSpec at `:14403`. `POST /api/freshness/refresh` already calls it.

**Fix:** replace the node shell-out block with `_run_freshness_scan_job()` and update the three docstrings. Roughly 12 lines net.

**Do not stop there — there is a precedence bug waiting under it.** The JS wrote `data/freshness.json` (the bundled seed, which is **tracked**). `_run_freshness_scan_job()` writes `$DATA_DIR/freshness.json`. But `admin_data_freshness()` reads its candidates in the order `BUNDLED_DATA_DIR` → `DATA_DIR` → `data/`, so after the swap a fresh scan writes to `$DATA_DIR` while the endpoint keeps serving the stale tracked seed — a refresh button that appears to work and changes nothing. Flip the read order to `DATA_DIR` first, matching every other `$DATA_DIR`-exclusive path P0.5 established. **Manual test 3 (§7) exists specifically to catch this.**

### 4.2 `campaign-os/tests/test_freshness_sanity_range.py`

`:24` `SCRIPT = REPO / "scripts" / "data_freshness_check.js"`; `test_freshness_regenerates` runs it with `cwd=REPO`.

It **skips gracefully** when the script is missing, so deletion does not red the suite — but it leaves a test whose stated subject no longer exists, and its sibling `test_no_year_2001_artifacts` then reads the tracked seed and passes for the wrong reason.

**Fix:** delete `test_node_available` and `test_freshness_regenerates`; retarget the regeneration assertion at `_run_freshness_scan_job()`. Keep `test_parseTs_rejects_bare_month_day` (`:140`) — it holds an **inline** copy of the JS `parseTs`/`_inSaneRange` pair and does not read the file, but add a comment noting the original is gone as of this commit, or it reads as a fixture pinned to vapour.

Deleting the JS is what ends the §0.4 `data/freshness.json` churn.

### 4.3 `campaign-os/_lib/intelligence.py:3258` — a user-facing instruction that becomes a lie

```python
"evidence": "Reach counter is 0 across all posts. ... Re-run sync_ig_analytics.js to verify."
```

This string ships to the operator in an intel view. `sync_ig_analytics.js` is cohort B. **Fix:** point it at the job — "re-run the `meta_refresh` job (`POST /api/jobs/run/meta_refresh`) to verify".

`intelligence.py:889` and `:3558`, and `_lib/postiz_client.py:5`, also name deleted scripts but are **comments recording history**. Leave them; they are the same kind of provenance note as the `layer1/*.py` docstrings, and rewriting history out of comments is how a repo loses its audit trail. Say this in the RFT handoff so verify does not flag them as t33-F failures.

### 4.4 `campaign-os/tests/test_v2026_08_10_insights_relative_tone.py:79` — the one hard failure

```python
fetcher = (REPO / "scripts" / "fetch_postiz_analytics.js").read_text(encoding="utf-8")
self.assertIn("permalink", fetcher, ...)
self.assertIn("p.releaseURL", fetcher, ...)
```

No guard. Deleting the JS turns `test_postiz_fetcher_captures_permalink` into a `FileNotFoundError`. **This is the only test in the repo that a naive `git rm` breaks outright.**

Its intent — "the next sync captures permalink" — now belongs to `_lib/meta_live_fetch.py:136`, which requests `permalink` in the IG media `fields`, and to `_lib/insights_correlator.py:113`, which reads it back. `_lib/postiz_client.py` does publishing and OAuth only; it has **zero** `permalink` hits, so there is no Postiz-side successor.

**Fix:** retarget the assertion at `_lib/meta_live_fetch.py` (assert `permalink` appears in the IG media fields string). Drop the `p.releaseURL` half — it was a Postiz API detail with no successor — and record the drop.

### 4.5 And the one that does not need a fix

`app.py:9581–9834` and `_lib/jobs/layer1/seo_rankings.py:46` join `'scripts'` with **`.py`** fetchers (`fetch_ig_business.py`, `fetch_facebook_page.py`, `fetch_ubersuggest.py`, …). These are live and untouched. They are why t33-I exists: `scripts/` is being pruned of JS, not emptied.

---

## 5. Path discipline

### 5.1 The manifest's `paths` allowlist is too narrow — raise this before coding

`manifests/plan-20260911-campaign-os-p1c-legacy.yaml` gives the implement job:

```yaml
paths: [legacy/agents/**, scripts/**, agents/**, app.py]
```

`agents/**` no longer exists (moved to `legacy/agents/` in t20), and the list cannot express §4. The following are required to satisfy t33-E/F and t34-K and are **outside** it:

| Path | Why | §|
|---|---|---|
| `campaign-os/app.py` | the node shell-out + read-order fix. (`app.py` in the manifest means the **root** twin t34 deletes — the ambiguity is worth resolving in writing) | 4.1 |
| `campaign-os/tests/test_freshness_sanity_range.py` | retarget at the Python job | 4.2 |
| `campaign-os/tests/test_v2026_08_10_insights_relative_tone.py` | hard `FileNotFoundError` otherwise | 4.4 |
| `campaign-os/_lib/intelligence.py` | one operator-facing string | 4.3 |
| `AGENTS.md` | §1, §9 and Appendix A describe a tree that stops existing | 5.2 |
| `legacy/**` (not just `legacy/agents/**`) | `legacy/README.md` documents the deleted directory | 5.2 |
| `campaign-data-staged.json` | `:51` points at `write-campaign.js` / `write-back.js`, both deleted | 9.3 |
| `.railwayignore`, `.dockerignore` | both ignore a root `agents/` that is already gone | 9.4 |
| `tests/**` | **only if Kyle takes Option B** (§3.2) | 3.2 |

**Ask the orchestrator to extend `paths` before the implement job starts.** Do not widen it unilaterally; do not work around it by leaving §4 half-done.

### 5.2 Doc truth

`AGENTS.md` §1 ("`legacy/agents/` is a retired Node tree — dead, kept for evidence"), §9's stale-docs row for `legacy/agents/{registry.json,README.md}`, and Appendix A's "Survives t33 deletion of `legacy/agents/`" all describe a directory that stops existing. `legacy/README.md` says "**Frozen until t33** ... Deletion of `legacy/agents/` is t33 only."

**Recommendation: delete `legacy/` entirely**, README included, and fold a two-line note into `AGENTS.md` §1 — "the Node fleet was deleted in t33 on <date> at `<sha>`; `docs/layer1-salvage-20260911.yaml` is the surviving record; git history holds the rest." Keeping a README that describes a deleted tree recreates exactly the fourth-inventory problem t33 exists to end.

### 5.3 Lanes that must stay untouched

The calendar SPA lane (`campaign-os/_lib/marketing_calendar.py`, the calendar routes, `data/brand-directory/*/calendar_config.json`) is active on integrate and disjoint from this slice. So is `campaign-os/_lib/jobs/**` — P1b's ports are the *reason* the deletions are safe; do not "tidy" them. `data/` takes **no commits** (AGENTS.md §8), which makes §9.1 and §9.2 handoff items rather than edits.

---

## 6. The t34 decisions

### 6.1 Root `app.py` — safe to delete, and here is the proof

`railway.json:8` says `"startCommand": "python app.py"`, which reads alarming. It is not: `Dockerfile:48` sets `WORKDIR /app/campaign-os`, so it resolves to `campaign-os/app.py`. The root twin is **never copied into the image** — `Dockerfile` copies only `campaign-os/`, `data/`, `assets/`, `scripts/`. Deleting it cannot affect production. Put that sentence in the RFT handoff; it is the first thing a reviewer will ask.

### 6.2 `scripts/patch-cockpit.py` and `.py.bak`

Byte-identical to each other, and **neither is referenced anywhere** — `deploy.yml:51` uses the `.js`. t34 names only the `.bak`. **Recommendation: delete both.** A dead Python twin of the one load-bearing JS file is the same "which one is production?" hazard as the root `app.py`, one level down. This exceeds t34's literal wording, so name it in the RFT handoff and let verify record it as a deliberate extension rather than an overreach.

### 6.3 `REBUILD_TRIGGER.txt`

Contains one timestamp, `2026-08-20T00:26:33Z`. Its only mentions are four narrative lines in `campaign-os/docs/nightshift-log.md` describing it as a manual nudge to force a Railway rebuild. `deploy.yml`'s `paths:` filter does not include it, and Railway rebuilds on every push regardless. **Recommendation: delete.**

### 6.4 `regenerate-cockpit.{js,py}`

`regenerate-cockpit.js` — no reference anywhere. **Delete** (it is already inside cohort G).
`regenerate-cockpit.py` — referenced by `campaign-os/CAMPAIGN-OS-FULL-SPEC.md:436,599` and `docs/CAMPAIGN-MOTHERSHIP-V2.md:597` as the campaign-data → cockpit-HTML renderer. It is Python, it is in the Pages lane, and **t51 owns the Pages decision**. **Recommendation: keep**, same reasoning as `patch-cockpit.js`. Record it as t51-gated.

---

## 7. Verify tier + manual test plan

### 7.1 Verify tier

Read-only, from a clean checkout of `feat/campaign-os-p1c-legacy`. Re-derive every number; do not read them out of the RFT handoff. Verdict vocabulary matching P0c/P1b: **PASS / PARTIAL / FAIL** per task, plus *code-met, live-unverified* for anything needing the branch on origin.

| # | Check | Command | Pass condition |
|---|---|---|---|
| V1 | JS count | `git ls-files '*.js' \| wc -l` | **19** (or **15** if Kyle took Option B) — and `awk -F/ '{print $1}' \| sort \| uniq -c` shows only `scripts` and `tests` |
| V2 | `legacy/` gone | `git ls-files legacy \| wc -l` | **0** |
| V3 | Three inventories gone (t33-C) | `git ls-files \| grep -E 'registry\.json\|manifest\.json' \| grep legacy` | no output |
| V4 | Retain set is exactly §3.1 | `git ls-files 'scripts/*.js'` | the 8 named files, no more, no fewer |
| V5 | **`visibility_guard` untouched** | `git diff <base>..HEAD -- scripts/_lib/visibility-guard.js campaign-os/_lib/visibility_guard.py` | **empty**. Any diff = instant FAIL (AGENTS.md §8) |
| V6 | `patch-cockpit.js` retained (t34-D) | `test -f scripts/patch-cockpit.js && grep -n patch-cockpit .github/workflows/deploy.yml` | file present, `deploy.yml:51` intact |
| V7 | CI names no deleted file | `grep -rnE '\.js\b' .github/workflows/ \| grep -v '\.json'` | exactly one hit: `deploy.yml:51` |
| V8 | **No dangling script path in live code** | `grep -rnE "scripts/[a-zA-Z0-9_.-]+\.js" --include='*.py' --include='*.yml' --include='*.html' --include='*.sh' campaign-os/ tests/ scripts/ .github/` | every hit is a retained file or a §4.3-sanctioned history comment. **Each surviving hit must be individually accounted for in the verdict — a bare count is not a verification** |
| V9 | No node shell-out to a deleted file (t33-E) | `grep -rn "'node'\|\"node\"" campaign-os/` | remaining hits are `node --version` probes or `node -e` inline sources only |
| V10 | `/api/admin/data-freshness?refresh=1` works without node | manual test 3 | `ok:true`, no `node` in the process tree |
| V11 | pytest has not regressed | `cd campaign-os && DATA_DIR=$(mktemp -d) python3 -m pytest tests -q -p no:randomly` | `failed` ≤ **418**, `passed` ≥ **1123**, `errors` ≤ **18**. Re-derive the merge-base baseline first |
| V12 | The §4.4 test is green, not deleted-and-forgotten | `pytest campaign-os/tests/test_v2026_08_10_insights_relative_tone.py -v` | green; `test_postiz_fetcher_captures_permalink` present and now asserting against `_lib/meta_live_fetch.py` |
| V13 | Retained JS tests still pass | `for f in tests/*.js; do node $f; done` | the 7 from §3.2 that passed still pass. A new failure = FAIL |
| V14 | Salvage survives (t33-H) | `test -f docs/layer1-salvage-20260911.yaml` | present |
| V15 | Python fetchers survive (t33-I) | `git ls-files 'scripts/*.py' \| wc -l` | **53** (54 minus `gate6-blueprint.py`) |
| V16 | Image still builds | `python3 scripts/check_lib_modules.py --source campaign-os/app.py --lib-dir campaign-os/_lib; echo $?` | exit 0, `missing_count: 0` — this is `Dockerfile:33` |
| V17 | Root `app.py` gone, `campaign-os/app.py` intact (t34-A) | `test ! -f app.py && python3 -c "import ast,sys; ast.parse(open('campaign-os/app.py').read())"` | both hold |
| V18 | No `.bak` left (t34-C) | `git ls-files \| grep -c '\.bak$'` | **0** |
| V19 | **`data/` is untouched** | `git diff --stat <base>..HEAD -- data/` | **empty**. AGENTS.md §8. Also `git status --porcelain data/` after V11/V13 → empty |
| V20 | Docs match reality (t33-K) | `grep -n 'legacy/agents' AGENTS.md; test ! -f legacy/README.md` | no AGENTS.md line asserts the tree exists |
| V21 | Diff is deletions plus the §4 edits, nothing else | `git diff --stat <base>..HEAD` | additions confined to `AGENTS.md`, `campaign-os/app.py`, the two test files, `_lib/intelligence.py`, `campaign-data-staged.json`, the two ignore files |

### 7.2 Manual test plan — 8 steps

Run in the implement worktree. Job-file port for any local server: **3460** (`runtime.ports.web`) — never 8765, never 8080. Never print a secret value.

```bash
export DATA_DIR=$(mktemp -d /tmp/cos-p1c-manual-XXXX)
export COS_JOB_TOKEN=test-token-not-a-secret
cp data/*.json "$DATA_DIR"/ 2>/dev/null || true
```

**After every suite run: `git status --porcelain data/ && git checkout -- data/`** (§0.4).

**1. The app boots and the route surface is unchanged (t34-A).**
```bash
cd campaign-os && PORT=3460 python3 app.py &
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3460/api/health
```
*Pass:* `200`. Compare `len(app.url_map)` against the merge-base — deleting the root twin must not move it.

**2. Job roster is intact (P1b regression).**
`curl -s -H "Authorization: Bearer $COS_JOB_TOKEN" http://127.0.0.1:3460/api/jobs/status | python3 -m json.tool`
*Pass:* **11** jobs — `meta_refresh`, `gbp_tick`, `freshness_scan` + the eight Layer 1. Unauth → `401`.

**3. Freshness refresh works with node absent — the step that proves §4.1.**
```bash
curl -s -H "Authorization: Bearer $COS_JOB_TOKEN" \
     "http://127.0.0.1:3460/api/admin/data-freshness?refresh=1" | python3 -m json.tool
ls -la "$DATA_DIR/freshness.json"
```
*Pass:* `ok` true; `$DATA_DIR/freshness.json` mtime is **now**; the `total_files` / `by_staleness` in the response match the file just written — **not** the tracked seed (this is the read-order bug in §4.1). Then re-run with `node` removed from `PATH` (`env PATH=/usr/bin:/bin ... ` with a shimmed dir) and confirm identical output. *If the response still reflects the bundled seed after a scan, §4.1's second half was not done.*

**4. `git grep` finds no dangling script (t33-F).**
```bash
git grep -nE "scripts/[a-zA-Z0-9_.-]+\.js" -- '*.py' '*.yml' '*.html' '*.sh' Dockerfile
```
*Pass:* every hit names a §3.1 file or is one of the three sanctioned history comments (`intelligence.py:889`, `:3558`, `postiz_client.py:5`). Read them; do not count them.

**5. pytest has not regressed (V11).**
```bash
cd campaign-os && python3 -m pytest tests -q -p no:randomly 2>&1 | tail -3
```
*Pass:* `failed` ≤ 418, `passed` ≥ 1123, `errors` ≤ 18 against a merge-base baseline you measured yourself. Then `git status --porcelain data/` → **empty**, which the §4.2 change should now make true for the first time.

**6. The retained JS tests still run (V13).**
```bash
for f in tests/test_visibility_guard.js tests/test_asset_state_engine.js \
         tests/test_campaign_state_engine.js tests/test_engine_convergence.js \
         tests/test_generate_publish_queue.js tests/test_publisher_writeback.js \
         tests/test_step100_runtime_proof.js; do echo "== $f"; node "$f" >/dev/null 2>&1; echo "exit=$?"; done
git status --porcelain data/
```
*Pass:* all seven exit 0; `data/` clean afterwards.

**7. Docker build context still builds (V16).**
```bash
python3 scripts/check_lib_modules.py --source campaign-os/app.py --lib-dir campaign-os/_lib; echo $?
docker build -t cos-p1c-test .    # if docker is on the desk
```
*Pass:* exit 0, `missing_count: 0`; image builds. If docker is unavailable locally, say so — do not claim a local pass.

**8. Pages deploy path is intact (t34-D).**
```bash
node scripts/patch-cockpit.js campaign-os/cockpit-operational.html campaign-os/campaign-data.json
git status --porcelain campaign-os/cockpit-operational.html
```
*Pass:* exit 0 and the file patches, exactly as `deploy.yml:51` would. **Revert the working-tree change afterwards** — this is a rehearsal, not a commit.

### 7.3 The RFT handoff must contain

- Branch + full SHA; merge target `integrate/campaign-os-option-c`; push state from a fresh `git ls-remote`.
- `git ls-files '*.js' | wc -l` before and after, with the per-directory breakdown, and the note that the master plan's "152" was a stale `scripts/`-only count.
- The four §4 fixes, each with the file:line it resolved, and the explicit statement that `intelligence.py:889`, `:3558` and `postiz_client.py:5` were **deliberately kept** as history comments.
- The three supersessions of §2.1 stated as supersessions, so t32's missing diffs are not read as a gap.
- Per-task PASS / PARTIAL / FAIL for t33 and t34, and the §6 decisions (`REBUILD_TRIGGER.txt`, `regenerate-cockpit.{js,py}`, `patch-cockpit.py`) each recorded with its verdict.
- The pytest before/after table and the confirmation that `data/` is clean.
- Whether Kyle took Option A (19) or Option B (15) on the four broken root JS tests.
- The §9 open items, each with a named owner.
- A one-line honest summary: *224 files and ~26,700 lines of dead Node deleted; 19 JS survive, every one of them load-bearing for a passing test or the Pages deploy; the only behaviour change is that the freshness refresh button no longer needs node installed.*

---

## 8. Suggested commit shape

Four commits, so a bisect lands somewhere useful:

1. `refactor(campaign-os): replace data_freshness_check.js shell-out with freshness_scan job (t33)` — §4.1 + §4.2 + §4.4 + §4.3. **The code change lands before the deletions, so the tree is never broken at any commit.**
2. `chore(legacy): delete legacy/agents/ — 225 files, three dead inventories (t33)` — §2 + §5.2.
3. `chore(scripts): delete 150 ported and unported JS + run_path2_chain.sh + gate6-blueprint.py (t33)` — §2.
4. `chore: delete root app.py twin, fix_syntax.py, patch-cockpit.py{,.bak}, REBUILD_TRIGGER.txt (t34)` — §6.

---

## 9. Open items for Kyle

### 9.1 The fourth inventory is a live endpoint, not a file

`GET /api/intel/agents` → `_lib/intelligence.py:2399 agents_view()` reads `data/agent-runs.json` — **23 agents, last updated 2026-08-13** — and forwards per-script results including `generate_pulse_keeper.js`, `store_daily_learnings.js` and friends into the "Agents & health" SPA surface. `intelligence.py:2802` and `:4351` build a weekly "fleet" summary from the same file.

After t33 that panel reports a fleet of 23 agents running `.js` files that exist nowhere in the repo. **t33's "inventories down to zero" is not truly met by deleting files while this surface is live.** It is out of scope here — it is product behaviour, `data/` is frozen by AGENTS.md §8, and the ops-UI lane is P1e (t42–t44).

**Recommendation:** open a P1e row — *"retire or relabel `/api/intel/agents` — it renders a fleet that t33 deleted"* — and state in the RFT handoff that t33-C is met **for the repo tree** with this surface named as the remaining carrier. Do not let it fall off the edge.

### 9.2 Two seed files become permanently static

`data/approval-queue.json` and `data/asset-needs.json` keep readers in `campaign-os/app.py`, and their producers (`generate_approval_queue.js`, `generate_asset_needs.js`) die in cohort E. Carried forward from the p1b plan §4, still unanswered: **port as one small job, or remove the `app.py` readers?** Either is fine; silence is not.

### 9.3 A dangling pointer in `campaign-data-staged.json`

`:51` — *"Write-back pipeline: agent writes staged → commit → push → GitHub Actions regenerates cockpit. See `scripts/write-campaign.js` and `scripts/write-back.js`."* Both are cohort G. The file is at repo root, not under `data/`, so a human-authored edit is allowed. One-line fix; needs the §5.1 paths extension.

### 9.4 Stale ignore entries

`.railwayignore` and `.dockerignore` both ignore a root `agents/` that has not existed since t20, and both list `campaign-os/app.js` / `campaign-os/server.js`, neither of which exists. Neither ignores `legacy/`, so all 225 files ship in the build context today. Tidy the four lines with the deletion.

### 9.5 A dead Mac path in a retained file

`scripts/_lib/postiz-credentials.js:19` carries `/Users/fivefriday/.openclaw-instance2/...` in a comment. It is one of the 8 survivors, and AGENTS.md §3 says *"Never `/Users/fivefriday/...` — that is a dead Mac path in old docs."* One-line comment fix, inside the manifest's existing `paths`.

### 9.6 P1a is unlanded and this slice depends on nothing from it — but the reverse is not true

§0.2. Nothing here blocks on P1a, and P1c can land first. But P1a's blocking CI allowlist contains `tests/test_parity.py`, which needs `scripts/_lib/visibility-guard.js` and a Node runtime. This plan retains both. **The P1a lander needs to know that, and the Gate P1 checklist ("Node gone (<20 JS)") should be read as "<20 JS, of which the visibility-guard parity pair is deliberate and frozen" — not as a licence to finish the job.**

---

## Appendix — commands used for §0–§3

```bash
# counts
git ls-files '*.js' | wc -l                                   # 243
git ls-files '*.js' | awk -F/ '{print $1}' | sort | uniq -c    # 158 scripts, 74 legacy, 11 tests
git ls-files legacy/agents | sed 's|.*/||' | sort | uniq -c    # 75 README, 74 run.js, 74 manifest.json, SCHEMA.md, registry.json

# the delete list (150)
git ls-files '*.js' | grep '^scripts/' | grep -vE \
  'patch-cockpit|_lib/(visibility-guard|asset-state-engine|campaign-state-engine|postiz-credentials)|run_publisher|generate_publish_queue|regenerate-publishing-index'

# evidence it is dead
grep -l '/Users/fivefriday' $(<delete-list) | wc -l            # 71/150
grep -ho "require('[a-z@][^'./][^']*')" $(<delete-list) | sort -u   # googleapis, google-auth-library only

# live references, both path forms
grep -rnoE "scripts/[a-zA-Z0-9_.-]+\.js" --include='*.py' --include='*.html' --include='*.yml' \
     --include='*.sh' campaign-os/ tests/ .github/ Dockerfile | sort -u
grep -rn "'scripts'\|\"scripts\"" --include='*.py' campaign-os/ tests/

# baselines
cd campaign-os && DATA_DIR=/tmp/cos-p1c-probe python3 -m pytest tests -q -p no:randomly | tail -1
for f in tests/*.js; do node "$f" >/dev/null 2>&1; echo "$? $f"; done
git status --porcelain data/ && git checkout -- data/          # after every run
```

**Branch/SHA discipline:** everything above was measured at `69b64e2ad185e4ffd75f4a97d20e39a82ed32180`. Rebase on `origin/integrate/campaign-os-option-c` before coding and re-derive §0.3 and §3.2 if the base has moved.
