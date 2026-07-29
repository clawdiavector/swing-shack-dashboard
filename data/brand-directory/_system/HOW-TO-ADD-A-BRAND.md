# How to add a brand to the directory

Use this checklist when adding a new brand (Stick and Bag Drop count too).
The image + copy generators depend on these slots being filled.

## 1. Create the folder

```bash
mkdir -p data/brand-directory/<brand-id>/{images,copy,voice,visual-spec,palette,typography,archetypes,examples}
```

## 2. Write `README.md`

One page. Plain language. Include:

- **What this brand is** (1-2 sentences — not marketing copy, a literal description)
- **Who it is for** (audience, in concrete terms)
- **What it is not** (anti-positioning — keep this short)
- **Voice id reference** (`data/voice_bible.json#voices/<brand-id>`)
- **Primary + accent colour** (hex)
- **Current state** (what's filled, what's still TODO)

## 3. Fill the nine slots (in order of generator-priority)

| Slot | Generator uses it for | Minimum viable |
|------|----------------------|----------------|
| `voice/tone-rules.md` | copy tone | 4 tones (educational, confident, funny, etc.) |
| `voice/do-say-dont-say.md` | copy vocabulary | at least 10 don't-say entries |
| `palette/brand.json` | image palette | `{"primary": "#hex", "accent": "#hex", "neutral_dark": "#hex", "neutral_light": "#hex"}` |
| `visual-spec/archetypes.json` | image layout | 1 named archetype with full layout spec |
| `copy/ctas.md` | CTA selection | 3 hard + 3 soft CTAs |
| `typography/fonts.json` | headline rendering | 1 font family with weights |
| `copy/headlines.md` | headline bank | 5 headlines tagged by tone/pillar/intent |
| `examples/good.md` | reference | 1 annotated example |
| `images/` | asset source | empty OK until Drive is wired in |

After step 5 (archetypes.json), the image generator can start producing brand-shaped
output. Before step 3 (palette), it falls back to generic golf imagery.

## 4. Re-run the indexer

```bash
python -m campaign-os._lib.brand_indexer
```

This regenerates `_system/brand-index.json`. The dashboard Brand surface will
pick up the change immediately on next load.

## 5. Verify readiness

Hit `/api/brand-directory/<brand-id>` in the live app. The `ready` field flips to
`true` once the four gate files exist. Until then, generated copy/images carry a
`BRAND: PARTIAL` tag so review catches them.
