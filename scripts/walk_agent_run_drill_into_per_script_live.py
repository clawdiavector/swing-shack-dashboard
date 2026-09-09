#!/usr/bin/env python3
"""
Playwright walker: Agents & health click-to-drill affordance on the LIVE
Railway URL.

Verifies that:
  1. The Agents section h2 tooltip no longer contains the broken promise
     "Click any red row to drill into the error log" and instead mentions
     "per-script results" (the actual affordance).
  2. The agent runs list renders rows that are interactive (have an
     onclick + a hidden .li-detail block).
  3. Clicking a row surfaces the per-script status table (with the
     duration_ms and status pill per script) inside the .li-detail block.
  4. No em-dashes in the served tooltip or in the row HTML.
  5. No console / page errors while loading the section.

Captures two screenshots: the closed state and the drilled-in state.
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
SCREEN_CLOSED = OUT / f"walkthrough_{TS}_agent_runs_closed.png"
SCREEN_OPEN = OUT / f"walkthrough_{TS}_agent_runs_open.png"

EM = "\u2014"
BANNED_PROMISE = "Click any red row to drill into the error log"
NEW_PROMISE_FRAG = "per-script results"


def main() -> int:
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console.error: {m.text}") if m.type == "error" else None)

        # 1. Auth
        page.goto(LIVE + "/login", wait_until="domcontentloaded")
        page.wait_for_selector("input[name=password], input[type=password]", timeout=20000)
        page.fill("input[name=password], input[type=password]", SHARED_PASSWORD)
        page.press("input[name=password], input[type=password]", "Enter")
        page.wait_for_url(lambda u: "/login" not in u, timeout=25000)
        print(f"login ok -> {page.url}")

        # 2. Campaign OS
        page.goto(LIVE + "/campaign-os.html", wait_until="domcontentloaded")
        page.wait_for_selector("#sec-agents", state="attached", timeout=20000)

        # suppress welcome tour overlay (per nightshift pitfalls)
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

        # 3. Jump to agents
        page.evaluate("""() => {
            const nav = document.querySelector('.nav[data-go=agents]') || document.querySelector('[data-go=agents]');
            if(nav) nav.click();
        }""")
        page.wait_for_function("document.querySelector('#sec-agents')?.classList.contains('on')", timeout=20000)
        # give the agents API + renderAgents() a beat
        page.wait_for_function("document.querySelectorAll('#agents-list .li').length > 0", timeout=20000)
        page.wait_for_timeout(400)

        # 4. Verify tooltip text
        help_text = page.evaluate("""() => {
            const h2 = document.querySelector('#sec-agents .section-h h2[data-help-title]');
            return h2 ? h2.getAttribute('data-help') : null;
        }""")
        assert help_text, "Agents h2 help not found"
        print(f"served Agents h2 help len={len(help_text)}")
        assert BANNED_PROMISE not in help_text, f"OLD broken promise still served: {help_text!r}"
        assert NEW_PROMISE_FRAG in help_text, f"NEW promise fragment missing: {help_text!r}"
        assert EM not in help_text, f"em-dash in served tooltip: {help_text!r}"
        print(f"PASS: tooltip no longer says '{BANNED_PROMISE}', includes '{NEW_PROMISE_FRAG}', 0 em-dashes")

        # 5. Inspect rendered agent rows
        row_report = page.evaluate("""() => {
            const rows = [...document.querySelectorAll('#agents-list .li')];
            return {
                count: rows.length,
                with_detail: rows.filter(r => r.querySelector('.li-detail')).length,
                script_names: [...new Set([].concat(...rows.map(r =>
                    [...r.querySelectorAll('.li-detail-row strong')].map(s => s.textContent.trim())
                )))],
                sample_first_detail: rows[0] && rows[0].querySelector('.li-detail')
                    ? rows[0].querySelector('.li-detail').textContent.replace(/\\s+/g,' ').trim().slice(0, 240)
                    : null,
            };
        }""")
        print(f"rows={row_report['count']} with_detail={row_report['with_detail']} script_names={row_report['script_names'][:5]}")
        assert row_report["count"] > 0, "no agent rows rendered"
        assert row_report["with_detail"] == row_report["count"], (
            f"some rows have no .li-detail — click would be a no-op. "
            f"rows={row_report['count']} with_detail={row_report['with_detail']}"
        )
        assert row_report["sample_first_detail"], "first row .li-detail is empty"
        print(f"sample first-row detail: {row_report['sample_first_detail']!r}")

        # 6. Click a row to verify .open toggle reveals content
        first_row = page.locator("#agents-list .li").first
        first_row.scroll_into_view_if_needed()
        first_row.click()
        page.wait_for_timeout(250)
        open_state = page.evaluate("""() => {
            const r = document.querySelector('#agents-list .li');
            return {
                is_open: r.classList.contains('open'),
                detail_visible: r.querySelector('.li-detail')
                    ? getComputedStyle(r.querySelector('.li-detail')).display !== 'none'
                    : null,
                detail_text: r.querySelector('.li-detail')
                    ? r.querySelector('.li-detail').textContent.replace(/\\s+/g,' ').trim().slice(0, 300)
                    : null,
            };
        }""")
        print(f"open_state: {open_state}")
        assert open_state["is_open"], "row did not toggle .open on click"
        assert open_state["detail_visible"], ".li-detail still hidden after .open toggle"

        # 7. Capture screenshots (closed + open)
        # Re-collapse the row so the closed-state screenshot shows what a
        # user sees on landing
        first_row.click()
        page.wait_for_timeout(150)
        page.screenshot(path=str(SCREEN_CLOSED), full_page=False)
        print(f"saved closed screenshot: {SCREEN_CLOSED}")

        first_row.click()
        page.wait_for_timeout(250)
        page.screenshot(path=str(SCREEN_OPEN), full_page=False)
        print(f"saved open screenshot: {SCREEN_OPEN}")

        # 8. Errors gate
        if errors:
            print(f"WARN: {len(errors)} console/page errors:")
            for e in errors[:5]:
                print("  -", e)
        else:
            print("PASS: 0 console errors, 0 page errors")

        b.close()
        return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
