"""
walk_perf_why_explain_live.py

Playwright walker that verifies the 2026-08-10 nightshift fix on the
Performance widget "Why this worked / failed" explainer button. The fix
moved the tone computation from absolute thresholds (er > 4 ? Strong :
er > 2 ? Average : er > 0 ? Underperformer) to relative-tone ranks
(computed against the in-list average ER from top_posts), added a
"★ Top" badge for the top row when it beats the local average by >= 1.5x,
and exposed the math via a tooltip ("Top performer (your avg: 51.7%)")
plus an inline ratio badge ("1.42x avg").

Flow:
  1. Log in (shared-password gate via /login).
  2. Wait for SPA to render the sidebar + dismiss the welcome tour modal.
  3. Open the Performance section (lives under the "Insight" nav group).
  4. Wait for #why-asset to populate with options from top_posts.
  5. Pick the first asset, click Explain, wait for #why-result to render.
  6. Inspect the verdict:
     - Must contain a ratio badge ("x avg") somewhere in the visible text.
     - Must contain a tooltip ("your avg:") on the ratio badge.
     - The verdict emoji + label must be one of the relative labels
       (Top performer / Above average / On par / Below average).
     - No em-dashes in the rendered output.
  7. Repeat for the LAST asset in the dropdown to exercise the bottom
     of the distribution (likely "Below average" or "On par" verdict).
  8. Capture screenshots.

Usage:
  .venv/bin/python scripts/walk_perf_why_explain_live.py
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


def _inspect_verdict(page, findings, asset_label):
    """Read the current #why-result text and assert the relative-tone contract."""
    out = page.locator("#why-result")
    text = out.text_content() or ""
    findings["results"][asset_label] = {
        "text": text,
        "has_ratio_badge": "x avg" in text,
        "has_avg_tooltip": False,  # tooltips are attribute-only, checked below
        "has_relative_label": False,
        "label": None,
        "has_top_badge": page.locator("#why-result").locator("text=★ Top").count() > 0,
    }
    # Find the ratio badge span and read its title attribute (the tooltip).
    try:
        badge = page.locator("#why-result").locator("span[title*='your avg']").first
        if badge.count() > 0:
            findings["results"][asset_label]["has_avg_tooltip"] = True
            findings["results"][asset_label]["tooltip_text"] = badge.get_attribute("title")
    except Exception:
        pass
    # Match the relative-tone label whitelist.
    for label in ("Top performer", "Above average", "On par", "Below average"):
        if label in text:
            findings["results"][asset_label]["has_relative_label"] = True
            findings["results"][asset_label]["label"] = label
            break
    # Em-dash check on the visible output (standing rule).
    findings["results"][asset_label]["em_dash_count"] = text.count("\u2014")
    findings["results"][asset_label]["en_dash_count"] = text.count("\u2013")


def main():
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    findings = {
        "ts": ts,
        "url": LIVE_URL,
        "errors": [],
        "console": [],
        "results": {},
        "issues": [],
    }

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
        page.wait_for_selector(".nav-group-h[data-nav-group='insight']", timeout=20000)
        page.wait_for_timeout(800)

        # Step 2: dismiss welcome tour
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

        # Step 3: open the Performance section. Lives under the "Insight" nav group.
        try:
            group_header = page.locator(".nav-group-h[data-nav-group='insight']").first
            if group_header.is_visible(timeout=2000):
                group_header.click()
                page.wait_for_timeout(500)
            perf_nav = page.locator(".nav[data-go='performance']:visible").first
            perf_nav.click()
            page.wait_for_timeout(2500)
        except Exception as e:
            findings["errors"].append(f"could not open performance: {e}")

        # Step 4: wait for the why-asset dropdown to populate.
        try:
            page.locator("#why-asset").wait_for(timeout=15000)
        except Exception:
            findings["errors"].append("why-asset dropdown not visible after opening performance")
        try:
            page.wait_for_function(
                "() => document.querySelectorAll('#why-asset option').length > 1",
                timeout=15000,
            )
        except Exception:
            findings["errors"].append("why-asset dropdown never populated with options")

        option_count = page.locator("#why-asset option").count()
        findings["dropdown_options"] = option_count

        # Capture the dropdown before any clicks so we can see the relabel.
        page.screenshot(
            path=str(OUT_DIR / f"walkthrough_{ts}_perf_why_dropdown.png"),
            full_page=False,
        )

        # Step 5: pick the first asset, click Explain, inspect the verdict.
        first_value = page.locator("#why-asset option").nth(1).get_attribute("value")
        findings["first_asset_id"] = first_value
        page.locator("#why-asset").select_option(index=1)
        page.locator("#why-explain-btn").click()
        # Wait for the result to settle (replaces "Computing explanation…").
        page.wait_for_function(
            "() => { const r = document.getElementById('why-result');"
            "  return r && !r.textContent.includes('Computing explanation');"
            "}",
            timeout=15000,
        )
        page.wait_for_timeout(800)
        _inspect_verdict(page, findings, "first")

        # Step 6: pick the LAST asset to exercise the bottom of the distribution.
        last_idx = option_count - 1
        last_value = page.locator("#why-asset option").nth(last_idx).get_attribute("value")
        findings["last_asset_id"] = last_value
        page.locator("#why-asset").select_option(index=last_idx)
        page.locator("#why-explain-btn").click()
        page.wait_for_function(
            "() => { const r = document.getElementById('why-result');"
            "  return r && !r.textContent.includes('Computing explanation');"
            "}",
            timeout=15000,
        )
        page.wait_for_timeout(800)
        _inspect_verdict(page, findings, "last")

        # Step 7: zoom screenshot of the Why-result card.
        try:
            card = page.locator("#why-result").locator(
                "xpath=ancestor::div[contains(@class, 'card')][1]"
            )
            if card.count() > 0:
                card.first.screenshot(
                    path=str(OUT_DIR / f"walkthrough_{ts}_perf_why_result.png")
                )
        except Exception as e:
            findings["errors"].append(f"could not zoom-screenshot the why-result: {e}")

        # Full-page screenshot for the record.
        page.screenshot(
            path=str(OUT_DIR / f"walkthrough_{ts}_perf_full.png"),
            full_page=True,
        )

        # Sanity assertions.
        for label in ("first", "last"):
            r = findings["results"].get(label, {})
            if r.get("em_dash_count", 0) > 0:
                findings["issues"].append(
                    f"{label}: em-dash rendered ({r['em_dash_count']} in #why-result)"
                )
            if not r.get("has_ratio_badge"):
                findings["issues"].append(f"{label}: ratio badge missing (no 'x avg' in text)")
            if not r.get("has_avg_tooltip"):
                findings["issues"].append(f"{label}: no tooltip with 'your avg:' on the ratio badge")
            if not r.get("has_relative_label"):
                findings["issues"].append(
                    f"{label}: no relative-tone label (Top performer / Above average / On par / Below average)"
                )
        if not findings["dropdown_options"] or findings["dropdown_options"] < 2:
            findings["issues"].append(
                f"why-asset dropdown empty or too small (options={findings['dropdown_options']})"
            )

        print(json.dumps(findings, indent=2))
        browser.close()

    out_path = OUT_DIR / f"walkthrough_{ts}_perf_why_findings.json"
    out_path.write_text(json.dumps(findings, indent=2))
    print(f"\n[walkthrough saved] {out_path}")
    return findings


if __name__ == "__main__":
    main()
