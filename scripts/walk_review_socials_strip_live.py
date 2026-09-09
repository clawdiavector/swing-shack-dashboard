"""
walk_review_socials_strip_live.py

Playwright walker that exercises the IG history strip in the Review modal on
LIVE (Railway). Used by the 2026-08-10 nightshift tick to verify the dead-link
fix is live. Captures /tmp/co-nightshift/walkthrough_<TIMESTAMP>_review_*.png.

Flow:
  1. Log in (shared-password gate via /login).
  2. Wait for SPA to render the sidebar + dismiss the welcome tour modal.
  3. Click the "Review" sidebar section.
  4. Wait for review queue rows.
  5. Click the FIRST visible row (opens the review modal).
  6. Wait for #rv-socials-strip to populate (or show empty state).
  7. Inspect the strip's children:
       - All <a> children MUST have a real href (not '#' or empty).
       - <div> fallbacks are OK (they're honest non-clickable).
  8. Capture screenshot.

Usage:
  .venv/bin/python scripts/walk_review_socials_strip_live.py
"""
from __future__ import annotations
import os
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

OUT_DIR = Path("/tmp/co-nightshift")
OUT_DIR.mkdir(parents=True, exist_ok=True)

LIVE_URL = "https://swing-shack-dashboard-production.up.railway.app"
PW = (
    os.environ.get("CAMPAIGN_OS_PASSWORD")
    or os.environ.get("SHARED_PASSWORD")
    or "swing-shack-dev-2026"
)  # dev shared gate


def main():
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    findings = {"ts": ts, "url": LIVE_URL, "errors": [], "console": [], "strip": {}}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        # Capture console + page errors
        page.on("console", lambda msg: findings["console"].append(f"{msg.type}: {msg.text}"))
        page.on("pageerror", lambda exc: findings["errors"].append(f"pageerror: {exc}"))

        # Step 1: log in (shared password gate)
        login_url = f"{LIVE_URL}/login"
        page.goto(login_url, wait_until="domcontentloaded")
        page.wait_for_selector("input[type=password]", timeout=15000)
        page.fill("input[type=password]", PW)
        page.locator("#submit-btn").click()
        # The login form does a fetch then window.location.href='/'. Wait for the
        # password input to disappear (proves we left /login) and for the SPA to
        # render its sidebar (proves we have data).
        page.wait_for_function(
            "() => !document.querySelector('input[type=password]')",
            timeout=20000,
        )
        page.wait_for_load_state("networkidle", timeout=20000)
        page.wait_for_selector(".nav[data-go='review']", timeout=20000)
        page.wait_for_timeout(800)

        # Step 2.5: dismiss the welcome tour modal if it pops up — it intercepts
        # every click we make until the user clicks "Skip the tour" or "Next".
        try:
            skip_btn = page.locator("text=Skip the tour").first
            if skip_btn.is_visible(timeout=2000):
                skip_btn.click()
                page.wait_for_timeout(500)
                findings["console"].append("welcome tour: dismissed via 'Skip the tour'")
        except Exception:
            pass
        # Fallback: force-hide the welcome dialog if it's still visible
        try:
            page.evaluate(
                "const bg = document.getElementById('welcome-bg');"
                "if (bg) { bg.classList.remove('on'); bg.style.display = 'none'; }"
            )
        except Exception:
            pass

        # Step 3: open Review section
        try:
            page.locator(".nav[data-go='review']").first.click()
            page.wait_for_timeout(1500)
        except Exception as e:
            findings["errors"].append(f"could not open review section: {e}")

        # Step 4: wait for review rows
        review_rows = page.locator('.review-item, .review-row, [onclick*="openReview"]')
        try:
            review_rows.first.wait_for(timeout=10000)
        except PWTimeoutError:
            findings["console"].append("review queue: no rows visible (empty inbox)")

        # Capture review queue state
        page.screenshot(path=str(OUT_DIR / f"walkthrough_{ts}_review_queue.png"), full_page=True)

        # Step 5: open the first VISIBLE review row.
        # The matching selector (.review-item, .review-row, [onclick*="openReview"])
        # also catches hidden off-screen "Open asset" buttons in inactive branches;
        # use nth() on the visible ones only.
        n_rows = review_rows.count()
        findings["review_rows_count"] = n_rows
        if n_rows > 0:
            opened = False
            for i in range(min(n_rows, 20)):
                row = review_rows.nth(i)
                try:
                    if not row.is_visible():
                        continue
                    row.scroll_into_view_if_needed(timeout=2000)
                    row.click(timeout=5000)
                    opened = True
                    break
                except Exception:
                    continue
            if not opened:
                findings["errors"].append(
                    "could not open first review row (no visible .review-item)"
                )
            page.wait_for_timeout(2000)

        # Step 6: wait for IG strip
        try:
            page.locator("#rv-socials-strip").wait_for(timeout=8000)
        except PWTimeoutError:
            findings["console"].append("IG strip: not visible after opening review modal")

        # Step 7: inspect the strip
        strip = page.locator("#rv-socials-strip")
        if strip.count() > 0:
            children = strip.locator("> *")
            n_children = children.count()
            findings["strip"]["children_count"] = n_children
            findings["strip"]["anchors"] = []
            findings["strip"]["divs"] = 0
            findings["strip"]["empty_msg"] = ""
            for i in range(n_children):
                child = children.nth(i)
                tag = child.evaluate("el => el.tagName")
                if tag == "A":
                    href = child.get_attribute("href") or ""
                    findings["strip"]["anchors"].append(href)
                else:
                    findings["strip"]["divs"] += 1
            if n_children == 0:
                try:
                    findings["strip"]["empty_msg"] = strip.inner_text()[:200]
                except Exception:
                    pass

        # Step 8: capture
        page.screenshot(path=str(OUT_DIR / f"walkthrough_{ts}_review_with_socials.png"), full_page=True)

        # Sanity assertions
        issues = []
        for href in findings["strip"].get("anchors", []):
            if not href or href == "#":
                issues.append(f"DEAD LINK: <a href={href!r}> in IG history strip")
        if not findings["strip"].get("children_count") and not findings["strip"].get("empty_msg"):
            issues.append("IG history strip empty (no children, no empty message)")
        findings["issues"] = issues

        print(json.dumps(findings, indent=2))

        browser.close()

    out_path = OUT_DIR / f"walkthrough_{ts}_review_findings.json"
    out_path.write_text(json.dumps(findings, indent=2))
    print(f"\n[walkthrough saved] {out_path}")
    return findings


if __name__ == "__main__":
    main()
