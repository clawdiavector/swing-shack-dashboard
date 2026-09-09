"""v2026-08-19 — Playwright walk of the LIVE Trends section to confirm
the new sub (signal radar + 4 source panels + 1-line why-now) renders
on first paint and carries the data-help anchor. Captures screenshot to
/tmp/co-nightshift/.

Run: cd campaign-os && ../.venv/bin/python3 tests/walk_trends_sub_fix.py
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
    """Login + walk to Trends tab. Returns probe state + screenshot path."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 1100})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(("pageerror", str(exc))))
        page.on(
            "console",
            lambda msg: msg.type == "error" and errors.append(("console", msg.text)),
        )

        page.goto(base_url, wait_until="domcontentloaded", timeout=20000)
        if "/login" in page.url:
            page.fill("input[name=password]", PASSWORD)
            page.click(
                "button[type=submit], button:has-text('Login'), button:has-text('Sign')"
            )
            page.wait_for_url(lambda u: "/login" not in u, timeout=15000)

        # Dismiss any welcome modal so it doesn't cover the screenshot.
        try:
            page.evaluate("""
                () => {
                    document.querySelectorAll('.modal-backdrop, .modal, .welcome-modal, [data-tour]').forEach(el => el.remove());
                    localStorage.setItem('cos.tour.skipped', '1');
                    localStorage.setItem('cos.tour.dismissed', '1');
                }
            """)
            try:
                page.click("text=Skip the tour", timeout=2000)
                page.wait_for_timeout(400)
            except Exception:
                pass
        except Exception:
            pass

        # Expand sidebar nav groups so Trends link is clickable.
        try:
            page.evaluate("""
                () => {
                    document.querySelectorAll('.nav-group, .nav[data-go]').forEach(el => {
                        if (el.classList.contains('collapsed')) el.classList.remove('collapsed');
                    });
                }
            """)
        except Exception:
            pass

        # Navigate to Trends section.
        try:
            page.click("[data-go=trends]", timeout=5000)
        except Exception:
            page.goto(base_url + "?page=trends", wait_until="domcontentloaded", timeout=10000)

        # Wait for the section header + the tr-summary element.
        page.wait_for_selector("#sec-trends", timeout=10000)
        page.wait_for_selector("#tr-summary", timeout=10000)
        # Let the dynamic section content paint.
        page.wait_for_timeout(1200)

        # Scroll to the Trends section header so the screenshot frames it.
        try:
            page.evaluate("""
                () => {
                    const sec = document.getElementById('sec-trends');
                    if (sec) sec.scrollIntoView({block: 'start', behavior: 'instant'});
                }
            """)
            page.wait_for_timeout(400)
        except Exception:
            pass

        # Probe the static sub state.
        sub_state = page.evaluate("""
            () => {
                const el = document.getElementById('tr-summary');
                if (!el) return {found: false};
                return {
                    found: true,
                    text: el.textContent.trim(),
                    has_data_help: el.hasAttribute('data-help'),
                    has_data_help_title: el.hasAttribute('data-help-title'),
                    data_help_title: el.getAttribute('data-help-title'),
                    section_header_visible: !!document.querySelector('#sec-trends h2'),
                };
            }
        """)

        # Probe the trends sub-cards so we know the screenshot frames the full surface.
        sub_cards = page.evaluate("""
            () => {
                const sec = document.getElementById('sec-trends');
                if (!sec) return [];
                const titles = [];
                sec.querySelectorAll('h3').forEach(h => {
                    const t = (h.textContent || '').trim();
                    if (t) titles.push(t);
                });
                return titles;
            }
        """)

        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        shot = SHOT_DIR / f"walkthrough_trends_sub_{ts}.png"
        try:
            page.screenshot(path=str(shot), full_page=False)
        except Exception as e:
            print(f"screenshot failed: {e}")
        browser.close()
        return {
            "url": base_url,
            "sub": sub_state,
            "sub_cards": sub_cards,
            "errors": errors,
            "screenshot": str(shot),
        }


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else LIVE_URL
    print(f"Walking {target} …")
    result = login_and_walk(target)
    print()
    print("TRENDS SUB FIX WALK")
    print(f"  url                          {result['url']}")
    s = result["sub"]
    print(f"  sub found                    {s.get('found')}")
    print(f"  sub text (first 140 chars)   {s.get('text','')[:140]}")
    print(f"  has data-help                {s.get('has_data_help')}")
    print(f"  has data-help-title          {s.get('has_data_help_title')}")
    print(f"  data-help-title value        {s.get('data_help_title')}")
    print(f"  Trends section-h visible     {s.get('section_header_visible')}")
    print()
    print("  sub-card titles found in Trends:")
    for c in result["sub_cards"]:
        print(f"    - {c}")
    print(f"  errors                       {len(result['errors'])}")
    for kind, msg in result["errors"][:5]:
        print(f"    [{kind}] {msg[:200]}")
    print(f"  screenshot                   {result['screenshot']}")
