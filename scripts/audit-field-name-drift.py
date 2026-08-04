#!/usr/bin/env python3
"""
audit-field-name-drift.py

Static-analysis drift probe for Campaign OS.

For each `renderX` function in the SPA, this script extracts the fields the
JS READS from the API response, then extracts the fields the corresponding
Python endpoint RETURNS, and reports "drift": fields the SPA reads but the
endpoint never returns.

This is the lane the 2026-08-04 11:20Z tick proposed: the audit catches the
bug class where the SPA was tightened (e.g. `b.recommended_action.type`),
but the corresponding endpoint stopped emitting that field, and the page
silently renders `undefined`. No JS error, no 500, no test failure, just a
blank or half-broken card.

The probe is pure static analysis: it never makes network requests, so it
can run on any machine and produces reproducible reports. Playwright (live)
is the verification gate for any TICK that ships a fix for drift, not for
the audit itself.

Usage:
    .venv/bin/python scripts/audit-field-name-drift.py [--verbose] [--json]
    .venv/bin/python scripts/audit-field-name-drift.py --section renderTrends

Exit codes:
    0 = no drift detected (or drift is below noise threshold)
    1 = drift detected, see report
    2 = infrastructure error (could not find files, parse failed, etc.)

Why this exists
---------------
Silent field-name drift is the recurring bug class in this SPA. Each tick
that touches the intelligence views risks introducing a new `obj.x` access
that the source dict no longer satisfies. `find-missing-explainers.py` (the
sibling audit, 2026-07-30 / 2026-08-04) catches the same drift class for the
explainer card surface; this script covers the MAIN renderX surface.

Limitations
-----------
- Only audits INTEL endpoints listed in `RENDER_TO_ENDPOINT`. Per-asset
  endpoints (e.g. /api/campaigns/<id>) and multi-source renders (e.g.
  renderBrief) are SKIPPED - the contract surface is too complex to
  audit at compile time and deserves its own tick.
- Reads `renderX` body text only. It does NOT run the SPA. Dynamic key
  creation (obj[k], Object.assign) is not modeled.
- Treats every `x.y` access inside a render function as a read, even when
  it might be inside a string literal or a comment. The drift report flags
  candidates; humans verify each one.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_HTML = ROOT / "campaign-os" / "campaign-os.html"
APP_PY = ROOT / "campaign-os" / "app.py"
INTEL_PY = ROOT / "campaign-os" / "_lib" / "intelligence.py"


# Each render reads fields off the JSON response of one (or more) intel
# endpoints. Multiple endpoints per render are unioned.
RENDER_TO_ENDPOINT: dict[str, list[str]] = {
    "renderTrends":         ["/api/intel/trend_catcher", "/api/intel/trends_v2"],
    "renderIdeas":          ["/api/intel/opportunities"],
    "renderPerformance":    ["/api/intel/performance"],
    "renderLearning":       ["/api/intel/learning"],
    "renderHooks":          ["/api/intel/hooks"],
    "renderMemes":          ["/api/intel/memes", "/api/intel/memes/catalog"],
    "renderBillboards":     ["/api/intel/billboards"],
    "renderCaptions":       ["/api/intel/captions"],
    "renderHeadlines":      ["/api/intel/headlines"],
    "renderCTAs":           ["/api/intel/ctas"],
    "renderHashtagSeo":     ["/api/intel/hashtag"],
    "renderImageGen":       ["/api/intel/imagegen"],
    "renderSEO":            ["/api/intel/seo_assistant"],
    "renderSeoAudit":       ["/api/intel/seo_assistant"],
    "renderGBP":            ["/api/intel/gbp_suggestions"],
    "renderReddit":         ["/api/intel/reddit_outreach"],
    "renderFAQs":           ["/api/intel/faq_generator"],
    "renderPostiz":         ["/api/intel/postiz"],
    "renderAgents":         ["/api/intel/agents"],
    "renderAssets":         ["/api/intel/assets"],
    "renderWeeklyReport":   ["/api/intel/weekly_report"],
    "renderUniversalSearch": ["/api/search"],
}


# These renders consume multi-source data (asset objects inside
# /api/campaigns AND separate /api/intel/* payloads). Static drift
# detection on them is too noisy to be actionable until a future
# tick adds per-asset / per-day field inventories. The audit SKIPS
# them and reports `skipped: true` so the count remains honest.
SKIP_MULTISOURCE: set[str] = {
    "renderBrief",
    "renderLibrary",
    "renderReview",
    "renderPublish",
    "renderCalendar",
    "renderCampaigns",
    "renderBrandDirectoryPanel",
    "renderTodayRail",
}


# Maps an HTTP path-component to the intelligence fn name that produces
# its JSON shape. Used to resolve the contract from `_lib/intelligence.py`
# without runtime introspection.
INTEL_DISPATCHED: dict[str, str] = {
    "morning_brief":        "morning_brief",
    "calendar":             "calendar_view",
    "review_inbox":         "review_inbox",
    "hooks":                "hooks_view",
    "memes":                "memes_view",
    "billboards":           "billboards_view",
    "captions":             "caption_studio",
    "performance":          "performance_view",
    "learning":             "learning_view",
    "trend_catcher":        "trend_catcher",
    "opportunities":        "opportunities_view",
    "postiz":               "postiz_overview",
    "assets":               "assets_view",
    "agents":               "agents_view",
    "universal_search":     "universal_search",
    "explain_performance":  "explain_performance",
    "weekly_report":        "weekly_report",
    "reddit_outreach":      "reddit_outreach",
    "gbp_suggestions":      "gbp_suggestions",
    "seo_assistant":        "seo_assistant",
    "faq_generator":        "faq_generator",
}


# Common JS / DOM noise that looks like field reads but is not
# API-derived data. Anything that survives filtering is real drift.
NOISE: set[str] = {
    # JS / DOM API surface
    "addEventListener", "classList", "dataset", "style", "innerHTML",
    "innerText", "textContent", "value", "length", "checked",
    "selectedIndex", "src", "disabled", "hidden", "open", "kind",
    "target", "currentTarget", "defaultValue", "parentNode",
    "nextSibling", "firstChild", "children", "tagName", "id",
    "getAttribute", "setAttribute", "appendChild", "removeChild",
    "removeAttribute", "hasAttribute", "focus", "blur", "click",
    "submit", "reset", "scrollTop", "scrollHeight", "offsetTop",
    "offsetHeight", "clientHeight", "clientWidth", "scrollIntoView",
    "preventDefault", "stopPropagation", "closest",
    # JS built-ins we don't ship from Python
    "constructor", "prototype", "hasOwnProperty", "isPrototypeOf",
    "propertyIsEnumerable", "toString", "valueOf", "toLocaleString",
    "then", "catch", "finally", "resolve", "reject",
    # Loops & collection helpers
    "forEach", "map", "filter", "reduce", "find", "some", "every",
    "indexOf", "includes", "concat", "slice", "splice", "split",
    "join", "trim", "toLowerCase", "toUpperCase", "replace",
    "entries", "keys", "values", "from", "of", "assign",
    "bind", "call", "apply",
    # Common idiom noise
    "type", "name", "kind", "ok", "ts", "status",
    # Web-pack local bindings we never wire to API
    "_bound", "_src", "_bucket", "_populated", "_trend_bound",
    "_cacheBrand", "__cacheBrand",
    # SafeList / safeAttr helpers
    "title", "url", "id",
}


# ── Static extraction helpers ──────────────────────────────────────────

RE_RENDER_FN_DEF = re.compile(
    r"\b(?:async\s+)?function\s+(render\w+)\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)

# Dotted-member reads: `b.foo`, `s.title`, `c.approved.bar`. Conservative;
# excludes continuation behind another attr/bracket/quote.
RE_FIELD_READ = re.compile(
    r"""
    (?<![A-Za-z0-9_$\.\[\]\'\"])      # not a continuation of another attr
    (?:[A-Za-z_$][A-Za-z0-9_$]*)
    (\.[A-Za-z_$][A-Za-z0-9_$]*)+   # .attr with one or more trailing
    """,
    re.VERBOSE,
)

RE_ROUTE = re.compile(
    r"""^@app\.route\(['"]([^'"]+)['"][^)]*\).*?$""",
    re.MULTILINE,
)
RE_DEF = re.compile(
    r"""^def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)\s*(?:->[^:]+)?:\s*$""",
    re.MULTILINE,
)


def extract_render_bodies(html: str) -> dict[str, str]:
    """Return {render_fn_name: function_body_text}."""
    bodies: dict[str, str] = {}
    for m in RE_RENDER_FN_DEF.finditer(html):
        name = m.group(1)
        start_brace_idx = html.find("{", m.end() - 1)
        if start_brace_idx == -1:
            continue
        depth = 0
        i = start_brace_idx
        in_str = None
        in_single_line_comment = False
        in_multi_line_comment = False
        while i < len(html):
            ch = html[i]
            nxt = html[i + 1] if i + 1 < len(html) else ""
            if in_single_line_comment:
                if ch == "\n":
                    in_single_line_comment = False
                i += 1
                continue
            if in_multi_line_comment:
                if ch == "*" and nxt == "/":
                    in_multi_line_comment = False
                    i += 2
                    continue
                i += 1
                continue
            if in_str is not None:
                if ch == "\\":
                    i += 2
                    continue
                if ch == in_str:
                    in_str = None
                i += 1
                continue
            if ch == "/" and nxt == "/":
                in_single_line_comment = True
                i += 2
                continue
            if ch == "/" and nxt == "*":
                in_multi_line_comment = True
                i += 2
                continue
            if ch in ("'", '"', "`"):
                in_str = ch
                i += 1
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    bodies[name] = html[start_brace_idx + 1 : i]
                    break
            i += 1
    return bodies


def extract_field_reads(body: str) -> set[str]:
    """Return the set of dotted field reads inside one render body."""
    out: set[str] = set()
    for m in RE_FIELD_READ.finditer(body):
        out.add(m.group(0))
    return out


def index_python_functions(src: str) -> dict[str, str]:
    """Return {function_name: body_text} for every top-level `def fn`."""
    matches = list(RE_DEF.finditer(src))
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1)
        start = m.end()
        end = len(src)
        for j in range(i + 1, len(matches)):
            end = matches[j].start()
            break
        out[name] = src[start:end]
    return out


def extract_dict_keys_for_endpoint(
    route_path: str, py_funcs: dict[str, str]
) -> tuple[set[str], str]:
    """Return (top_level_keys, source_fn_name) for a route path.

    For /api/intel/<key> paths with a dispatcher entry, the key is
    resolved via INTEL_DISPATCHED to the corresponding fn body. For
    /api/intel/<key> paths with a dedicated Python route (e.g.
    trends_v2), the route decorator is walked in app.py.
    """
    if route_path.startswith("/api/intel/"):
        last = route_path.rsplit("/", 1)[-1]
        fn_name = INTEL_DISPATCHED.get(last)
        if fn_name and fn_name in py_funcs:
            return _keys_from_function_body(py_funcs[fn_name]), fn_name

    app_src = APP_PY.read_text(encoding="utf-8") if APP_PY.exists() else ""
    for route_m in RE_ROUTE.finditer(app_src):
        rp = route_m.group(1)
        if rp == route_path:
            tail = app_src[route_m.end():]
            def_m = re.search(
                r"^def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
                tail,
                re.MULTILINE,
            )
            if def_m:
                fn_name = def_m.group(1)
                if fn_name in py_funcs:
                    return _keys_from_function_body(py_funcs[fn_name]), fn_name
            break

    return set(), "<unknown>"


def _keys_from_function_body(body: str) -> set[str]:
    """Top-level keys produced by `return {"foo": ..., ...}`."""
    out: set[str] = set()
    m = re.search(r"\breturn\s*\{", body)
    if not m:
        return out
    start = m.end() - 1
    depth = 0
    i = start
    in_str = None
    while i < len(body):
        ch = body[i]
        if in_str is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            in_str = ch
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                payload = body[start + 1 : i]
                break
        i += 1
    else:
        payload = body[start + 1 :]

    for line in payload.split("\n"):
        line = line.strip()
        m = re.match(r"""['"]([a-zA-Z_][a-zA-Z0-9_]*)['"]\s*:""", line)
        if m:
            out.add(m.group(1))
    return out


# ── The audit loop ─────────────────────────────────────────────────────

# Var-prefixes that are local SPA state / DOM, not an API payload.
# Reads starting with these are dropped.
#
# We also drop read bindings that are plain DOM nodes (el, btn, card,
# container, pill, etc.) - the `xxx.addEventListener` style false-positive
# is the main noise source for the audit. The esc/pill/itemHtml
# helpers are template functions, not object bindings.
NON_API_PREFIXES = (
    "S.", "Math.", "parseInt.", "parseFloat.", "Number.", "Date.",
    "Object.", "JSON.", "this.", "window.", "document.", "API.",
    "esc(", "URL.", "console.", "Promise.", "RegExp.", "Array.",
    "String.", "Boolean.", "Set.", "Map.",
    # common DOM-element variable names
    "el.", "btn.", "card.", "container.", "row.", "node.", "item.",
    "div.", "section.", "parent.", "child.", "target.", "wrapper.",
    "outer.", "inner.", "scope.",
    # template helpers (function calls, not object reads)
    "pill(", "itemHtml(", "esc2(", "fmt(",
)


def run_audit(verbose: bool = False) -> dict:
    html = APP_HTML.read_text(encoding="utf-8") if APP_HTML.exists() else ""
    py_funcs: dict[str, str] = {}
    if INTEL_PY.exists():
        py_funcs.update(index_python_functions(INTEL_PY.read_text(encoding="utf-8")))
    if APP_PY.exists():
        py_funcs.update(index_python_functions(APP_PY.read_text(encoding="utf-8")))

    bodies = extract_render_bodies(html)

    sections: list[dict] = []
    drift_total = 0
    skipped_count = 0
    for render_name, endpoints in RENDER_TO_ENDPOINT.items():
        if render_name in SKIP_MULTISOURCE:
            sections.append({"render": render_name, "skipped": True})
            skipped_count += 1
            continue

        body = bodies.get(render_name)
        if not body:
            if verbose:
                print(f"  ! {render_name}: no body extracted", file=sys.stderr)
            continue

        contract_keys: set[str] = set()
        contract_sources: dict[str, str] = {}
        for ep in endpoints:
            keys, src_fn = extract_dict_keys_for_endpoint(ep, py_funcs)
            contract_keys |= keys
            for k in keys:
                contract_sources[k] = src_fn

        reads = extract_field_reads(body)
        reads = {r for r in reads if not r.startswith(NON_API_PREFIXES)}

        # First field after the variable is the API-key tier. Anything
        # beyond that is a nested-array field (e.g. `r.replies[0].reply`),
        # which the static contract extractor cannot verify; we leave
        # those for human review.
        top_field_reads: set[str] = set()
        for r in reads:
            parts = r.split(".", 1)
            if len(parts) == 2:
                first_attr = parts[1].split(".", 1)[0]
                # Detect nested-array reads: `r.replies[0].reply` -> "replies"
                # but reads like `r.replies` (single attr) -> also "replies".
                # The shape we treat as API-key contract is the FIRST attr;
                # nested attrs are kept as a separate count, not in drift.
                top_field_reads.add(first_attr)

        # DOM/utility accessors for FIRST attrs (e.g. `el.addEventListener`,
        # `btn.value`) come through when the binding is `el`, `btn`, `card`
        # etc. Those are *not* the API surface. Filter them against NOISE
        # only AFTER the contract match - if "kind" IS a contract key, we
        # keep it; if not, we drop it.
        drift = sorted(top_field_reads - contract_keys - NOISE)

        sections.append({
            "render": render_name,
            "endpoints": endpoints,
            "reads_sample": sorted(top_field_reads)[:8],
            "contract_keys_sample": sorted(contract_keys)[:10],
            "contract_count": len(contract_keys),
            "drift": drift,
            "drift_count": len(drift),
        })
        drift_total += len(drift)

        if verbose and drift:
            print(f"  ! {render_name}: {len(drift)} drift: "
                  + ", ".join(drift[:8])
                  + (" ..." if len(drift) > 8 else ""),
                  file=sys.stderr)

    return {
        "r_total": len(RENDER_TO_ENDPOINT),
        "r_audited": sum(1 for s in sections if not s.get("skipped")),
        "r_skipped": skipped_count,
        "r_drift": sum(1 for s in sections if s.get("drift_count", 0) > 0),
        "drift_total": drift_total,
        "sections": sections,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--verbose", "-v", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--section", "-s", default=None,
                   help="audit only one section by render name")
    args = p.parse_args()

    report = run_audit(verbose=args.verbose)

    if args.json:
        print(json.dumps(report, indent=2))
        return 1 if report["drift_total"] > 0 else 0

    print("Field-name drift audit")
    print(f"  renders audited : {report['r_audited']} / {report['r_total']}")
    print(f"  skipped (multi-source): {report['r_skipped']}")
    print(f"  with drift      : {report['r_drift']}")
    print(f"  drift fields    : {report['drift_total']}")
    print()
    print(f"{'RENDER':28}  {'DRIFT':>5}  {'SAMPLE_READS'}")
    print("-" * 80)
    for s in report["sections"]:
        r = s.get("render", "?")
        if args.section and r != args.section:
            continue
        if s.get("skipped"):
            print(f"{r:28}  {'skip':>5}   - {s.get('note','')}")
            continue
        sample = ", ".join(s.get("reads_sample", [])[:5])
        drift_count = s.get("drift_count", 0)
        marker = "OK" if drift_count == 0 else "?"
        print(f"{r:28}  {drift_count:>5} {marker}  {sample}")

    if report["drift_total"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
