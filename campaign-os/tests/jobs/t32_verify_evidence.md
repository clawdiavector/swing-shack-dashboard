# t32 Pi verify — evidence contract (Deep tier)

**Job:** `job-20260911-campaign-os-p1b-port-implement` (t30/t31 implement)
**Verifier:** Pi Deep — `deepseek/deepseek-v4-pro` (plan §6)
**Method:** read-only PASS/FAIL from exported artifacts + registry checks.
**Do not run JS. Do not fix code.**

## Artifact root

```
/home/kyle/Work/artifacts/campaign-os-p1b/
  manifest.json
  <job>/<YYYY-MM-DD>/
    js.json
    py.json
    normalized-js.json
    normalized-py.json
    diff.json
```

Diff helper (scoped port of plan's `scripts/dev/diff_job_output.py`):

```bash
cd campaign-os && python3 -m _lib.jobs.diff_job_output \
  --job insights_hooks --js "$SNAP/js.json" --py "$SNAP/py.json" \
  --out-dir /home/kyle/Work/artifacts/campaign-os-p1b/insights_hooks/seed
```

## Registered jobs (expect 11 with app bootstrap)

From `_lib.jobs.registry` alone: `meta_refresh` + 8 Layer 1.
With `app.py` gbp_tick + freshness_scan: **11**.

Layer 1 names: `golf_news`, `reddit_trends`, `youtube_trends`, `seo_rankings`,
`ga4_report`, `site_audit`, `insights_hooks`, `insights_reco`.

## Per-job rubric (plan §6)

| Job | Class | PASS requires | Artifact status at implement close |
|---|---|---|---|
| `insights_hooks` | A | Normalised byte-identical across 3 snapshots | Helper ready; Class A snapshot export is operator follow-up |
| `insights_reco` | A | Same + all 8 writes present | Helper ready; Class A snapshot export is operator follow-up |
| `ga4_report` | B | Schema identical; total_sessions within 2% | Class B week not started |
| `youtube_trends` | B | Schema + volume/overlap/classification | Class B week not started |
| `site_audit` | B | Schema both files; volume envelope | Class B week not started |
| `golf_news` | B zero-baseline | Absolute bar (≥5 articles on ≥5/7 days) **or** written "source dead" | Class B week not started; both-empty is NOT PASS |
| `reddit_trends` | B zero-baseline | Absolute bar (≥20 trends on ≥5/7 days) **or** "source dead" | Class B week not started; both-empty is NOT PASS |
| `seo_rankings` | C | Shape matches seed; wrap not JS port; `fetch_seo_rankings.js` superseded | Shape covered by contract tests |

## Cross-cutting checks for verifier

1. `GET /api/jobs/status` lists 11 jobs (bearer or session).
2. `git status --porcelain data/` clean after runs.
3. `python3 scripts/check_lib_modules.py` exit 0 (no `--warn-only`).
4. Every `writes` path produced; no undeclared writes.
5. `$DATA_DIR/job-runs.jsonl` has started+finished; `rows` integer for new jobs.

## Contract tests (t31 CI subset)

```bash
cd campaign-os && python3 -m pytest tests/jobs/ -q
```

## Notes for Pi

- `retries` on JobSpecs is **inert until t35**.
- `seo_rankings` wraps `scripts/fetch_ubersuggest.py`; JS SERP scraper was never the producer.
- `taskmaster` consciously dropped (plan §4); `site_audit` is the +1 scope job.
- Class B calendar gate: seven consecutive live days required before Class B PASS.
