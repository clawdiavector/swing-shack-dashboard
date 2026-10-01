# Creative one-shot Phase 1 — ready for testing

**Date:** 2026-10-01  
**Job:** `job-20261001-cos-oneshot-prompt-ready-for-testing`  
**Run:** `20261001T180543-ready-for-testing-249458`  
**Branch:** `feat/cos-oneshot-prompt`  
**Base:** `integrate/campaign-os-brand-lanes-v1`  
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/feat/cos-oneshot-prompt`

## Commit under test

Record the tip after this handoff lands (handoff commit may follow the feature commit):

- **Feature commit:** `b87d4dba7f5b30e4ac9817c2e134f25e17457903` — `feat(creative): Phase 1 one-shot prompt pipeline cleanup`

## Verification (worker)

From `campaign-os/` with bundled data:

```bash
export BUNDLED_DATA_DIR=<worktree>/data DATA_DIR=$(mktemp -d) COS_JOB_TOKEN=dev-token
python3 -m pytest \
  tests/test_creative_oneshot_wire_prompt.py \
  tests/test_brand_visual_lint.py \
  tests/test_image_pipeline_p2_provider.py \
  tests/test_p0_brand_context.py::test_compose_prompt_section_order_and_length \
  -q
python3 ../scripts/lint_brand_visual.py <worktree-root>
```

**Result:** 19 passed; `stick` / `bag-drop` / `swing-shack` lint ok.  
Two unrelated failures remain in `test_p0_brand_context.py` (Instagram/Facebook platform spec defaults) — pre-existing on base, not introduced by this branch.

## Inspect a composed prompt (no image generation)

Phase 1 adds **`wire_prompt`** (provider-bound prose, no `[SECTION]` headers) alongside unchanged **`master_prompt`** (labeled sections for UI and `/api/creative/compile`).

### Stick background-plate fixture (matches pytest)

Same job string as `test_stick_wire_prompt_has_measured_hex_no_section_headers`:

```bash
cd campaign-os
export BUNDLED_DATA_DIR=<worktree>/data
python3 - <<'PY'
import json
from _lib.creative_director import compose_prompt

job = (
    "Flat navy gradient background plate for a Stick coaching poster, "
    "no people, no text"
)
result = compose_prompt(brand_id="stick", job=job)
print("=== wire_prompt (sent to providers) ===")
print(result["wire_prompt"])
print("\n=== master_prompt (UI / labeled) ===")
print(result["master_prompt"])
print("\n=== negative_prompt ===")
print(result["negative_prompt"])
print("\n=== meta ===")
print(json.dumps({
    "wire_len": len(result["wire_prompt"]),
    "master_len": len(result["master_prompt"]),
    "neg_len": len(result["negative_prompt"]),
    "has_hex": "#073C52" in result["wire_prompt"],
    "sections": [s["key"] for s in result["sections"]],
}, indent=2))
PY
```

**Expect:** `#073C52` in `wire_prompt`; no `[` in `wire_prompt`; `NEGATIVE` only in `master_prompt`, not in `wire_prompt`; `wire_len` ≤ 1200.

### Labeled “fixture” via pytest (Swing Shack TrackMan)

Prints the historical composed prompt used in P0 brand context tests:

```bash
cd campaign-os
export BUNDLED_DATA_DIR=<worktree>/data
python3 -m pytest tests/test_p0_brand_context.py::test_compose_prompt_section_order_and_length -s -q
```

### HTTP (local dev, port from job file)

Job runtime web port: **3622**. Start Flask with `DATA_DIR` scratch + `COS_JOB_TOKEN` set, then:

```bash
curl -sS -X POST "http://127.0.0.1:3622/api/creative/compile" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $COS_JOB_TOKEN" \
  -d '{
    "brand_id": "stick",
    "job": "Flat navy gradient background plate for a Stick coaching poster, no people, no text"
  }' | python3 -m json.tool
```

Response includes `master_prompt`, `wire_prompt`, `negative_prompt`, and `sections`.

## Scope reminder

Phase 1 only — prompt pipeline cleanup. No one-shot routing, calendar/review UI, or live Krea/OpenRouter generation in this job.

## Push

Branch pushed to `origin/feat/cos-oneshot-prompt` after verify PASS (feature + handoff commits).
