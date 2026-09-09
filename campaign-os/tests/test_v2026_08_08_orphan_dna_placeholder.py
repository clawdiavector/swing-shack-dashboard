"""Regression: orphan-DNA tiles must render a palette placeholder, not a broken img.

The /api/visual-library/swing-shack/images response includes an entry for
`takomo.png` (a .visual-dna.json record indexed under swing-shack but the
actual PNG lives under takomo/). Before this fix, the visualizer rendered
that tile as a black box and the modal opened onto a broken thumbnail.

After the fix:
  * the takomo tile shows a palette-swatch placeholder div
  * the placeholder carries data-fallback-reason="image-missing"
  * clicking the tile still opens the modal
  * the modal also shows the placeholder (not a broken <img>)
"""
from pathlib import Path
import sys, json, time
from playwright.sync_api import sync_playwright

BASE = "https://swing-shack-dashboard-production.up.railway.app"
OUT = Path("/tmp/co-nightshift")

def main():
    fail = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 1100})
        page = ctx.new_page()

        page.goto(f"{BASE}/login", wait_until="domcontentloaded", timeout=20000)
        page.fill("input#pw", "swing-shack-dev-2026")
        with page.expect_navigation(wait_until="domcontentloaded", timeout=20000):
            page.locator("button#submit-btn").click()

        page.goto(f"{BASE}/visualizer", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(3000)

        # The takomo tile should now contain an .img-placeholder, not an img.
        tile_state = page.evaluate("""
() => {
  const tile = document.querySelector('[data-filename="takomo.png"]');
  if(!tile) return {found:false};
  const img = tile.querySelector('img');
  const placeholder = tile.querySelector('.img-placeholder');
  return {
    found: true,
    hasBrokenImg: !!img,
    hasPlaceholder: !!placeholder,
    placeholderReason: placeholder ? placeholder.getAttribute('data-fallback-reason') : null,
    placeholderBg: placeholder ? getComputedStyle(placeholder).backgroundImage : null,
    placeholderText: placeholder ? (placeholder.querySelector('.ph-label')?.textContent || null) : null,
  };
}
""")
        print("tile_state:", json.dumps(tile_state, indent=2))
        if not tile_state.get("found"):
            fail.append("takomo tile not found in grid")
        if tile_state.get("hasBrokenImg"):
            fail.append("takomo tile still contains an <img> tag (not replaced by placeholder)")
        if not tile_state.get("hasPlaceholder"):
            fail.append("takomo tile missing .img-placeholder")
        if tile_state.get("placeholderReason") != "image-missing":
            fail.append(f"placeholder reason wrong: {tile_state.get('placeholderReason')}")

        # Open the modal for the orphan tile
        page.locator('[data-filename="takomo.png"]').first.click()
        page.wait_for_selector('#modal-bg.open', timeout=5000)
        page.wait_for_timeout(800)
        modal_state = page.evaluate("""
() => {
  const img = document.getElementById('modal-img');
  const placeholder = document.querySelector('.modal .img-placeholder, .modal .imgwrap .img-placeholder');
  return {
    imgSrc: img ? img.src : null,
    imgNaturalWidth: img ? img.naturalWidth : null,
    hasModalPlaceholder: !!placeholder,
    placeholderReason: placeholder ? placeholder.getAttribute('data-fallback-reason') : null,
  };
}
""")
        print("modal_state:", json.dumps(modal_state, indent=2))
        if modal_state.get("hasModalPlaceholder") is not True:
            fail.append("modal did not render the placeholder for takomo.png")

        # Capture proof
        page.screenshot(path=str(OUT / f"after_takomo_modal_{int(time.time())}.png"))
        # Close modal
        page.locator('#modal-close').click()
        page.wait_for_timeout(400)
        page.locator('[data-filename="takomo.png"]').first.screenshot(path=str(OUT / f"after_takomo_tile_{int(time.time())}.png"))

        # Now confirm the home brand-detail panel also has the fallback armed
        page.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2500)
        armed = page.evaluate("() => typeof window.__coImgFallbackInstalled === 'boolean' && window.__coImgFallbackInstalled")
        print("home installed:", armed)
        if not armed:
            fail.append("campaign-os.html did not install __coImgFallbackInstalled")

        browser.close()

    if fail:
        print("FAIL:")
        for f in fail:
            print("  -", f)
        sys.exit(1)
    print("PASS: orphan-DNA placeholder works in both visualizer tile and modal.")

if __name__ == "__main__":
    main()
