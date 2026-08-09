#!/usr/bin/env python3
"""Pre-pick sweep across Campaign OS sections on the LIVE Railway URL.

Logs in, walks every nav[data-go=X] target, captures:
  - console errors
  - page errors
  - textContent of the section root (truncated)
  - any <pre> blocks that JSON-stringify a plain string (the
    "JSON dump of a string" anti-pattern)
  - raw <pre> blocks whose text starts with "{" (raw JSON dump of a row)
  - any element whose textContent contains literal "[object Object]"
"""
from __future__ import annotations
import os, sys, json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

LIVE = "https://swing-shack-dashboard-production.up.railway.app"
SHARED_PASSWORD = os.environ.get("CAMPAIGN_OS_PASSWORD", "swing-shack-dev-2026")
OUT = Path("/tmp/co-nightshift")
OUT.mkdir(parents=True, exist_ok=True)
TS = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
REPORT = OUT / f"sweep_{TS}.json"

TARGETS = [
    ("brief",   "#sec-brief"),
    ("review",  "#sec-review"),
    ("library", "#sec-library"),
    ("socials", "#sec-socials"),
    ("gmb",     "#sec-gmb"),
    ("create",  "#sec-create"),
    ("campaigns","#sec-campaigns"),
    ("captions","#sec-captions"),
    ("headlines","#sec-headlines"),
    ("hooks",   "#sec-hooks"),
    ("memes",   "#sec-memes"),
    ("imagegen","#sec-imagegen"),
    ("billboards","#sec-billboards"),
    ("ctas",    "#sec-ctas"),
    ("hashtagseo","#sec-hashtagseo"),
    ("ideas",   "#sec-ideas"),
    ("reddit",  "#sec-reddit"),
    ("faqs",    "#sec-faqs"),
    ("insights","#sec-insights"),
    ("trends",  "#sec-trends"),
    ("performance","#sec-performance"),
    ("learning","#sec-learning"),
    ("seo",     "#sec-seo"),
    ("calendar","#sec-calendar"),
    ("publish", "#sec-publish"),
    ("postiz",  "#sec-postiz"),
    ("gbp",     "#sec-gbp"),
    ("agents",  "#sec-agents"),
]


def main() -> int:
    findings = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        console_errors = []
        page_errors = []
        page.on("pageerror", lambda e: page_errors.append(f"pageerror: {e}"))
        page.on(
            "console",
            lambda m: console_errors.append(f"console.{m.type}: {m.text}")
            if m.type == "error" else None,
        )

        page.goto(LIVE + "/login", wait_until="domcontentloaded")
        page.wait_for_selector(
            "input[name=password], input[type=password]", timeout=15000
        )
        page.fill("input[name=password], input[type=password]", SHARED_PASSWORD)
        page.press("input[name=password], input[type=password]", "Enter")
        page.wait_for_url(lambda u: "/login" not in u, timeout=20000)
        print(f"login ok -> {page.url}")

        page.goto(LIVE + "/campaign-os.html", wait_until="domcontentloaded")
        page.wait_for_selector("#sec-brief", state="attached", timeout=15000)

        page.evaluate("""
          () => {
            try { localStorage.setItem('co_welcomed', '1'); } catch(e){}
            const tour = document.querySelector('.tour, .welcome-tour, [data-tour]');
            if(tour) tour.remove();
            const skip = [...document.querySelectorAll('button')].find(b => /skip|close/i.test(b.textContent || ''));
            if(skip) skip.click();
          }
        """)

        for name, sel in TARGETS:
            clicked = page.evaluate(
                """(sel) => {
                  const section = document.querySelector(sel);
                  if(!section) return 'no-section';
                  const m = sel.match(/#sec-([a-z0-9_-]+)/);
                  const target = m ? m[1] : '';
                  const nav = document.querySelector(`.nav[data-go="${target}"]`) ||
                              document.querySelector(`[data-go="${target}"]`);
                  if(nav) nav.click();
                  return 'ok';
                }""",
                sel,
            )
            try:
                page.wait_for_function(
                    f"document.querySelector('{sel}')?.classList.contains('on')",
                    timeout=4000,
                )
            except Exception:
                pass
            page.wait_for_timeout(300)

            probe = page.evaluate(
                """(sel) => {
                  const section = document.querySelector(sel);
                  if(!section) return {error: 'no-section'};
                  const text = (section.textContent || '').trim().replace(/\s+/g, ' ');
                  const pre_dump = [];
                  document.querySelectorAll(sel + ' pre').forEach((pre) => {
                    const t = (pre.textContent || '').trim();
                    if (/^\{[\s\S]*\}$/.test(t) && t.length < 400) pre_dump.push(t);
                  });
                  const object_object_hits = [];
                  document.querySelectorAll(sel + ' *').forEach((el) => {
                    const t = (el.textContent || '').trim();
                    if (t.includes('[object Object]')) {
                      object_object_hits.push({
                        tag: el.tagName,
                        cls: el.className || '',
                        text: t.slice(0, 120),
                      });
                    }
                  });
                  const json_row_dump = [];
                  document.querySelectorAll(sel + ' li, ' + sel + ' .row, ' + sel + ' .item').forEach((el) => {
                    const t = (el.textContent || '').trim();
                    if (/^\{[\s\S]*\}$/.test(t) && t.length < 200) json_row_dump.push(t);
                  });
                  return {
                    section_text_len: text.length,
                    section_text_head: text.slice(0, 220),
                    pre_json_dump_count: pre_dump.length,
                    pre_json_dump_samples: pre_dump.slice(0, 3),
                    object_object_hits: object_object_hits.slice(0, 3),
                    json_row_dump_count: json_row_dump.length,
                    json_row_dump_samples: json_row_dump.slice(0, 3),
                  };
                }""",
                sel,
            )
            findings.append({
                "target": name,
                "selector": sel,
                "clicked": clicked,
                "probe": probe,
            })

        b.close()

    n_pre = sum(1 for f in findings if f["probe"].get("pre_json_dump_count", 0) > 0)
    n_obj = sum(1 for f in findings if len(f["probe"].get("object_object_hits", [])) > 0)
    n_json = sum(1 for f in findings if f["probe"].get("json_row_dump_count", 0) > 0)
    n_blank = sum(1 for f in findings if f["probe"].get("section_text_len", 0) < 30 and "no-section" not in f["probe"])
    summary = {
        "ts": TS,
        "console_errors_total": len(console_errors),
        "page_errors_total": len(page_errors),
        "sections_with_pre_json_dump": n_pre,
        "sections_with_object_object_text": n_obj,
        "sections_with_json_row_dump": n_json,
        "sections_blank_or_minimal": n_blank,
        "console_errors_sample": console_errors[:8],
        "page_errors_sample": page_errors[:8],
        "findings": findings,
    }
    REPORT.write_text(json.dumps(summary, indent=2))
    print(f"saved: {REPORT}")
    print("--- summary ---")
    print(json.dumps({k: v for k, v in summary.items() if k != "findings"}, indent=2))
    print("--- top findings ---")
    for f in findings:
        p = f["probe"]
        hits = []
        if p.get("pre_json_dump_count", 0) > 0:
            hits.append("pre_dump=" + str(p["pre_json_dump_count"]))
        if len(p.get("object_object_hits", [])) > 0:
            hits.append("[object Object]=" + str(len(p["object_object_hits"])))
        if p.get("json_row_dump_count", 0) > 0:
            hits.append("json_row=" + str(p["json_row_dump_count"]))
        if p.get("section_text_len", 0) < 30 and "no-section" not in p:
            hits.append("BLANK(text=" + str(p["section_text_len"]) + ")")
        if hits:
            print(f"  {f['target']:14s} -> " + " | ".join(hits))
            if p.get("pre_json_dump_samples"):
                print(f"      pre sample: {p['pre_json_dump_samples'][0][:160]}")
            if p.get("object_object_hits"):
                print(f"      [object Object] sample: {p['object_object_hits'][0]['text'][:160]}")
            if p.get("json_row_dump_samples"):
                print(f"      json_row sample: {p['json_row_dump_samples'][0][:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
