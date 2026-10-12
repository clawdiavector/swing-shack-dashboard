# MyCarMatch (MCM) — seven questions for Kyle and Christelle

Skeleton pack only. Answers replace `TODO:` placeholders in this tree. Do not invent copy, colours, or claims until these are answered.

---

## 1. Audience — who are we talking to?

**Question:** Who is the primary buyer (demographics, intent, geography)? Who is explicitly *not* the audience?

**Answers land in:**

| File | Fields / sections |
|------|-------------------|
| `README.md` | What this brand is · Who it is for · What it is not |
| `knowledge.json` | `verified_facts` (e.g. audience, geography, exclusions) |
| `calendar_config.json` | `scouting_profile.interest_areas`, `weighted_preferences` |
| `copy/headlines.md` | Pillar / intent tags once voice is known |

---

## 2. Goal — what must marketing move?

**Question:** What are the 1–3 measurable outcomes (leads, app installs, dealer visits, brand awareness)? Weekly/monthly targets if any?

**Answers land in:**

| File | Fields / sections |
|------|-------------------|
| `north_stars.json` | `north_stars[]` (metric, connector, `do_not_fabricate_progress`) |
| `calendar_config.json` | `pillars[]` (objective, `north_star_metric`, `north_star_target`) |
| `README.md` | Current state · Canonical references (goals) |
| `knowledge.json` | `verified_facts` for approved targets and numbers discipline |

---

## 3. Accounts — which surfaces do we operate?

**Question:** Instagram / Facebook / TikTok / LinkedIn / YouTube handles? Who owns credentials? Meta page IDs if known?

**Answers land in:**

| File | Fields / sections |
|------|-------------------|
| `feedback/instagram-audit.json` | `ig_account_id`, `username`, audit `posts[]` (after `/audit-social mcm`) |
| `source.json` | Ingestion records for social exports or asset drops |
| `data/integrations/mcm/instagram.json` | **Outside this folder** — credential env mapping when engineering wires Meta (later slice) |
| `sitemap-snapshot.json` | Public web URLs (site, app store, dealer pages) |

---

## 4. Voice — how should MCM sound?

**Question:** Tone (formal vs conversational), taboo phrases, required disclaimers in copy, CTA style, language (EN only vs multilingual)?

**Answers land in:**

| File | Fields / sections |
|------|-------------------|
| `voice/tone-rules.md` | Per-tone guidance |
| `voice/punctuation-rules.md` | Punctuation and formatting bans |
| `voice/do-say-dont-say.md` | Approved / banned phrases |
| `knowledge.json` | `voice_rules`, `verified_facts.voice_constraints`, `verified_facts.tone` |
| `copy/ctas.md` | Hard and soft CTAs |
| `copy/headlines.md` | Headline bank |
| `examples/good.md` · `examples/bad.md` | Calibrated examples |
| `visual-spec/platforms.json` | `brand_voice_for_images` (image-gen hints, not caption voice) |

---

## 5. Photos — where do visuals come from?

**Question:** Google Drive folder (public or OAuth)? Client-supplied library only? Stock forbidden? Logo / UI / vehicle imagery rules?

**Answers land in:**

| File | Fields / sections |
|------|-------------------|
| `source.json` | `ingestions[]` (`method`, `folder_id`, file lists) |
| `ingest-manifest.json` | `images{}` after ingest |
| `images/` | Binary assets + optional `.visual-dna.json` sidecars |
| `visual-dna-index.json` | Index over `images/` |
| `bible-visual.json` | Photography, composition, anti-patterns |
| `bible-intelligence.json` | Structured bible extractions |
| `bible-source.txt` · `strategy-source.txt` | Pasted authoritative brand docs |
| `palette/brand.json` | Measured colour tokens (from brand assets, not guessed) |
| `typography/fonts.json` · `typography/fonts/` | Measured or licensed font files |
| `logo.png` | Brand mark file (add when supplied) |
| `templates/` | Measured post templates (`campaign-os-template` graduates winners here) |

---

## 6. Client or ours — who owns the relationship?

**Question:** Is MCM a Five Friday retained client, a product we operate, or co-marketing? Who approves publish? Cross-mention rules with other brands?

**Answers land in:**

| File | Fields / sections |
|------|-------------------|
| `README.md` | Authority rules · What it is not · Linked brands |
| `knowledge.json` | `verified_facts` (relationship, approval chain, booking URLs) |
| `north_stars.json` | `source` on each north star (operator vs client directive) |
| `calendar_config.json` | `north_star_target.source` / `source_provenance` on pillars |

---

## 7. Compliance — what claims are never allowed?

**Question:** FSCA / NCA / advertising standards / OEM rules / pricing disclaimers / competitor naming / financial promises?

**Answers land in:**

| File | Fields / sections |
|------|-------------------|
| `knowledge.json` | `verified_facts.banned_fabrications`, `rules.no_fabrication`, `rules.exact_only` |
| `voice/do-say-dont-say.md` | Banned claims and mandatory disclaimer lines |
| `README.md` | Authority rules |
| `ads/video-ideas.json` | `note` — numbers only if in `knowledge.json` or on-screen during shoot |

---

## After answers

1. Replace `TODO:` strings in JSON and markdown with verified content; set `knowledge.json` → `verified_at`.
2. Run ingest when Drive root is known (`campaign-os-map` — add MCM to `BRAND_PUBLIC_ROOTS` in a **later engineering slice**).
3. Run `/audit-social mcm` once `data/integrations/mcm/` exists.
4. Do **not** expect MCM in the cockpit brand picker until a separate data-driven brand-list slice lands.
