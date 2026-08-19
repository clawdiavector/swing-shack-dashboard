"""Walk the LIVE SEO Audit page and capture a screenshot of the score-card fix.

One-shot verification for the 2026-08-19 nightshift tick. Captures
/tmp/co-nightshift/walkthrough_seo_audit_score_fix_<TS>.png.

Run with:
  .venv/bin/python campaign-os/tests/walk_seo_audit_score_fix.py
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "campaign-os"))

LIVE_URL = "https://swing-shack-dashboard-production.up.railway.app"
PASSWORD = "swing-shack-dev-2026"
OUT_DIR = Path("/tmp/co-nightshift")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
        # Block the tour BEFORE the page even boots
        ctx.add_init_script("""
          try { localStorage.setItem('cos.tour.skipped', '1'); } catch(e) {}
        """)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(("pageerror", str(e))))
        page.on("console", lambda m: errors.append((m.type, m.text)) if m.type in ("error", "warning") else None)
        # Login (live URL first load returns login page)
        page.goto(LIVE_URL, wait_until="networkidle", timeout=20000)
        try:
            page.fill('input[name="password"], input[type="password"]', PASSWORD)
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            print(f"login skipped: {e}")
        # Wait for SPA to mount
        page.wait_for_timeout(2000)
        # Click the seo-audit nav — pick any visible nav (topbar OR sidebar)
        clicked = page.evaluate("""() => {
          const links = Array.from(document.querySelectorAll('[data-go="seo-audit"]'));
          for (const l of links) {
            const rect = l.getBoundingClientRect();
            const visible = rect.width > 0 && rect.height > 0 &&
                            getComputedStyle(l).display !== 'none' &&
                            l.offsetParent !== null;
            if (visible) { l.click(); return ['visible', l.outerHTML.slice(0,80)]; }
          }
          // fallback: click any
          if (links.length) { links[0].click(); return ['hidden', links[0].outerHTML.slice(0,80)]; }
          return ['none', ''];
        }""")
        print(f"clicked={clicked}")
        try:
            page.wait_for_function("""() => {
              const score = document.querySelector('#sa-score');
              return score && score.textContent.trim().length > 5 && !score.textContent.includes('skeleton');
            }""", timeout=15000)
        except Exception as e:
            print(f"wait_for_score timeout: {e}")
        page.wait_for_timeout(1500)
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        out = OUT_DIR / f"walkthrough_seo_audit_score_fix_{ts}.png"
        page.screenshot(path=str(out), full_page=True)
        # Extract the visible score + band
        info = page.evaluate("""() => {
          const scoreEl = document.querySelector('#sa-score div[style*="font-size:36px"]');
          const bandEl = document.querySelector('#sa-score .pill');
          const allText = document.querySelector('#sa-score') ? document.querySelector('#sa-score').textContent : '';
          return { score: scoreEl ? scoreEl.textContent.trim() : null,
                   band: bandEl ? bandEl.textContent.trim() : null,
                   allText: allText.replace(/\\s+/g, ' ').slice(0, 300) };
        }""")
        print(f"screenshot={out}")
        print(f"info={info}")
        print(f"errors_count={len(errors)}")
        if errors:
            for e in errors[:5]:
                print(f"  {e[0]}: {e[1][:200]}")
        browser.close()


if __name__ == "__main__":
    main()