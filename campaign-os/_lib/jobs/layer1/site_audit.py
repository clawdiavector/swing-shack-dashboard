"""Run SEO + GEO site audits and write seo-audit.json / geo-audit.json."""

from __future__ import annotations

import os
import re
from typing import Any

import requests

from ..errors import describe_exception
from ._io import atomic_write, io_for_job, resolve_brand_domain, utc_now_iso

JOB_NAME = "site_audit"

SEO_OUTPUT = "seo-audit.json"
GEO_OUTPUT = "geo-audit.json"
USER_AGENT = "SwingShackCampaignOS/1.0 (site audit; contact ops)"
FETCH_TIMEOUT = 15
MAX_BYTES = 80_000

PAGES = (
    {"url_suffix": "", "name": "Homepage"},
    {"url_suffix": "/membership", "name": "Membership"},
    {"url_suffix": "/coaching", "name": "Coaching"},
    {"url_suffix": "/club-fitting", "name": "Club Fitting"},
)


def _site_base(brand: str | None = None) -> tuple[str | None, str | None]:
    domain, err = resolve_brand_domain(brand)
    if err:
        return None, err
    if domain.startswith("http://") or domain.startswith("https://"):
        return domain.rstrip("/"), None
    return f"https://{domain.rstrip('/')}", None


def _fetch_page(url: str) -> str:
    """Fetch page HTML; patch in tests."""
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=FETCH_TIMEOUT,
        stream=True,
    )
    resp.raise_for_status()
    chunks: list[bytes] = []
    size = 0
    for chunk in resp.iter_content(chunk_size=8192):
        if not chunk:
            continue
        chunks.append(chunk)
        size += len(chunk)
        if size >= MAX_BYTES:
            break
    return b"".join(chunks).decode("utf-8", errors="replace")


def _audit_seo_page(html: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    title = title_match.group(1).strip() if title_match else ""
    if not title:
        findings.append({"type": "missing_title", "severity": "high", "message": "Page missing <title> tag"})
    elif len(title) < 30:
        findings.append(
            {
                "type": "title_too_short",
                "severity": "medium",
                "message": f"Title too short ({len(title)} chars): \"{title}\"",
            }
        )
    elif len(title) > 60:
        findings.append(
            {
                "type": "title_too_long",
                "severity": "medium",
                "message": f"Title too long ({len(title)} chars): \"{title[:60]}...\"",
            }
        )

    desc_match = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]+)"', html, re.I)
    if not desc_match:
        findings.append(
            {"type": "missing_meta_description", "severity": "high", "message": "Missing meta description"}
        )
    elif len(desc_match.group(1)) < 120:
        findings.append(
            {"type": "meta_description_short", "severity": "medium", "message": "Meta description too short"}
        )

    h1_matches = re.findall(r"<h1[^>]*>([^<]+)</h1>", html, re.I)
    if not h1_matches:
        findings.append({"type": "missing_h1", "severity": "high", "message": "No H1 found"})
    elif len(h1_matches) > 1:
        findings.append(
            {
                "type": "multiple_h1",
                "severity": "medium",
                "message": f"Multiple H1s ({len(h1_matches)})",
            }
        )

    img_without_alt = len(re.findall(r"<img(?![^>]*alt=)[^>]*>", html, re.I))
    if img_without_alt > 0:
        findings.append(
            {
                "type": "images_missing_alt",
                "severity": "medium",
                "message": f"{img_without_alt} images missing alt text",
            }
        )

    if not re.search(r"faq|FAQ|frequently", html):
        findings.append(
            {
                "type": "missing_faq",
                "severity": "low",
                "message": "No FAQ section found - adding FAQ could improve SEO",
            }
        )

    local_signals = ("johannesburg", "randburg", "south africa", "sa", "parkview")
    if not any(s in html.lower() for s in local_signals):
        findings.append(
            {
                "type": "missing_local_signals",
                "severity": "medium",
                "message": "Page missing local intent terms (Johannesburg/Randburg/SA)",
            }
        )

    internal_links = len(re.findall(r'href="(https?://[^"]*swingshack[^"]+)"', html, re.I))
    if internal_links < 3:
        findings.append(
            {
                "type": "weak_internal_linking",
                "severity": "low",
                "message": f"Only {internal_links} internal links found",
            }
        )

    return findings


def _audit_geo_page(html: str, url: str) -> tuple[list[dict[str, Any]], list[str]]:
    findings: list[dict[str, Any]] = []
    positive: list[str] = []
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()

    has_who = re.search(r"(Swing Shack|coaches|instructors| certified|TrackMan)", html, re.I)
    has_what = re.search(r"(golf|simulator|fitting|lessons|sessions|indoor)", html, re.I)
    has_where = re.search(r"(Johannesburg|Randburg|Parkview|South Africa|SA)", html, re.I)

    if has_who and has_what and has_where:
        positive.append("Clear entity signals (who/what/where) present")
    else:
        if not has_who:
            findings.append(
                {
                    "type": "unclear_entity",
                    "severity": "medium",
                    "message": "Page does not clearly identify who provides the service",
                }
            )
        if not has_what:
            findings.append(
                {
                    "type": "unclear_offering",
                    "severity": "high",
                    "message": "Page does not clearly state what the service is",
                }
            )
        if not has_where:
            findings.append(
                {
                    "type": "missing_location",
                    "severity": "high",
                    "message": "Page does not clearly state the location",
                }
            )

    qa_blocks = len(re.findall(r"<dl>|<dt>|<dd>|<h[23][^>]*>(?:What|Why|How|Is|Can|Should)", html, re.I))
    if qa_blocks > 2:
        positive.append(f"{qa_blocks} Q&A blocks found - good for AI extraction")
    else:
        findings.append(
            {
                "type": "no_qa_blocks",
                "severity": "medium",
                "message": "No clear Q&A blocks found - AI summaries may miss key info",
            }
        )

    service_pages = ("membership", "coaching", "fitting", "lessons", "practice")
    page_service = next((s for s in service_pages if s in url), None)
    if page_service:
        has_price = re.search(r"R\s*\d+", html)
        has_duration = re.search(r"\d+\s*(min|hour|session)", html, re.I)
        has_cta = re.search(r"(book|contact|call|schedule|get started)", html, re.I)
        if has_price and has_duration and has_cta:
            positive.append(f"{page_service} page has clear pricing, duration, and CTA")
        else:
            if not has_price:
                findings.append(
                    {
                        "type": "missing_price",
                        "severity": "medium",
                        "message": f"{page_service} page missing pricing",
                    }
                )
            if not has_duration:
                findings.append(
                    {
                        "type": "missing_duration",
                        "severity": "low",
                        "message": f"{page_service} page missing session duration",
                    }
                )
            if not has_cta:
                findings.append(
                    {
                        "type": "missing_cta",
                        "severity": "high",
                        "message": f"{page_service} page missing clear call-to-action",
                    }
                )

    if "application/ld+json" in html or "schema.org" in html:
        positive.append("Structured data (JSON-LD/schema.org) detected")
    else:
        findings.append(
            {
                "type": "no_structured_data",
                "severity": "medium",
                "message": "No structured data found - AI/search engines may struggle to extract entities",
            }
        )

    if len(text) < 300:
        findings.append(
            {
                "type": "thin_content",
                "severity": "high",
                "message": f"Page content very thin ({len(text)} chars) - may not satisfy AI summaries",
            }
        )
    elif len(text) > 800:
        positive.append(f"Good content depth ({len(text)} chars)")

    return findings, positive


_GEO_FIXES = {
    "no_qa_blocks": "Add FAQ section with clear Q&A format",
    "missing_price": "Add pricing information with R amount",
    "missing_location": "Add Johannesburg/Randburg location prominently",
    "no_structured_data": "Add LocalBusiness schema markup",
    "unclear_offering": "State clearly what the service is in the first 100 chars",
    "missing_cta": 'Add "Book Now" or "Contact" button above the fold',
}


def run(*, brand: str | None = None) -> dict:
    """Audit site pages for SEO and GEO signals."""
    io = io_for_job(JOB_NAME, brand)
    site, site_err = _site_base(brand)
    if site_err:
        return {"ok": False, "error": site_err}
    seo_reports: list[dict[str, Any]] = []
    geo_reports: list[dict[str, Any]] = []
    all_seo_findings: list[dict[str, Any]] = []
    all_geo_findings: list[dict[str, Any]] = []
    all_positive: list[dict[str, str]] = []
    fetch_failures = 0
    network_errors: list[str] = []

    for page in PAGES:
        url = f"{site}{page['url_suffix']}"
        try:
            html = _fetch_page(url)
        except Exception as exc:  # noqa: BLE001 — network stubs may raise any type
            fetch_failures += 1
            network_errors.append(f"{page['name']}: {describe_exception(exc)}")
            seo_reports.append({"name": page["name"], "url": url, "status": "FETCH_FAILED", "findings": []})
            geo_reports.append({"name": page["name"], "status": "FETCH_FAILED", "findings": [], "positive": []})
            continue

        seo_findings = _audit_seo_page(html)
        geo_findings, geo_positive = _audit_geo_page(html, url)
        seo_reports.append({"name": page["name"], "url": url, "status": "OK", "findings": seo_findings})
        geo_reports.append(
            {"name": page["name"], "status": "OK", "findings": geo_findings, "positive": geo_positive}
        )
        all_seo_findings.extend({**f, "page": page["name"]} for f in seo_findings)
        all_geo_findings.extend({**f, "page": page["name"]} for f in geo_findings)
        all_positive.extend({"text": p, "page": page["name"]} for p in geo_positive)

    if fetch_failures == len(PAGES):
        return {"ok": False, "error": "site audit fetch failed: " + "; ".join(network_errors[:3])}

    high = [f for f in all_seo_findings if f["severity"] == "high"]
    medium = [f for f in all_seo_findings if f["severity"] == "medium"]
    low = [f for f in all_seo_findings if f["severity"] == "low"]
    recommendations = [
        {**f, "action": "FIX ASAP", "priority": 1} for f in high
    ] + [{**f, "action": "Fix this week", "priority": 2} for f in medium] + [
        {**f, "action": "Consider fixing", "priority": 3} for f in low
    ]

    seo_payload = {
        "updated": utc_now_iso(),
        "site": site,
        "total_findings": len(all_seo_findings),
        "high_severity": len(high),
        "medium_severity": len(medium),
        "low_severity": len(low),
        "recommendations": recommendations,
        "pages": seo_reports,
    }

    geo_high = [f for f in all_geo_findings if f["severity"] == "high"]
    geo_payload = {
        "updated": utc_now_iso(),
        "site": site,
        "geo_score": "GOOD" if all_positive and not geo_high else "NEEDS_WORK",
        "summary": {
            "clear_pages": len(
                [p for p in geo_reports if p.get("status") == "OK" and not any(f["severity"] == "high" for f in p.get("findings", []))]
            ),
            "needs_work": len(
                [p for p in geo_reports if any(f.get("severity") == "high" for f in p.get("findings", []))]
            ),
        },
        "high_priority": geo_high,
        "medium_priority": [f for f in all_geo_findings if f["severity"] == "medium"],
        "low_priority": [f for f in all_geo_findings if f["severity"] == "low"],
        "positive_signals": all_positive,
        "recommendations": [
            {
                "type": f["type"],
                "severity": f["severity"],
                "message": f["message"],
                "page": f.get("page"),
                "fix": _GEO_FIXES.get(f["type"], f"Review and improve {f['type']}"),
            }
            for f in all_geo_findings
        ],
    }

    io.write(SEO_OUTPUT, seo_payload)
    io.write(GEO_OUTPUT, geo_payload)
    return {"ok": True, "rows": len(all_seo_findings) + len(all_geo_findings)}
