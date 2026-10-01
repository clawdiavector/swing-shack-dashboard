"""
_lib/geo_audit.py — GEO audit helpers for swing-shack-dashboard Campaign OS.

Checks:
  - llms.txt present at domain root
  - FAQPage JSON-LD schema
  - Organization schema completeness
  - Blog post schema (Article/BlogPosting) on recent posts
  - Open Graph tags
  - Twitter Card tags

Module-level cache: data/cache/geo-audit-cache.json with 6h TTL.
"""
from __future__ import annotations
import base64
import datetime
import json
import os
import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional

BUNDLED_DATA_DIR = os.environ.get(
    "BUNDLED_DATA_DIR",
    str(Path(__file__).parent.parent / "data"),
)
DATA_DIR = os.environ.get("DATA_DIR", "/data/campaign-os")

_BRAND_DOMAINS = {
    "swing-shack": "https://swingshack.co.za",
    "stick":      "https://stickgolf.co.za",
    "bag-drop":   "https://swingshack.co.za",
}

# ── Cache helpers ────────────────────────────────────────────────────────────

def _cache_path() -> Path:
    p = Path(DATA_DIR) / "cache" / "geo-audit-cache.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_cache() -> Dict[str, Any]:
    try:
        return json.loads(_cache_path().read_text())
    except Exception:
        return {}


def _save_cache(cache: Dict[str, Any]) -> None:
    try:
        _cache_path().write_text(json.dumps(cache, ensure_ascii=False))
    except Exception:
        pass


def _cache_get(key: str, ttl_seconds: int = 6 * 3600) -> Optional[Any]:
    cache = _load_cache()
    entry = cache.get(key)
    if entry is None:
        return None
    ts = entry.get("_ts", 0)
    if (datetime.datetime.utcnow() - datetime.datetime.utcfromtimestamp(ts)).total_seconds() > ttl_seconds:
        return None
    return entry.get("value")


def _cache_set(key: str, value: Any) -> None:
    cache = _load_cache()
    cache[key] = {"value": value, "_ts": datetime.datetime.utcnow().timestamp()}
    _save_cache(cache)


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def _http_get(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 10) -> tuple[int, str]:
    h = dict(headers) if headers else {}
    h.setdefault("User-Agent", "CampaignOS-GEO-Audit/1.0")
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def _wp_request(brand: str, method: str, path: str,
                 payload: Optional[Dict] = None) -> Dict[str, Any]:
    """Make an authenticated WP REST request. Returns dict with ok/error fields."""
    from _lib.wp_publisher import _wp_auth_header, _http
    from _lib.publish_v1 import load_publishing_target

    target = load_publishing_target(brand)
    if not target:
        return {"ok": False, "code": "TARGET_NOT_FOUND", "error": f"no target for {brand}"}

    auth = _wp_auth_header(target)
    if not auth:
        return {"ok": False, "code": "CMS_AUTH_MISSING", "error": "missing WP creds env"}

    base = target.get("wp_api_base", "").rstrip("/")
    url = f"{base}{path}"
    hdrs = {
        "Authorization": auth,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "CampaignOS-GEO/1.0",
    }
    body = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    status, data = _http(method.upper(), url, headers=hdrs, body=body)
    if status == 0:
        return {"ok": False, "code": "WP_UNREACHABLE", "http": 0, "url": url,
                "note": "Could not connect to WP REST. Manual approval required."}
    try:
        parsed = json.loads(data)
    except Exception:
        parsed = {"raw": data[:500]}
    return {"ok": status in (200, 201), "http": status, "url": url,
            "data": parsed, "raw": data[:500]}


# ── HTML parsing helpers ──────────────────────────────────────────────────────

def _extract_jsonld(html: str) -> List[Dict]:
    """Return all JSON-LD blocks found in HTML."""
    blocks = []
    pattern = re.compile(
        r'<script[^>]*\stype=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )
    for m in pattern.finditer(html):
        raw = m.group(1)
        if isinstance(raw, str):
            try:
                blocks.append(json.loads(raw))
            except Exception:
                pass
    # Also handle multiline scripts with newlines
    pattern2 = re.compile(r'type=["\']application/ld\+json["\'][^>]*>\s*(.*?)\s*</script>', re.DOTALL | re.IGNORECASE)
    for m in pattern2.finditer(html):
        raw = m.group(1)
        if isinstance(raw, str):
            try:
                blocks.append(json.loads(raw))
            except Exception:
                pass
    return blocks


def _flatten_jsonld(blocks: List[Any]) -> List[Dict]:
    """Flatten @graph arrays into individual items."""
    items = []
    for block in blocks:
        if isinstance(block, dict):
            if "@graph" in block:
                items.extend(block["@graph"])
            else:
                items.append(block)
        elif isinstance(block, list):
            items.extend(_flatten_jsonld(block))
    return items


def _find_schema(blocks: List[Dict], type_name: str) -> Optional[Dict]:
    for block in blocks:
        t = block.get("@type", "")
        if isinstance(t, list):
            if type_name in t:
                return block
        elif t == type_name:
            return block
    return None


# ── Individual checks ────────────────────────────────────────────────────────

def check_llms_txt(brand: str) -> Dict[str, Any]:
    """Check if /llms.txt exists at the brand domain."""
    cache_key = f"llms_txt:{brand}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    url = f"{_BRAND_DOMAINS.get(brand, '').rstrip('/')}/llms.txt"
    status, text = _http_get(url)
    # V1.1 calibration (2026-10-01): llms.txt is EXPERIMENTAL, not a proven
    # AI citation signal. Some crawlers read it, most LLMs do not cite content
    # surfaced only via llms.txt. We track it as an OPTIONAL signal with no
    # severity weight in the GEO score.
    result = {
        "check": "llms_txt",
        "signal_type": "EXPERIMENTAL",
        "status": "OK" if status == 200 else "MISSING",
        "severity": "low",
        "message": (
            "llms.txt found (experimental — adoption is fragmented; not a "
            "proven AI citation signal yet)"
            if status == 200
            else "llms.txt not found (optional experimental asset; most LLMs "
                 "still do not index it; not weighted in GEO score)"
        ),
        "fix_suggestion": None,
    }
    if status != 200:
        result["fix_suggestion"] = _build_llms_txt_suggestion(brand)
    _cache_set(cache_key, result)
    return result


# ── Robots.txt review (V1.1) ────────────────────────────────────────────────────
# Per operator direction: do NOT label robots.txt as a high-severity GEO
# blocker just because it lacks a generic User-agent: * group. Most crawlers
# default to allow when no rule matches. Only REVIEW_RECOMMENDED when an
# actual crawler block is proved or when a Sitemap: directive is missing.

def _build_robots_review(brand: str) -> Dict[str, Any]:
    """Fetch /robots.txt, classify current state, surface proposed state with
    per-line effect. Never returns high severity unless a real block exists."""
    domain = _BRAND_DOMAINS.get(brand, "")
    if not domain:
        return {
            "check": "robots_review",
            "signal_type": "TECHNICAL_SEO",
            "status": "UNKNOWN",
            "severity": "low",
            "excluded_from_score": True,
            "message": "No domain configured for brand",
            "fix_suggestion": None,
        }
    url = f"{domain.rstrip('/')}/robots.txt"
    status, text = _http_get(url)

    if status != 200:
        # No robots.txt at all — that is a low-severity REVIEW_RECOMMENDED,
        # not high. Crawlers default to allow-everything.
        return {
            "check": "robots_review",
            "signal_type": "TECHNICAL_SEO",
            "status": "MISSING",
            "severity": "low",
            "message": f"No robots.txt at {url} (default: all crawlers allowed; recommended to publish one with sitemap pointer)",
            "fix_suggestion": _build_robots_proposed_text(brand),
        }

    has_sitemap = bool(re.search(r"^\s*Sitemap\s*:", text, re.IGNORECASE | re.MULTILINE))
    has_explicit_allow = "Allow:" in text or "Disallow: /" in text
    has_meta_only = "meta-externalagent" in text and len(text.splitlines()) <= 3

    if has_meta_only:
        # Operator's exact case: swingshack has only meta-externalagent entry.
        # Not a crawl block. Sitemap pointer is the real gap.
        return {
            "check": "robots_review",
            "signal_type": "TECHNICAL_SEO",
            "status": "REVIEW_RECOMMENDED",
            "severity": "low",
            "message": (
                "Current robots.txt only configures meta-externalagent — no actual "
                "crawler block. Real gap: missing Sitemap: directive. See proposed "
                "text for the fix."
            ),
            "fix_suggestion": _build_robots_proposed_text(brand, current_text=text),
            "current_robots": text,
        }

    if has_sitemap and has_explicit_allow:
        return {
            "check": "robots_review",
            "signal_type": "TECHNICAL_SEO",
            "status": "OK",
            "severity": "low",
            "message": "robots.txt looks configured (sitemap + allow rules present)",
            "fix_suggestion": None,
            "current_robots": text,
        }

    return {
        "check": "robots_review",
        "signal_type": "TECHNICAL_SEO",
        "status": "REVIEW_RECOMMENDED",
        "severity": "low",
        "message": (
            f"robots.txt present but missing {'Sitemap: directive' if not has_sitemap else 'explicit Allow/Disallow rules'}. Not a crawl block; recommendation only."
        ),
        "fix_suggestion": _build_robots_proposed_text(brand, current_text=text),
        "current_robots": text,
    }


def _build_robots_proposed_text(brand: str, current_text: str = "") -> str:
    """Build a proposed robots.txt with sitemap pointer + clear allow rules.
    Includes current vs proposed vs per-line effect so operator can audit
    before any live write."""
    domain = _BRAND_DOMAINS.get(brand, "")
    if brand == "swing-shack":
        site_label = "Swing Shack — Johannesburg indoor golf + TrackMan + coaching"
        sitemap_xml = "sitemap_index.xml"
    else:
        site_label = "Stick Golf — Paarl / Cape Winelands golf coaching + TrackMan"
        sitemap_xml = "sitemap_index.xml"
    return (
        f"# CURRENT — held for review. NOT pushed to live WP.\n"
        f"# {current_text.strip() or '(no robots.txt currently)'}\n\n"
        f"# PROPOSED — Operator-approved candidate. Diff with current above.\n\n"
        f"# {site_label}\n\n"
        f"User-agent: *\n"
        f"Allow: /\n"
        f"Disallow: /cart/\n"
        f"Disallow: /checkout/\n"
        f"Disallow: /my-account/\n"
        f"Disallow: /*?s=\n"
        f"Disallow: /*?add-to-cart=\n\n"
        f"# Meta's scraper (Instagram link previews, etc.)\n"
        f"User-agent: meta-externalagent\n"
        f"Allow: /\n\n"
        f"Sitemap: {domain.rstrip('/')}/{sitemap_xml}\n"
        f"Sitemap: {domain.rstrip('/')}/news-sitemap.xml\n\n"
        f"# Per-line effect:\n"
        f"#   User-agent: *          — applies to all crawlers that do not match a more specific group below\n"
        f"#   Allow: /                — explicitly allow crawling of the whole site\n"
        f"#   Disallow: /cart/        — block checkout-thrash pages\n"
        f"#   Disallow: /*?s=         — block WordPress internal search result pages\n"
        f"#   Disallow: /*?add-to-cart= — block product add-to-cart queries\n"
        f"#   meta-externalagent      — keep explicit allowance for Instagram link previews\n"
        f"#   Sitemap: ...            — points crawlers at the Yoast-generated sitemap (currently MISSING)\n"
    )


def _build_llms_txt_suggestion(brand: str) -> str:
    domain = _BRAND_DOMAINS.get(brand, "")
    if brand == "swing-shack":
        lines = [
            "# https://swingshack.co.za — llms.txt",
            "# Generated by Campaign OS GEO module",
            f"Source: {domain}",
            "",
            "## Pages",
            f"{domain}/",
            f"{domain}/indoor-golf",
            f"{domain}/coaching",
            f"{domain}/club-fitting",
            f"{domain}/trackman",
            f"{domain}/blog",
            "",
            "## Capabilities",
            "Swing Shack is South Africa's premier indoor golf venue in Johannesburg.",
            "Services: TrackMan fitting, golf coaching, club fitting, swing analysis.",
            "Uses TrackMan launch monitors for precise club and ball data.",
            "",
            "## Brand voice",
            "Expert, approachable, SA-grounded — never 'lessons', always 'coaching'.",
            "",
            f"Contact: {domain}/contact",
            f"Sitemap: {domain}/sitemap.xml",
        ]
    else:
        lines = [
            f"# https://stickgolf.co.za — llms.txt",
            "# Generated by Campaign OS GEO module",
            f"Source: {domain}",
            "",
            "## Pages",
            f"{domain}/",
            f"{domain}/coaching",
            f"{domain}/trackman",
            f"{domain}/vice-golf",
            f"{domain}/blog",
            "",
            "## Capabilities",
            "Stick Golf offers premium golf coaching and TrackMan fitting in Paarl, Cape Winelands.",
            "Specialises in Vice Golf South Africa, custom club fitting, and swing coaching.",
            "",
            "## Brand voice",
            "Expert, refined, Cape Winelands — never 'lessons', always 'coaching'.",
            "",
            f"Contact: {domain}/contact",
            f"Sitemap: {domain}/sitemap.xml",
        ]
    return "\n".join(lines)


def check_faqpage(brand: str, html: str) -> Dict[str, Any]:
    """Check if FAQPage JSON-LD is present."""
    cache_key = f"faqpage:{brand}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    blocks = _extract_jsonld(html)
    items = _flatten_jsonld(blocks)
    faq = _find_schema(items, "FAQPage")
    # V1.1 calibration: FAQPage is TECHNICAL_SEO/structured_data. Only
    # relevant when genuine FAQ content exists on the page. Adding FAQPage
    # schema to a page that has no FAQ content will not improve AI citation
    # and may reduce trust signals. We mark CONTEXTUAL and keep severity low.
    faq_present_in_html = bool(re.search(r"\bFAQ\b|<h[1-6][^>]*>[^<]*\?[^<]*</h[1-6]>|frequently asked|questions and answers", html, re.IGNORECASE))
    result = {
        "check": "faqpage_schema",
        "signal_type": "TECHNICAL_SEO",
        "status": "OK" if faq else "MISSING",
        "severity": "low",
        "message": (
            "FAQPage schema found"
            if faq
            else (
                "FAQPage JSON-LD missing but FAQ content detected on page — adding schema may help"
                if faq_present_in_html
                else "FAQPage JSON-LD missing and no FAQ content detected — adding schema now would not improve AI citation"
            )
        ),
        "fix_suggestion": None,
    }
    if not faq and faq_present_in_html:
        result["fix_suggestion"] = _build_faqpage_suggestion(brand)
    # If no FAQ content exists, we deliberately do NOT suggest adding the
    # schema — that would be the wrong recommendation.
    _cache_set(cache_key, result)
    return result


def _build_faqpage_suggestion(brand: str) -> str:
    if brand == "swing-shack":
        faqs = [
            {"question": "What indoor golf facilities do you have in Johannesburg?",
             "answer": "Swing Shack has two TrackMan simulators, a putting green, and a short-game area. Book online or call us."},
            {"question": "Do you offer TrackMan fitting in Johannesburg?",
             "answer": "Yes — our TrackMan fitting sessions use radar and camera to match clubs to your swing. Book via our website."},
            {"question": "What's included in golf coaching at Swing Shack?",
             "answer": "Coaching is available in 30, 45, or 60-minute sessions. All levels welcome. TrackMan data included in every session."},
            {"question": "Can beginners access coaching?",
             "answer": "Absolutely. Our coaches work with complete beginners through to low-handicap players. Book a discovery session to get started."},
        ]
    else:
        faqs = [
            {"question": "Do you offer golf coaching in Paarl?",
             "answer": "Yes — Stick Golf provides expert coaching in Paarl, Cape Winelands. All levels welcome. Book online."},
            {"question": "Do you sell Vice Golf in South Africa?",
             "answer": "Yes — Stick Golf is an authorised Vice Golf South Africa retailer. Custom fitting available."},
            {"question": "What is TrackMan fitting?",
             "answer": "TrackMan fitting uses dual radar + camera to measure every aspect of your ball and club data, helping you find the right clubs."},
            {"question": "Can beginners get coaching at Stick Golf?",
             "answer": "Yes — coaching starts from your very first session. Our coaches help beginners build fundamentals and confidence on the course."},
        ]
    faq_json = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f["question"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": f["answer"],
                },
            }
            for f in faqs
        ],
    }
    return json.dumps(faq_json, indent=2, ensure_ascii=False)


def check_organization_schema(brand: str, html: str) -> Dict[str, Any]:
    """Check Organization schema completeness."""
    cache_key = f"org_schema:{brand}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    blocks = _extract_jsonld(html)
    items = _flatten_jsonld(blocks)
    org = _find_schema(items, "Organization")
    # V1.1 calibration: Organization schema is ENTITY_DISCOVERY. LLMs use it
    # to identify the entity behind a domain. Incomplete Organization schema
    # is a real medium-priority gap (entity identification under-specifies the
    # brand), but it is a SITE READINESS signal, not a citation-rate signal.
    result = {
        "check": "organization_schema",
        "signal_type": "ENTITY_DISCOVERY",
        "status": "OK",
        "severity": "medium",
        "message": "Organization schema found (entity discovery — helps LLMs identify the brand behind the domain)",
        "fix_suggestion": None,
    }
    if not org:
        result = {
            "check": "organization_schema",
            "signal_type": "ENTITY_DISCOVERY",
            "status": "MISSING",
            "severity": "medium",
            "message": "No Organization JSON-LD found (entity discovery gap — LLMs cannot confidently identify the brand)",
            "fix_suggestion": _build_org_schema_suggestion(brand),
        }
    else:
        # Check completeness
        required = ["name", "url", "logo", "sameAs", "contactPoint", "address"]
        missing = [f for f in required if not org.get(f)]
        if missing:
            result["status"] = "PARTIAL"
            result["message"] = f"Organization schema incomplete — missing: {', '.join(missing)}"
            result["fix_suggestion"] = _build_org_schema_suggestion(brand)
    _cache_set(cache_key, result)
    return result


def _build_org_schema_suggestion(brand: str) -> str:
    if brand == "swing-shack":
        org = {
            "@context": "https://schema.org",
            "@type": "SportsActivityLocation",
            "name": "Swing Shack",
            "url": "https://swingshack.co.za",
            "logo": "https://swingshack.co.za/wp-content/uploads/swing-shack-logo.png",
            "description": "South Africa's premier indoor golf venue in Johannesburg, with TrackMan fitting, golf coaching, and club fitting.",
            "address": {
                "@type": "PostalAddress",
                "streetAddress": "2nd Floor, Melrose Arch",
                "addressLocality": "Johannesburg",
                "addressRegion": "Gauteng",
                "postalCode": "2076",
                "addressCountry": "ZA",
            },
            "telephone": "+27-11-XXX-XXXX",
            "email": "info@swingshack.co.za",
            "sameAs": [
                "https://www.instagram.com/swingshack",
                "https://www.facebook.com/swingshack",
            ],
            "geo": {
                "@type": "GeoCoordinates",
                "latitude": -26.1367,
                "longitude": 28.0571,
            },
        }
    else:
        org = {
            "@context": "https://schema.org",
            "@type": "SportsActivityLocation",
            "name": "Stick Golf",
            "url": "https://stickgolf.co.za",
            "logo": "https://stickgolf.co.za/wp-content/uploads/stick-golf-logo.png",
            "description": "Premium golf coaching and TrackMan fitting in Paarl, Cape Winelands, South Africa.",
            "address": {
                "@type": "PostalAddress",
                "streetAddress": "Main Road",
                "addressLocality": "Paarl",
                "addressRegion": "Western Cape",
                "postalCode": "7646",
                "addressCountry": "ZA",
            },
            "telephone": "+27-21-XXX-XXXX",
            "email": "info@stickgolf.co.za",
            "sameAs": [
                "https://www.instagram.com/stickgolf",
                "https://www.facebook.com/stickgolf",
            ],
        }
    return json.dumps(org, indent=2, ensure_ascii=False)


def check_open_graph(html: str) -> Dict[str, Any]:
    """Check Open Graph meta tags."""
    cache_key = "og_tags:" + str(hash(html[:500]))
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    required = ["og:title", "og:description", "og:image", "og:type"]
    missing = []
    for tag in required:
        pattern = re.compile(
            rf'<meta[^>]+property=["\']' + re.escape(tag) + r'["\'][^>]*/?>',
            re.IGNORECASE,
        )
        if not pattern.search(html):
            # Try alternate: content= first
            pattern2 = re.compile(
                rf'<meta[^>]+content=["\'][^"\']*["\'][^>]+property=["\']' + re.escape(tag) + r'["\']',
                re.IGNORECASE,
            )
            if not pattern2.search(html):
                missing.append(tag)

    result = {
        "check": "og_tags",
        "signal_type": "SOCIAL_METADATA",
        "status": "OK" if not missing else ("PARTIAL" if len(missing) < len(required) else "MISSING"),
        "severity": "low",
        "message": (
            "Open Graph complete (social metadata only — not a direct AI citation signal)"
            if not missing
            else f"Open Graph incomplete — missing: {', '.join(missing)} (social metadata only; some AI crawlers read og:image, most do not weight it for citation)"
        ),
        "fix_suggestion": None,
    }
    if missing:
        og_type_val = "article" if "og:type=article" in [f"og:{m}" for m in missing] else None
        lines = [
            '<meta property="og:title" content="Your Page Title | Brand Name" />',
            '<meta property="og:description" content="Your page description (150-200 chars)." />',
            '<meta property="og:image" content="https://example.com/image.jpg" />',
            '<meta property="og:type" content="article" />',
            '<meta property="og:url" content="https://example.com/page-url" />',
            '<meta property="og:site_name" content="Brand Name" />',
        ]
        result["fix_suggestion"] = "\n".join(lines)
    _cache_set(cache_key, result)
    return result


def check_twitter_cards(html: str) -> Dict[str, Any]:
    """Check Twitter Card meta tags."""
    cache_key = "twitter_cards:" + str(hash(html[:500]))
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    required = ["twitter:card", "twitter:title", "twitter:description", "twitter:image"]
    missing = []
    for tag in required:
        pattern = re.compile(
            rf'<meta[^>]+name=["\']' + re.escape(tag) + r'["\'][^>]*/?>',
            re.IGNORECASE,
        )
        if not pattern.search(html):
            pattern2 = re.compile(
                rf'<meta[^>]+content=["\'][^"\']*["\'][^>]+name=["\']' + re.escape(tag) + r'["\']',
                re.IGNORECASE,
            )
            if not pattern2.search(html):
                missing.append(tag)

    result = {
        "check": "twitter_card",
        "signal_type": "SOCIAL_METADATA",
        "status": "OK" if not missing else ("PARTIAL" if len(missing) < len(required) else "MISSING"),
        "severity": "low",
        "message": (
            "Twitter Cards complete (social metadata only — minimal AI citation influence)"
            if not missing
            else f"Twitter Cards incomplete — missing: {', '.join(missing)} (social metadata only; minimal AI citation influence)"
        ),
        "fix_suggestion": None,
    }
    if missing:
        result["fix_suggestion"] = "\n".join([
            '<meta name="twitter:card" content="summary_large_image" />',
            '<meta name="twitter:title" content="Your Page Title" />',
            '<meta name="twitter:description" content="Your page description." />',
            '<meta name="twitter:image" content="https://example.com/image.jpg" />',
        ])
    _cache_set(cache_key, result)
    return result


def check_blog_schema(posts: List[Dict], homepage_html: str = "") -> Dict[str, Any]:
    """Check Article/BlogPosting schema on recent WP posts."""
    cache_key = "blog_schema:" + str(sorted(p.get("id", 0) for p in posts[:3]))
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    result = {
        "check": "blog_post_schema",
        "signal_type": "TECHNICAL_SEO",
        "status": "OK",
        "severity": "low",
        "message": "Blog post schema found on recent posts",
        "fix_suggestion": None,
    }
    if not posts:
        # V1.1 calibration: if we cannot reach the WP posts feed, we mark
        # this check UNKNOWN and EXCLUDE it from the GEO score. We do NOT
        # fabricate a severity. Operator must investigate WP connectivity
        # before this finding earns any weight.
        result = {
            "check": "blog_post_schema",
            "signal_type": "TECHNICAL_SEO",
            "status": "UNKNOWN",
            "severity": "low",
            "excluded_from_score": True,
            "message": "No WP posts found — check could not run. EXCLUDED FROM GEO SCORE until WP feed is reachable.",
            "fix_suggestion": None,
        }
        _cache_set(cache_key, result)
        return result

    posts_with_schema = 0
    for post in posts[:3]:
        url = post.get("link", "")
        if not url:
            continue
        _, html = _http_get(url)
        if not html:
            continue
        blocks = _extract_jsonld(html)
        items = _flatten_jsonld(blocks)
        if _find_schema(items, "Article") or _find_schema(items, "BlogPosting"):
            posts_with_schema += 1

    if posts_with_schema == 0:
        result = {
            "check": "blog_post_schema",
            "signal_type": "TECHNICAL_SEO",
            "status": "MISSING",
            "severity": "low",
            "message": "No Article/BlogPosting JSON-LD found on recent posts (may help article extraction in AI crawlers, not proven)",
            "fix_suggestion": _build_blog_schema_suggestion(posts[0] if posts else {}),
        }
    elif posts_with_schema < 3:
        result["status"] = "PARTIAL"
        result["severity"] = "low"
        result["signal_type"] = "TECHNICAL_SEO"
        result["message"] = f"Only {posts_with_schema}/3 recent posts have Article schema"

    _cache_set(cache_key, result)
    return result


def _build_og_suggestion(domain: str, brand: str) -> str:
    if brand == "swing-shack":
        site_name = "Swing Shack"
        desc = "South Africa's premier indoor golf venue in Johannesburg."
    else:
        site_name = "Stick Golf"
        desc = "Premium golf coaching and TrackMan fitting in Paarl, Cape Winelands."
    return "\n".join([
        f'<meta property="og:title" content="{site_name} — Your Page" />',
        f'<meta property="og:description" content="{desc}" />',
        '<meta property="og:image" content="https://example.com/og-image.jpg" />',
        '<meta property="og:type" content="article" />',
        f'<meta property="og:url" content="{domain}/your-page-slug/" />',
        f'<meta property="og:site_name" content="{site_name}" />',
    ])


def _build_twitter_suggestion(domain: str, brand: str) -> str:
    if brand == "swing-shack":
        site_name = "Swing Shack"
    else:
        site_name = "Stick Golf"
    return "\n".join([
        '<meta name="twitter:card" content="summary_large_image" />',
        '<meta name="twitter:title" content="Your Page Title" />',
        '<meta name="twitter:description" content="Page description." />',
        '<meta name="twitter:image" content="https://example.com/twitter-image.jpg" />',
        f'<meta name="twitter:site" content="@{site_name.replace(" ", "")}" />',
    ])


def _build_blog_schema_suggestion(post: Dict) -> str:
    title = post.get("title", {}).get("rendered", "Your Post Title")
    link = post.get("link", "https://example.com/post")
    slug = post.get("slug", "post-slug")
    date = post.get("date", datetime.datetime.utcnow().isoformat() + "Z")
    schema = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "url": link,
        "datePublished": date,
        "author": {
            "@type": "Person",
            "name": "Swing Shack Coach",
        },
        "publisher": {
            "@type": "Organization",
            "name": "Swing Shack",
            "logo": {
                "@type": "ImageObject",
                "url": "https://swingshack.co.za/wp-content/uploads/logo.png",
            },
        },
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": link,
        },
    }
    return json.dumps(schema, indent=2, ensure_ascii=False)


# ── Full audit runner ────────────────────────────────────────────────────────

def run_geo_audit(brand: str, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Run all GEO checks for a brand. Returns a list of check results + metadata.
    Uses cached values (6h TTL) unless force_refresh=True.
    """
    if brand not in _BRAND_DOMAINS:
        return {"ok": False, "error": f"unknown brand: {brand}"}

    if not force_refresh:
        # Check if we have a full audit cached
        cache_key = f"full_audit:{brand}"
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    domain = _BRAND_DOMAINS[brand]

    # Fetch homepage
    _, homepage_html = _http_get(domain)

    # Fetch recent WP posts
    posts = []
    wp_resp = _wp_request(brand, "GET", "/posts?per_page=3&status=publish")
    if wp_resp.get("ok") and isinstance(wp_resp.get("data"), list):
        posts = wp_resp["data"]

    checks = []

    # llms.txt — EXPERIMENTAL
    checks.append(check_llms_txt(brand))

    # FAQPage — TECHNICAL_SEO (only relevant when FAQ content exists)
    if homepage_html:
        checks.append(check_faqpage(brand, homepage_html))
    else:
        checks.append({
            "check": "faqpage_schema",
            "signal_type": "TECHNICAL_SEO",
            "status": "UNKNOWN",
            "severity": "low",
            "excluded_from_score": True,
            "message": "Could not fetch homepage HTML — check excluded from GEO score until reachable",
            "fix_suggestion": None,
        })

    # Organization schema — ENTITY_DISCOVERY
    if homepage_html:
        checks.append(check_organization_schema(brand, homepage_html))
    else:
        checks.append({
            "check": "organization_schema",
            "signal_type": "ENTITY_DISCOVERY",
            "status": "UNKNOWN",
            "severity": "low",
            "excluded_from_score": True,
            "message": "Could not fetch homepage HTML — check excluded from GEO score until reachable",
            "fix_suggestion": None,
        })

    # Blog post schema — TECHNICAL_SEO
    checks.append(check_blog_schema(posts, homepage_html))

    # OG tags — SOCIAL_METADATA
    if homepage_html:
        checks.append(check_open_graph(homepage_html))
    else:
        checks.append({
            "check": "og_tags",
            "signal_type": "SOCIAL_METADATA",
            "status": "UNKNOWN",
            "severity": "low",
            "excluded_from_score": True,
            "message": "Could not fetch homepage HTML — check excluded from GEO score until reachable",
            "fix_suggestion": None,
        })

    # Twitter cards — SOCIAL_METADATA
    if homepage_html:
        checks.append(check_twitter_cards(homepage_html))
    else:
        checks.append({
            "check": "twitter_card",
            "signal_type": "SOCIAL_METADATA",
            "status": "UNKNOWN",
            "severity": "low",
            "excluded_from_score": True,
            "message": "Could not fetch homepage HTML — check excluded from GEO score until reachable",
            "fix_suggestion": None,
        })

    # Robots.txt — TECHNICAL_SEO. V1.1 calibration: only REVIEW_RECOMMENDED
    # when an actual crawler block is proven. Default low. Show current
    # state, proposed state, and per-line effect so operator can decide.
    robots_review = _build_robots_review(brand)
    checks.append(robots_review)

    # Merge with existing SEO audit findings for this brand
    seo_findings = []
    try:
        seo_file = Path(BUNDLED_DATA_DIR) / "seo-audit.json"
        if seo_file.exists():
            seo_data = json.loads(seo_file.read_text())
            # Find this brand's pages
            for page in seo_data.get("pages", []):
                if page.get("brand", "").lower().replace(" ", "-") == brand.replace("swing-shack", "swing-shack"):
                    for finding in page.get("findings", []):
                        finding_type = finding.get("type", "")
                        # Map SEO findings to GEO checks where applicable.
                        # V1.1 calibration: missing_h1 + missing_meta_description
                        # are TECHNICAL_SEO, low severity. missing_faq stays
                        # TECHNICAL_SEO but only meaningful when FAQ content
                        # actually exists on the page.
                        if finding_type in ("missing_h1", "missing_meta_description", "missing_faq"):
                            geo_finding = {
                                "check": finding_type,
                                "signal_type": "TECHNICAL_SEO",
                                "status": "MISSING",
                                "severity": "low",
                                "message": f"[SEO audit] {finding.get('message', '')} — why this may help: clearer on-page structure for AI crawlers; not proven to lift citation rate.",
                                "fix_suggestion": None,
                            }
                            if finding_type == "missing_h1":
                                geo_finding["fix_suggestion"] = (
                                    f"Add an <h1> tag to {page.get('name', 'this page')}. "
                                    "In WP: edit the page and ensure the main heading is an <h1>, not <h2> or bold text. "
                                    f"Yoast SEO will pick it up automatically."
                                )
                            elif finding_type == "missing_meta_description":
                                geo_finding["fix_suggestion"] = (
                                    f"Add a meta description to {page.get('name', 'this page')} via Yoast SEO "
                                    "snippet editor in the WP page editor. "
                                    "Keep it 120–160 characters and include a call to action."
                                )
                            elif finding_type == "missing_faq":
                                geo_finding["fix_suggestion"] = _build_faqpage_suggestion(brand)
                            seo_findings.append(geo_finding)
    except Exception:
        pass

    result = {
        "ok": True,
        "brand": brand,
        "domain": domain,
        "fetched_at": datetime.datetime.utcnow().isoformat() + "Z",
        "checks": checks,
        "seo_findings": seo_findings,
        "wp_posts_checked": len(posts),
        "wp_reachable": wp_resp.get("ok", False),
    }

    _cache_set(f"full_audit:{brand}", result)
    return result
