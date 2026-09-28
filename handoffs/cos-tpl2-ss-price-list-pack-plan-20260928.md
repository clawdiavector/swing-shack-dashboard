# Plan — SS `ss-price-list`: complete price-list pack + selection

- **Job** `job-20260928-cos-tpl2-ss-price-list-pack-plan` (read-only) · run `20260928T120213-plan-55ad42`
- **Ticket** `ticket-20260928-cos-tpl2-ss-price-list-pack` · manifest `plan-20260928-cos-tpl2-ss-price-list-pack.yaml`
- **Branch** `plan/cos-tpl2-ss-price-list-pack` off `integrate/campaign-os-brand-lanes-v1` · no code edits made
- **Skill** `campaign-os-template` (`~/.agents/skills/campaign-os-template/`)
- **Next job** `job-20260928-cos-tpl2-ss-price-list-pack-implement` (Cursor, branch `feat/cos-tpl2-ss-price-list-pack-template`)

---

## TL;DR

`ss-price-list` is **further along than "partial"** — the archetype, the selection rule, the pack
skeleton and 8 passing tests are already on the base branch (commit `c64e45d7`). The **`ig_post`
geometry is pixel-accurate** against the reference (every zone within 1–2 px).

Four real defects remain, one of them shipping-blocking:

| # | Severity | Defect |
|---|---|---|
| 1 | **P0** | `ig_story` render is broken — zones stretched instead of centred, the URL line is clipped off the bottom edge |
| 2 | P1 | Reference uses **two accents** (blue title + green prices/CTA); the archetype paints all three one colour |
| 3 | P1 | Row labels render at ~half the reference's stroke weight (`h3` = Montserrat **ExtraLight** Italic vs reference **Regular** Italic) |
| 4 | P2 | Shared photo library stand-in `standin-zen-stage.jpg` has residual baked-in headline text along its top edge |

Plus pack/doc completion work (§6) and one operational gap that affects whether this template can
ever be auto-produced (§7).

---

## 1. References — the ticket's `content_bank_refs` entry is wrong

The manifest lists:

```
/home/kyle/Downloads/Content Bank-.../Swing Shack/Services/package1_post.jpg
```

That file is **`ss-price-package`'s ref-01**, not this template's. Verified by md5:

| Content Bank file | md5 | Where it actually lives |
|---|---|---|
| `package1_post.jpg` | `964f4a20…` | `templates/price-package/references/ref-01.jpg` |
| `package1_post copy.jpg` | `3deaba86…` | `templates/price-package/references/ref-02.jpg` |
| `package1_post copy 2.jpg` | `327b3346…` | `templates/price-package/references/ref-03.jpg` |
| `package1_story.jpg` | `84c50b46…` | `templates/price-package/references/ref-04.jpg` |
| **`coachinpackages_post.jpg`** | `12dbfac3…` | **`templates/price-list/references/ref-01.jpg`** |
| **`coachinpackages_story.jpg`** | `16a38c43…` | **`templates/price-list/references/ref-02.jpg`** |

**The pack's existing two refs are the correct ones.** Do not re-measure against `package1_*`.

`membership_post.jpg` / `membership_story.jpg` were also checked as possible family members and are
**not** — different layout entirely (centred kicker, 5 short white bullet rows at cap 30, no price
column). Leave them out.

> **Action for the orchestrator:** correct `template_job.content_bank_refs` in
> `manifests/plan-20260928-cos-tpl2-ss-price-list-pack.yaml` to the two `coachinpackages_*` files.

### 1a. The refs are CMYK — read colours through the ICC profile

Both price-list refs (and the price-package and discount-code refs) are **CMYK JPEGs carrying a
`U.S. Web Coated (SWOP) v2` profile**. Every other SS pack's refs are RGB.

A naive `Image.open(p).convert('RGB')` — which is what `measure_refs.py` does — decodes them
without the profile and reports shifted colours. Convert properly first:

```python
from PIL import Image, ImageCms; import io
im = Image.open(ref)                       # mode 'CMYK'
icc = im.info["icc_profile"]
rgb = ImageCms.profileToProfile(
    im, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
    ImageCms.createProfile("sRGB"), outputMode="RGB")
```

| Zone | naive decode | **ICC → sRGB** | palette token |
|---|---|---|---|
| title | `#6FB9FF` | **`#6DA0D5`** | `ss_blue` `#64A3F0` |
| prices | `#6FFF0C` | **`#7BC24A`** | `ss_green` `#74CB46` |
| CTA | `#6FFF0C` | **`#7BC24A`** | `ss_green` |
| labels / URL | `#FFFFFF` | `#FFFFFF` | `white` |

Identical in both post and story refs. **No new palette tokens are needed** — the design uses the
canonical `ss_blue` / `ss_green`.

> **Side finding, not this ticket:** `ss_lime #70FF0F`, `ss_orange_hot #E95105`,
> `ss_blue_bright #3B7FEE`, `ss_panel_black #070707` in `palette/brand.json` all match the *naive*
> decode of CMYK refs, while every RGB ref in the brand lands pixel-exactly on the canonical four
> (`#74CB46` `#E27123` `#64A3F0` `#8F4BFA`). Those extra tokens look like decode artifacts recorded
> by earlier template jobs. Worth a separate cleanup ticket; do not touch here.

> **For the verify job:** a compare sheet built from these refs will always show a colour shift
> between ref and render unless the sheet ICC-converts first. That is a reference artifact, not a
> render bug. `compare_sheet.py` does not currently convert.

---

## 2. Measured layout — reference vs current archetype

`references/ref-01.jpg` (coachinpackages_post), 1081×1351. Target canvas `ig_post` 1080×1350.

```
frame     inset 32–41 px, stroke 6–7 px, white
logo      x 108–279   y 171–244    (white lockup, top-left)
title     x  86–727   y 291–377    line 1   cap 86  pitch 95   ← 2 balanced lines
          x  84–717   y 386–472    line 2
rule_top  x  83–956   y 526–534    grey divider
rows      labels  x  84–542  |  values  x 680–936
          y 624–675 / 695–746 / 766–817 / 837–888     cap 51  pitch 71
rule_btm  x  83–956   y 965–973
cta       x  83–795   y 1047–1089  cap 42
url       x  86–792   y 1133–1170  cap 37
```

Derived type metrics (`cap ≈ 0.70 × font_px`, `line_height = pitch / font_px`):

| Zone | measured font px | measured `line_height` | spec has | verdict |
|---|---|---|---|---|
| title | 123 | 0.772 | `119` / `0.798` | ✓ within tolerance |
| rows | 73 | 0.973 | `72` / `0.986` | ✓ |
| cta | 60 | — | `59` | ✓ |
| url | 53 | — | `52` | ✓ |

**Both divider bands were confirmed at the pixel level** by scanning for near-uniform grey rows:
y 526–534 and y 965–973, exactly matching the spec's `rule_top` / `rule_bottom` rects.

Rendering the live archetype and re-measuring the output gives title y 289–470, rows y 623–885,
columns x 679 / x 89 — **every `ig_post` zone within 1–2 px of the reference.** Ink coverage of the
price column is 56.5 % (ref) vs 54.5 % (render). The `ig_post` geometry needs no work.

---

## 3. P0 — `ig_story` is broken (URL clipped off-canvas)

### Symptom

Re-rendered live from the current archetype (not a stale golden):

| Zone | reference story (1081×1921) | current render (1080×1920) |
|---|---|---|
| logo | y 456–529 | y 525–597 |
| title | y 576–757 | y 697–878 |
| rows | y 909–1173 | y 1171–1433 |
| cta | y 1332–1374 | y 1773–1816 |
| **url** | **y 1418–1455** | **y ~1895–1948 — runs off the 1920 px canvas** |

The bottom frame edge also reads as broken (`inset 0, stroke 12`) because the clipped URL text
merges with it. The block is *stretched*, not translated: the offset grows down the page
(+408 at the title, +548 at the rows, +727 at the CTA).

### Root cause — `_shift_rect_anchor` scales before it translates

`campaign-os/_lib/archetype_compose.py:108` (`_shift_rect_anchor`)

```python
delta = (target_h - base_h) / 2 / target_h
return {... "y0": rect["y0"] + delta, ...}
```

The returned fraction is later multiplied by `target_h` in `_rect_px`, so the rendered row is

```
y = rect.y0 * target_h + (target_h - base_h) / 2     # base fraction gets stretched ×1.422
```

when centring a fixed-size block requires

```
y = rect.y0 * base_h   + (target_h - base_h) / 2
```

Check against the title (`y0 = 0.2154`): broken `0.2154 × 1920 + 285 = 698` (measured 697);
correct `0.2154 × 1350 + 285 = 576` (reference 576). ✔

### Blast radius

**14 archetypes across 3 brands** declare `instagram_story` without an `ig_story` override and are
hit by this: `ss-photo-post`, `ss-service-frame`, `ss-story-banner`, `ss-price-package`,
`ss-price-list`, `ss-sale-offer`, `stick-product-post`, `stick-service-frame`, `stick-venue-post`,
`stick-service-start`, `stick-service-end`, `bd-member-moment`, `bd-thursday-invite`,
`bd-warm-quote`. Every template that renders stories *correctly* today
(`ss-did-you-know`, `ss-discount-code`, `ss-fitting-headline`, `ss-service-promo`,
`stick-brand-statement`, `stick-location-drive`, …) does so by carrying an explicit
`canvas_overrides.ig_story`.

### Recommendation — fix it in the archetype, not the engine

**Do (this ticket): add `canvas_overrides.ig_story` to `ss-price-list`.** It is the established
house pattern, it is zero-blast-radius, and every rect below is verified against the story
reference to within 1 px. Derivation: `y_story = (y_post × 1350 + 285) / 1920`.

```json
"canvas_overrides": {
  "ig_story": {
    "logo":        { "rect": { "x0": 0.0972, "y0": 0.2353, "x1": 0.2609, "y1": 0.2822 } },
    "title":       { "rect": { "x0": 0.0796, "y0": 0.2999, "x1": 0.6725, "y1": 0.3941 } },
    "rule_top":    { "rect": { "x0": 0.0768, "y0": 0.4222, "x1": 0.8844, "y1": 0.4264 } },
    "list_labels": { "rect": { "x0": 0.0777, "y0": 0.4732, "x1": 0.5014, "y1": 0.6106 } },
    "list_values": { "rect": { "x0": 0.6290, "y0": 0.4732, "x1": 0.8800, "y1": 0.6106 } },
    "rule_bottom": { "rect": { "x0": 0.0768, "y0": 0.6507, "x1": 0.8844, "y1": 0.6548 } },
    "cta":         { "rect": { "x0": 0.0768, "y0": 0.6934, "x1": 0.7354, "y1": 0.7152 } },
    "url":         { "rect": { "x0": 0.0796, "y0": 0.7381, "x1": 0.7327, "y1": 0.7573 } }
  }
}
```

Verification against the story reference:

| zone | override → px | reference px |
|---|---|---|
| logo | 452–542 | 456–529 |
| title | 576–757 | 576–757 |
| list rows | 909–1172 | 909–1173 |
| cta | 1331–1373 | 1332–1374 |
| url | 1417–1454 | 1418–1455 |

Notes:
- `frame` is deliberately **omitted** — it is `kind: decorative` and driven by `inset_px`, so its
  rect is ignored. `_zones_for_canvas` merges rect-only patches onto the base zone map and leaves
  unlisted zones alone, so omitting it is safe and keeps the JSON honest.
- Logo top lands at `452/1920 = 0.235`, comfortably inside the story safe zone (`y ≥ 0.16`). ✔
- `channel_canvas: {"facebook": "ig_post"}` already works — Facebook renders 1080×1350. ✔

**Do not** fix `_shift_rect_anchor` inside this ticket. It is a genuine engine bug and the fix is
three lines, but it would move the story output of 14 archetypes and invalidate their goldens.
File it as its own ticket:

```
title:  fix block_anchor:center stretching zones on taller canvases
where:  campaign-os/_lib/archetype_compose.py:_shift_rect_anchor
fix:    y_new = (rect.y * base_h + (target_h - base_h)/2) / target_h
after:  re-render every ig_story golden; the 8 archetypes carrying an explicit
        canvas_overrides.ig_story can then drop it
```

---

## 4. P1 — the reference pairs two accents; the archetype uses one

Reference (ICC-corrected, identical in post and story):

- **title** → `ss_blue`
- **prices + CTA** → `ss_green`
- labels + URL → `white`

The archetype gives `title`, `list_values` and `cta` the same four `colour_options`
(`ss_green`, `ss_orange`, `ss_blue`, `ss_purple`). `_zone_colour` (`archetype_compose.py:380`)
resolves `fields.accent` for every zone whose options contain it, so all three land on one colour —
visible in `golden/compare-refs.jpg`, where the ref shows a blue title over green prices and the
render is blue throughout.

Note this is **specific to `ss-price-list`**. Its sibling `ss-price-package` was checked and is
genuinely single-accent in 3 of its 4 refs, so its current model is right; `ss-did-you-know`'s
template.md even says "don't mix two accents in one post". This template is the exception.

### Recommendation (needs Kyle's nod — it trades variety for fidelity)

Simplest faithful change, no engine work:

```json
"title":       { "colour_options": ["ss_green","ss_orange","ss_blue","ss_purple"], … },
"list_values": { "colour": "ss_green", … },     // was colour_options
"cta":         { "colour": "ss_green", … }      // was colour_options
```

The `accent` field then drives the title only, and prices/CTA are always brand green — exactly what
both references do. If Kyle wants the price colour to vary too, that needs a secondary-accent
concept in the engine (e.g. `accent_role: "secondary"` resolving `fields.accent_secondary`); worth
it only if a future ref shows a non-green price column.

---

## 5. P1 — row labels are half the reference's weight

`list_labels` uses `font_role: h3`, which for swing-shack is
`typography/fonts/Montserrat-ExtraLightItalic.ttf`. Ink coverage of `1X SESSION`, measured over the
same bounding box:

| source | ink coverage |
|---|---|
| **reference (ICC-corrected)** | **22.8 %** |
| current render | 10.9 % |
| Montserrat-ThinItalic @73px | 6.6 % |
| Montserrat-ExtraLightItalic @73px | 11.4 % ← what ships today |
| Montserrat-LightItalic @73px | 17.3 % |
| → extrapolated Montserrat-**Italic** (wght 400) | ~23 % ✔ |

Glyph widths confirm the size is right (`1X SESSION` renders 400–406 px unsquashed at 73 px;
reference is 369 px at `h_scale 0.9` → 410 × 0.9 = 369 ✔), so **only the weight is wrong**.

### The constraint

`h_scale` and size are fine; the problem is the role. `h3` is shared by **10 zones across 5
swing-shack archetypes** (`ss-did-you-know.kicker`, `ss-price-package.kicker`/`period`,
`ss-sale-offer.kicker`/`subline`/`cta`, `ss-lesson-corner.service_1..3`). Repointing the role would
change all of them. The `font_role` enum in `archetype_schema_data.json` is fixed
(`display, h1, h2, h3, body, caption, cta`), so a new role is not an option either.

### Recommendation — add a generic per-zone font override

This is the skill's prescribed route ("missing engine capability → add it generically"), and both
files are inside the implement job's declared paths.

1. **Vendor the font.** Variable cut from
   `github.com/google/fonts/raw/main/ofl/montserrat/Montserrat-Italic[wght].ttf`, then
   `fonttools varLib.instancer -q 'Montserrat-Italic[wght].ttf' wght=400 -o Montserrat-Italic.ttf`
   → `data/brand-directory/swing-shack/typography/fonts/Montserrat-Italic.ttf`.
   `OFL.txt` is already present for Montserrat.
2. **Schema** (`campaign-os/_lib/archetype_schema_data.json`): add an optional
   `"font_file": {"type": "string"}` to the zone properties — brand-relative path, overrides
   `font_role` when set.
3. **Engine** (`campaign-os/_lib/archetype_compose.py`, `_draw_text_zone`, line 407 — `role = str(zone.get("font_role") or "body")`): resolve
   `zone["font_file"]` through `_resolve_brand_relative` before falling back to the role lookup.
4. **Archetype**: `"list_labels": { …, "font_role": "h3", "font_file": "typography/fonts/Montserrat-Italic.ttf" }`
   (keep `font_role` as the fallback so nothing breaks if the file is missing).

**Fallback if Kyle wants zero engine change:** point `list_labels` at
`Montserrat-LightItalic` by the same mechanism, or accept the thin labels and log it. Accepting is
the weakest option — at 11 % vs 23 % the labels visibly wash out against the dimmed photo.

---

## 6. P2 — photo library stand-in has baked-in text

`background.library` is `templates/did-you-know/photos` (shared with `ss-did-you-know` and
`ss-price-package`). `standin-zen-stage.jpg` still carries the tail of a headline
("…CHANGES EVERYTHING") across its top edge plus a faint frame line from the post it was cropped
from. It shows through above the frame in `golden/render-instagram.png` and dominates the top of
the story render.

Cheapest fix: re-crop that stand-in below the text (roughly the top 40 px at 1081 wide) and
re-commit it. It lives under `data/brand-directory/swing-shack/`, inside the implement job's paths.
The other two stand-ins (`standin-putting.jpg`, `standin-sim-bay.jpg`) are clean.

Also worth raising with Kyle: all three are stand-in crops from existing posts. Raw, text-free
venue shots would retire this whole class of problem for three archetypes at once.

---

## 7. Operational gap — nothing in the repo writes `compose_price_labels` / `compose_price_values`

`_lib/compose_visual_copy.py:215-216` reads the row copy from the calendar record's sidecar:

```python
price_labels = str(sidecar.get("compose_price_labels") or "").strip()
price_values = str(sidecar.get("compose_price_values") or "").strip()
```

A repo-wide grep finds **no writer and no authoring UI** for those keys — no `compose_price_*`
anywhere in the HTML surfaces, no L5 create path that fills them. Verified behaviour with the
fields absent: `compose_post_for_channels` raises `ComposeError: missing text` rather than
rendering an empty card.

So today the selection rule can route a `post_type: price_list` record to this archetype and the
compose then **hard-fails** unless someone has hand-authored the sidecar. Safe (no broken image
ships) but it means the template cannot be auto-produced.

Not fixable inside this ticket's paths. Record it in `template.md` ("requires hand-authored
`compose_price_labels` / `compose_price_values` on the calendar record") and raise a follow-up
ticket for an authoring surface. `ss-price-package` has the same gap for `compose_price` /
`compose_qualifier` / `compose_price_period`.

---

## 8. What is already done — do not redo

| Item | State |
|---|---|
| Archetype `ss-price-list` in `visual-spec/archetypes.json` | ✔ present, in sync with the pack `spec.json` (only `measured_from` / `reference_size` differ, as intended) |
| Selection rule `price_list` / `package_list` / `rate_card` | ✔ present in `selection.rules` |
| `templates/price-list/references/ref-01,02.jpg` | ✔ correct files |
| `templates/price-list/spec.json` | ✔ with `measured_from` + `reference_size` |
| `templates/price-list/golden/` | ✔ `compare-refs.jpg`, `render-instagram.png`, `render-story.png` — **all need regenerating** after §3–§5 |
| Tests | ✔ `campaign-os/tests/test_ss_price_package_template.py` covers both archetypes — **8 passed** |
| Schema / selection tests | ✔ `campaign-os/tests/jobs/test_archetype_schema_v2.py` + `test_archetype_selection.py` — **5 passed** |
| Archetype count cap | ✔ swing-shack has 11, schema `maxItems` is 12 — no bump needed, but **only one slot is left** |
| `ig_post` + Facebook geometry | ✔ pixel-accurate |

> Tests live at `campaign-os/tests/jobs/…`, **not** `tests/jobs/…` as the skill's SKILL.md says.

---

## 9. Remaining pack / doc work

- `cases.json` — the pack has none; `compare_sheet.py` needs one entry per sorted ref:
  ```json
  [ {"caption_hook":"Coaching packages","price_labels":"1x session|3x sessions|5x sessions|10x sessions",
     "price_values":"R 820|R 2350|R 3850|R 7200","cta":"Book online or DM us","accent":"ss_blue"},
    {"caption_hook":"Coaching packages","price_labels":"1x session|3x sessions|5x sessions|10x sessions",
     "price_values":"R 820|R 2350|R 3850|R 7200","cta":"Book online or DM us","accent":"ss_blue"} ]
  ```
  (ref-02 is the story cut of the same campaign — same copy. Note ref-01's real CTA is
  `BOOK ONLINE OR DM US`; the committed golden used `DM US FOR DETAILS`, which is why the CTA
  differs in `compare-refs.jpg`.)
- `campaign-os/tools/render_ss_price_list.py` — missing; every sibling template has one. Copy
  `render_ss_price_package.py`, emit `golden/render-instagram.png` + `golden/render-story.png`.
- `golden/compare-refs.jpg` currently covers **one** of the two refs — rebuild it over both.
- `template.md` — thin (533 bytes) next to `did-you-know/template.md`. Add the sections that file
  has: **Intent**, **Anatomy** (use §2's measurements), **Platforms** table, **When to use**,
  **Copy budget** (4 rows max via `max_lines: 4`; `max_total_chars: 120`), **Photos**, **Don't**.
  Record the two-accent rule and the §7 sidecar requirement.
- `data/brand-directory/_system/POST_TYPE_SELECTION.md` — mentions neither `price_list` nor
  `price_package`. Add both.
- `agent-control/handoffs/campaign-os-template-taxonomy-review-20260927.md` — add the
  `**Built:** SS ss-price-list` line with branch + pack path + `post_type: price_list`.

### Test coverage to add

`test_ss_price_package_template.py` currently gives `ss-price-list` only three assertions
(`test_price_list_explicit_wrap_row_count`, `test_rate_list_renders`,
`test_post_type_price_list_selects_rate_card`). Bring it up to the `did-you-know` pattern:

- `test_price_list_platform_canvases` — instagram 1080×1350, instagram_story 1080×1920,
  facebook 1080×1350.
- **`test_price_list_story_url_not_clipped`** — the regression guard for §3. Render
  `instagram_story`, mask white pixels in the URL band and assert the bottom row is above
  `1920 - 34` (the frame inset). This test must fail on the current archetype.
- `test_price_list_value_column_not_clipped` — mask the accent colour, assert
  `cols.max() < 1080 - 36` with the longest realistic value (`R 12 500`).
- `test_price_list_rows_align` — label row tops and value row tops match within a few px.
- `test_price_list_accent_is_deterministic` — two renders byte-identical.
- If §4 lands: assert the title and the value column resolve to **different** colours.

Run `campaign-os/tests/test_ss_price_package_template.py`,
`campaign-os/tests/jobs/test_archetype_schema_v2.py`,
`campaign-os/tests/jobs/test_archetype_selection.py` and
`campaign-os/tests/test_stick_service_frame_renderer.py`. For the full suite, diff the failure list
against the base checkout — it carries ~160 pre-existing failures, so zero is not the bar. Revert
`feedback/image-performance.json` and `product-library.json` if the suite rewrites them.

---

## 10. Suggested order for the implement job

1. `canvas_overrides.ig_story` (§3) — the P0, and it is pure JSON.
2. Two-accent colours (§4) — pure JSON, but **get Kyle's nod first**; it locks prices to green.
3. Vendor `Montserrat-Italic.ttf` + `font_file` zone override (§5) — engine + schema + archetype.
4. Re-crop `standin-zen-stage.jpg` (§6).
5. `cases.json` + `tools/render_ss_price_list.py`; regenerate all three goldens.
6. Extend the tests (§9), including the story-clipping regression guard.
7. `template.md`, `POST_TYPE_SELECTION.md`, taxonomy handoff `Built:` line.
8. Push `feat/cos-tpl2-ss-price-list-pack-template` only. Show Kyle `golden/compare-refs.jpg`.

Open decisions for Kyle: **§4** (lock prices to green?) and **§5** (add the `font_file` override, or
settle for Montserrat LightItalic?). Everything else is unambiguous.

---

## Appendix — commands used

```bash
S=~/.agents/skills/campaign-os-template/scripts
python3 $S/measure_refs.py <refs>/*.jpg --json measured.json     # frame, lines, cap, pitch, accents
# live re-render (from campaign-os/):
python3 -c 'from _lib.archetypes import archetype_by_id; \
            from _lib.archetype_compose import compose_post_for_channels; ...'
python3 -m pytest campaign-os/tests/test_ss_price_package_template.py \
                  campaign-os/tests/jobs/test_archetype_schema_v2.py \
                  campaign-os/tests/jobs/test_archetype_selection.py -q    # 13 passed
```

Scratch artifacts (side-by-sides, zooms, fresh renders) are in this session's scratchpad and are
not committed.
