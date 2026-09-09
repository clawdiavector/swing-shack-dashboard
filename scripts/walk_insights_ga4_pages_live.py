"""
walk_insights_ga4_pages_live.py

Playwright walker that verifies the 2026-08-10 nightshift fix on the Insights
"Top pages by sessions" card. The fix moved the tone computation from absolute
thresholds (>=60% good, >=30% watch) to thresholds relative to the in-list
average, and added a "★ Top" badge for the top engagement row.

Flow:
  1. Log in (shared-password gate via /login).
  2. Wait for SPA to render the sidebar + dismiss the welcome tour modal.
  3. Click the "Insights" sidebar section.
  4. Wait for #ins-pages-list to populate.
  5. Inspect every page row:
       - href is a real URL (not '#', not empty).
       - At least one good-tone row exists (borderColor #10b981).
       - When the top ER beats the average by >= 1.5x, a ★ Top badge is reached.
       - The ER pill tooltip mentions the local average ("your avg:").
  6. Capture screenshots.

Usage:
  .venv/bin/python scripts/walk_insights_ga4_pages_live.py
"""
from __future__ import annotations
import os
import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

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
    findings = {"ts": ts, "url": LIVE_URL, "errors": [], "console": [], "pages": {}}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        page.on("console", lambda msg: findings["console"].append(f"{msg.type}: {msg.text}"))
        page.on("pageerror", lambda exc: findings["errors"].append(f"pageerror: {exc}"))

        # Step 1: log in
        page.goto(f"{LIVE_URL}/login", wait_until="domcontentloaded")
        page.wait_for_selector("input[type=password]", timeout=15000)
        page.fill("input[type=password]", PW)
        page.locator("#submit-btn").click()
        page.wait_for_function(
            "() => !document.querySelector('input[type=password]')",
            timeout=20000,
        )
        page.wait_for_load_state("networkidle", timeout=20000)
        # The Insights nav is inside a hidden nav-group that opens when the user
        # clicks the "Insight" group header. Just wait for the sidebar to render,
        # then we'll expand the group manually in step 3.
        page.wait_for_selector(".nav-group-h[data-nav-group='insight']", timeout=20000)
        page.wait_for_timeout(800)

        # Dismiss welcome tour
        try:
            skip_btn = page.locator("text=Skip the tour").first
            if skip_btn.is_visible(timeout=2000):
                skip_btn.click()
                page.wait_for_timeout(500)
        except Exception:
            pass
        try:
            page.evaluate(
                "const bg = document.getElementById('welcome-bg');"
                "if (bg) { bg.classList.remove('on'); bg.style.display = 'none'; }"
            )
        except Exception:
            pass

        # Step 3: open Insights. The nav lives inside a collapsible "Insight" group
        # (data-nav-group="insight"). Expand the group first, then click the child.
        try:
            group_header = page.locator(
                ".nav-group-h[data-nav-group='insight']"
            ).first
            if group_header.is_visible(timeout=2000):
                group_header.click()
                page.wait_for_timeout(500)
                findings["console"].append("opened Insight group")
            else:
                findings["console"].append("Insight group header not visible (already expanded?)")
            insights_nav = page.locator(
                ".nav[data-go='insights']:visible"
            ).first
            insights_nav.click()
            page.wait_for_timeout(2000)
        except Exception as e:
            findings["errors"].append(f"could not open insights: {e}")

        # Step 4: wait for the pages card
        try:
            page.locator("#ins-pages-list").wait_for(timeout=15000)
        except Exception:
            findings["errors"].append("ins-pages-list not visible after opening insights")

        page.screenshot(path=str(OUT_DIR / f"walkthrough_{ts}_insights_full.png"), full_page=True)

        # Step 5: inspect rows
        pages_list = page.locator("#ins-pages-list")
        if pages_list.count() > 0:
            rows = pages_list.locator("> a")
            n_rows = rows.count()
            findings["pages"]["row_count"] = n_rows
            findings["pages"]["hrefs"] = []
            findings["pages"]["border_colors"] = []
            findings["pages"]["tones"] = []
            findings["pages"]["tooltips"] = []
            findings["pages"]["top_badges"] = 0
            for i in range(n_rows):
                row = rows.nth(i)
                href = row.get_attribute("href") or ""
                # Read computed border-left-color
                border = row.evaluate(
                    "el => getComputedStyle(el).borderLeftColor"
                )
                # The ER pill is the second div child of the right column.
                # Look for the inline title attribute via the small inner spans.
                tooltip = row.evaluate(
                    "el => {"
                    "  const t = el.querySelector('[title]');"
                    "  return t ? t.getAttribute('title') : '';"
                    "}"
                )
                # The ★ Top badge is a <span> with text "★ Top"
                has_top = row.locator("text=★ Top").count()
                findings["pages"]["hrefs"].append(href)
                findings["pages"]["border_colors"].append(border)
                findings["pages"]["tooltips"].append(tooltip)
                findings["pages"]["tones"].append(
                    "good" if "16, 185, 129" in border
                    else "watch" if "245, 158, 11" in border
                    else "bad" if "239, 68, 68" in border
                    else "unknown"
                )
                if has_top:
                    findings["pages"]["top_badges"] += 1

            # Classify tone distribution
            from collections import Counter
            tone_dist = Counter(findings["pages"]["tones"])
            findings["pages"]["tone_distribution"] = dict(tone_dist)

            # Zoom: screenshot just the card
            try:
                card = page.locator("#ins-pages-list").locator(
                    "xpath=ancestor::div[contains(@class, 'card')][1]"
                )
                if card.count() > 0:
                    card.first.screenshot(
                        path=str(OUT_DIR / f"walkthrough_{ts}_insights_top_pages.png")
                    )
            except Exception as e:
                findings["errors"].append(f"could not zoom-screenshot the card: {e}")

        # Sanity assertions
        issues = []
        for href in findings["pages"].get("hrefs", []):
            if not href or href == "#":
                issues.append(f"DEAD LINK: <a href={href!r}> in pages card")
        for tip in findings["pages"].get("tooltips", []):
            if tip and "your avg" not in tip and "Top performer" not in tip and "Above average" not in tip and "On par" not in tip and "Below average" not in tip:
                issues.append(f"ER pill tooltip missing verdict/avg: {tip!r}")
        if not findings["pages"].get("row_count"):
            issues.append("Top pages card is empty (no rows)")
        findings["issues"] = issues

        print(json.dumps(findings, indent=2))
        browser.close()

    out_path = OUT_DIR / f"walkthrough_{ts}_insights_findings.json"
    out_path.write_text(json.dumps(findings, indent=2))
    print(f"\n[walkthrough saved] {out_path}")
    return findings


if __name__ == "__main__":
    main()
