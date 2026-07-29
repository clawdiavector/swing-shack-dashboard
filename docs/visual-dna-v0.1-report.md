# Visual DNA Engine — v0.1 Report

**Date:** 2026-07-29
**Brand:** swing-shack
**Source folder:** Google Drive `1n9pHD6hwr7oEfRBAGBriRrsqv_I-qGge`
**Owner (Drive):** `fivefridaymarketing@gmail.com`
**Auth account:** `christellew@fivefriday.com` (read-only, oauth refresh-token saved)

## What was built

### 1. Brand Bible — machine-readable
`data/brand-directory/swing-shack/bible-visual.json`

Parsed from your paste. Captures:
- **Dark backgrounds:** `#000000`, `#191919` (flat or gradient)
- **Accent colours:** `#74cc46`, `#e17026`, `#63a3ef`, `#8f4bf9`
- **Light colour:** `#ffffff`
- **Border:** thin white at 20% opacity
- **Headings:** Avenir Next Heavy Italic, **ALL CAPS**
- **Body:** Avenir Next Italic

### 2. Ingest — 122 brand assets pulled from Drive
- 3 subfolders: `Services/`, `Products/`, `Others/`
- 122 JPEGs, 116 MB total, all valid, all dedup-checked via Drive md5
- Per-image manifest in `data/brand-directory/swing-shack/ingest-manifest.json`
- Provenance in `source.json`

### 3. Visual DNA dissector — `campaign-os/_lib/image_dissector.py` (~480 lines)
Extracts per image:
- **Layer 1** — basic metadata (size, dimensions, format, EXIF, orientation)
- **Layer 6** — OCR text (tesseract) with bounding boxes + confidence
- **Layer 7** — typography detection (heading text via OCR, all-caps check, sampled text colour)
- **Layer 9** — colour palette via Pillow median-cut quantize (top 8 dominants + shares)
- **Layer 10** — composition (aspect, gradient direction, edge-density 3×3 grid, subject position)
- **Layer 8** — brand-bible compliance score (0.0-1.0) across 7 checks
- **Layer 17** — Visual Recipe schema (background type, gradient direction, subject position, OCR text, all-caps flag, reusability)

Outputs `*.visual-dna.json` per image + cross-image `visual-dna-index.json`.

## Results — read as a reference index, NOT a quality grade

**Important framing:** Every one of these 122 images is approved, in-use brand material. The compliance score doesn't grade them — it groups them by *style pattern* so future generation can pull recipes from the strongest examples and add variety from the edge cases.

### Style distribution across your 122 active assets

| Compliance score | Count | What this means for generation |
|---|---|---|
| **0.70+ (high alignment)** | 59 | Use as **Visual Recipe templates** — these are your brand canon. When generating a new SS post, copy their layer17 recipe first, then adapt. |
| **0.60–0.69 (typical)** | 39 | Standard assets — they fit the brand but with some variation. Use as **secondary references** when the brief calls for less strict alignment. |
| **<0.60 (variants)** | 24 | These add range: product-on-white shots, vendor-supplied colours, edge compositions. **Use deliberately** when the brief needs product clarity or vendor-presence (e.g. "Srixon bag feature"). Not flaws — variety. |
| **Total** | **122** | The full distribution of what SS actually looks like in market. |

Average: 0.664 — that's your brand's centre of gravity.

### Top performers

1. `blackfriday copy 3.jpg` — 0.875 (white text on dark bg, ALL CAPS)
2. `mileseey.jpg` — 0.875
3. `social_lab1_story copy 2.jpg` — 0.875
4. `Artboard 1 copy 2.jpg` — 0.775 (template artwork, dark bg)
5. `coaching_post2.jpg` — 0.775

### Worst (real issues surfaced)

1. `fullrange copy 5-100.jpg` — 0.375 (off-brand `#3b6176` dominant — light blue, not in palette)
2. `Quantammini1 copy*.jpg` (×2) — 0.475 (light product-shot background, white not dark)
3. `VESSEL_BAG copy 2.jpg` — 0.475
4. `cf3 copy.jpg` — off-brand dominant

### Failure modes (across the 63 failing)

| Mode | Count | Why |
|---|---|---|
| accent not detected | 52 | Accent colour is in small CTA area, not in top-8 dominants (mitigated by checking sampled-text-colour) |
| white text/border not detected | 47 | Same root cause — white is in text pixels, not in top-8 dominants (mitigated but not fully solved) |
| background not dark | 15 | Product shots on white background — e.g. Callaway Quantum putter |
| off-brand dominant colour | 6 | Srixon red, light blue range, etc. |
| headings not all-caps | 3 | Tesserart reads logo glyphs as text, polluting the heading tier (mitigated by confidence filter) |

## What's intentionally NOT built (and why)

These layers need ML models I haven't installed yet:

- **Layer 2, 3, 4, 5, 11, 12, 13, 14, 15, 16, 18** — require CLIP / face_recognition / object detection / brand-classifier / mood-classifier. Each is a 1-3 day install + integration. Worth doing, but each is its own tick.
- **Font detection (Avenir Next Heavy Italic vs other)** — currently assigned 50% partial credit as "unverified". Need a font-CV model or local Avenir Next corpus to do real matching.

## How the next tick can use this

1. **Run on Stick and Bag Drop folders** — same Drive auth, same dissector, different brand IDs. Already wired up.
2. **Cross-reference with performance data** — when GA4/Meta analytics are wired, layer 18 (performance learning) becomes: "smile + TrackMan visible + red CTA → X% higher engagement". The dissector already provides the input features.
3. **Visual Recipe suggestions for new images** — when generating a new asset, the system can pull the top-5 highest-scoring images' layer17 recipes and use them as the prompt scaffolding.
4. **Brand-compliance warnings before publish** — gate any new asset through `dissect()` and refuse publish if score < 0.70.

## Open questions for you

1. **Body font weight** — you said "Avenir Next (Italic)" but didn't specify weight. Is it Regular Italic or Demi Italic? Once you confirm, I'll tighten the check.
2. **Open questions in `bible-visual.json`** — five of them. Review and answer.
3. **Avenir Next font file** — can you provide the actual `.otf` or `.ttf`? With the font on disk, we can hash-match it for real font detection instead of partial credit.
4. **Threshold** — 0.70 is my guess for "pass". Want it higher (0.75, 0.80) for stricter compliance? Lower (0.65) to be more forgiving?

## Files written

- `campaign-os/_lib/image_dissector.py` (new, ~480 lines)
- `data/brand-directory/swing-shack/bible-visual.json` (new)
- `data/brand-directory/swing-shack/visual-dna-index.json` (new, cross-image rollup)
- `data/brand-directory/swing-shack/ingest-manifest.json` (new)
- `data/brand-directory/swing-shack/source.json` (updated)
- `data/brand-directory/swing-shack/images/*.visual-dna.json` (122 new files)
- `data/brand-directory/swing-shack/images/*.jpg` (122 files, ~115 MB, gitignored)

Commit: `39a7fec` on `feat/asset-state-engine`.
