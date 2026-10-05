---
description: Probe the specs this repo drifts on and report what is actually true
allowed-tools: Bash(python3 campaign-os/scripts/verify_specs.py:*), Bash(git diff:*), Read, Grep, Edit
argument-hint: "[substring filter, e.g. krea | drive | archetypes]"
---

## Why this exists

Specs in this repo drift from reality silently and nothing checks. Six were
found wrong in a single day on 2026-10-05 by probing live; a seventh — the
one-shot image path routing to `ideogram/ideogram-4`, a model id that does not
exist upstream — was found by this command on its first run.

Every check is free. No image is generated, no credits are spent, nothing is
posted. Run it before trusting a model id, a resolution, a scrim value, a
template budget or a Drive folder.

## Run it

```bash
python3 campaign-os/scripts/verify_specs.py
```

Filter to one area with `$1` when given: `--only krea`, `--only drive`,
`--only archetypes`, `--only templates`. `--json` emits a machine-readable
report. Exit status is the number of failures, so a job can gate on it.

## What it checks

| Check | Asserts |
|---|---|
| `krea.reachable` | the endpoint accepts the token in `~/.krea/mcp.json` |
| `krea.model_ids` | every model id the repo routes a generate call to exists in `list_models` |
| `krea.aspect_pixels` | `_KREA_ASPECT_PIXELS` is internally consistent and 4:5 normalises |
| `archetypes.load` | every brand's `archetypes.json` parses; renderers have a canvases block |
| `archetypes.declared_budget` | copy filled to each zone's own `max_lines × max_chars_per_line` still composes |
| `templates.render` | every archetype with a template pack composes to a real PNG |
| `ss-service-promo.partner_logo` | the partner-mark zone the real Services posts show is present |
| `brand_dna.city` | `build_system_message()` does not assert one brand's city onto another |
| `image_gen_router.references` | reference image bytes reach the payload instead of being dropped |
| `audit_social.reels` | reels and video get their own metric set, not the image one |
| `drive.roots` | each brand's canonical Drive root lists and still holds imagery |
| `drive.map_names_roots` | `campaign-os-map` names the parent share folder and every id in `BRAND_PUBLIC_ROOTS` |
| `drive.manifest_matches_disk` | manifest entries correspond to files that exist |

## Reading the output

- **FAIL** is a claim in the repo that reality contradicts. Quote the `actual:`
  line when reporting it — it carries the measured numbers.
- **skip** means the check could not run (missing font, unparseable upstream
  response). A skip is not a pass; say which and why.
- A check that fails because *the check* is miscalibrated is a bug in
  `verify_specs.py`, not a finding. Three were on the first run: measuring
  `max_lines` at max font instead of min, calling the reference-injection helper
  positionally, and filling zones with copy that did not match their shape. Fix
  the check and re-run before reporting anything.

## After a run

Report the failures with their measured numbers, and say plainly which ones you
fixed and which you left. Do not fix a `declared_budget` or `char budget`
failure by guessing new numbers — changing a wrap width changes the layout, so
those get re-measured against golden renders with the `campaign-os-template`
skill. Dead model ids, wrong cities and dropped references are safe to fix
directly.
