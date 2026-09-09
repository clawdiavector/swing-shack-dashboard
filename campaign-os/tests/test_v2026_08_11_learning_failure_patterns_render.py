"""Test for the Learning > Failure patterns fix.

Verifies:
- _flattenFailurePatterns extracts rows from the by_agent_partial / by_agent_fail / by_time nested shape
- Renders the right number of rows
- Falls through to the empty state when no signal across all sub-fields
- Survives a missing field (only by_agent_partial set)
"""
import json
import urllib.request
import urllib.parse
import os
import sys

BASE = "http://127.0.0.1:8765"
PW   = "swing-shack-dev-2026"


def _login():
    """Hit /login with shared password and return the cookie jar."""
    import http.cookiejar
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    data = urllib.parse.urlencode({"password": PW}).encode()
    req = urllib.request.Request(BASE + "/login", data=data, method="POST",
                                  headers={"Content-Type": "application/x-www-form-urlencoded"})
    opener.open(req, timeout=10)
    return opener


def _get(opener, path):
    return json.loads(opener.open(BASE + path, timeout=10).read())


def test_learn_endpoint_has_rich_shape():
    """The /api/intel/learning endpoint returns a rich failure_patterns object,
    not a flat list. Pre-fix this meant the card always rendered empty."""
    op = _login()
    learn = _get(op, "/api/intel/learning")
    assert learn.get("ok"), f"learning endpoint not ok: {learn}"
    fp = learn.get("failure_patterns") or {}
    assert isinstance(fp, dict), f"failure_patterns should be a dict, got {type(fp).__name__}"
    # At least one of the nested fields should exist
    has_signal = any([
        fp.get("by_agent_partial") and any(v > 0 for v in fp["by_agent_partial"].values()),
        fp.get("by_agent_fail") and any(v > 0 for v in fp["by_agent_fail"].values()),
        fp.get("by_time") and any(
            isinstance(v, dict) and (v.get("partials", 0) + v.get("fails", 0)) > 0
            for v in fp["by_time"].values()
        ),
    ])
    assert has_signal, "Expected at least one failure_patterns sub-field with positive counts"


def test_render_learning_includes_failure_rows():
    """Render the learning section via Playwright, count rows in #learn-fail-pat.

    Pre-fix: 0 rows (empty state shown).
    Post-fix: >= 1 row showing agent/time data.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        errors = []
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(BASE, wait_until="domcontentloaded")
        page.fill("input[type=password]", PW)
        page.evaluate("const b=document.querySelector('button[type=submit]');if(b)b.click();")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
        # Dismiss tour
        page.evaluate("const b=Array.from(document.querySelectorAll('button,a,.mini-link')).find(x=>/skip the tour/i.test(x.textContent||''));if(b)b.click();")
        page.wait_for_timeout(300)
        page.evaluate("if(typeof go==='function')go('learning');")
        page.wait_for_timeout(2200)

        row_count = page.evaluate("document.querySelectorAll('#learn-fail-pat .li').length")
        opt_out = page.evaluate("document.querySelectorAll('#learn-fail-pat [data-no-image-link]').length")
        gen_btns = page.evaluate("document.querySelectorAll('#learn-fail-pat .image-link-cluster').length")
        empty = page.evaluate("!!document.querySelector('#learn-fail-pat .empty')")

        # Capture one row sample
        sample = page.evaluate("""
          (() => {
            const li = document.querySelector('#learn-fail-pat .li');
            return li ? li.innerText.replace(/\\n+/g,' | ').trim() : '';
          })()
        """)

        assert not errors, f"Console/page errors: {errors}"
        assert row_count >= 1, f"Expected >= 1 failure-pattern row, got {row_count}"
        assert opt_out == row_count, f"All {row_count} rows should have data-no-image-link, got {opt_out}"
        assert gen_btns == 0, f"Expected 0 injected Generate buttons on opt-out rows, got {gen_btns}"
        assert not empty, f"Expected non-empty, got empty state"
        assert sample and ("morning" in sample.lower() or "partial" in sample.lower() or any(
            name in sample for name in ["hook_smith", "pulse_keeper", "blog_beast", "qa_inspector", "reddit_ghost"]
        )), f"Sample row looks wrong: {sample!r}"

        print(f"OK rows={row_count} opt_out={opt_out} gen_btns={gen_btns} empty={empty}")
        print(f"OK sample={sample!r}")
        b.close()


def test_flatten_helper_handles_empty_and_partial():
    """The _flattenFailurePatterns helper should:
    - return [] for null / undefined / non-object input
    - return [] for {} input (no signal anywhere)
    - return rows when only by_agent_partial is populated
    - return rows when only by_time is populated
    """
    # We test via the running page (helper is in the bundle).
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        page = b.new_context().new_page()
        page.goto(BASE, wait_until="domcontentloaded")
        page.fill("input[type=password]", PW)
        page.evaluate("const b=document.querySelector('button[type=submit]');if(b)b.click();")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        results = page.evaluate("""
          ({
            null:    typeof _flattenFailurePatterns==='function' ? _flattenFailurePatterns(null) : 'no-helper',
            undef:   typeof _flattenFailurePatterns==='function' ? _flattenFailurePatterns(undefined) : 'no-helper',
            empty:   typeof _flattenFailurePatterns==='function' ? _flattenFailurePatterns({}) : 'no-helper',
            arr:     typeof _flattenFailurePatterns==='function' ? _flattenFailurePatterns([1,2,3]) : 'no-helper',
            partialOnly: typeof _flattenFailurePatterns==='function' ? _flattenFailurePatterns({by_agent_partial: {foo: 2}}) : 'no-helper',
            timeOnly:    typeof _flattenFailurePatterns==='function' ? _flattenFailurePatterns({by_time: {morning: {total: 5, partials: 2, fails: 0}}}) : 'no-helper',
          })
        """)
        b.close()

    assert results["null"] == [], f"null -> {results['null']!r}"
    assert results["undef"] == [], f"undefined -> {results['undef']!r}"
    assert results["empty"] == [], f"empty obj -> {results['empty']!r}"
    assert results["arr"] == [], f"array -> {results['arr']!r} (should treat non-objects as no signal)"
    assert len(results["partialOnly"]) == 1, f"partialOnly -> {results['partialOnly']!r}"
    assert results["partialOnly"][0]["kind"] == "agent"
    assert results["partialOnly"][0]["label"] == "foo"
    assert "2" in results["partialOnly"][0]["value"]
    assert len(results["timeOnly"]) == 1, f"timeOnly -> {results['timeOnly']!r}"
    assert results["timeOnly"][0]["kind"] == "time"
    assert "morning" in results["timeOnly"][0]["label"]
    print("OK helper edges pass", results)


if __name__ == "__main__":
    test_learn_endpoint_has_rich_shape()
    test_render_learning_includes_failure_rows()
    test_flatten_helper_handles_empty_and_partial()
    print("ALL PASS")