#!/usr/bin/env python3
"""
Playwright walker: Data freshness help tooltip on the LIVE Railway URL.

Verifies commit 4f5033d is served: the Agents-page "Data freshness" card's
help tooltip carries the actionable decision rule, has no em-dash, and no
longer carries the internal changelog note. Opens the tooltip by clicking the
h3 so the screenshot shows what Christelle actually sees.
"""
from __future__ import annotations
import os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

LIVE = "https://swing-shack-dashboard-production.up.railway.app"
SHARED_PASSWORD = os.environ.get("CO_SHARED_PASSWORD", "swing-shack-dev-2026")
OUT = Path("/tmp/co-nightshift")
OUT.mkdir(parents=True, exist_ok=True)
TS = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
SCREEN = OUT / f"walkthrough_{TS}_freshness_help.png"

EM = "\u2014"
ACTIONABLE = ("If a feed shows up as rotten here, treat any recommendation "
              "built on it as unreliable until it refreshes.")
BANNED = ["This card used to live on the home", "moved here where fleet"]


def main() -> int:
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console.error: {m.text}") if m.type == "error" else None)

        page.goto(LIVE + "/login", wait_until="domcontentloaded")
        page.wait_for_selector("input[name=password], input[type=password]", timeout=20000)
        page.fill("input[name=password], input[type=password]", SHARED_PASSWORD)
        page.press("input[name=password], input[type=password]", "Enter")
        page.wait_for_url(lambda u: "/login" not in u, timeout=25000)
        print(f"login ok -> {page.url}")

        page.goto(LIVE + "/campaign-os.html", wait_until="domcontentloaded")
        page.wait_for_selector("#sec-agents", state="attached", timeout=20000)

        # suppress the welcome tour overlay (TOUR_KEY = 'cos.tour.skipped',
        # overlay is #welcome-bg toggled by the .on class)
        page.evaluate("""() => {
            try { localStorage.setItem('cos.tour.skipped','1'); } catch(e){}
            const bg = document.querySelector('#welcome-bg');
            if(bg) bg.classList.remove('on');
        }""")
        page.wait_for_timeout(900)
        page.evaluate("""() => {
            const bg = document.querySelector('#welcome-bg');
            if(bg) bg.classList.remove('on');
        }""")

        clicked = page.evaluate("""() => {
            const nav = document.querySelector(".nav[data-go=agents]") || document.querySelector("[data-go=agents]");
            if(!nav) return false; nav.click(); return true;
        }""")
        assert clicked, "Agents nav element not found"
        page.wait_for_function("document.querySelector('#sec-agents')?.classList.contains('on')", timeout=20000)

        # read the served help attribute
        help_text = page.evaluate("""() => {
            const hs = [...document.querySelectorAll('h3[data-help]')]
                .filter(h => h.getAttribute('data-help').includes('Per-file age check'));
            return hs.length === 1 ? hs[0].getAttribute('data-help') : `COUNT=${hs.length}`;
        }""")
        print(f"served help len={len(help_text)}")
        assert "Per-file age check" in help_text, f"freshness help not found: {help_text!r}"
        assert ACTIONABLE in help_text, "actionable sentence NOT served (deploy lag?)"
        assert EM not in help_text, "em-dash still served in freshness help"
        for frag in BANNED:
            assert frag not in help_text, f"changelog phrasing still served: {frag!r}"
        print("PASS: actionable sentence served, 0 em-dashes, 0 changelog phrasing")

        # global check: no static h3 data-help on the served page has an em-dash
        offenders = page.evaluate("""() => [...document.querySelectorAll('h3[data-help]')]
            .map(h => h.getAttribute('data-help'))
            .filter(v => v.includes('\\u2014'))
            .map(v => v.slice(0,90))""")
        print(f"h3 data-help em-dash offenders on live: {len(offenders)}")
        for o in offenders:
            print("  OFFENDER:", o)

        # open the tooltip for the screenshot. The help pop is HOVER-driven
        # (HELP.tip attaches mouseenter/mouseleave, NOT click), so a
        # synthetic .click() does nothing. Use a real Playwright hover.
        page.evaluate("""() => {
            const h = [...document.querySelectorAll('h3[data-help]')]
                .find(h => h.getAttribute('data-help').includes('Per-file age check'));
            if(h){ h.scrollIntoView({block:'center'}); }
        }""")
        page.wait_for_timeout(500)
        h3 = page.locator("h3[data-help*='Per-file age check']").first
        h3.hover()
        page.wait_for_timeout(1200)
        pop_visible = page.evaluate("""() => {
            const p = document.querySelector('.help-pop, .help-pop.on, #help-pop');
            if(!p) return 'NO_POP_EL';
            const r = p.getBoundingClientRect();
            return (r.width > 0 && r.height > 0) ? (p.innerText||'').slice(0,120) : 'POP_HIDDEN';
        }""")
        print(f"tooltip on hover: {pop_visible!r}")
        page.screenshot(path=str(SCREEN), full_page=False)
        print(f"screenshot: {SCREEN}")

        real_errors = [e for e in errors if "favicon" not in e.lower()]
        print(f"page/console errors: {len(real_errors)}")
        for e in real_errors[:8]:
            print("  ", e)

        b.close()
        return 0 if not offenders else 1


if __name__ == "__main__":
    sys.exit(main())
