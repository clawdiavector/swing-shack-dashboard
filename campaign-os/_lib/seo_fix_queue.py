"""SEO/GEO fix queue: turn daily site-audit findings into a queue of fixes.

Policy (approved by Christelle 2026-10-19, wiki decisions/seo-geo-automation-tiers):
  1. Audits and drafting run automatically. Nothing here writes to the live site.
  2. Only meta descriptions on non-homepage pages are eligible to publish
     automatically (with an undo). That publish path does not exist yet; the
     queue only marks which items would be eligible.
  3. Everything else asks first: the homepage, anything about price, location,
     entity or claims, and any finding type this module does not know.

Pure functions. The site_audit job calls sync() after each run and stores the
result; GET /api/seo/fix-queue reads it back.
"""
from __future__ import annotations

import hashlib
from typing import Any

# The audit's pages, wording and local terms are Swing Shack's. Do not queue
# fixes for another brand until it has its own page list.
QUEUE_BRANDS = ("swing-shack",)

HOMEPAGE = "Homepage"
MAX_RESOLVED_KEPT = 100

# Finding types that are only ever eligible for automatic publishing.
AUTO_PUBLISH_TYPES = frozenset({"missing_meta_description", "meta_description_short"})

# Finding types about price, location, who/what the business is, or claims.
ALWAYS_ASK_TYPES = frozenset(
    {
        "missing_price",
        "missing_duration",
        "missing_cta",
        "unclear_entity",
        "unclear_offering",
        "missing_location",
        "missing_local_signals",
    }
)

# Existing /api/geo/apply-fix check ids that already build the snippet.
APPLY_FIX_CHECK = {
    "missing_meta_description": "missing_meta_description",
    "missing_h1": "missing_h1",
    "missing_faq": "missing_faq",
    "no_qa_blocks": "missing_faq",
    "no_structured_data": "missing_organization_schema",
}

PUBLISH_AUTO = "auto_with_undo"
PUBLISH_ASK = "asks_first"


def classify(finding_type: str, page: str | None) -> str:
    """Return PUBLISH_AUTO or PUBLISH_ASK. Unknown types always ask."""
    if page == HOMEPAGE or finding_type in ALWAYS_ASK_TYPES:
        return PUBLISH_ASK
    if finding_type in AUTO_PUBLISH_TYPES:
        return PUBLISH_AUTO
    return PUBLISH_ASK


def item_id(brand: str, source: str, finding_type: str, page: str | None) -> str:
    key = "|".join([brand, source, finding_type, page or ""])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _item(brand: str, source: str, finding: dict[str, Any], fix: str | None, now: str) -> dict[str, Any]:
    ftype = str(finding.get("type") or "unknown")
    page = finding.get("page")
    return {
        "id": item_id(brand, source, ftype, page),
        "brand": brand,
        "source": source,
        "type": ftype,
        "page": page,
        "severity": finding.get("severity"),
        "message": finding.get("message"),
        "fix": fix,
        "apply_via": APPLY_FIX_CHECK.get(ftype),
        "publish_policy": classify(ftype, page),
        "status": "draft",
        "first_seen": now,
        "last_seen": now,
    }


def sync(
    brand: str,
    seo_findings: list[dict[str, Any]],
    geo_findings: list[dict[str, Any]],
    previous: dict[str, Any] | None,
    now: str,
    geo_fixes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Merge today's findings into the previous queue.

    Existing items keep their id, first_seen and any status a person set
    (dismissed, done). A draft whose finding is gone becomes resolved. Raises
    for a brand with no queue, so another brand's findings are never queued
    under Swing Shack's rules.
    """
    if brand not in QUEUE_BRANDS:
        raise ValueError(f"no SEO fix queue for brand {brand!r}; supported: {', '.join(QUEUE_BRANDS)}")

    geo_fixes = geo_fixes or {}
    current: dict[str, dict[str, Any]] = {}
    for f in seo_findings:
        it = _item(brand, "seo", f, None, now)
        current[it["id"]] = it
    for f in geo_findings:
        it = _item(brand, "geo", f, geo_fixes.get(str(f.get("type"))), now)
        current[it["id"]] = it

    old = {i["id"]: i for i in (previous or {}).get("items", []) if isinstance(i, dict) and i.get("id")}

    items: list[dict[str, Any]] = []
    for iid, it in current.items():
        prev = old.get(iid)
        if prev:
            it["first_seen"] = prev.get("first_seen") or now
            # A person's decision sticks; a resolved item that reappears is a draft again.
            if prev.get("status") in ("dismissed", "done"):
                it["status"] = prev["status"]
        items.append(it)

    resolved: list[dict[str, Any]] = []
    for iid, prev in old.items():
        if iid in current:
            continue
        kept = dict(prev)
        if kept.get("status") == "draft":
            kept["status"] = "resolved"
            kept["resolved_at"] = now
        resolved.append(kept)
    resolved.sort(key=lambda i: i.get("resolved_at") or i.get("last_seen") or "", reverse=True)
    items.extend(resolved[:MAX_RESOLVED_KEPT])

    open_items = [i for i in items if i["status"] == "draft"]
    return {
        "brand": brand,
        "updated": now,
        "counts": {
            "open": len(open_items),
            "auto_eligible": sum(1 for i in open_items if i["publish_policy"] == PUBLISH_AUTO),
            "asks_first": sum(1 for i in open_items if i["publish_policy"] == PUBLISH_ASK),
        },
        "items": items,
    }
