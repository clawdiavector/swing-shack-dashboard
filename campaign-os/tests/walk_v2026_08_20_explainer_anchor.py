"""v2026-08-20 — verify attachExplainers ? icon fix.

Checks that:
  1. Every section header has at most ONE ? icon visible (no double ??).
  2. The auto-injected section-explain ? is anchored beside the title (h2/h3),
     not at the end of the .section-h row.
  3. For sections that already have a manual help-tip ? on the h2, the
     auto-injected ? is suppressed (no doubling).
"""
import os, sys, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

LIVE_URL = "https://swing-shack-dashboard-production.up.railway.app/"
PASSWORD = "swing-shack-dev-2026"
SHOT_DIR = Path("/tmp/co-nightshift")
SHOT_DIR.mkdir(parents=True, exist_ok=True)
TS = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
BASE_URL = sys.argv[1] if len(sys.argv) > 1 else LIVE_URL


def walk():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_init_script("""
            localStorage.setItem('cos.tour.skipped','1');
            localStorage.setItem('cos.tour.dismissed','1');
            localStorage.setItem('cos.tour.done','1');
        """)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(("pageerror", str(exc))))
        page.on("console", lambda msg: msg.type == "error" and errors.append(("console", msg.text)))

        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
        if "/login" in page.url:
            page.fill("input[name=password]", PASSWORD)
            page.click("button[type=submit]")
            page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        page.wait_for_timeout(2500)

        # Per-section audit
        per_section = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('.section-h').forEach(h => {
                const sec = h.closest('.section');
                const secId = sec ? sec.id : '?';
                const h2 = h.querySelector('h2, h3');
                const explainInTitle = h2 ? h2.querySelector('.section-explain') : null;
                const explainInRow = h.querySelector(':scope > .section-explain');
                const helpTipInTitle = h2 ? h2.querySelector('.help-tip') : null;
                const subText = h.querySelector('.sub')?.textContent?.trim()?.slice(0, 60) || null;
                out.push({
                    sec_id: secId,
                    h2_text: h2 ? h2.textContent.trim().slice(0, 60) : null,
                    explain_in_title: !!explainInTitle,
                    explain_in_row: !!explainInRow,
                    has_help_tip: !!helpTipInTitle,
                    sub: subText,
                });
            });
            return out;
        }""")

        # Take screenshots: Home + Calendar (the two affected surfaces)
        for sec_id, name in [("sec-brief", "home"), ("sec-calendar", "calendar")]:
            page.evaluate(
                "({secId}) => { document.querySelectorAll('.section').forEach(s => s.classList.remove('on')); document.getElementById(secId)?.classList.add('on'); }",
                {"secId": sec_id},
            )
            page.wait_for_timeout(700)
            shot = SHOT_DIR / f"walkthrough_explainer_fix_{name}_{TS}.png"
            page.screenshot(path=str(shot), full_page=False)

        out = {
            "ts": TS,
            "base": BASE_URL,
            "per_section": per_section,
            "errors": errors[:6],
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))

        # Sanity: no section should have the explainer stranded at the end of
        # the row (explain_in_row=true), and no h2 with a manual help-tip
        # should ALSO have an injected section-explain (double ??).
        bad_row = [r for r in per_section if r["explain_in_row"]]
        double_help = [r for r in per_section if r["has_help_tip"] and r["explain_in_title"]]
        print(f"=== EXPLAINER IN ROW (bad): {len(bad_row)} ===")
        print(f"=== DOUBLE ? (bad): {len(double_help)} ===")
        browser.close()


if __name__ == "__main__":
    walk()
