#!/usr/bin/env python3
"""
Multi-tab sweep walker on LIVE URL.
"""
from __future__ import annotations
import os, sys, json, time, re
from pathlib import Path
from playwright.sync_api import sync_playwright

LIVE = "https://swing-shack-dashboard-production.up.railway.app"
PWD = os.environ.get("SHARED_PASSWORD", "swing-shack-dev-2026")
OUT = Path("/tmp/co-nightshift")
OUT.mkdir(parents=True, exist_ok=True)
TS = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

NAV_NAMES = [
    ("brief", "Brief"), ("review", "Review"), ("publish", "Publish"),
    ("calendar", "Calendar"), ("trends", "Trends"), ("ideas", "Ideas"),
    ("performance", "Performance"), ("learning", "Learning"), ("hooks", "Hook Bank"),
    ("memes", "Meme Lord"), ("billboards", "Billboards"),
    ("captions", "Captions"), ("headlines", "Headlines"), ("ctas", "CTAs"),
    ("seo", "SEO"), ("seo-audit", "SEO Audit"), ("gbp", "GBP"), ("reddit", "Reddit"), ("faqs", "FAQs"),
    ("postiz", "Postiz"), ("campaigns", "Campaigns"), ("agents", "Agents"),
    ("socials", "Socials"), ("insights", "Insights"), ("library", "Library"),
    ("create", "Create"), ("imagegen", "Image Gen"),
    ("gmb", "Google Business"), ("hashtagseo", "Hashtags + SEO"),
]


def main() -> int:
    findings: dict[str, dict] = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        errors: list[str] = []
        net_failures: list[str] = []
        console_errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: console_errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
        page.on("requestfailed", lambda req: net_failures.append(f"{req.failure} {req.url}"))

        page.goto(LIVE + "/campaign-os", wait_until="domcontentloaded")
        page.wait_for_selector("input[type=password]", timeout=15000)
        page.fill("input[type=password]", PWD)
        page.press("input[type=password]", "Enter")
        page.wait_for_load_state("domcontentloaded", timeout=8000)
        page.wait_for_timeout(500)

        # Dismiss welcome tour if present (it intercepts nav clicks)
        try:
            page.locator("button.welcome-skip").first.click(timeout=2000)
            page.wait_for_timeout(300)
        except Exception:
            pass

        # Expand all collapsed sidebar nav groups so sub-navs are clickable.
        # Without this, .nav[data-go='memes'] (for example) resolves to the
        # hidden first match inside #nav-group-build[hidden], and the click
        # hits an unclickable target — walker reports NAV_ERR on ~19/28 tabs.
        page.evaluate("""() => {
            document.querySelectorAll('.nav-group-h[aria-expanded=\"false\"]').forEach(h => h.click());
        }""")
        page.wait_for_timeout(300)

        for slug, label in NAV_NAMES:
            err_before = len(errors)
            console_before = len(console_errors)
            net_before = len(net_failures)
            try:
                sel = f".nav[data-go='{slug}']"
                cnt = page.locator(sel).count()
                if cnt == 0:
                    findings[slug] = {"nav_error": f"selector {sel} not found"}
                    continue
                # Pick the visible match. .nav elements inside [hidden] nav-groups
                # are display:none and unclickable; force=True still hits them but
                # the section switch handler in app.js only runs for visible rows.
                target = None
                for i in range(cnt):
                    cand = page.locator(sel).nth(i)
                    if cand.is_visible():
                        target = cand
                        break
                if target is None:
                    findings[slug] = {"nav_error": f"no visible {sel} (all {cnt} matches hidden in collapsed nav group)"}
                    continue
                target.scroll_into_view_if_needed(timeout=3000)
                target.click(timeout=6000)
            except Exception as e:
                findings[slug] = {"nav_error": str(e)[:200]}
                continue
            page.wait_for_load_state("domcontentloaded", timeout=4000)
            page.wait_for_timeout(700)
            body_text = page.evaluate("() => document.body.innerText.slice(0, 6000)")
            em_count = body_text.count("\u2014") + body_text.count("\u2013")
            json_leak = bool(re.search(r'\{\s*\"[a-z_]+\"\s*:\s*[\[\{\"\\d\-]', body_text))
            empty_phrases = ["No patterns yet", "Nothing scheduled", "Nothing to review",
                             "No data yet", "Nothing here yet", "Loading\u2026",
                             "Loading...", "No items", "0 posts"]
            empty_hits = [p for p in empty_phrases if p in body_text]
            # section_head: prefer the active section's text over the sidebar nav
            # (body.innerText.slice(0,N) is always dominated by the fixed sidebar).
            section = page.evaluate(
                """(slug) => {
                    const sec = document.querySelector(`#sec-${slug}`);
                    if (!sec) return document.body.innerText.slice(0, 1500);
                    const t = sec.innerText || '';
                    return t.length > 1500 ? t.slice(0, 1500) : t;
                }""",
                slug,
            )
            shot = OUT / f"walkthrough_{TS}_sweep_{slug}.png"
            try:
                page.screenshot(path=str(shot), full_page=False)
            except Exception:
                pass
            findings[slug] = {
                "pageerrors": errors[err_before:],
                "console_errors": console_errors[console_before:],
                "net_failures": net_failures[net_before:],
                "em_dash_count": em_count,
                "json_leak": json_leak,
                "empty_hits": empty_hits,
                "section_head": section[:400],
                "screenshot": str(shot) if shot.exists() else None,
            }
        b.close()

    out = {"ts": TS, "errors": errors[:50], "console_errors": console_errors[:50],
           "net_failures": net_failures[:30], "by_nav": findings}
    (OUT / f"sweep_{TS}.json").write_text(json.dumps(out, indent=2))
    print("DONE", TS)
    print("TOTAL pageerrors:", len(errors))
    print("TOTAL console.errors:", len(console_errors))
    print("TOTAL net failures:", len(net_failures))
    for slug, f in findings.items():
        label = next((l for s,l in NAV_NAMES if s == slug), slug)
        flags = []
        if f.get("nav_error"): flags.append(f"NAV_ERR")
        if f.get("pageerrors"): flags.append(f"PE={len(f['pageerrors'])}")
        if f.get("console_errors"): flags.append(f"CE={len(f['console_errors'])}")
        if f.get("net_failures"): flags.append(f"NF={len(f['net_failures'])}")
        if f.get("json_leak"): flags.append("JSON_LEAK")
        if f.get("em_dash_count"): flags.append(f"EMDASH={f['em_dash_count']}")
        if f.get("empty_hits"): flags.append(f"EMPTY={f['empty_hits']}")
        print(f"  {label:14s} -> {' | '.join(flags) if flags else 'clean'}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
