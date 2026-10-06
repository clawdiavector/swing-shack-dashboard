---
name: krea-lab
description: >-
  Look up Krea model ids, input schemas and accepted resolutions before generating, and
  refine image prompts locally without spending production slots. Use whenever work touches
  Krea, Ideogram, Recraft, Flux or Campaign OS image generation — picking a model, debugging
  a 422, choosing an aspect ratio, adding reference images, or iterating on a prompt. Load
  BEFORE writing any generate call.
---

# Krea lab

Local, read-only lookup plus a cheap probe loop. The point: **never guess a model id, a
parameter or a resolution.** Every one of those is answerable for free in seconds.

Cost of guessing, measured 2026-10-05: three prod deploys, three one-shot slots, a lost day,
and the answer was still wrong. Cost of looking up: four minutes, zero credits.

## Setup (check once per session)

Token — `krea_mcp` finds it automatically in either:
- env `KREA_API_KEY` / `KREA_MCP_TOKEN` / `KREA_ACCESS_TOKEN` / `KREA_BEARER`
- `~/.krea/mcp.json` → `{"access_token": "..."}`

Native MCP tools (`mcp__krea__*`) come from `.mcp.json` in `swing-shack-dashboard-main`.
If they aren't loaded, fall back to the Python client:

```bash
cd "${CLAUDE_PROJECT_DIR:-.}"/campaign-os
python3 -c "import sys;sys.path.insert(0,'.');from _lib import krea_mcp as k;print(k.credentials_present())"
```

`list_models`, `get_model_schema`, `get_prompting_guide`, `list_tools` are **free**.
Only a *completed* generation costs credits.

## Rule 1 — look up the model id

Krea's real image ids are not the marketing names. Verified live 2026-10-05:

| Don't write | Real id |
|---|---|
| `ideogram/ideogram-4` | `ideogram/ideogram-4.5`, `ideogram/ideogram-4.5-precise` |
| `recraft/recraft-v4`, `recraft/recraft-v3` | `recraft/recraft-v4.1-flash` |
| — | `ideogram/ideogram-3` is correct |

A wrong id returns **422 "Unsupported image model"**. `list_models("image")` settles it.
Model ids change; re-check rather than trusting this table.

## Rule 2 — every schema is `additionalProperties: false`

One unexpected key = 422. Models want **opposite** payloads:

| Model | Sizing | Must NOT send |
|---|---|---|
| `ideogram-3` | `width` + `height` | `aspect_ratio` |
| `ideogram-4.5` | `aspect_ratio` enum + `resolution: "2K"` | `width`, `height` |
| `ideogram-4.5-precise` | neither — no size params | `width`, `height`, `aspect_ratio` |
| `recraft-v4.1-flash` | `aspect_ratio` enum + `resolution: "1K"` | `width`, `height` |

Branching on `"ideogram" in model` and applying one rule to all of them is the bug that
produced 422s for a day. Always `get_model_schema(id)` first.

## Rule 3 — ideogram-3 takes a fixed resolution allowlist

Its schema claims width/height 512–8192. **That is not true.** It accepts a fixed set at
roughly 1.0 MP and rejects everything else, including correct ratios:

| Aspect | Accepted |
|---|---|
| 1:1 | 1024×1024 |
| **4:5** | **896×1120** |
| 3:4 | 864×1152 |
| 2:3 | 832×1248 |
| 9:16 | 768×1344 |
| 5:4 | 1120×896 |
| 4:3 | 1152×864 |
| 3:2 | 1248×832 |
| 16:9 | 1344×768 |
| 2.4:1 | 1536×640 |

Rejected despite being correct 4:5: 1024×1280 (too big), 960×1200 (too big), 800×1000 (too
small). It is an allowlist, not a formula.

**`campaign-os/_lib/krea_mcp.py` → `_KREA_ASPECT_PIXELS` is wrong for every aspect except
1:1 and 2.4:1.** Check it still is before trusting it.

**Recraft v4.1-flash has no 4:5** — its enum is 1:1, 4:3, 3:2, 16:9, 3:4, 2:3, 9:16. Use 3:4
for portrait collage, or route to Ideogram.

## Rule 4 — probe before you spend

A rejected submit generates nothing and costs nothing. An accepted submit starts a job —
cancel it immediately if you only wanted to validate the payload.

```python
try:
    r = k.image_generate(PROMPT, brand="stick", model=MODEL,
                         aspect_ratio="1:1", background_plate=True,
                         extra={"width": W, "height": H})
    jid = (r.get("structuredContent") or {}).get("job_id") or r.get("job_id") or ""
    print("OK", jid);  k.cancel_job(jid)        # validating only — don't let it run
except Exception as e:
    print("REJECTED", str(e)[:120])             # free
```

`background_plate=True` skips brand-bible enrichment so you test the exact prompt you wrote.
Bisect one variable at a time: size, then prompt, then model.

## Capabilities worth reaching for

| Want | Parameter | Where |
|---|---|---|
| Repeat a look exactly | `seed` | ideogram-3, ideogram-4.5 |
| Match existing brand posts | `style_images` (url + `strength` −2…2) | ideogram-3 |
| Reference / edit from images | `image_urls` (≤5) | ideogram-4.5 |
| Masked inpainting | `image_url` + `mask_url` | ideogram-4.5-precise |
| Stop Ideogram rewriting your prompt | `skip_prompt_expansion: true` | ideogram-4.5 |
| Longer prompts | `prompt` maxLength 10000 | ideogram-4.5 |

Campaign OS's router **drops reference images before the Krea branch runs**
(`image_gen_router.py`, `reference_dropped`). Reference-driven generation needs that changed
first — the model supports it, the pipeline does not.

Krea's MCP exposes ~32 tools; `krea_mcp.py` wires about nine. `list_tools()` shows the rest.

## Prompt quality

Model and payload only get a render to happen. Whether it's *good* is a separate standard:
`swing-shack-dashboard-main/docs/plans/oneshot-prompt-composer/benchmark.md` — gold set,
ten-dimension rubric, and the hard constraints that fail rather than score.

## Related

- `campaign-os` — ops hub, jobs, prod health
- `campaign-os-template` — deterministic PIL templates measured from reference images (no AI
  on pixels); the right tool when the look must be exact rather than generated
