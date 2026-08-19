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

        page.evaluate("""() => {
            document.querySelectorAll('.modal-backdrop,.modal,.welcome-modal,[data-tour]').forEach(el => el.remove());
            localStorage.setItem('cos.tour.skipped','1');
            localStorage.setItem('cos.tour.dismissed','1');
        }""")
        page.wait_for_timeout(2500)

        # Click any nav element pointing at memes
        nav_clicked = page.evaluate("""() => {
            const candidates = document.querySelectorAll('a,button,.nav-item,[data-nav],[data-section]');
            for (const el of candidates) {
                const t = (el.textContent || '').toLowerCase();
                if (t.includes('meme lord') || el.dataset?.nav === 'memes' || el.dataset?.section === 'memes') {
                    el.click();
                    return (el.textContent || '').trim().slice(0, 40);
                }
            }
            return null;
        }""")
        page.wait_for_timeout(2500)

        # Force scroll to sec-memes
        page.evaluate("""() => {
            const el = document.getElementById('sec-memes');
            if (el) el.scrollIntoView({block:'start',behavior:'instant'});
        }""")
        page.wait_for_timeout(1500)

        result = page.evaluate(
            """(nav) => {
                const sec = document.getElementById('sec-memes');
                if (!sec) return {found: false};
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
                    return r.width > 0 && r.height > 0;
                })();
                return {
                    found: true,
                    section_visible: secVisible,
                    nav_clicked: nav,
                    sub_text: subText,
                    sub_attrs: subAttrs,
                    card_titles: cardTexts.slice(0, 12),
                };
            }""",
            nav_clicked,
        )

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

        print("=== nav_clicked ===")
        print(nav_clicked)
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
