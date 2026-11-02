---
name: brand-voice-truth
description: >-
  Write captions and headlines the way Herman (CEO) wants each brand to sound: his
  rules first, the brand bible next, the Instagram audit as evidence. Load BEFORE
  writing any caption, headline, CTA, script or ad copy for Stick, Swing Shack or
  Bag Drop, and before trusting voice/, copy/ or bible-visual.json.
---

# Brand voice — what Herman wants, then what the feed shows

## Herman's rules come first (email, 31 Oct 2026)

Herman Kriel is the CEO. Christelle calls these rules gold. Apply all five before
writing a word, and never trade one away for something the feed does.

1. **The brand bible beats the feed, always.** "Old doesn't mean incorrect." The
   Instagram audit is evidence of what works, never the authority. Aim at the
   goal, balance it with the feed, and keep pushing the boundaries.
2. **Never call Stick or Swing Shack a "golf shop".** It puts the reader in the
   wrong place. Stick is a fitting studio and workshop in Paarl. Swing Shack is an
   indoor golf venue in Johannesburg (TrackMan, fitting, coaching). Both bibles ban
   the phrase, so `caption_lint` fails it.
3. **Stick winks, especially in video.** Facts about gear stay level and dry. The
   human side of "the world's most gloriously frustrating game" gets plenty of
   winks. Apparel splits the same way: quality claims stay straight, how it makes
   you feel gets a lot of winks.
4. **Swing Shack can be lighthearted.** The goal is engaging content. Don't hold a
   line back because it's fun.
5. **Sign-offs.** Stick closes on `Better begins here.` Swing Shack closes on
   `Keep Swinging` (Herman: it "has always been" the closing line, even though the
   feed used it once in 789 captions). Both are required last lines in the bibles.

His rules sit beside Christelle's standing ones: the joke never lands on the
golfer, confident not needy, no number without a source.

Full notes: wiki `decisions/herman-tone-feedback-2026-10-31`. Tone guides:
Stick https://claude.ai/artifact/4QHZCmQZf4JvoUGqJjyqoQ, Swing Shack
https://claude.ai/artifact/JnPh2zio2NboUbLZq88nFM.

## What the feed shows (evidence, not authority)

The copy files in `data/brand-directory/<brand>/voice/` and `copy/` drift from both
the bible and the feed. The audit below shows habits worth keeping, gaps worth
pushing, and lanes the old files missed. Where it disagrees with the bible or
Herman, they win.

Evidence: `data/brand-directory/<brand>/feedback/instagram-audit.json`.
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
