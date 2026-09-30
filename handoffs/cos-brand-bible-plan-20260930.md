# Campaign OS brand bible for captions and poster text — implementation plan

**Date:** 2026-09-30
**Job:** `job-20260930-cos-brand-bible-plan` (Claude, plan tier, **read-only**)
**Run:** `20260930T210832-plan-07938b`
**Worktree:** `/home/kyle/Work/worktrees/swing-shack-dashboard-main/plan/cos-brand-bible`
**Branch:** `plan/cos-brand-bible` @ `3e9d2821`
**Declared base:** `integrate/campaign-os-brand-lanes-v1` @ `480f4a44`
**Manifest:** agent-control `manifests/plan-20260930-cos-brand-bible.yaml`
**Ticket:** `ticket-20260930-cos-brand-bible`

**No product code edits were made by this job.** `git status --porcelain` shows only the
untracked job files (`.agent-job.json`, `.agent-job/`) plus this handoff.

---

## 0. Grounding — read this before anything else

### 0.1 This worktree is BEHIND its own base by one commit, and that commit is the whole first half of the work

```
git rev-parse HEAD                                          → 3e9d2821
git rev-parse origin/integrate/campaign-os-brand-lanes-v1   → 480f4a44
git log --oneline HEAD..origin/integrate/campaign-os-brand-lanes-v1
→ 480f4a44 feat(caption): P11 copy contracts, bans, and alignment gates
```

`480f4a44` already landed:

| Path | Delta at `480f4a44` |
|---|---|
| `campaign-os/_lib/caption_copy_contract.py` | **new, 271 lines** — the shared phrase gate module already exists |
| `campaign-os/tests/test_caption_copy_contract.py` | **new, 96 lines**, 6 tests |
| `campaign-os/_lib/p11_context_engine.py` | +93 net — `copy_contract` layer, `banned_terms` in prompt, vague-data fact check, two new pipeline gates |
| `campaign-os/_lib/jobs/layer5/draft_assets.py` | +4 — passes `template_id` / `post_type` / `lodge_title` into the pipeline |
| `campaign-os/_lib/jobs/layer5/image_draft_context.py` | +1 — `template_id` into calendar lineage |
| `data/brand-directory/stick/voice/do-say-dont-say.md` | +1 — `❌ "data shows" / "research shows"` |

**Implement must start by rebasing / branching `feat/cos-brand-bible` off `480f4a44`, not off this
worktree's `3e9d2821`.** Everything in §3–§5 below is written against `480f4a44`; line numbers are
`480f4a44` line numbers (that file is 2681 lines, not the 2604 in this worktree).

### 0.2 The pytest suite does not currently collect cleanly on the base

```
python3 -m pytest --collect-only -q
→ 2496 tests collected, 1 error in 2.79s
→ ERROR campaign-os/tests/jobs/test_compose_template_wiring.py
→ ImportError: cannot import name 'enrich_compose_template_fields' from '_lib.archetypes'
```

This is **pre-existing** and unrelated to this ticket (the worktree is byte-clean). The error
**interrupts the whole run** ("Interrupted: 1 error during collection"), so a bare `pytest`
aborts before executing anything. Implement and verify must run with
`--ignore=campaign-os/tests/jobs/test_compose_template_wiring.py` (or
`--continue-on-collection-errors`) and must not be marked FAIL for it. Do not fix it here —
it is outside the manifest `paths`.

### 0.3 The "v3 bible" is Stick only

| File | First line | Bytes |
|---|---|---|
| `data/brand-directory/stick/bible-source.txt` | `STICKFull Brand BibleDraft v3` | 13,991 |
| `data/brand-directory/swing-shack/bible-source.txt` | `SWING SHACKFull Brand Bible … Draft v1` | 9,531 |
| `data/brand-directory/swing-shack/workbook-source.txt` | `CAMPAIGN OSFULL BRAND BIBLE WORKBOOK` | 145,497 |

Both `.docx` sources named in the manifest exist and are already extracted into those `.txt`
files, so **implement does not need to open or commit the docx**:

```
/home/kyle/Downloads/STICK Brand Bible .docx                    34,074 bytes
/home/kyle/Downloads/Campaign_OS_Full_Brand_Bible_Workbook.docx 95,111 bytes
```

Say "v3" only about Stick. Swing Shack's own bible is Draft v1; its authority for copy comes
from the workbook §D/§E plus `knowledge.json verified_facts`.

### 0.4 Measured state of the gate, on the base branch

`caption_copy_contract.py` extracted to a scratch dir and exercised directly:

| Input | Brand | Result today |
|---|---|---|
| `Data shows fitting helps.` | stick | **blocked** `forbidden_phrase:data shows` |
| `Join our membership today.` | swing-shack | blocked `off_topic:membership` (template contract) |
| `Join the club and get fitted.` | **stick** | **PASSES — this is the gap** |
| `Join the club. Four practice sessions a month.` | swing-shack | passes (correct, see §3.1) |
| `Club fitting at Stick. Fit first. Buy second.` | stick | passes (correct) |
| `FREE CLUB ASSESSMENT` | swing-shack | passes (correct) |
| `vague_data_claim_in_text("TrackMan shows attack angle")` | — | `None` (correct) |
| `vague_data_claim_in_text("The ball speaks. Data confirms.")` | — | `None` (correct — see §3.6) |

So of Kyle's four acceptance examples, **three already hold** and exactly one is missing:
a Stick-scoped `join the club` ban.

### 0.5 The markdown side of the gate is dead code in production, and garbage even locally

`_extract_banned_terms` (p11 `480f4a44:838`) reads
`_brand_dir(brand_id)/voice/do-say-dont-say.md`, and `_brand_dir` (`:38`) is
`DATA_DIR/brand-directory/<brand>` with **no bundled fallback**. Measured:

```
DATA_DIR=/data/campaign-os python3 -c "…"
stick        brand_dir=/data/campaign-os/brand-directory/stick  exists=False
             banned=[]  required=[]  rules_excerpt_len=0
swing-shack  same
```

`Dockerfile` does `COPY data/ /app/data/` and `fly.toml` sets `DATA_DIR = "/data/campaign-os"`
(a volume). `app.py` `_seed_*` (around `:26082`) seeds only
`feedback/*.json`, `calendar_config.json`, `integrations/*` — **never `voice/*.md`,
`knowledge.json` or `product-library.json`**. Nothing else mirrors `brand-directory` into
`DATA_DIR` (grepped). So in the deployed container:

* `_load_brand_knowledge` works (it falls back to `_bundled_data_dir()` = `/app/data`), so
  `knowledge.json voice_rules.dont_say` **is** enforced by `_check_brand`.
* `_load_brand_rules`, `_extract_banned_terms`, `_extract_required_terms` and the
  `product-library.json` read all resolve under the empty volume and return nothing.
  The markdown do-say/tone/punctuation rules **never reach the prompt** (`rules_excerpt`,
  `tone_rules_excerpt`, `punctuation_excerpt` are all `""`).

Note also `_bundled_data_dir()` (`:30`) reads `globals().get("_BUNDLED_DATA_DIR")` of the **p11
module**, and `app.py:33715` sets `_BUNDLED_DATA_DIR` in **app.py's** globals — nothing ever
assigns it on the p11 module — so it always returns the literal `/app/data`. That happens to be
right inside the container and wrong everywhere else.

And when the file *is* found (`DATA_DIR` pointed at repo `data/`), the parser produces
unusable entries, because it strips only the leading `- ❌ "` and keeps the closing quote plus
the em-dash rationale:

```
stick    → ['LOL" / "LMAO" — text-speak is not Stick voice',
            'Emojis as filler (one emoji max per post)',
            'We\'d never" / "We\'d totally" — too informal',
            'Bro" / "Fam" — Stick is not bro-voice', '—']
swing-shack → ['World-class" — banned unless verified',
            'Whether you\'re a beginner or a pro" — we are performance, not beginner',
            'Take your game to the next level" — generic stock phrase', … 9 entries]
```

`_check_brand` (`:1990`) matches with `bad.lower() in candidate.lower()`, so none of those
strings can ever match real copy. Two further parser defects measured:

* Stick's `❌ Any reference to other brands (Bag Drop, Swing Shack) unless Christelle approves`
  is exactly **80 chars** after cleaning and is dropped by `if … len(clean) < 80`.
* `_extract_required_terms` (`:860`) scans the `## Do say` section for lines starting `✅`, but
  both brands write plain `- ` bullets there and put `✅` under `## Numbers discipline`.
  Measured `required = 0` for both brands, so `optional_related_facts.all_terminology` is
  always empty.
* `## Numbers discipline` `❌` lines (`No fake TrackMan numbers`, `No fake fitting outcomes`)
  are excluded because the section walker resets on any `## `.

`knowledge.json` has a matching defect: `stick.voice_rules.dont_say` contains the literal
prose entry `"Bag Drop / Swing Shack (cross-brand text banned unless approved)"`, which
`_check_brand` treats as a substring to match and therefore never fires.

### 0.6 Poster text is generated, then never phrase-checked

`run_caption_pipeline` (`:2244`) runs every gate against `c["body"]` only:

* `_check_brand(c["body"], …)`, `_check_fact(c["body"], ctx)`, `check_copy_contract(c["body"], ctx)`.
* `_check_locale` (`:1650`) is the **only** check that reads `copy_package["poster_hook"]` and
  `["cta_line"]`, and it only tests US spellings, US hype, and `$`-currency, plus soft
  length warnings.
* `check_poster_caption_alignment` reads the hook but only for equipment-family drift.

So the hook and CTA that land **on the image** are never tested against banned phrases, the
`membership_offered` rule, or the fact rules. They flow
`copy_package` → sidecar → `poster_copy.resolve_poster_hook` / `resolve_poster_cta` →
`compose_visual_copy.visual_copy_for_archetype` → render, ungated.

The deterministic fallbacks in `compose_visual_copy.py` are ungated too, and three of them are
brand-wrong or unverified:

| `compose_visual_copy.py` | String | Problem |
|---|---|---|
| `:145` | `Book your free club assessment` | asserts **free** with no verified offer; `swing-shack/voice/do-say-dont-say.md` says `"free" — only for verified free offerings (never invented)` |
| `:147` | `Book your free swing assessment` | same |
| `:149` | `Book your free assessment` | same |
| `:82` | `Golf, made simpler.` | Stick fallback tagline. "Simpler" appears nowhere in the v3 bible; the master line is `Better Begins Here` |
| `:76` | `Brand-agnostic fittings guided by data and science.` | "guided by data and science" is Swing Shack register, not Stick's |
| `:140` | `_service_cta` | takes `brand_id` but never branches on it — Swing Shack posters get Stick's CTA vocabulary |

`_check_sidecar` in `campaign-os/_lib/jobs/layer5/asset_qc.py:67` does call
`_extract_banned_terms`, but only against `caption` — never the compose fields — and given
§0.5 it is a no-op in production anyway.

### 0.7 `bible-intelligence.json` already has a contract, and it cannot hold copy rules

`campaign-os/_lib/brand_bible.py` (227 lines) already defines the file this ticket names:

```python
def _bible_path(brand_id): return _data_root()/"brand-directory"/brand_id/"bible-intelligence.json"
STRUCTURED_FIELDS = ["voice","visual_language","colours","typography","logo_rules",
                     "photography","product_fidelity","positive_prompts","negative_prompts",
                     "creative_properties","approved_examples","rejected_examples"]
def retrieve_for_job(brand_id,*,lane="product",job_type="apparel",product_category=""): …
```

No brand has the file today (`find` → 0 hits), so `get_bible()` returns `None` everywhere.
Three consequences for implement:

1. **Do not invent a new schema.** Extend `STRUCTURED_FIELDS` and `retrieve_for_job` lanes.
2. Of the 12 fields, 11 are image-gen oriented and `voice` is a single free-text string.
   The workbook §D/§E copy system (voice-in-5-words, humour rule, approved CTAs, signature
   lines, banned phrases, messaging hierarchy) has **nowhere to go** without new fields.
3. `retrieve_for_job` has lanes `product` / `human` / `campaign` — there is **no `caption`
   or `poster` lane**. That lane is the "P11 retrieval slice" this ticket asks for.

Also: the only consumer today is
`campaign-os/_lib/jobs/layer5/image_draft_context.py:631` `_brand_bible_lineage`, which
records `available` / `last_updated` / `sorted(fields.keys())` into image lineage. Creating
the file **flips `available` from `false` to `true` and changes the `fields` list in image
lineage** — see §6 on verify tier.

`knowledge.json verified_facts` already carries part of the bible, and P11 cannot see it:
`_knowledge_facts_matching` (`:212`) walks only `services`, `products`, `product_brands`.
`verified_tagline`, `verified_promise`, `verified_internal_mantra`, `verified_archetype`,
`verified_quote`, `voice_constraints`, `tone`, `banned_fabrications` are **never retrieved**.

---

## 1. Sources, and what each may legitimately supply

| Source | Authority for copy | Use for |
|---|---|---|
| `stick/bible-source.txt` (v3) | **canonical** | Stick essence, promise/tagline, values, archetype, tone principles, personality never-list, mantra, litmus test |
| workbook §D **Voice and copy system** (Stick `@58383`, SS `@10013`) | **canonical** | voice-in-5-words, sentence length, humour rule, technical depth, slang, emoji policy, punctuation, signature lines, **banned phrases**, approved headlines, **approved CTAs**, not-us examples |
| workbook §E **Messaging hierarchy** | **canonical** | master message, ranked supporting messages, commercial + trust messages, seasonal messages |
| workbook §K product/service communication | canonical | how a product/service is introduced |
| workbook §L channel rules | **unusable** | all 7 rows per brand have `[FILL IN]` in the channel column (measured: 7 Swing Shack, 7 Stick, 7 Bag Drop). Per Kyle these stay empty — do not infer channel labels |
| workbook §F/G/H/I/J/M/N/R | out of scope | image gen, negative prompts, product fidelity — belongs in `bible-visual.json`, not this ticket |
| `swing-shack/bible-source.txt` (v1) | canonical | Swing Shack promise, values, personality never-list, mantra, litmus test |
| `knowledge.json verified_facts` | canonical, **already exists** | do not duplicate into `bible-intelligence.json`; reference by fact key |
| `voice_bible.json` | **demoted** | keeps `label`, `allowed_tones` shape, `hashtag_suggestions`; loses authority over personality/CTAs (§3) |

---

## 2. Target shape

```
bible-intelligence.json (new, per brand)         ← ingest, copy-system fields only
        │
        │  brand_bible.retrieve_for_job(lane="caption"|"poster")   ← retrieval slice
        ▼
p11_context_engine.build_generation_context()
        ├── GLOBAL_FACTS["bible"]  →  _build_llm_prompt system message
        └── copy_contract          →  unchanged
        │
        ▼
run_caption_pipeline  ── _gate_copy_package(brand_id, copy_package, ctx)  ← NEW, shared
        │                       body + poster_hook + cta_line
        ▼
copy_package ─ sidecar ─ poster_copy ─ compose_visual_copy
                                          └── gate_poster_text(...)       ← same module
```

One gate implementation in `caption_copy_contract.py`, two call sites.

---

## 3. Conflicts between the v3 bible / workbook and the current stores

Required deliverable. Each row states the authority, the conflicting store, and the resolution
implement should apply. **C1–C4 are the ones the verify job's PASS criterion depends on.**

### 3.1 C1 — "join the club" is banned for Stick and approved for Swing Shack

* **Stick v3 §1**: "not a country-club extension"; §3 purpose rejects "stuffy culture, legacy
  gatekeeping"; §10 Rebel "golf culture is no longer controlled by the old guard". Stick's
  workbook §D approved CTA list is `Book a fitting / Enquire / Find your fit / View product /
  Try it on / Visit us / Message to order / Ask us / Shop the drop / Get your spec done` —
  **no membership or club CTA**. `caption_copy_contract.build_copy_contract` already sets
  `membership_offered=False` for stick.
* **Swing Shack workbook §D approved CTAs explicitly include `"Join the club" — membership`**,
  and `bible-source.txt §1` is "South Africa's first and only true indoor golf club".
* **Resolution:** add `"join the club"` (and `"join the stick club"`, `"become a member"`) to
  `BRAND_FORBIDDEN_PHRASES["stick"]` **only**. Leave `swing-shack` empty. Do **not** add it to
  `GLOBAL_FORBIDDEN_PHRASES` — that would break a Swing Shack approved CTA. This is exactly
  Kyle's "Swing Shack does not inherit Stick 'not a club' rules".
* Phrase-scoped, so `club fitting`, `club assessment`, `FREE CLUB ASSESSMENT`, `indoor golf
  club`, `club heads` all stay legal. Verified by measurement in §0.4.

### 3.2 C2 — `voice_bible.json` tells Stick to be sarcastic and to belittle the golfer

| Field | Current `data/voice_bible.json` | v3 bible / workbook authority |
|---|---|---|
| `stick.personality` | `sarcastic, golf insider, calling out bad habits, meme-aware` | workbook §D voice in 5 words: **`Sharp, confident, direct, smart, rebellious`**; v3 §11 "sharp, modern, confident, informed, energetic, selective, culturally awake" |
| `stick.description` | `Sarcastic … Calls out bad habits … provokes thought with irony` | v3 §10 "**Not a punk brand.** Not an engineering robot" — Smart Rebel = Rebel + Sage |
| `stick.allowed_tones` | `["sarcastic","funny","confident","relatable","provocative"]` | workbook §D humour: **"Wry, confident — never clownish or gag-driven. Edge comes from attitude, not punchlines."** v3 §16 Don't: "posture", "sound bitter or hostile"; "The edge must feel like confidence, not resentment" |
| `stick.template_suffix` | `Not sure why you'd do it any other way.` | posturing — v3 §16 Don't |
| `stick.cta_default` | `Get fitted. Your game deserves better.` | not in the workbook's approved CTA list |
| `stick.cta_alternatives[2]` | `Book a fitting before your next round → swingshack.co.za` | **triple violation**: cross-brand (banned by stick's own `do-say-dont-say.md` and `ctas.md`), wrong domain (`knowledge.json verified_bookings_url` = `stickgolf.co.za/bookings/`), and not an approved CTA |
| `stick.template_prefix` | `🚩 Reality check:` | workbook §D emoji: "**Rare.** … **Never as substitute for personality**" — a fixed prefix emoji on every caption is the definition of a crutch |
| `swing-shack.personality` | `data-driven coach, confident, educational, no-nonsense` | workbook §D voice in 5 words: **`Warm, knowledgeable, witty, useful, confident`** — "warm" and "witty" are absent, "no-nonsense" is invented |
| `swing-shack.template_prefix` | `⛳ Here's the data-backed truth:` | §D emoji "Occasional and intentional… Never as a crutch"; and "the truth" trips `_check_fact` causal_terms (§3.6) |
| `swing-shack.cta_alternatives` / `ctas.md` soft CTA | `Your clubs deserve better than you.` | §D humour: "**never at the golfer's expense**"; Stick `verified_respect_the_player` = "Never use expertise to make the golfer feel stupid" |
| missing | — | Stick `Better Begins Here`, `Everything has to earn its place`, `Fit First. Buy Second.`; Swing Shack `Real Golf, Indoors.`, `The ball speaks. Data confirms. Feel seals the deal.`, `Golf is more fun when it makes sense` — **none of the master lines are in `voice_bible.json`** |

**Resolution:** §4.5. `voice_bible.json` stops being voice authority and becomes a thin
label/tone-enum/hashtag file; personality, CTAs and signature lines come from
`bible-intelligence.json`.

### 3.3 C3 — `stick/voice/tone-rules.md` contradicts the v3 bible, and contradicts `knowledge.json`

`data/brand-directory/stick/voice/tone-rules.md:3` opens:

> "The voice is **sarcastic, golf insider, calling out bad habits, meme-aware**. Stick is the
> meme side of Swing Shack."

Three-way conflict:

* **v3 bible** never mentions memes. §1 "It is not a simulator bar pretending to be serious";
  §8 positioning is "Modern golf performance retailer and culture brand"; §10 "Not a punk brand".
  Stick is a standalone brand, not a sub-brand's meme arm.
* **`stick/knowledge.json rules.voice_only`** already says the opposite:
  `"Cheeky and helpful, never sarcasm-as-punchline"`, and `verified_facts.tone` =
  `"Cheeky and helpful. Sharp, modern, confident, informed…"`. So `knowledge.json` is already
  aligned with v3 and `tone-rules.md` is the stale file.
* `tone-rules.md` `## Sarcastic (primary)`, `✅ "Your clubs deserve better than you."`, and
  `"The challenge must be something Swing Shack can deliver on"` all have to go.

**Resolution:** `tone-rules.md` is **outside the manifest's `paths` only in spirit** —
`data/brand-directory/stick/` **is** in scope, so implement may rewrite it. Minimum viable fix:
replace the `## Sarcastic (primary)` section with `## Wry (primary)` sourced from workbook §D,
delete the "meme side of Swing Shack" sentence and the two cross-brand lines. If implement
prefers to keep the diff tight, at minimum delete those three items and record the rest as a
follow-up — but the first sentence of the file is the one thing the verify job will read.

### 3.4 C4 — Swing Shack's own `do-say-dont-say.md` bans two things its bible asserts

| `swing-shack/voice/do-say-dont-say.md` | `bible-source.txt` (v1) |
|---|---|
| `❌ "Whether you're a beginner or a pro" — we are performance, not beginner` | §4 Mission: "Welcome every level — **from first-time beginners** to aspiring tour players — without condescension"; §10 Audience: "Golf enthusiasts of **all levels and abilities**"; §15: "**Not** a place where beginners are looked down on" |
| `❌ "World-class" — banned unless verified` | §4 Mission: "Give serious golfers a **world-class** performance hub" |

Both are real, and both are resolvable without contradiction:

* **"world-class"**: the workbook §D not-us list is explicit — `'World-class facility' — generic,
  says nothing specific`. So the bible uses it as *internal* mission language and the workbook
  bans it in *published copy*. Resolution: keep the ban, and mark the bible line
  `internal_only: true` in `bible-intelligence.json` so it is never retrieved into the caption
  lane.
* **"beginner or a pro"**: the banned item is the *stock phrase*, not the audience. Resolution:
  reword the entry to `❌ "Whether you're a beginner or a pro" — banned as a stock phrase, not
  as a policy. Swing Shack welcomes every level (bible §4, §10); say the specific thing instead.`
  This removes the apparent policy contradiction while keeping the phrase ban.

### 3.5 C5 — Stick and Swing Shack currently share soft CTAs verbatim

`stick/copy/ctas.md` soft CTAs `TrackMan doesn't lie.` and `Your clubs deserve better than you.`
are **byte-identical** to two of `swing-shack/copy/ctas.md` soft CTAs. Two brands with one
voice is the drift this ticket exists to stop.

* TrackMan itself is **legitimate for Stick** — workbook §E Stick trust messages:
  "TrackMan data in every fitting — real, explainable numbers". Do **not** ban it for Stick.
* `Your clubs deserve better than you.` violates "never at the golfer's expense" /
  `verified_respect_the_player` for **both** brands. Delete it from both `ctas.md` files and
  from `voice_bible.json`.
* Replace Stick's soft CTA bank from workbook §D approved lines:
  `Everything has to earn its place.` / `Fit first. Buy second.` / `This is why we stock it.`

### 3.6 C6 — the existing fact gate blocks both brands' own signature lines

`_check_fact` (`480f4a44:2015`) hard-fails on
`causal_terms = ["proves","guarantee","guarantees","guaranteed","the truth","nobody tells","the only way"]`
with a plain substring test. That kills:

| Blocked line | Where it is canonical |
|---|---|
| `The swing may lie, but the ball tells the truth.` | `swing-shack/knowledge.json verified_facts.verified_quote` (`verified_current`) |
| `The ball tells the truth. We just read it.` | workbook §D Swing Shack signature line |
| `⛳ Here's the data-backed truth:` | `voice_bible.json swing-shack.template_prefix` |

And `COMPARATIVE_CAUSAL_PATTERNS` (`:305`) `r"\bcosts?\s+you\s+\w+"` flags two approved lines:
`"Why this shaft? Because your current one is costing you 15 metres."` (Stick workbook §D
approved headline) and `"Off-rack clubs. The cost-saving that costs you strokes."`
(`swing-shack/voice/tone-rules.md` ✅ Provocative). Note the Stick one also asserts an
unverified `15 metres`, which `_check_fact` rule 3 independently rejects — that example should
not be promoted into `bible-intelligence.json` approved_headlines without a verified source.

**Resolution (narrow, do not widen the gate):** allow `the truth` when the candidate matches a
`signature_lines` entry retrieved from `bible-intelligence.json` for that brand — i.e. an
allowlist check before the `causal_terms` loop, keyed on the brand's own canonical lines. Leave
`proves` / `guarantee*` unconditional. Do **not** touch `COMPARATIVE_CAUSAL_PATTERNS`; instead
drop the "costing you 15 metres" headline from the ingest, and record the `tone-rules.md`
✅ example as a known-unenforceable case in the handoff rather than loosening the gate.

### 3.7 C7 — `data confirms` must stay legal while `data shows` stays banned

`GLOBAL_FORBIDDEN_PHRASES` contains `data shows` / `the data proves` / `research shows` /
`studies show` / `statistics show`. Swing Shack's `verified_promise` is
`"The ball speaks. Data confirms. Feel seals the deal."`

Measured: `vague_data_claim_in_text("The ball speaks. Data confirms.")` → `None`. **Correct
today. Do not "tidy" the list by adding `data confirms` or a `\bdata\s+\w+s\b` pattern.**
Add a regression test that pins this.

Also note `COMPARATIVE_CAUSAL_PATTERNS` has `r"\bthe\s+data\s+(proves|shows)"`, which requires
the leading `the` — but that list is only consumed by `_facts_to_grounded_claims`, and
`GLOBAL_FORBIDDEN_PHRASES` already catches the bare `data shows`. Measured drift confirming the
bare form is the one that actually escapes: `data/campaign-data.json` contains
`"Data shows what your eye cannot see — and that moment is the content."`

### 3.8 C8 — the em dash ban is violated by the files that teach it

`_check_brand` hard-fails on `"—"`, `restrictions.em_dash_banned = True`, and every
`do-say-dont-say.md` has an `## Em dash ban` section. Yet:

* `swing-shack/voice/tone-rules.md` ✅ Educational example contains **two** em dashes:
  `"Driver fittings isolate 4 variables — swing speed, attack angle, path, face — then match them."`
* `stick/knowledge.json verified_facts.verified_archetype.value` =
  `"Smart Rebel — Rebel + Sage combined…"` — an em dash inside a canonical fact that
  `canonical_block` puts in the prompt.
* `stick/bible-visual.json philosophy` = `"High-contrast insider commentary — black field…"`.

Per §0.5 the tone-rules excerpt does not currently reach the prompt in production, so this is
latent rather than live — but fixing §0.5 makes it live. **Resolution:** replace em dashes with
pipes/colons in `swing-shack/voice/tone-rules.md` and in the `verified_archetype` value while
implement is in those files. `bible-visual.json` is image-lane and out of scope.

### 3.9 C9 — `stick/knowledge.json cta_rules` is Takomo's, pointing at the wrong domain

```json
"cta_rules": { "source": "data/brand-directory/takomo/copy/ctas.md",
               "default_cta": "Build your 101T → swingshack.co.za/takomo", … }
```

Stick's default CTA is a Takomo product CTA on the Swing Shack domain, while the same file's
`verified_bookings_url` is `stickgolf.co.za/bookings/` and Stick's own `ctas.md` bans any CTA
mentioning Swing Shack. **Resolution:** set Stick `cta_rules.default_cta` to
`Book a fitting → stickgolf.co.za/bookings/`, move the Takomo CTAs under a
`product_brand_cta_rules.takomo` key, and re-source. (Takomo lives under
`data/brand-directory/takomo/`, which is **not** in the manifest `paths` — only the
`stick/knowledge.json` edit is in scope.)

### 3.10 C10 — `bible-visual.json` still describes Stick as sarcastic and meme-aware

`stick/bible-visual.json` `voice` = `"Sarcastic golf-insider voice; meme-aware; provokes thought
with irony…"`. This feeds `brand_dna` / `creative_director` / `template_gallery`, i.e. the
**image** lane. It is genuinely inconsistent with v3, but the manifest puts
"Krea/image negative prompts" out of scope and editing it would move this ticket into the
image-gen verify tier (§6). **Resolution: leave it. Record it as a follow-up ticket** so the
next image-lane job picks it up.

### 3.11 C11 — lower-severity notes, no action this ticket

* `swing-shack/voice/tone-rules.md` Educational: `"Never start with 'Did you know…' — that is
  Stick voice"`, yet `data/brand-directory/swing-shack/templates/did-you-know/` exists and
  `caption_copy_contract.TEMPLATE_COPY_CONTRACTS` has `ss-did-you-know`. Either the rule or the
  template name is wrong; the workbook §D does not settle it. **Ask Kyle** (§8).
* Stick workbook §L "Typical CTA" lists `Learn more` for Facebook and paid Meta, which
  `stick/copy/ctas.md` bans. §L is `[FILL IN]`-broken anyway (§1) — ignore.
* `swing-shack/voice/tone-rules.md` ✅ `"TrackMan shows attack angle within 0.5° in a 30-minute
  session."` is a specific unverified number and would be rejected by `_check_fact` rules 3 and
  6. Do not promote it into `approved_headlines`.

---

## 4. Implement decomposition — six edits

All paths below are inside the manifest's `paths` allowlist. **`campaign-os/_lib/poster_copy.py`
is NOT in the allowlist** — the poster slice must therefore land in `compose_visual_copy.py` and
`caption_copy_contract.py` only (§4.3). Branch `feat/cos-brand-bible` off `480f4a44`.

### 4.1 `data/brand-directory/{stick,swing-shack}/bible-intelligence.json` — new, 2 files

Populate the existing `brand_bible.py` contract, extended with a copy block. Keep the 12
`STRUCTURED_FIELDS` present (empty strings/lists where image-lane) so `get_bible_meta` and
`_brand_bible_lineage` keep working, and add:

```json
{
  "_schema": "https://campaign-os/brand-directory/bible-intelligence/v1",
  "brand_id": "stick",
  "version": "1.0.0",
  "confidence": "verified_current",
  "sources": [
    {"path": "data/brand-directory/stick/bible-source.txt", "label": "STICK Full Brand Bible Draft v3"},
    {"path": "data/brand-directory/swing-shack/workbook-source.txt", "label": "Campaign OS Full Brand Bible Workbook, STICK section D+E+K", "offsets": [50831, 96297]}
  ],
  "copy_system": {
    "voice_in_5_words": ["sharp","confident","direct","smart","rebellious"],
    "sentence_length": "Short to medium. One idea per sentence. Get to the point.",
    "humour": "Wry, confident. Never clownish or gag-driven. Edge comes from attitude, not punchlines.",
    "technical_depth": "High where it serves the reader. Low where it distracts.",
    "emoji_policy": "Rare. Only when tone genuinely needs it. Never as a substitute for personality.",
    "punctuation": "Sentence case headlines. No full stops where brevity serves. Commas tight. No em dashes.",
    "personality_never": ["stuffy","snobbish","corporate","try-hard","fake luxury","old-money","salesy"],
    "signature_lines": ["Better Begins Here","Everything has to earn its place","Fit First. Buy Second.","Why It's Here","Respect the Player"],
    "master_message": "STICK is where modern golfers come to get better, and everything has to earn its place.",
    "supporting_messages": ["…5 ranked, workbook §E…"],
    "approved_ctas": ["Book a fitting","Enquire","Find your fit","View product","Try it on","Visit us","Message to order","Ask us","Shop the drop","Get your spec done"],
    "approved_headlines": ["Everything has to earn its place.","This is why we stock it.","Better Begins Here.","Fit first. Buy second.","Your driver is telling you something."],
    "banned_phrases": ["we are passionate about golf","your journey","unlock your potential","world-class","bespoke","game changer","next level","the perfect driver","join the club","become a member"],
    "not_us_examples": ["…4 workbook §D rejected paragraphs…"],
    "internal_only": ["Modern golf. Real improvement."]
  },
  "litmus_test": ["Does this help golfers get better?", "…v3 §24…"]
}
```

Rules for the ingest:

* `approved_headlines` **omits** `"Why this shaft? Because your current one is costing you 15
  metres."` (§3.6 — unverified number).
* Swing Shack's `internal_only` carries `world-class performance hub`, `Real Golf. Real Data.
  Real Welcome.` (mantra, explicitly "not our public tagline"), and the §16 litmus test.
* Do **not** copy anything already in `knowledge.json verified_facts` (tagline, promise,
  mantra, archetype, quote, bookings URL, banned_fabrications, voice_constraints, tone).
  Reference them as `{"knowledge_fact": "verified_tagline"}` so there is one source of truth.
* Do **not** populate `positive_prompts` / `negative_prompts` / `photography` /
  `product_fidelity` from the workbook. Image lane, out of scope.
* No `[FILL IN]` value is ever written. If a workbook cell is `[FILL IN]`, the key is omitted.
* Written under `data/brand-directory/<brand>/` (bundled), **not** `DATA_DIR` — see §4.2 on the
  path fix that makes the bundled copy actually readable.

### 4.2 `campaign-os/_lib/brand_bible.py` — retrieval slice

1. Extend `STRUCTURED_FIELDS` with `copy_system` and `litmus_test` (dict / list defaults), and
   teach `save_bible` their default types.
2. Add lanes to `retrieve_for_job`:

```python
elif lane == "caption":
    cs = bible.get("copy_system") or {}
    out["fields"]["copy_system"] = {
        k: cs.get(k) for k in (
            "voice_in_5_words", "sentence_length", "humour", "technical_depth",
            "emoji_policy", "punctuation", "personality_never", "signature_lines",
            "master_message", "supporting_messages", "approved_ctas",
            "approved_headlines", "banned_phrases",
        ) if cs.get(k)
    }
elif lane == "poster":
    cs = bible.get("copy_system") or {}
    out["fields"]["copy_system"] = {
        k: cs.get(k) for k in (
            "signature_lines", "approved_ctas", "approved_headlines",
            "banned_phrases", "punctuation",
        ) if cs.get(k)
    }
```

   `internal_only`, `not_us_examples` and `litmus_test` are deliberately **not** retrieved into
   either lane — they are reviewer context, not prompt input.
3. **Path fix (required, or §4.1 is unreadable in production).** `_data_root()` currently
   returns the *first existing* of `BUNDLED_DATA_DIR`, `DATA_DIR`, and a stale hardcoded
   `/Users/fivefriday/…` path. In the container `BUNDLED_DATA_DIR` is unset
   (`app.py:469` computes it in Python, it is not an env var), so `_data_root()` falls through
   to `DATA_DIR=/data/campaign-os` — the empty volume. Change `_bible_path` to try, in order,
   `DATA_DIR/brand-directory/<b>/bible-intelligence.json` then
   `<repo>/data/brand-directory/<b>/bible-intelligence.json` (resolved from `__file__`, the way
   `brand_directory.py:24` already does it), and drop the `/Users/fivefriday` candidate.
   Keep `save_bible` writing to `DATA_DIR` (runtime is truth, per the P0.5 seed doctrine).
4. Add a `bible_copy_slice(brand_id, lane)` thin wrapper that returns `{}` on any failure, so
   P11 never raises on a missing/corrupt file.

### 4.3 `campaign-os/_lib/caption_copy_contract.py` — the shared phrase gate

This is the module that already exists; extend it.

1. `BRAND_FORBIDDEN_PHRASES["stick"] += ("join the club", "join the stick club", "become a member")`.
   `swing-shack` stays `()`. **C1.**
2. Fold in the bible's `banned_phrases`:

```python
def bible_banned_phrases(brand_id: str) -> tuple[str, ...]:
    from _lib.brand_bible import bible_copy_slice
    cs = (bible_copy_slice(brand_id, "caption") or {}).get("copy_system") or {}
    return tuple(p for p in (cs.get("banned_phrases") or []) if isinstance(p, str) and p.strip())
```
   and merge it in `merged_banned_terms` after `BRAND_FORBIDDEN_PHRASES`.
3. **Fix the markdown parser** (`_extract_banned_terms` in p11 — see §4.4) by moving the parse
   here as `parse_dont_say_markdown(text) -> list[str]`, which:
   * extracts only the **quoted** phrases from a `❌` line (`re.findall(r'"([^"]{2,60})"', line)`),
     falling back to the text before the first ` — ` / ` – ` / `(` when a line has no quotes;
   * also walks `## Numbers discipline` and `## Say with care` `❌` lines;
   * drops the `len < 80` cap (it silently ate Stick's cross-brand ban, §0.5);
   * never emits a phrase containing `—` (the em dash has its own check).
   Pin this with a unit test asserting `"world-class"` and `"look no further"` come out clean.
4. **One gate, callable on any text:**

```python
def gate_text(brand_id: str, text: str, *, ctx: dict | None = None) -> dict:
    """Returns {"passed": bool, "reason": str}. Em dash + merged banned phrases +
    brand-scoped phrases + bible banned_phrases + membership_offered."""
```
   and a `copy_package` wrapper:
```python
def gate_copy_package(brand_id, copy_package, *, ctx=None) -> dict:
    """Runs gate_text over caption_body, poster_hook and cta_line.
    Returns {"passed", "reason", "field"} naming which field failed."""
```
   `gate_text` must be **case-insensitive** and **substring-based on phrases**, never on single
   words — this is Kyle's "Phrase bans, not the word 'club'".
5. Add `allow_signature_line(brand_id, text) -> bool` backed by the bible's `signature_lines`,
   for §3.6's `the truth` allowlist.

### 4.4 `campaign-os/_lib/p11_context_engine.py` — retrieval + gate wiring

Five edits, all small. Line numbers are `480f4a44`.

| # | Anchor | Change |
|---|---|---|
| a | `_brand_dir` `:38` | add the bundled fallback: return `DATA_DIR/brand-directory/<b>` if it exists, else `<repo>/data/brand-directory/<b>`. **This is the single highest-value line in the ticket** — it turns the entire markdown voice layer from dead to live in production (§0.5). Keep `_data_dir()` first so a runtime volume still wins. |
| b | `_extract_banned_terms` `:838` | replace the inline parser with `caption_copy_contract.parse_dont_say_markdown(txt)`, keep `banned.append("—")`, keep `merged_banned_terms(...)`. |
| c | `_extract_required_terms` `:860` | accept plain `- ` bullets under `## Do say` as well as `✅`, so `optional_related_facts.all_terminology` stops being empty. |
| d | `GLOBAL_FACTS` `:1126` | add `"bible": bible_copy_slice(brand_id, "caption").get("copy_system") or {}`, and in `_build_llm_prompt` (`:1699`) emit, when present: voice-in-5-words, humour rule, emoji policy, personality_never, signature_lines, approved_ctas, master_message. Put them in the **system** message next to `Personality:` / `Default CTA:`. Keep it short — this is a *slice*, not the bible. |
| e | `run_caption_pipeline` `:2387` | after `checks["copy_contract"]`, add `checks["phrase_gate"] = gate_copy_package(ctx["brand_id"], c.get("copy_package"), ctx=ctx)` and a `rejects["phrase_gate"]` bucket. **This is the fix for §0.6** — the first time `poster_hook` and `cta_line` are phrase-checked. |
| f | `_check_fact` `:2015` | before the `causal_terms` loop, `if allow_signature_line(brand_id, candidate): skip "the truth"`. Needs `ctx["brand_id"]`, which is already on the ctx. **C6.** |

Do not change the existing check ordering or the `rejects` keys that
`test_caption_copy_contract.py` and the layer-5 job tests already assert.

### 4.5 `data/voice_bible.json` — cleanup

Demote, do not delete (25+ call sites across `app.py` and `_lib`; `schema`/`voices`/`tones`
shape must survive).

| Key | Action |
|---|---|
| `stick.personality` | → `sharp, confident, direct, smart, rebellious` |
| `stick.description` | → `Smart Rebel: edge and brains. Modern golf performance and culture. Not a punk brand, not an engineering robot.` |
| `stick.allowed_tones` | drop `sarcastic`; → `["confident","direct","wry","relatable","provocative"]` |
| `stick.template_prefix` / `template_suffix` | → `""` (emoji policy is "rare"; a fixed prefix is a crutch) |
| `stick.cta_default` | → `Book a fitting` |
| `stick.cta_alternatives` | → `["Find your fit","Enquire","Get your spec done"]`. **Remove the `swingshack.co.za` line.** |
| `stick.example_caption` | → `Everything has to earn its place. This is why we stock it.` |
| `stick.callout_style` | → `direct, informed, confident` (drop `meme-reference`) |
| `swing-shack.personality` | → `warm, knowledgeable, witty, useful, confident` |
| `swing-shack.description` | keep the TrackMan/data substance, add `warm` and `never at the golfer's expense` |
| `swing-shack.template_prefix` / `template_suffix` | → `""` |
| `swing-shack.cta_alternatives` | **remove** `Your clubs deserve better than you.` wherever it appears |
| `tones.sarcastic` | keep the definition (`bag-drop` and the meme lab still reference the enum) but remove it from both brands' `allowed_tones` |
| new `voices.*.authority` | → `"bible-intelligence.json#copy_system"` so the demotion is legible in the file |
| `bag-drop.*` | **untouched** — out of scope |
| `updated` | bump |

Add a `"note"` field recording that personality/CTA authority moved, so the next reader does
not re-derive it.

### 4.6 `data/brand-directory/{stick,swing-shack}/voice/do-say-dont-say.md`

| File | Change |
|---|---|
| stick | add `❌ "join the club" / "become a member" — Stick does not sell membership` under `## Don't say`; add the workbook §D bans `❌ "we are passionate about golf"`, `❌ "your journey"`, `❌ "unlock your potential"`, `❌ "world-class"`, `❌ "bespoke"`, `❌ "game changer"`, `❌ "next level"`, `❌ "the perfect driver"`; delete `❌ "LOL" / "LMAO"` rationale drift only if it stays under 80 chars post-parser-fix (it no longer matters after §4.3.3). Add a `## Numbers discipline` note that `15 metres`-style distance claims need a verified source. |
| swing-shack | reword the beginner entry per **C4**; add the workbook §D bans `❌ "your golf journey"`, `❌ "game changer"`, `❌ "state of the art"`, `❌ "we are passionate about golf"`, `❌ "world-class facility"`; add `## Do say` entry `"Join the club" — membership CTA, Swing Shack only` so the asymmetry with Stick is documented at the point of use. |
| both | keep `## Em dash ban` verbatim. Keep every existing `❌` line unless listed above — the gate now actually reads them (§4.4a), so deletions have teeth. |

Also in scope and worth doing in the same commit (both under `data/brand-directory/<brand>/`):

* `stick/voice/tone-rules.md` — **C3**, at minimum the first sentence and the two cross-brand lines.
* `swing-shack/voice/tone-rules.md` — **C8**, replace the two em dashes with pipes.
* `stick/copy/ctas.md` + `swing-shack/copy/ctas.md` — **C5**, delete
  `Your clubs deserve better than you.` from both; remove Stick's `→ swingshack.co.za` hard CTA.
* `stick/knowledge.json` — **C9** `cta_rules`, and **C8** the em dash in `verified_archetype`.

### 4.7 `campaign-os/_lib/compose_visual_copy.py` — poster slice

`poster_copy.py` is out of the allowlist, so all of this lands here.

1. `_service_cta` (`:140`) — branch on `brand_id`, and source the default from the bible's
   `approved_ctas` (falling back to today's string only when the bible is unavailable):
   * `stick` → `Book a fitting`
   * `swing-shack` → `Book your session`
   * **drop the unverified `free`** from all three returns (§0.6). Keep
     `Book your free club assessment` reachable **only** when the sidecar or the calendar row
     supplies it explicitly — per Kyle, template headlines like `FREE CLUB ASSESSMENT` stay
     allowed, but the generator must not invent "free" on its own.
2. `_service_end_tagline` (`:69`) — replace the `Golf, made simpler.` fallback with the brand's
   master line from the bible (`Better Begins Here` for Stick). Reword
   `Brand-agnostic fittings guided by data and science.` to Stick register
   (`Fit first. Buy second.` or `Equipment matched to the player.`).
3. Add, at the end of `visual_copy_for_archetype` (`:151`), a single gate pass over the
   text-bearing fields before the `return`:

```python
from _lib.caption_copy_contract import gate_text  # noqa: PLC0415
for field in ("caption_hook", "cta", "qualifier", "service_lockup", "service_label", "kicker"):
    val = base.get(field)
    if val and not gate_text(brand_id, str(val))["passed"]:
        base[field] = ""            # blank, then let the existing fallback re-derive
        base["_poster_gate_blocked"] = f"{base.get('_poster_gate_blocked','')} {field}".strip()
```
   Blanking rather than raising keeps compose deterministic and keeps the existing
   `caption_fallback` chain intact. `_poster_gate_blocked` gives `asset_qc` and Review
   something to surface.
4. Return path is `dict[str, str]` — keep every value `str`; the four early `return` branches
   (`stick-service-end`, `stick-service-start`/`shop-corner`, `stick-coach-profile`,
   bare `needs_photo`) each need the same pass, so factor it into a
   `_gate_fields(brand_id, base)` helper called from all five exits.

---

## 5. Test plan — unit only, no Playwright

New file `campaign-os/tests/test_cos_brand_bible_20260930.py` (repo convention:
`test_<slug>_<date>.py`, `unittest.TestCase`, lazy imports inside test methods so a missing
module fails one test not collection). Extend the existing
`campaign-os/tests/test_caption_copy_contract.py` rather than duplicating its 6 tests.

**Phrase gate — Kyle's four acceptance examples, pinned exactly:**

1. `gate_text("stick", "Join the club and get fitted.")` → blocked.
2. `gate_text("swing-shack", "Join the club. Four practice sessions a month.")` → **passes**
   (C1 asymmetry; the test comment must cite workbook §D).
3. `gate_text("stick", "Club fitting at Stick. Fit first. Buy second.")` → passes.
4. `gate_text("swing-shack", "FREE CLUB ASSESSMENT")` → passes.
5. `gate_text("stick", "Data shows fitting helps.")` → blocked `data shows`.
6. `gate_text("swing-shack", "The ball speaks. Data confirms. Feel seals the deal.")` →
   **passes** (C7 regression pin).

**Poster gate (the §0.6 hole):**

7. `gate_copy_package("stick", {"caption_body": "ok", "poster_hook": "JOIN THE CLUB", "cta_line": "Book a fitting"})`
   → blocked, `field == "poster_hook"`.
8. Same with the ban in `cta_line` → blocked, `field == "cta_line"`.
9. `visual_copy_for_archetype(brand_id="stick", …)` with a sidecar
   `compose_headline="Join the club"` → returned `caption_hook` is not that string and
   `_poster_gate_blocked` mentions `caption_hook`.
10. `_service_cta(brand_id="swing-shack", …)` and `(brand_id="stick", …)` return **different**
    strings, and neither contains `free`.

**Markdown parser (§0.5):**

11. `parse_dont_say_markdown(open("data/brand-directory/swing-shack/voice/do-say-dont-say.md").read())`
    contains `"world-class"` and `"look no further"` as clean lowercase phrases, and contains
    no entry containing `—`.
12. The stick 80-char cross-brand ban survives the parse.
13. `_extract_required_terms("swing-shack")` is non-empty (regression for `required == 0`).

**Retrieval slice:**

14. `retrieve_for_job("stick", lane="caption")["fields"]["copy_system"]["signature_lines"]`
    contains `"Better Begins Here"`.
15. `retrieve_for_job("stick", lane="poster")["fields"]["copy_system"]` has **no**
    `master_message` key and **no** `internal_only` key.
16. `retrieve_for_job("swing-shack", lane="caption")` `copy_system.banned_phrases` contains
    `"world-class"` but **not** `"join the club"`.
17. `retrieve_for_job("bag-drop", lane="caption")["available"] is False` — no file, no crash.

**Context slice:**

18. `build_generation_context(brand_id="stick", user_brief="driver fitting")["brand"]["bible"]`
    is non-empty and contains `voice_in_5_words`.
19. `_build_llm_prompt(ctx, route)[0]` (system) contains `Better Begins Here` and does **not**
    contain `sarcastic`.
20. `build_generation_context(brand_id="swing-shack", …)["brand"]["bible"]` does not contain
    `Real Golf. Real Data. Real Welcome.` (internal_only is not retrieved).

**voice_bible.json (the verify job's stated PASS criterion):**

21. `json.load(data/voice_bible.json)`: `"sarcastic" not in voices["stick"]["allowed_tones"]`,
    `"sarcastic" not in voices["stick"]["personality"]`.
22. No string anywhere under `voices["stick"]` contains `swingshack.co.za`.
23. `"Your clubs deserve better than you."` appears in **neither** brand's
    `cta_alternatives`, and in neither `copy/ctas.md`.
24. `voices["bag-drop"]` is byte-identical to the base-branch value (out-of-scope guard).

**Fact-gate allowlist (C6):**

25. `_check_fact("The swing may lie, but the ball tells the truth.", ctx_swing_shack)` → passes.
26. `_check_fact("This fitting is guaranteed to add 10 metres.", ctx)` → still fails.

**Existing suites that must stay green** (they touch the same functions):
`test_caption_copy_contract.py`, `test_compose_visual_copy.py`, `test_caption_coherence.py`,
`tests/jobs/test_caption_copy_package.py`, `tests/jobs/test_layer5_image_context.py`
(it patches `_extract_banned_terms`), `tests/jobs/test_draft_assets_serial_complete.py`,
`test_p0_brand_context.py`, `test_template_gallery.py`, and the 17 `test_ss_*` /
`test_stick_*` template tests.

Run command for implement and verify:

```bash
cd /home/kyle/Work/worktrees/... && python3 -m pytest -q \
  --ignore=campaign-os/tests/jobs/test_compose_template_wiring.py
```

Baseline to beat: **2496 collected** (§0.2), plus the new file's ~26 tests.

---

## 6. Verify tier

**Light — `meta/muse-spark-1.3-contributor`.** Reason: the slice is caption and poster *text*
only. No image generation, no Krea, no negative prompts, no renderer. The six edits are bounded
Python plus JSON/markdown data, with assertions that are all string-equality or substring —
exactly the shape muse-spark verifies reliably.

**One caveat that keeps it light rather than deep, and must be checked:** creating
`bible-intelligence.json` (§4.1) flips `_brand_bible_lineage` in
`campaign-os/_lib/jobs/layer5/image_draft_context.py:631` from `available: false` to
`available: true` and changes its `fields` list, which lands in **image** draft lineage. That is
a lineage-metadata change, not a prompt or pixel change — `_brand_bible_lineage` returns only
`available` / `last_updated` / `sorted(fields.keys())` and never the values. Verify must confirm
that `campaign-os/tests/jobs/test_layer5_image_context.py` and the golden-render template tests
are unchanged. **If implement ends up feeding any bible field into a prompt on the image lane
(`creative_director.compose_prompt`, `krea_mcp`, `image_dissector`, `bible-visual.json`), the
tier escalates to deep (`deepseek/deepseek-v4-pro`).** Per §3.10 that must not happen in this
ticket.

---

## 7. Sequencing, and what implement should do first

1. Branch `feat/cos-brand-bible` off `480f4a44` (**not** `3e9d2821`). Confirm
   `campaign-os/_lib/caption_copy_contract.py` exists before writing a line.
2. `§4.4a` — `_brand_dir` bundled fallback. One function. Run the suite. This alone makes the
   existing markdown rules live and will change generated copy, so land it first and alone.
3. `§4.3.3` parser fix + `§4.4b/c`, with tests 11–13. Still no new data files.
4. `§4.3.1/4` — Stick `join the club` ban + `gate_text` / `gate_copy_package`, tests 1–8.
   **Kyle's acceptance criterion is satisfied at the end of this step.**
5. `§4.1` + `§4.2` — the two JSON files and the retrieval lanes, tests 14–17.
6. `§4.4d/e/f` — prompt slice, pipeline gate, fact allowlist, tests 18–20, 25–26.
7. `§4.5` + `§4.6` — `voice_bible.json` and the markdown/`ctas.md`/`knowledge.json` cleanup,
   tests 21–24.
8. `§4.7` — compose poster slice, tests 9–10.
9. Finish via `bin/agent-job-finish` with `--verdict`, `--commit`, `--commits-ahead`.

Steps 2 and 3 are the ones most likely to break existing tests, which is why they go first and
separately. Steps 4–8 are additive.

---

## 8. Open questions for Kyle — none of these block implement

1. **`ss-did-you-know`** (C11): `swing-shack/voice/tone-rules.md` says "Did you know…" is Stick
   voice, but there is a Swing Shack `did-you-know` template with golden renders and a
   `caption_copy_contract` entry. Which wins? Default if no answer: leave both, note it.
2. **`free` in poster CTAs** (§0.6): is there a genuinely free club/swing assessment? If yes,
   it belongs in `knowledge.json verified_facts` and the CTA can stay hardcoded. If no, the
   generator must never say it. Default: drop `free` from the generated fallback, keep it
   reachable from an explicit sidecar/calendar value.
3. **`bible-visual.json`** (C10): Stick's image-lane `voice` field still says "sarcastic,
   meme-aware". Out of scope here. Want a follow-up ticket?
4. **`stick/knowledge.json cta_rules`** (C9) currently points at Takomo on the Swing Shack
   domain. Proposed fix in §4.3 of C9 — confirm `Book a fitting → stickgolf.co.za/bookings/`
   is the right default.
5. **Workbook §L** is `[FILL IN]` for every channel label, so there is no authoritative
   per-channel CTA map. Kyle's instruction is that these stay empty, so P11's hardcoded
   `channel_rules` (`p11_context_engine.py:1258`) stays as-is. Confirm.

---

## 9. Out of scope, stated explicitly

* Bag Drop — `voice_bible.json voices["bag-drop"]`, `data/brand-directory/bag-drop/**`, and
  `MECHANISM_FIT["bag-drop"]` are untouched (test 24 guards this).
* Krea / image-gen prompts, negative prompts, `bible-visual.json`, `brand_dna.py`,
  `creative_director.py`, `image_dissector.py`.
* Full-week regeneration; any Postiz publish; any push to `main`.
* `campaign-os/_lib/poster_copy.py` — not in the manifest `paths`.
* `data/brand-directory/takomo/**` — not in the manifest `paths`.
* `campaign-os/tests/jobs/test_compose_template_wiring.py` collection error (§0.2) —
  pre-existing, different subsystem.
