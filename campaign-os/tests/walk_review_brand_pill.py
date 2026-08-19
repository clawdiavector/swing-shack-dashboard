"""v2026-08-19 — Playwright walk of the LIVE Review queue to confirm the
brand pill now renders on every row. Captures screenshot to /tmp/co-nightshift/.

Run: cd campaign-os && ../.venv/bin/python3 tests/walk_review_brand_pill.py
"""
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

LIVE_URL = "https://swing-shack-dashboard-production.up.railway.app/"
PASSWORD = "swing-shack-dev-2026"
SHOT_DIR = Path("/tmp/co-nightshift")
SHOT_DIR.mkdir(parents=True, exist_ok=True)


def login_and_walk(base_url):
    """Login + walk to Review tab. Returns the Playwright page + the screenshot path."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 1100})
        page = ctx.new_page()
        # Capture page errors for the report.
        errors = []
        page.on("pageerror", lambda exc: errors.append(("pageerror", str(exc))))
        page.on("console", lambda msg: msg.type == "error" and errors.append(("console", msg.text)))

        page.goto(base_url, wait_until="domcontentloaded", timeout=20000)
        # If we're bounced to /login, fill the password.
        if "/login" in page.url:
            page.fill("input[name=password]", PASSWORD)
            page.click("button[type=submit], button:has-text('Login'), button:has-text('Sign')")
            page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        # Click the Review nav.
        try:
            page.click("text=Review", timeout=5000)
        except Exception:
            page.goto(base_url + "?page=review", wait_until="domcontentloaded", timeout=10000)
        # Wait for the review-pending container to populate.
        try:
            page.wait_for_selector(".review[data-aid]", timeout=10000)
        except Exception:
            pass
        # Give the brandNames fetch + render a beat to settle.
        page.wait_for_timeout(800)
        # Probe each review row for the brand pill (the .pill.muted span with the
        # brand display name like "Swing Shack"). Old render was empty for all.
        rows = page.locator(".review[data-aid]").all()
        rows_with_pill = 0
        rows_with_brand_field = 0
        pill_texts = []
        for row in rows:
            cap = row.locator(".review-cap-t").first
            cap_html = cap.inner_html() if cap.count() else ""
            # The brand pill renders as <span class="pill muted">Swing Shack</span>
            if "<span class=\"pill muted\"" in cap_html and "Swing Shack" in cap_html:
                rows_with_pill += 1
            elif "pill muted" in cap_html:
                rows_with_pill += 1
                pill_texts.append(cap_html)
            # Fallback: at least the campaign id is visible
            if "·" in cap_html:
                rows_with_brand_field += 1
        # Also check the brand-names lookups
        brand_names_count = page.evaluate("""
            () => {
                // Trigger renderReview indirectly by inspecting the rows themselves
                // The pill text is what we care about
                const rows = document.querySelectorAll('.review[data-aid]');
                let withBrandText = 0;
                rows.forEach(r => {
                    const cap = r.querySelector('.review-cap-t');
                    if (cap && /Swing Shack/i.test(cap.textContent)) withBrandText++;
                });
                return withBrandText;
            }
        """)

        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        shot = SHOT_DIR / f"walkthrough_brand_pill_{ts}.png"
        try:
            page.screenshot(path=str(shot), full_page=False)
        except Exception as e:
            print(f"screenshot failed: {e}")
        browser.close()
        return {
            "url": base_url,
            "rows_total": len(rows),
            "rows_with_brand_pill": rows_with_pill,
            "rows_with_brand_text": brand_names_count,
            "pill_text_samples": pill_texts[:3],
            "errors": errors,
            "screenshot": str(shot),
        }


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else LIVE_URL
    print(f"Walking {target} …")
    result = login_and_walk(target)
    print()
    print("REVIEW ROW BRAND-PILL WALK")
    print(f"  url                       {result['url']}")
    print(f"  rows total                {result['rows_total']}")
    print(f"  rows with brand pill      {result['rows_with_brand_pill']}")
    print(f"  rows with 'Swing Shack'   {result['rows_with_brand_text']}")
    print(f"  errors                    {len(result['errors'])}")
    for kind, msg in result["errors"][:5]:
        print(f"    [{kind}] {msg[:200]}")
    print(f"  screenshot                {result['screenshot']}")
    if result["pill_text_samples"]:
        print("  pill samples:")
        for s in result["pill_text_samples"]:
            print(f"    {s[:160]}")