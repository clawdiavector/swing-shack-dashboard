# P1a t25 baseline / after (desk evidence)

Branch: `feat/campaign-os-p1a-tests`  
Python: **3.14.7** (desk). CI gate uses **3.12** — re-measure there after Kyle pushes.  
`DATA_DIR` / `OPENCLAW_CREDENTIALS_DIR`: scratch under `/tmp` (never commit under `data/`).

## Command (both trees, plan §6.2 / verify V2–V3)

```bash
export DATA_DIR=/tmp/cos-scratch OPENCLAW_CREDENTIALS_DIR=/tmp/cos-creds
mkdir -p "$DATA_DIR" "$OPENCLAW_CREDENTIALS_DIR"
python3 -m pytest campaign-os/tests tests scripts/tests -q --tb=line \
  --ignore=campaign-os/tests/test_v2026_08_08_orphan_dna_placeholder.py
# V3: 401 lines among failure traceback lines must be 0
#   pytest ... --tb=line | grep -E ':[0-9]+: ' | grep -cE '\b401\b'  → 0
```

## Counts

| | baseline (pre-conftest, plan) | after t25 (this branch, re-measured) |
|---|---:|---:|
| passed | 1,174 | **1,403** |
| failed | 433 | **160** |
| errors | 25 | **18** |
| skipped | 16 | **16** |
| auth-401 on `--tb=line` failure lines | ~190 (audit) | **0** |

SHA at measurement: `687e7c94b9754c4037210edb2c79d0a3c470b4eb` (suite numbers; tip may be docs-only ahead). Desk Python 3.14.7.

Residual **non-auth** failures are named in [`RESIDUAL-TRIAGE.md`](./RESIDUAL-TRIAGE.md)
(t25-E). t25 does not fix them — it made them legible.

## CI allowlist (t27-D)

```bash
xargs -a tests/ci-allowlist.txt python3 -m pytest -q
# then: git diff --quiet -- data/
```

Desk re-measure: **905 passed**, 16 skipped, exit **0**, `data/` gate **PASS**.

## Scope note (`t25_scope`)

Fixture authenticates via Flask `POST /login` + session cookie only.
No `COS_JOB_TOKEN` / Bearer in `campaign-os/tests/conftest.py`.
