# Residual failure triage (t25-E)

Measured on `feat/campaign-os-p1a-tests` after t25 conftest (desk Python 3.14.7).

```bash
export DATA_DIR=/tmp/cos-scratch OPENCLAW_CREDENTIALS_DIR=/tmp/cos-creds
python3 -m pytest campaign-os/tests tests scripts/tests -q --tb=line \
  --ignore=campaign-os/tests/test_v2026_08_08_orphan_dna_placeholder.py
# -> 162 failed, 1401 passed, 16 skipped, 18 errors (pre caption_studio login fix)
```

Counts below are **FAILED+ERROR node lines** from that report (177). Pytest’s
headline `162 failed` folds some subfailures; use the table for triage, the
headline for suite health.

t25 did **not** fix these — it made auth-401 noise disappear so these classes
are legible. Owner tasks are follow-ups, not P1a.

| Class | Count | Owner |
|---|---:|---|
| Stale HTML / SPA string assertions | 78 | New P1/P2 ticket — largest backlog |
| `test_seo_audit_detail.py` (stale HTML + shape) | 29 | Own ticket; biggest single-file win |
| Other assertion / shape drift | 19 | Triage into contracts (feeds t31) or HTML tickets |
| Windsor fetcher drift | 11 | Windsor / Meta fetch ticket |
| Mac path hardcoded in tests (`/Users/fivefriday/...`) | 10 | t07 sibling — fix *tests* still hardcoding Mac paths |
| `ideas_column_dedup` setUp / stale HTML (ERROR) | 8 | Stale-HTML class reported as ERROR |
| Ubersuggest / SEO cross-cut drift | 6 | Ubersuggest + weekly-report SEO ticket |
| Stale payload-shape KeyErrors | 6 | Feeds t31 (contract tests) |
| Generation / meme / image router drift | 4 | Generation routes ticket |
| Calendar schedule IndexError / empty fixture | 2 | Calendar lane (leave free; not gated by CI allowlist) |
| Theme token / raw hex assertions | 2 | Theme tokens ticket |
| auth-401 subprocess (caption_studio `python -c`) | 2 | **Closed in P1a follow-up** — explicit `POST /login` in subprocess |
| **Sum** | **177** | |

### Intentionally not in this table
- Playwright / live-network walks: still ignored or off-allowlist; do not add Playwright to CI in P1a.
- Pillow / 3.14 `utcnow` desk noise: CI is 3.12 + installs `campaign-os/requirements.txt`.

### Re-check after caption_studio fix
Post-fix desk re-run: **160 failed, 1403 passed, 18 errors**; auth-401 class → **0**;
`401` lines in `--tb=line` output → **0**.

### Re-check after t27 data-gate isolation (2026-09-11 rerun)
Allowlisted writers no longer leave tracked `data/` dirty:
`test_freshness_sanity_range` restores `freshness.json` (+ detail);
`test_v2026_08_13_weekly_report_share` snapshots/restores `weekly-report.md`;
`test_v2026_08_13_html_export` uses `cos_anon=True` for format probes.
CI `git diff --quiet -- data/` after allowlist → **PASS**. `STRICT=1 smoke_boot` → **PASS**.
`check_lib_modules` → `missing_count: 0`.

### Allowlist ratchet (verify FAIL follow-up)
`tests/test_caption_studio_v2.py` added to `tests/ci-allowlist.txt` so the two
session-gated subprocess routes that previously returned 401 stay in the
blocking CI subset (was green after explicit `POST /login`, but off-list).
