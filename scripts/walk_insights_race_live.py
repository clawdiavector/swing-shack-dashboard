#!/usr/bin/env python3
"""
Playwright walker for the Insights V2 re-entry race fix on the LIVE Railway URL.

Logs in, triggers the race (navigate Insights -> away -> back within the async
fetch window), and asserts that no pageerror fires.

The fix: renderInsightsV2() snapshots a per-section render token at entry and
bails silently after the awaited Promise.all resolves if a newer render has
taken over. Pre-fix the second invocation overwrites sec.innerHTML, wiping the
first invocation's `#ins-ig-count`/`#ins-v2-summary` DOM nodes, so when the
first invocation's Promise.all resolves it throws
   TypeError: Cannot set properties of null (setting 'textContent')
on `$('#ins-ig-count').textContent = ...`.

Run from repo root with the venv active.
"""
from __future__ import annotations
import os, sys, json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

LIVE = "https://swing-shack-dashboard-production.up.railway.app"
SHARED_PASSWORD = os.environ.get("CO_SHARED_PASSWORD", "swing-shack-dev-2026")
OUT = Path("/tmp/co-nightshift")
OUT.mkdir(parents=True, exist_ok=True)
TS = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
SCREEN = OUT / f"walkthrough_{TS}_insights_race.png"


def main() -> int:
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on(
            "console",
            lambda m: errors.append(f"console.{m.type}: {m.text}")
            if m.type == "error" else None,
        )

        # 1. Login
        page.goto(LIVE + "/login", wait_until="domcontentloaded")
        page.wait_for_selector("input[name=password], input[type=password]", timeout=15000)
        page.fill("input[name=password], input[type=password]", SHARED_PASSWORD)
        page.press("input[name=password], input[type=password]", "Enter")
        page.wait_for_url(lambda u: "/login" not in u, timeout=20000)
        print(f"login ok -> {page.url}")

        # 2. Open Campaign OS
        page.goto(LIVE + "/campaign-os.html", wait_until="domcontentloaded")
        page.wait_for_selector("#sec-insights", state="attached", timeout=15000)
        # Dismiss welcome tour if present
        page.evaluate(
            """() => {
              try { localStorage.setItem('co_welcomed', '1'); } catch(e){}
              const skip = [...document.querySelectorAll('button')].find(b => /skip|close/i.test(b.textContent || ''));
              if(skip) skip.click();
            }"""
        )
        page.wait_for_timeout(800)

        # 3. Pre-fix check: trigger the race (Insights -> away -> back within fetch window)
        # Each round-trip below causes the SPA to call renderInsightsV2() while a
        # previous instance's Promise.all is still resolving.
        for round_n in range(5):
            page.evaluate('go("insights")')
            page.wait_for_timeout(80)
            page.evaluate('go("hooks")')
            page.wait_for_timeout(80)
            page.evaluate('go("insights")')
            page.wait_for_timeout(80)
            page.evaluate('go("memes")')
            page.wait_for_timeout(80)
            page.evaluate('go("insights")')
            page.wait_for_timeout(1500)
            print(f"  round {round_n+1}: pageerrors so far = {sum(1 for e in errors if 'pageerror' in e)}")

        # 4. Wait for the final render to settle, then probe DOM.
        page.evaluate('go("insights")')
        page.wait_for_timeout(4000)

        probe = page.evaluate(
            """() => {
              const sec = document.querySelector("#sec-insights");
              const body = document.querySelector("#ins-v2-body");
              const igCount = document.querySelector("#ins-ig-count");
              const token = sec ? sec.dataset.insRenderToken : null;
              return {
                sec_text_len: sec ? sec.textContent.length : -1,
                body_html_len: body ? body.innerHTML.length : -1,
                ig_count_text: igCount ? igCount.textContent : null,
                ins_render_token: token,
                still_loading: body && body.textContent.includes("Loading"),
              };
            }"""
        )
        print("FINAL PROBE:", json.dumps(probe, indent=2))

        # 5. Assertions
        page_errors = [e for e in errors if e.startswith("pageerror")]
        ins_related = [e for e in page_errors if "renderInsightsV2" in e]
        print(f"\npage errors total: {len(page_errors)}")
        print(f"insights-related pageerrors: {len(ins_related)}")
        if ins_related:
            print("\n!!! INSIGHTS PAGEERRORS DETECTED:")
            for e in ins_related:
                print(" ", e)

        # 6. Screenshot
        page.screenshot(path=str(SCREEN), full_page=True)
        # Tight-crop of the Insights section header
        sec_box = page.evaluate(
            """() => {
              const sec = document.querySelector("#sec-insights");
              if(!sec) return null;
              const r = sec.getBoundingClientRect();
              return {x: r.left, y: r.top, width: r.width, height: Math.min(r.height, 800)};
            }"""
        )
        if sec_box:
            page.screenshot(
                path=str(OUT / f"walkthrough_{TS}_insights_zoom.png"),
                clip=sec_box,
            )

        print(f"\nscreenshot saved: {SCREEN}")
        ok = (
            len(ins_related) == 0
            and probe["sec_text_len"] > 1500
            and probe["still_loading"] is False
            and probe["ig_count_text"] is not None
        )
        print("OK" if ok else "FAILED")
        b.close()
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())