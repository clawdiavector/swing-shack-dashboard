"""v2026-08-19 — Playwright walk of the LIVE Meme Lord section to confirm the
new sub renders on first paint, carries id + data-help + data-help-title,
and matches the test's expected static fallback. Captures screenshot to
/tmp/co-nightshift/.

Run: cd campaign-os && ../.venv/bin/python3 tests/walk_memes_sub_fix.py
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


def login_and_walk(base_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 1100})
        # Pre-set the tour-dismiss localStorage so the welcome modal never shows.
        ctx.add_init_script("""
            localStorage.setItem('cos.tour.skipped','1');
            localStorage.setItem('cos.tour.dismissed','1');
            localStorage.setItem('cos.tour.done','1');
        """)
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

        # Welcome modal is suppressed via the context init script above; no
        # manual DOM removal needed (the previous approach crashed renderBrief).
        page.wait_for_timeout(3000)

        # Make sec-memes visible (sections are display:none by default; only .on shows).
        # This is what the SPA does when you click a nav item. We do it manually
        # so we can screenshot the section directly.
        page.evaluate("""() => {
            document.querySelectorAll('.section').forEach(s => s.classList.remove('on'));
            const sec = document.getElementById('sec-memes');
            if (sec) sec.classList.add('on');
        }""")
        page.wait_for_timeout(800)
        page.wait_for_timeout(1500)

        # Trigger renderMemes (the section was just scrolled into view; the
        # SPA lazy-renders per section when shown).
        render_attempt = page.evaluate("""async () => {
            if (typeof renderMemes === 'function') {
                try { await renderMemes(); return 'rendered'; } catch (e) { return 'err:' + e.message; }
            }
            return 'no renderMemes';
        }""")
        page.wait_for_timeout(1500)

        # No second-pass modal removal (the init script already suppresses it).
        page.wait_for_timeout(500)

        result = page.evaluate(
            """(render) => {
                const sec = document.getElementById('sec-memes');
                if (!sec) return {found: false};
                // Scroll the section header into the centre of the viewport.
                const rect = sec.getBoundingClientRect();
                window.scrollTo({top: window.scrollY + rect.top - 80, behavior: 'instant'});
                const sub = document.getElementById('memes-summary');
                const subText = sub ? (sub.textContent || '').trim() : null;
                const subAttrs = sub ? {
                    has_data_help: sub.hasAttribute('data-help'),
                    has_data_help_title: sub.hasAttribute('data-help-title'),
                    data_help_title: sub.getAttribute('data-help-title'),
                } : null;
                const cardHs = sec.querySelectorAll('.card-h h3');
                const cardTexts = [];
                cardHs.forEach(c => {
                    const v = (c.textContent || '').trim();
                    if (v) cardTexts.push(v.slice(0, 80));
                });
                const secVisible = (() => {
                    const r = sec.getBoundingClientRect();
                    return r.width > 0 && r.height > 0 && r.top < window.innerHeight && r.bottom > 0;
                })();
                return {
                    found: true,
                    section_visible: secVisible,
                    render_attempt: render,
                    sub_text: subText,
                    sub_attrs: subAttrs,
                    card_titles: cardTexts.slice(0, 12),
                };
            }""",
            render_attempt,
        )
        page.wait_for_timeout(600)

        shot_path = SHOT_DIR / f"walkthrough_memes_sub_{TS}.png"
        page.screenshot(path=str(shot_path), full_page=False)

        sec_box = page.evaluate("""() => {
            const sec = document.getElementById('sec-memes');
            if (!sec) return null;
            const r = sec.getBoundingClientRect();
            return {x: r.x, y: r.y, width: r.width, height: r.height};
        }""")
        sec_shot = None
        if sec_box:
            sec_shot = SHOT_DIR / f"walkthrough_memes_sub_section_{TS}.png"
            try:
                page.screenshot(
                    path=str(sec_shot),
                    clip={
                        "x": max(0, sec_box["x"]),
                        "y": max(0, sec_box["y"]),
                        "width": min(1440, sec_box["width"]),
                        "height": min(1100, sec_box["height"]),
                    },
                )
            except Exception as e:
                sec_shot = f"sec-screenshot failed: {e}"

        print("=== render_attempt ===")
        print(render_attempt)
        print("=== probe ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        print("=== errors (first 10) ===")
        for e in errors[:10]:
            print(e)
        print(f"=== screenshot === {shot_path}")
        print(f"=== section screenshot === {sec_shot}")
        browser.close()


if __name__ == "__main__":
    login_and_walk(LIVE_URL)
