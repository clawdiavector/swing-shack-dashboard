# t32 Pi verify — evidence contract (Deep tier)

**Job:** `job-20260911-campaign-os-p1b-port-implement` (t30/t31/t32 evidence)
**Verifier:** Pi Deep — `deepseek/deepseek-v4-pro` (plan §6)
**Method:** read-only PASS/FAIL from exported artifacts + registry checks.
**Do not run JS. Do not fix code.**

## Artifact root

```
/home/kyle/Work/artifacts/campaign-os-p1b/
  manifest.json                         # index + Class A pass flags
  snapshots/{seed,empty_ig,meta_fresh}/
    in/                                 # frozen inputs
    js/                                 # JS same-input outputs
    py/                                 # Python same-input outputs
  insights_hooks/<snap>/<file>/{js,py,normalized-*,diff}.json
  insights_reco/<snap>/<file>/{js,py,normalized-*,diff}.json
```

Diff helper (scoped under `_lib/jobs`):

```bash
cd campaign-os && python3 -m _lib.jobs.diff_job_output \
  --job insights_hooks --js "$SNAP/js.json" --py "$SNAP/py.json" \
  --out-dir /home/kyle/Work/artifacts/campaign-os-p1b/insights_hooks/seed/hook-bank.json
```

## Class A status (implement close)

Same-input replay completed for **3 snapshots** (`seed`, `empty_ig`, `meta_fresh`).

| Job | seed | empty_ig | meta_fresh | Overall |
|---|---|---|---|---|
| `insights_hooks` (2 files) | PASS | PASS | PASS | **PASS** |
| `insights_reco` (8 files) | PASS | PASS | PASS | **PASS** |

`manifest.json` → `class_a_overall_pass: true`.

Method notes for the verifier:

- JS scripts were **copied** into a sandbox (not symlinked) so `__dirname/../data` does not touch repo `data/`.
- Pipeline order matches legacy: `analyse_hooks` then `extract_youtube_signals` (prior `youtube-hook-signals.json` feeds analyse).
- Volatile keys stripped in diff: `updated`, `generated`, `fetched_at`, `timestamp`, `created_at`, `posted_at`, …
- Numeric parity: whole floats coerced like Node `JSON.stringify`.

## Registered jobs (expect 11 with app bootstrap)

From `_lib.jobs.registry` alone: `meta_refresh` + 8 Layer 1 = 9.
With `app.py` gbp_tick + freshness_scan: **11**.

Layer 1 names: `golf_news`, `reddit_trends`, `youtube_trends`, `seo_rankings`,
`ga4_report`, `site_audit`, `insights_hooks`, `insights_reco`.

## Per-job rubric (plan §6)

| Job | Class | PASS requires | Artifact status at implement close |
|---|---|---|---|
| `insights_hooks` | A | Normalised byte-identical across 3 snapshots | **PASS** — see manifest |
| `insights_reco` | A | Same + all 8 writes present | **PASS** — see manifest |
| `ga4_report` | B | Schema identical; total_sessions within 2% | Class B week not started |
| `youtube_trends` | B | Schema + volume/overlap/classification | Class B week not started |
| `site_audit` | B | Schema both files; volume envelope | Class B week not started |
| `golf_news` | B zero-baseline | Absolute bar (≥5 articles on ≥5/7 days) **or** written "source dead" | Class B week not started; both-empty is NOT PASS |
| `reddit_trends` | B zero-baseline | Absolute bar (≥20 trends on ≥5/7 days) **or** "source dead" | Class B week not started; both-empty is NOT PASS |
| `seo_rankings` | C | Shape matches seed; wrap not JS port; `fetch_seo_rankings.js` superseded | Shape covered by contract tests; wrap in `seo_rankings.py` |

## Cross-cutting checks for verifier

1. `GET /api/jobs/status` lists 11 jobs (bearer or session).
2. `git status --porcelain data/` clean after runs.
3. `python3 scripts/check_lib_modules.py` exit 0 (no `--warn-only`).
4. Every `writes` path produced; no undeclared writes.
5. `$DATA_DIR/job-runs.jsonl` has started+finished; `rows` integer for new jobs on success paths.

## Contract tests (t31 CI subset)

```bash
cd campaign-os && python3 -m pytest tests/jobs/ -q
```

## Notes for Pi

- `retries` on JobSpecs is **inert until t35**.
- `seo_rankings` wraps `scripts/fetch_ubersuggest.py`; JS SERP scraper was **superseded, never ported**.
- `taskmaster` consciously dropped (plan §4); `site_audit` is the +1 scope job.
- Class B calendar gate: seven consecutive live days required before Class B PASS.
- `feedparser` not added — `golf_news` uses stdlib `xml.etree.ElementTree` (recorded deviation).
- Outcomes matching is caption-faithful to JS (`caption` only; seed posts use `captionPreview`, so both sides correctly report `not_executed`).
