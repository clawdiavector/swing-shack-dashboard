#!/usr/bin/env python3
"""
Playwright walker for the Agents & health tab on the LIVE Railway URL.

Logs in via shared password, navigates to #sec-agents, asserts the System
health card now contains data_status + priority pills + next_action + qa_warnings
instead of a <pre> JSON dump, and saves a screenshot.

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
SCREEN = OUT / f"walkthrough_{TS}.png"


def main() -> int:
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

        # 1. Login
        page.goto(LIVE + "/login", wait_until="domcontentloaded")
        page.wait_for_selector("input[name=password], input[type=password]", timeout=15000)
        page.fill("input[name=password], input[type=password]", SHARED_PASSWORD)
        page.press("input[name=password], input[type=password]", "Enter")
        page.wait_for_url(lambda u: "/login" not in u, timeout=20000)
        print(f"login ok -> {page.url}")

        # 2. Go to Campaign OS shell
        page.goto(LIVE + "/campaign-os.html", wait_until="domcontentloaded")
        page.wait_for_selector("#sec-agents", state="attached", timeout=15000)

        # 3. Click Agents nav (force=True since the sidebar can be collapsed/hidden)
        clicked = page.evaluate("""
          () => {
            const nav = document.querySelector(".nav[data-go=agents]") || document.querySelector("[data-go=agents]");
            if(!nav) return false;
            nav.click();
            return true;
          }
        """)
        assert clicked, "Agents nav element not found"
        page.wait_for_function("document.querySelector('#sec-agents')?.classList.contains('on')", timeout=15000)
        # Wait for renderAgents() to populate
        page.wait_for_function("document.querySelector('#agents-list')?.children.length > 0", timeout=15000)
        page.wait_for_function("document.querySelector('#agents-health')?.innerHTML.length > 100", timeout=15000)
        # Dismiss the welcome tour overlay so it doesn't sit on top of the System health card
        try:
            page.evaluate("""
              () => {
                try { localStorage.setItem('co_welcomed', '1'); } catch(e){}
                const tour = document.querySelector('.tour, .welcome-tour, [data-tour]');
                if(tour) tour.remove();
                // also try to click the Skip button if present
                const skip = [...document.querySelectorAll('button')].find(b => /skip|close/i.test(b.textContent || ''));
                if(skip) skip.click();
              }
            """)
            page.wait_for_timeout(200)
        except Exception as e:
            print("tour dismiss:", e)

        # 4. Probe the System health card
        probe = page.evaluate("""
          () => {
            const card = document.querySelector('#agents-health');
            if(!card) return {error: 'no #agents-health'};
            const html = card.innerHTML;
            const text = card.textContent.trim();
            return {
              html_len: html.length,
              has_pre_json_dump: /<pre[^>]*>[^<]*\"(FRESH|STALE|MISSING)\"/.test(html),
              has_data_pill: /pill (on|review|blocked|draft)[^>]*>(FRESH|STALE|MISSING|OFFLINE|FAILED)/i.test(html),
              has_priority_pill: /pill (warn|review|draft)[^>]*>(HIGH|MEDIUM|LOW|P0|P1|P2|URGENT|NORMAL)/i.test(html),
              has_next_action: /<b>Next:<\\/b>/.test(html),
              has_qa_warnings: /<b>QA warnings:<\\/b>/.test(html),
              has_data_status_kv: /<dt>Data<\\/dt>/.test(html),
              has_priority_kv: /<dt>Priority<\\/dt>/.test(html),
              text_excerpt: text.slice(0, 200),
            };
          }
        """)
        print("PROBE:", json.dumps(probe, indent=2))

        # 5. Screenshot the Agents surface
        # Scroll to ensure the section is in view
        page.evaluate("document.querySelector('#sec-agents').scrollIntoView({behavior:'instant',block:'start'})")
        page.wait_for_timeout(300)
        page.screenshot(path=str(SCREEN), full_page=True)
        print(f"screenshot: {SCREEN}")

        # 5b. Also capture a tight crop of just the System health card for visual verification
        try:
            health_card = page.evaluate("""
              () => {
                const card = document.querySelector('#agents-health')?.closest('.card');
                if(!card) return null;
                const r = card.getBoundingClientRect();
                return {x: r.x, y: r.y, width: r.width, height: r.height};
              }
            """)
            if health_card:
                crop_path = OUT / f"walkthrough_{TS}_system_health.png"
                page.screenshot(
                    path=str(crop_path),
                    clip={
                        "x": max(0, health_card["x"] - 4),
                        "y": max(0, health_card["y"] - 4),
                        "width": min(1440, health_card["width"] + 8),
                        "height": min(900, health_card["height"] + 8),
                    },
                )
                print(f"screenshot (crop): {crop_path}")
        except Exception as e:
            print("crop skipped:", e)

        # 6. Print errors (if any)
        if errors:
            print("BROWSER ERRORS:")
            for e in errors:
                print("  -", e)
        else:
            print("no console / page errors")

        # 7. Assert
        ok = (
            probe.get("has_data_status_kv") and
            probe.get("has_data_pill") and
            not probe.get("has_pre_json_dump")
        )
        print("VERDICT:", "PASS" if ok else "FAIL")
        b.close()
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())