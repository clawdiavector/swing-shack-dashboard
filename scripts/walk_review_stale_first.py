#!/usr/bin/env python3
"""Visual walk of the Review tab after the stale-first sort fix.
Captures the new ordering to /tmp/co-nightshift/.
"""
from __future__ import annotations
import os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("/tmp/co-nightshift")
OUT.mkdir(parents=True, exist_ok=True)
TS = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
PWD = "swing-shack-dev-2026"

with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    errors = []
    console = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: console.append(f"{m.type}: {m.text}") if m.type == "error" else None)

    page.goto("http://127.0.0.1:8765/campaign-os", wait_until="domcontentloaded")
    page.wait_for_selector("input[type=password]", timeout=10000)
    page.fill("input[type=password]", PWD)
    page.press("input[type=password]", "Enter")
    page.wait_for_load_state("domcontentloaded", timeout=8000)
    page.wait_for_timeout(500)

    # Dismiss welcome
    try:
        page.locator("button.welcome-skip").first.click(timeout=1500)
        page.wait_for_timeout(200)
    except Exception:
        pass

    # Expand sidebar
    page.evaluate("""
        document.querySelectorAll('.nav-group-h[aria-expanded="false"]').forEach(h => h.click());
    """)
    page.wait_for_timeout(300)

    # Click Review
    page.locator(".nav[data-go='review']").first.click()
    page.wait_for_timeout(800)

    # Capture first viewport screenshot
    shot1 = OUT / f"walkthrough_{TS}_review_stale_first_top.png"
    page.screenshot(path=str(shot1), full_page=False)
    print(f"Saved {shot1}")

    # Capture full page
    shot2 = OUT / f"walkthrough_{TS}_review_stale_first_full.png"
    page.screenshot(path=str(shot2), full_page=True)
    print(f"Saved {shot2}")

    # Extract the visible ordering of pending rows
    rows = page.evaluate("""
        () => {
            const items = document.querySelectorAll('#review-pending .review');
            return Array.from(items).slice(0, 8).map(el => {
                const t = el.querySelector('.review-cap-t');
                const age = el.querySelector('.pill.review, .pill.blocked, .pill.on');
                return {
                    text: (t?.innerText || '').trim().slice(0, 80),
                    agePill: (age?.innerText || '').trim(),
                };
            });
        }
    """)
    print("\nFIRST 8 ROWS (top of pending list):")
    for i, r in enumerate(rows):
        print(f"  {i+1}. [{r['agePill']}] {r['text']}")

    print(f"\nPageErrors: {len(errors)}")
    print(f"ConsoleErrors: {len(console)}")
    b.close()