#!/usr/bin/env python3
"""
Playwright walker part 2: confirm a PARTIAL agent row also drills correctly,
plus take an extra screenshot of a row that has outputs_invalid (we know
qa_inspector and hook_smith were PARTIAL on real data, so this will hit one
of them).
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
SCREEN = OUT / f"walkthrough_{TS}_agent_partial_open.png"

EM = "\u2014"


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

        page.goto(LIVE + "/campaign-os.html", wait_until="domcontentloaded")
        page.wait_for_selector("#sec-agents", state="attached", timeout=20000)
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
        page.evaluate("""() => {
            const nav = document.querySelector('.nav[data-go=agents]') || document.querySelector('[data-go=agents]');
            if(nav) nav.click();
        }""")
        page.wait_for_function("document.querySelector('#sec-agents')?.classList.contains('on')", timeout=20000)
        page.wait_for_function("document.querySelectorAll('#agents-list .li').length > 0", timeout=20000)
        page.wait_for_timeout(400)

        # Find the first PARTIAL row and click it
        partial = page.evaluate("""() => {
            const rows = [...document.querySelectorAll('#agents-list .li')];
            const idx = rows.findIndex(r => r.querySelector('.pill.review'));
            if(idx < 0) return null;
            const li = rows[idx];
            const id = li.querySelector('.li-title')?.textContent.trim() || '';
            li.click();
            return { idx, id };
        }""")
        assert partial, "no PARTIAL row found on live (expected qa_inspector or hook_smith)"
        print(f"clicked PARTIAL row #{partial['idx']}: {partial['id']!r}")
        page.wait_for_timeout(300)
        # capture the section screenshot
        page.screenshot(path=str(SCREEN), full_page=False)
        print(f"saved partial screenshot: {SCREEN}")

        # Read the detail text
        detail = page.evaluate("""() => {
            const open = document.querySelector('#agents-list .li.open');
            if(!open) return null;
            return {
                id: open.querySelector('.li-title')?.textContent.trim(),
                detail_text: open.querySelector('.li-detail')?.textContent.replace(/\\s+/g,' ').trim(),
                row_status: open.querySelector('.pill')?.textContent.trim() || '',
            };
        }""")
        assert detail, "no .li.open after click"
        assert detail["id"] == partial["id"], f"mismatch: clicked {partial['id']!r} but open is {detail['id']!r}"
        print(f"open detail: {detail['detail_text']!r}")
        # A PARTIAL row must NOT show 'All N scripts passed' (that would
        # contradict the row status and mislead the user). The data we
        # have here is 'analyse_hooks.js PASS' but row status is PARTIAL,
        # so the summary line must be suppressed. This is the regression
        # guard for the 'only-say-when-status-PASS' fix.
        if detail["row_status"].upper() == "PARTIAL":
            assert "All" not in (detail["detail_text"] or "") or "passed" not in (detail["detail_text"] or "").lower(), (
                f"PARTIAL row must NOT claim 'all scripts passed' — got: {detail['detail_text']!r}"
            )
            print(f"PASS: PARTIAL row suppresses misleading 'all scripts passed' summary")

        if errors:
            print(f"WARN: {len(errors)} console/page errors:")
            for e in errors[:5]:
                print("  -", e)
        b.close()
        return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
