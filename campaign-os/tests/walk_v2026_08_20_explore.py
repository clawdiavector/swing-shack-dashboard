"""v2026-08-20 — exploratory nightshift walk.

Logs JS errors, walks every nav section, captures screenshots, and probes
for common UX anti-patterns: literal-dash placeholders, empty cards, dead
buttons, broken image refs. Output drives the night's pick.
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

# (section_id, nav_label, render_fn) — sections we want to inspect
SECTIONS = [
    ("sec-brief",        "Home",        "renderBrief"),
    ("sec-ideas",        "Ideas",       "renderIdeas"),
    ("sec-meme",         "Meme Lord",   "renderMemeLord"),
    ("sec-billboards",   "Billboards",  "renderBillboards"),
    ("sec-hooks",        "Hooks",       "renderHooks"),
    ("sec-headlines",    "Headlines",   "renderHeadlines"),
    ("sec-captions",     "Captions",    "renderCaptions"),
    ("sec-calendar",     "Calendar",    "renderCalendar"),
    ("sec-ctas",         "CTA Studio",  "renderCtaStudio"),
    ("sec-hashtags",     "Hashtags",    "renderHashtags"),
    ("sec-seo-audit",    "SEO Audit",   "renderSEOAudit"),
    ("sec-seo-keywords", "SEO Keywords","renderSEOKeywords"),
    ("sec-trends",       "Trends",      "renderTrends"),
    ("sec-ubersuggest",  "Ubersuggest", "renderUbersuggest"),
    ("sec-insights",     "Insights",    "renderInsights"),
    ("sec-socials",      "Socials",     "renderSocials"),
    ("sec-publishing",   "Publishing",  "renderPublishing"),
    ("sec-gmb",          "GMB",         "renderGMB"),
    ("sec-fleet",        "Fleet",       "renderFleet"),
    ("sec-agents",       "Agents",      "renderAgents"),
    ("sec-library",      "Library",     "renderLibrary"),
    ("sec-review",       "Review",      "renderReview"),
]


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
        page_errors = []
        console_errors = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("console", lambda msg: msg.type == "error" and console_errors.append(msg.text))

        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
        if "/login" in page.url:
            page.fill("input[name=password]", PASSWORD)
            page.click("button[type=submit]")
            page.wait_for_url(lambda u: "/login" not in u, timeout=15000)
        page.wait_for_timeout(3000)

        summary = []
        for sec_id, name, render_fn in SECTIONS:
            r = page.evaluate(
                """({secId, fn}) => {
                    document.querySelectorAll('.section').forEach(s => s.classList.remove('on'));
                    const sec = document.getElementById(secId);
                    if (!sec) return {found: false};
                    sec.classList.add('on');
                    if (typeof window[fn] === 'function') {
                        try { window[fn](); } catch(e) { return {found: true, render_error: e.message}; }
                    }
                    return {found: true};
                }""",
                {"secId": sec_id, "fn": render_fn},
            )
            page.wait_for_timeout(700)
            # Probe the section's h-meta, sub text, and innerHTML length
            probe = page.evaluate(
                """(secId) => {
                    const sec = document.getElementById(secId);
                    if (!sec) return null;
                    const sub = sec.querySelector('.sub');
                    const meta = sec.querySelector('.h-meta');
                    const cards = sec.querySelectorAll('.card');
                    const buttons = sec.querySelectorAll('button');
                    const images = sec.querySelectorAll('img');
                    const brokenImgs = [...images].filter(i => i.complete && i.naturalWidth === 0).map(i => i.src);
                    return {
                        sub: sub ? sub.textContent.trim().slice(0, 120) : null,
                        sub_is_dash: sub ? (sub.textContent.trim() === '—') : false,
                        h_meta: meta ? meta.textContent.trim().slice(0, 80) : null,
                        h_meta_is_dash: meta ? (meta.textContent.trim() === '—') : false,
                        n_cards: cards.length,
                        n_buttons: buttons.length,
                        n_images: images.length,
                        broken_images: brokenImgs,
                    };
                }""",
                sec_id,
            )
            r.update(probe or {})
            r["section"] = name
            r["sec_id"] = sec_id
            summary.append(r)

        # Probe "—" placeholders across whole document
        dashes = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('.h-meta, .sub, .muted').forEach(el => {
                const t = (el.textContent || '').trim();
                if (t === '—' || t === '-' || t === '') {
                    const r = el.closest('.section, .card, .row');
                    out.push({
                        kind: el.className,
                        sec: r?.id || r?.closest('.section')?.id || '?',
                        text: t,
                        txt_excerpt: (el.parentElement?.textContent || '').trim().slice(0, 80),
                    });
                }
            });
            return out.slice(0, 40);
        }""")

        # One overview shot of the brief surface
        page.evaluate("() => { document.querySelectorAll('.section').forEach(s => s.classList.remove('on')); document.getElementById('sec-brief')?.classList.add('on'); }")
        page.wait_for_timeout(800)
        overview = SHOT_DIR / f"walkthrough_explore_{TS}.png"
        page.screenshot(path=str(overview), full_page=False)

        # Pick a target section with a likely bug to capture
        for sec_id, name, render_fn in SECTIONS:
            page.evaluate(
                """({secId, fn}) => {
                    document.querySelectorAll('.section').forEach(s => s.classList.remove('on'));
                    const sec = document.getElementById(secId);
                    if (sec) sec.classList.add('on');
                    if (typeof window[fn] === 'function') { try { window[fn](); } catch(e) {} }
                }""",
                {"secId": sec_id, "fn": render_fn},
            )
            page.wait_for_timeout(700)

        out = {
            "ts": TS,
            "base": BASE_URL,
            "summary": summary,
            "dashes": dashes,
            "page_errors": page_errors[:12],
            "console_errors": console_errors[:12],
            "overview": str(overview),
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        browser.close()


if __name__ == "__main__":
    walk()
