---
name: brand-voice-truth
description: >-
  Write captions and headlines in the voice a brand actually uses, not the one its
  copy bible claims. Load BEFORE writing any caption, headline, CTA or ad copy for
  Stick, Swing Shack or Bag Drop, and before trusting voice/, copy/ or
  bible-visual.json. Carries the measured findings from the full Instagram audit.
---

# Brand voice — what the feed actually says

The copy bibles in `data/brand-directory/<brand>/voice/` and `copy/` drift from the
real feed, and prompts read the bible — so they inherit a voice the brand does not
use. **When the audit and the bible disagree, the audit wins.**

Source of truth: `data/brand-directory/<brand>/feedback/instagram-audit.json`.
Regenerate it with `/audit-social <brand>`.

## Stick — measured over all 261 posts

Counted directly from the audit on 2026-10-06; 258 of the 261 posts carry a caption.

| Finding | Count | Why it matters |
|---|---|---|
| `"Better begins here."` appears | **173 / 258** | Appears in **no** brand file — not `copy/ctas.md`, not the headline bank |
| …and actually **closes** the caption | **121 / 258** | The sign-off is the house move; the other 52 use it mid-caption |
| Mentions fitting | **39 / 258** (15%) | The bible is ~100% fitting and TrackMan. The feed is not |
| Says "available at stick" | **36 / 258** | Product-arrival posts are a major lane the bible ignores entirely |
| Asks a question | **6 / 258** | For a brand whose voice is built on provocation. A real gap, not a rule |
| Mentions apparel / "bunny" | 3 / 14 | **No apparel vocabulary exists in the bible at all** |

### What this means when you write

- **Close with "Better begins here."** unless there is a reason not to. It is the
  single most consistent thing the brand does, and it is undocumented.
- **Do not write everything as a fitting post.** Product arrivals are a first-class
  lane. "available at stick" is the idiom.
- **Apparel has a voice and it is only on Instagram.** The register is playful and
  a little arch — the Psycho Bunny drop ran "The Bunny has landed. A little too
  good at looking good." Nothing in `voice/` will tell you this.
- **Questions are underused, not banned.** Six in seven months is a gap worth
  exploiting deliberately, not a convention to preserve.

## Known-stale brand files

- `bible-visual.json` is still `confidence: draft`, and its `text_policy` reads
  "no model-rendered text" — the opposite of what one-shot posts need. Do not treat
  it as settled.
- `brand_dna.build_system_message()` once called every brand "a premium indoor golf
  studio in Johannesburg, SA". Stick is a fitting studio, workshop and retailer in
  **Paarl, Western Cape**. Fixed, but old generated copy may still carry the error.

## Before you trust a number here

Re-count it. Every figure above came from one command against the audit JSON, and
the audit is regenerable:

```bash
python3 -c "
import json
d=json.load(open('data/brand-directory/stick/feedback/instagram-audit.json'))
caps=[p.get('caption') or '' for p in d['posts']]
caps=[c for c in caps if c]
print(len(caps), 'captions')
print(sum('Better begins here' in c for c in caps), 'contain the tagline')
"
```

Two figures in circulation are **wrong**: "closes 173 of 261" (it appears in 173,
closes 121) and "39% are product arrivals" (36 captions, 14%, say "available at
stick" — the 39% figure has no derivation anyone has reproduced). Prefer the table.

## Related

`campaign-os-map` for what exists · `/audit-social` to regenerate · `/render-post`
to put the copy on a measured template rather than describing it to a model.
