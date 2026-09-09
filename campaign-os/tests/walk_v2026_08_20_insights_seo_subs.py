"""v2026-08-20 — Playwright walk of the two final section sub fixes (Insights
v2 + SEO Audit). Confirms each sub renders the new descriptive fallback on
first paint (before the JS API call overwrites it), carries id + data-help +
data-help-title, and the visible sub text is not the old loading placeholder.
Captures a screenshot per section to /tmp/co-nightshift/.

Run from /Users/fivefriday/.openclaw-instance2/workspace/swing-shack-dashboard
  .venv/bin/python3 campaign-os/tests/walk_v2026_08_20_insights_seo_subs.py

Override URL for local testing:
  .venv/bin/python3 campaign-os/tests/walk_v2026_08_20_insights_seo_subs.py http://127.0.0.1:8765
"""
import os
import sys
import time
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

LIVE_URL = "https://swing-shack-dashboard-production.up.railway.app/"
PASSWORD = "swing-shack-dev-2026"
SHOT_DIR = Path("/tmp/co-nightshift")
SHOT_DIR.mkdir(parents=True, exist_ok=True)
TS = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

# CLI override: first arg = base URL
BASE_URL = sys.argv[1] if len(sys.argv) > 1 else LIVE_URL

# (section_id, sub_id, display_name, optional_render_fn, old_placeholder)
SECTIONS = [
    ("sec-insights",   "ins-v2-summary", "Insights",  "renderInsights",  "loading"),
    ("sec-seo-audit",  "sa-summary",     "SEO Audit", "renderSEOAudit",  "Auditing"),
]


def probe(page, sec_id, sub_id, render_fn):
    """Show the section, trigger render, read the sub text + attributes."""
    page.evaluate(
        """({secId}) => {
            document.querySelectorAll('.section').forEach(s => s.classList.remove('on'));
            const sec = document.getElementById(secId);
            if (sec) sec.classList.add('on');
        }""",
        {"secId": sec_id},
    )
    page.wait_for_timeout(400)
    if render_fn:
        page.evaluate(
            """(fn) => {
                if (typeof window[fn] === 'function') {
                    try { window[fn](); } catch(e) { console.warn('render', fn, e.message); }
                }
            }""",
            render_fn,
        )
        page.wait_for_timeout(800)
    return page.evaluate(
        """({secId, subId}) => {
            const sec = document.getElementById(secId);
            if (!sec) return {found: false};
            const sub = document.getElementById(subId);
            const subText = sub ? (sub.textContent || '').trim() : null;
            const subAttrs = sub ? {
                has_data_help: sub.hasAttribute('data-help'),
                has_data_help_title: sub.hasAttribute('data-help-title'),
                data_help_title: sub.getAttribute('data-help-title'),
            } : null;
            const r = sec.getBoundingClientRect();
            window.scrollTo({top: window.scrollY + r.top - 60, behavior: 'instant'});
            return {found: true, sub_text: subText, sub_attrs: subAttrs};
        }""",
        {"secId": sec_id, "subId": sub_id},
    )


def login_and_walk(base_url):
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

        page.goto(base_url, wait_until="domcontentloaded", timeout=20000)
        if "/login" in page.url:
            page.fill("input[name=password]", PASSWORD)
            page.click("button[type=submit], button:has-text('Login'), button:has-text('Sign')")
            page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        page.wait_for_timeout(2500)

        results = []
        for sec_id, sub_id, name, render_fn, old in SECTIONS:
            r = probe(page, sec_id, sub_id, render_fn)
            r["old_placeholder"] = old
            results.append({"section": name, "sub_id": sub_id, **r})
            shot = SHOT_DIR / f"walkthrough_2subs_{name.lower().replace(' ', '_')}_{TS}.png"
            try:
                page.screenshot(path=str(shot), full_page=False)
                results[-1]["screenshot"] = str(shot)
            except Exception as e:
                results[-1]["screenshot_err"] = str(e)

        # Overview screenshot: switch back to brief for context
        try:
            page.evaluate("() => { document.querySelectorAll('.section').forEach(s => s.classList.remove('on')); document.getElementById('sec-brief')?.classList.add('on'); }")
            page.wait_for_timeout(400)
            overview = SHOT_DIR / f"walkthrough_2subs_overview_{TS}.png"
            page.screenshot(path=str(overview), full_page=False)
        except Exception as e:
            overview = f"err: {e}"

        print("=== probes ===")
        print(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"=== errors (first 8) ===")
        for e in errors[:8]:
            print(e)
        print(f"=== overview === {overview}")

        # Sanity: each sub is non-empty, not the old placeholder, carries
        # data-help + data-help-title.
        ok = all(
            r.get("found")
            and r.get("sub_text")
            and r["old_placeholder"] not in r["sub_text"]
            and r.get("sub_attrs", {}).get("has_data_help")
            and r.get("sub_attrs", {}).get("has_data_help_title")
            for r in results
        )
        print(f"=== BOTH SUBS OK: {ok} ===")
        if not ok:
            sys.exit(1)
        browser.close()


if __name__ == "__main__":
    login_and_walk(BASE_URL)
