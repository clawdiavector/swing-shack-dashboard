#!/usr/bin/env python3
"""Turn a markdown blog draft (docs/seo/blog-drafts/*.md) into a Writer artifact.

The Review page ("Approve drafts") reads Writer artifacts: JSON files at
data/writer-artifacts/<brand>/<slug>.json that the boot patch copies onto the
volume. This lets a draft written as plain markdown be reviewed, edited,
commented on and approved section by section inside Campaign OS, instead of
somewhere outside it.

The artifact says draft_status WRITTEN, publishing NONE, live_site_changes
NONE. Review never publishes; publishing is a separate, later, human step.

Usage:
  python campaign-os/scripts/seo_draft_to_writer_artifact.py docs/seo/blog-drafts/01-*.md --brand swing-shack
  (writes data/writer-artifacts/<brand>/<slug>.json; brief id is seo-brief-<slug>)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Where each claim in a draft comes from. Rows are plain language; status VERIFIED
# only where a person or a file confirmed it. Keyed by draft slug.
VENUE_ROWS = [
    {
        "claim": "Swing Shack is at Old Parktonian Sports Club, 1 Garden Road, Bordeaux, Randburg, Johannesburg",
        "evidence_layer": "OFFICIAL BUSINESS",
        "evidence_source": "swingshack.co.za footer and page schema, Google Maps listing; Christelle confirmed Old Parks and Old Parktonian are the same place and Randburg is in Johannesburg (2026-10-21)",
        "evidence_type": "official-business",
        "status": "VERIFIED",
    },
    {
        "claim": "Open Monday to Saturday 09:00 to 21:00 and Sunday 09:00 to 17:00",
        "evidence_layer": "OFFICIAL BUSINESS",
        "evidence_source": "Google Business Profile hours, from Christelle's screenshot 2026-10-23. The website's hidden search data says 07:00 to 21:00 Monday to Saturday and 09:00 to 18:00 Sunday, which is out of date",
        "evidence_type": "official-business",
        "status": "VERIFIED",
    },
    {
        "claim": "Clubs can be hired on request; walk-ins are welcome but a bay cannot be guaranteed, so book online; parking is ample",
        "evidence_layer": "OFFICIAL BUSINESS",
        "evidence_source": "Christelle, chat 2026-10-21",
        "evidence_type": "operator-statement",
        "status": "VERIFIED",
    },
    {
        "claim": "Sessions are 30 or 60 minutes",
        "evidence_layer": "OFFICIAL BUSINESS",
        "evidence_source": "data/brand-directory/swing-shack/voice/do-say-dont-say.md",
        "evidence_type": "brand-file",
        "status": "VERIFIED",
    },
]

TRACKMAN_ROW = {
    "claim": "Definitions of club head speed, smash factor, attack angle, club path and face angle",
    "evidence_layer": "EDITORIAL",
    "evidence_source": "General launch monitor definitions, not Swing Shack claims",
    "evidence_type": "common-knowledge",
    "status": "EDITORIAL / EXPLANATORY",
    "action_taken": "kept; a coach should read once before publishing",
}

FLAGS = {
    "01-indoor-golf-johannesburg-what-to-expect": [
        {"flag": "PHOTO", "detail": "Needs a real bay photo as the lead image. Never a render."},
    ],
    "02-golf-lessons-johannesburg-first-session": [
        {"flag": "COACHES AND PRICES", "detail": "No coach names or prices are given on purpose. Add coach names you are happy to publish, and link to the lesson product page for prices."},
        {"flag": "PHOTO", "detail": "Needs a real photo of a lesson in the bay."},
    ],
    "03-trackman-numbers-explained": [
        {"flag": "COACH READ", "detail": "Definitions are general launch monitor definitions. A coach should read them once before this is approved. No target numbers are given on purpose."},
    ],
}


def _front_matter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not m:
        return {}, text
    meta: dict = {}
    key = None
    for line in m.group(1).splitlines():
        if re.match(r"^\s+- ", line) and key:
            meta.setdefault(key, []).append(line.split("- ", 1)[1].strip())
            continue
        kv = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if kv:
            key = kv.group(1)
            meta[key] = kv.group(2).strip() if kv.group(2).strip() else []
    return meta, text[m.end():]


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def slug_of(path: Path) -> str:
    stem = path.stem
    return re.sub(r"^\d+-", "", stem) if not stem[0].isalpha() else stem


def build(path: Path, brand: str) -> tuple[str, dict]:
    text = path.read_text(encoding="utf-8")
    meta, body = _front_matter(text)
    body = body.strip() + "\n"
    title_m = re.search(r"^#\s+(.+?)\s*$", body, re.M)
    title = title_m.group(1) if title_m else path.stem
    slug = slug_of(path)
    internal = [l for l in (meta.get("internal_links") or []) if isinstance(l, str)]
    rows = [dict(r) for r in VENUE_ROWS]
    if slug.startswith("trackman"):
        rows.append(dict(TRACKMAN_ROW))
    flags = FLAGS.get(path.stem, [])
    artifact = {
        "status": "DRAFT_FOR_REVIEW",
        "draft_status": "WRITTEN",
        "publishing": "NONE",
        "live_site_changes": "NONE",
        "operating_brand": brand,
        "approved_brief_id": f"seo-brief-{slug}",
        "writer_mode": "NEW",
        "source": f"markdown draft {_repo_relative(path)}",
        "seo_metadata": {
            "target_keyword": meta.get("target_keyword", ""),
            "secondary_keywords": meta.get("secondary_keywords", ""),
            "meta_title": meta.get("meta_title", ""),
            "meta_description": meta.get("meta_description", ""),
        },
        "human_facing_article_draft": body,
        "human_facing_article": {
            "title": title,
            "body": re.sub(r"^#\s+.+\n+", "", body, count=1),
            "cta": "Book a session",
            "cta_url": "https://swingshack.co.za/bookings/",
        },
        "internal_links_used": [
            {"anchor": l, "url": f"https://swingshack.co.za{l}", "why": "linked from the draft"} for l in internal
        ],
        "cta": {"chosen": "Book a session", "url": "https://swingshack.co.za/bookings/", "rationale": "Every draft ends on the bookings page."},
        "fact_check": rows,
        "evidence_still_needed": [f["detail"] for f in flags],
        "review_flags": flags,
    }
    return slug, artifact


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("drafts", nargs="+", type=Path)
    ap.add_argument("--brand", default="swing-shack", choices=["swing-shack", "stick", "bag-drop"])
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "writer-artifacts")
    args = ap.parse_args(argv)
    for d in args.drafts:
        slug, artifact = build(d, args.brand)
        dest = args.out / args.brand / f"{slug}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{d.name} -> {dest}  (brief seo-brief-{slug})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
