---
name: image-scout
description: >-
  Find official, good-quality product images online for what the weekly stock list says is missing
  a photo, check them, save them for approval, and list what has to be shot in store. Use when a
  weekly stock list arrives, when asked to source product images, find a product photo, fill the
  photo gaps, or scout images for Swing Shack or Stick. Never generates or redraws a product.
---

# Image scout

Christelle's rule (2026-10-15): find official images online, or we take them in person. Do not email
suppliers. Products are real and golf is model-specific, so the exact make and model matters.

Standing yes (2026-10-15): the scout may download official-site images of products on the stock
list. Every file still waits as `needs-check` until a person approves it. Ask again if the scope grows.

## The loop (weekly, after the stock list is loaded)

1. **What is missing.**
   `python campaign-os/scripts/image_scout_cli.py gaps --brand <brand> --csv <stock.csv>`
   (products with no photo and no candidate; drinks, food and fitting shafts are already left out).
2. **Find each one at the maker.** Read `data/brand-directory/_system/image-sources.json` first: it says
   where each brand's official images live and what blocks plain fetches. Use the built-in browser pane
   for sites that return 403. Shopify sites: `/products.json` gives every image at full size.
3. **Record it.** Write a found.json (`sku`, `product`, `page_url`, `image_url`, `note`, `exact_build`) and
   `image_scout_cli.py add --brand <brand> --file found.json`. Use `exact_build=false` when the stock line is a
   custom build or a different year than the image.
4. **Check and save.** `image_scout_cli.py fetch --brand <brand> --images <images folder>`. The gate rejects
   non-images and anything under 800px; files under 1500px are noted for the faithful Topaz upscale.
   Saved files are named `SKU__front.<ext>` and sit on the photo map as `needs-check`.
5. **Look at them.** `scripts/photo_contact_sheet.py --brand <brand> --out sheet.png`, then view it. Page
   titles lie (Callaway). Confirm each picture is the model its label says.
6. **Tell Christelle** what was found, what is blocked, and what cannot be found online (the shot list).
   She approves with `photo_map_cli.py approve`.

## Rules

- Maker's own page first. Never a retailer's copy with their watermark, never generated or redrawn.
- A standard image of a custom build is marked, not hidden.
- Update `image-sources.json` with anything new you learn about a brand's site.
- Do not relay image bytes through a local server or any other workaround when a site blocks downloads
  (a try on 2026-10-15 was denied). Record the candidate as `blocked` and say so.
- Keep to one brand's folder at a time; never file Stick's photos under Swing Shack.

## What usually cannot be found online

Own-brand items (Stick towels, ball markers, snapbacks; Swing Shack custom drivers), custom builds
(L.A.B. shaft/colour), discontinued models, sleeve shots (sites show dozens), unbranded lines, and
apparel colour/size combinations. These go on the in-store shot list (`Save the new photo as` column).

## Related
`campaign-os-map` (what exists), `krea-lab` (faithful enhance only, never generate a product), wiki runbook
`sku-named-product-photos-2026-10-15`.
