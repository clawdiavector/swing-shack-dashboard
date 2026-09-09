#!/usr/bin/env python3
"""
find-missing-explainers.py — diff sec-* section ids against EXPLAINERS dict keys
in campaign-os/campaign-os.html. Prints the surfaces that need an explainer.

Used by Campaign OS nightshift to pick the next explainer tick when
last-report.md's "Next pick" is stale. See skill pitfall #8 ("Ship-the-explainer
is a 36-line change") and the "EXPLAINERS gap analysis recipe" section.

Usage:
    .venv/bin/python scripts/find-missing-explainers.py [--explainer-key KEY]

By default prints ALL section ids missing an EXPLAINERS key. Pass --explainer-key
to constrain to one section (useful for ad-hoc checks like "did this ship?").
Exits 0 always; parse the stdout for picks.
"""

import argparse
import re
import sys
from pathlib import Path

# Walk up to find campaign-os.html. Try a few layouts:
#   1. <repo>/scripts/find-missing-explainers.py  ->  <repo>/campaign-os/campaign-os.html
#   2. <repo>/<sub>/scripts/find-missing-explainers.py  ->  <repo>/campaign-os/campaign-os.html
#   3. <home>/.hermes/profiles/<p>/skills/<skill>/scripts/  ->  walk up to a workspace dir
# Strategy: from the script's own dir, walk up. At each level, check (a) sibling
# campaign-os/campaign-os.html and (b) campaign-os/campaign-os.html at the walk-up
# parent's location. Bail at depth 8 to avoid runaway loops.
HTML_PATH = None
probe = Path(__file__).resolve().parent
for _depth in range(8):
    candidates = [
        probe / "campaign-os" / "campaign-os.html",          # script lives in <repo>/scripts/
        probe.parent / "campaign-os" / "campaign-os.html",   # script lives in <repo>/<sub>/scripts/
    ]
    for c in candidates:
        if c.exists():
            HTML_PATH = c
            break
    if HTML_PATH:
        break
    probe = probe.parent

if not HTML_PATH:
    print("ERROR: could not locate campaign-os/campaign-os.html (walked 8 levels up from script)", file=sys.stderr)
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--explainer-key", help="Check whether a single section id is missing its explainer")
    args = ap.parse_args()

    html = HTML_PATH.read_text()

    # All section ids, deduped + sorted.
    sec_ids = sorted(set(re.findall(r'id="sec-([a-z0-9-]+)"', html)))

    # EXPLAINERS dict = the first `const EXPLAINERS = { ... };` block.
    m = re.search(r"const EXPLAINERS\s*=\s*\{(.*?)^\s*\};", html, re.DOTALL | re.MULTILINE)
    if not m:
        print("ERROR: could not find EXPLAINERS dict in HTML", file=sys.stderr)
        sys.exit(2)
    expl_block = m.group(1)
    # Keys look like: 'foo': {  (section) or 'foo-bar': { or 'ga4': { (analytics).
    # Character class includes digits so 'ga4' is not silently dropped (regression note 2026-08-04).
    expl_keys = sorted(set(re.findall(r"'([a-z0-9-]+)':\s*\{", expl_block)))

    # Every key in EXPLAINERS can serve as a section explainer because HELP.section
    # looks up EXPLAINERS[id] when mounting (see HELP const in campaign-os.html).
    # The dual-purpose case ('seo' is BOTH a section key and an analytics key in
    # EXPLAINERS_ANALYTICS) is fine: HELP.section('seo', 'seo') mounts BOTH panels,
    # the section body from EXPLAINERS + the analytics primer from EXPLAINERS_ANALYTICS.
    # The previous hardcoded ANALYTICS_KEYS = {'ga4','meta','seo'} denylist wrongly
    # classified 'seo' as analytics-only and produced a false-positive "missing"
    # row for sec-seo even though the polished 4-card explainer mounts correctly.
    section_expl_keys = set(expl_keys)
    # Reporting transparency: surface which keys are also in ANALYTICS so future
    # audits know what's a dual-purpose entry.
    analytics_keys = set()
    m_a = re.search(r"const EXPLAINERS_ANALYTICS\s*=\s*\{(.*?)^\s*\};", html, re.DOTALL | re.MULTILINE)
    if m_a:
        analytics_keys = set(re.findall(r"'([a-z0-9-]+)':\s*\{", m_a.group(1)))
    dual_purpose = sorted(section_expl_keys & analytics_keys)
    analytics_only = sorted(analytics_keys - section_expl_keys)

    if args.explainer_key:
        present = args.explainer_key in section_expl_keys
        print(f"PASS: {args.explainer_key} explainer present" if present else f"MISS: {args.explainer_key} explainer missing")
        sys.exit(0 if present else 1)

    missing = [s for s in sec_ids if s not in section_expl_keys]
    present = [s for s in sec_ids if s in section_expl_keys]

    print(f"Sections with explainers ({len(present)}/{len(sec_ids)}):")
    for s in present:
        print(f"  ok  sec-{s}")
    print()
    print(f"Missing explainers ({len(missing)}):")
    for s in missing:
        print(f"  --  sec-{s}")
    if dual_purpose or analytics_only:
        print()
        print(f"Dual-purpose keys (in EXPLAINERS + EXPLAINERS_ANALYTICS): {dual_purpose}")
        print(f"Analytics-only keys (in EXPLAINERS_ANALYTICS only):         {analytics_only}")
    print()
    print("Next pick tip: ladder-surface pairings worth considering:")
    print("  seo + seo-audit + hashtagseo + faqs + library + gbp  → SEO content cluster")
    print("  billboards + imagegen                                  → visual-content cluster")
    print("  reddit + faqs + gbp                                     → outreach/answering cluster")
    print("  postiz + campaigns + agents                             → ops cluster")


if __name__ == "__main__":
    main()
