"""Automatic meta-description publishing for the SEO fix queue, with undo.

Policy (approved by Christelle 2026-10-19, wiki decisions/seo-geo-automation-tiers):
only meta descriptions on non-homepage pages may be published without asking,
and every change has a one-click undo. Everything else stays in the queue.

Safety rules, all enforced here:
  - Off unless SEO_AUTOPUBLISH is "dry-run" or "on". Anything else is off.
  - Swing Shack only (seo_fix_queue.QUEUE_BRANDS).
  - Only fills an EMPTY description. A description a person wrote is never touched.
  - Text is the page's own words: whole sentences, 120-160 characters, nothing
    with prices, percentages, superlatives, other brands' names or contact
    details. No model writes it, so nothing is invented.
  - Every write is read back. A change that did not stick is reported, and a
    page left with a value we did not intend is put back.
  - Undo restores the previous value and refuses if the description has been
    edited by someone since.
  - At most MAX_PER_RUN changes per run. The homepage is never included.

wp is any callable wp(method, path, payload=None) -> {"ok", "http", "data"};
default_wp() builds one on the same authenticated helper the GEO audit uses.
"""
from __future__ import annotations

import hashlib
import html as _html
import os
import re
from typing import Any, Callable

from . import seo_fix_queue

MODE_OFF, MODE_DRY, MODE_ON = "off", "dry-run", "on"
ENV_MODE = "SEO_AUTOPUBLISH"

META_KEY = "_yoast_wpseo_metadesc"
TITLE_KEY = "_yoast_wpseo_title"

# Yoast fields a change can touch: WordPress meta key, and how long Google lets it be.
FIELDS_META = {
    "meta_description": {"key": META_KEY, "label": "Search description", "min": 120, "max": 160},
    "title": {"key": TITLE_KEY, "label": "Page title", "min": 30, "max": 60},
}
DESC_MIN, DESC_MAX = 120, 160
MAX_PER_RUN = 3
MAX_LOG = 500
LOG_FILE = "seo-publish-log.json"

# Audit page name -> WordPress slug. The homepage is deliberately absent.
PAGE_SLUGS = {"Membership": "membership", "Coaching": "coaching", "Club Fitting": "club-fitting"}
PAGE_SLUGS_BY_BRAND = {
    "swing-shack": PAGE_SLUGS,
    "stick": {"Club Fitting": "club-fitting-at-stick", "Coaching": "coaching-at-stick"},
}


def page_slugs(brand: str | None) -> dict[str, str]:
    """Audit page name -> WordPress slug for one brand's site (homepage excluded)."""
    return PAGE_SLUGS_BY_BRAND.get(brand or "swing-shack", {})

WpClient = Callable[..., dict]


def mode() -> str:
    v = (os.environ.get(ENV_MODE) or "").strip().lower()
    return v if v in (MODE_DRY, MODE_ON) else MODE_OFF


# ── Text: build a description from the page's own words ─────────────────────

_NOISE = re.compile(r"<(style|script|noscript|svg)\b.*?</\1\s*>", re.I | re.S)
_BLOCK_END = re.compile(r"</(p|h[1-6]|li|div|section|tr|td|blockquote)\s*>|<br\s*/?>", re.I)
_TAG = re.compile(r"<[^>]+>")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")

# Claims and details that can go stale or that nobody has signed off.
_REJECT = re.compile(
    r"(\bR\s?\d)|%|\bfree\b|\bguarantee|\bbest\b|\bcheapest\b|\b(no\.?|number)\s?1\b|#1|"
    r"\b(stick|bag\s?drop)\b|https?:|www\.|@|\d{3}[\s-]?\d{3}|�",
    re.I,
)
# Same rules for Stick's text, where the other companies are Swing Shack and Bag Drop.
_REJECT_STICK = re.compile(
    _REJECT.pattern.replace(r"\b(stick|bag\s?drop)\b", r"\b(swing\s?shack|bag\s?drop)\b"), re.I
)


def _reject_for(brand: str | None) -> "re.Pattern[str]":
    return _REJECT_STICK if brand == "stick" else _REJECT


def _blocks(raw_html: str) -> list[str]:
    cleaned = _NOISE.sub(" ", raw_html or "")
    parts = _BLOCK_END.split(cleaned)
    out = []
    for part in parts:
        if not part:
            continue
        text = _html.unescape(_TAG.sub(" ", part))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            out.append(text)
    return out


def candidates(raw_html: str, brand: str = "swing-shack") -> list[str]:
    """Every safe 120-160 character description the page's own whole sentences
    can make, one per starting sentence, best-first (page order)."""
    sentences: list[str] = []
    for block in _blocks(raw_html):
        if len(block.split()) < 8:  # headings, buttons, labels
            continue
        sentences.extend(s.strip() for s in _SENTENCE.split(block) if s.strip())
    out: list[str] = []
    for start in range(len(sentences)):
        text = ""
        for sentence in sentences[start:]:
            text = f"{text} {sentence}".strip()
            if len(text) > DESC_MAX:
                break
            if len(text) >= DESC_MIN:
                if not _reject_for(brand).search(text) and text[-1] in ".!?" and text not in out:
                    out.append(text)
                break
    return out


def propose(raw_html: str, prefer: tuple[str, ...] = (), avoid: str = "", brand: str = "swing-shack") -> str | None:
    """A 120-160 character description built from whole sentences of the page's
    own paragraphs, or None when no safe candidate exists. When `prefer` is
    given (brand and page names), the first safe candidate that mentions one of
    those terms wins; otherwise the first safe candidate does. `avoid` is the
    text already on the page, never proposed again."""
    terms = [t.lower() for t in prefer if t]
    options = [c for c in candidates(raw_html, brand) if c != (avoid or "").strip()]
    if not options:
        return None
    for text in options:
        if any(t in text.lower() for t in terms):
            return text
    return options[0]


# ── WordPress ───────────────────────────────────────────────────────────────

_FIELDS = "id,slug,status,link,content,meta,yoast_head_json"


def default_wp(brand: str) -> WpClient:
    from . import geo_audit

    def wp(method: str, path: str, payload: dict | None = None) -> dict:
        return geo_audit._wp_request(brand, method, path, payload)

    return wp


def current_value(page: dict, field: str = "meta_description") -> str:
    """What WordPress/Yoast reports for a field. For a title with no custom value
    Yoast reports the title it builds from its template, which is what Google sees."""
    if field == "meta_description":
        return current_description(page)
    meta = page.get("meta") or {}
    key = FIELDS_META[field]["key"]
    from_meta = meta.get(key) if isinstance(meta, dict) else None
    from_head = (page.get("yoast_head_json") or {}).get("title")
    return str(from_meta or from_head or "").strip()


def current_description(page: dict) -> str:
    """The description WordPress/Yoast reports for a page. Either signal counts."""
    meta = page.get("meta") or {}
    from_meta = meta.get(META_KEY) if isinstance(meta, dict) else None
    from_head = (page.get("yoast_head_json") or {}).get("description")
    return str(from_meta or from_head or "").strip()


def page_field_writable(wp: WpClient, field: str = "meta_description") -> bool | None:
    """Does WordPress let the REST API save this Yoast field on pages?

    Yoast registers its fields as REST-writable for posts only. On pages a write is
    accepted and silently dropped (found live 2026-10-23). True or False from
    WordPress's own schema; None when it cannot be told, in which case callers go
    ahead and rely on the read-back after writing.
    """
    key = FIELDS_META[field]["key"]
    try:
        r = wp("OPTIONS", "/pages")
        props = (((r.get("data") or {}).get("schema") or {}).get("properties") or {}).get("meta", {}).get("properties")
        if not isinstance(props, dict) or not props:
            return None
        return key in props
    except Exception:  # noqa: BLE001
        return None


PAGE_UNWRITABLE_WHY = (
    "WordPress does not let Campaign OS save Yoast fields on pages yet. "
    "A small WordPress snippet makes the field writable; until then paste the text into Yoast by hand."
)


def fetch_page(wp: WpClient, slug: str) -> dict | None:
    r = wp("GET", f"/pages?slug={slug}&context=edit&_fields={_FIELDS}")
    data = r.get("data") if r.get("ok") else None
    if not isinstance(data, list):
        return None
    for page in data:
        if isinstance(page, dict) and page.get("status") == "publish":
            return page
    return None


def _read_back(wp: WpClient, page_id: int, field: str = "meta_description") -> str | None:
    r = wp("GET", f"/pages/{page_id}?context=edit&_fields={_FIELDS}")
    if not r.get("ok") or not isinstance(r.get("data"), dict):
        return None
    return current_value(r["data"], field)


def write_description(wp: WpClient, page_id: int, new: str, before: str) -> dict:
    return write_field(wp, page_id, "meta_description", new, before)


def write_field(wp: WpClient, page_id: int, field: str, new: str, before: str) -> dict:
    """Write, then read back. Returns {ok, verified, error?, current}."""
    key = FIELDS_META[field]["key"]
    last_error = None
    for body in ({"meta": {key: new}}, {"meta_input": {key: new}}):
        r = wp("POST", f"/pages/{page_id}", body)
        if not r.get("ok"):
            last_error = f"WordPress said {r.get('http')} {r.get('code') or ''}".strip()
            continue
        current = _read_back(wp, page_id, field)
        if current == new:
            return {"ok": True, "verified": True, "current": current}
        last_error = "WordPress accepted the change but the page does not show it"
        if current is not None and current not in (before, new):
            wp("POST", f"/pages/{page_id}", {"meta": {key: before}})
            return {"ok": False, "verified": False, "error": "unexpected value, put back", "current": current}
    return {"ok": False, "verified": False, "error": last_error or "write failed", "current": None}


# ── Log ─────────────────────────────────────────────────────────────────────

def _entry_id(brand: str, page: str, now: str) -> str:
    return hashlib.sha1(f"{brand}|{page}|{now}".encode()).hexdigest()[:12]


def load_log(io: Any) -> dict:
    doc = io.read(LOG_FILE)
    return doc if isinstance(doc, dict) and isinstance(doc.get("entries"), list) else {"entries": []}


def _save_log(io: Any, log: dict, now: str) -> None:
    log["updated"] = now
    log["entries"] = log["entries"][-MAX_LOG:]
    io.write(LOG_FILE, log)


def _already_recorded(log: dict, page: str, after: str, statuses: tuple[str, ...]) -> bool:
    for e in reversed(log["entries"]):
        if e.get("page") == page:
            return e.get("after") == after and e.get("status") in statuses
    return False


# ── Run ─────────────────────────────────────────────────────────────────────

def run_auto(io: Any, brand: str, queue: dict | None, wp: WpClient, now: str, run_mode: str | None = None) -> dict:
    """Publish (or, in dry-run, only record) descriptions for eligible queue items."""
    run_mode = run_mode or mode()
    summary: dict[str, Any] = {"mode": run_mode, "applied": 0, "dry_run": 0, "skipped": [], "failed": []}
    if run_mode == MODE_OFF or brand not in seo_fix_queue.QUEUE_BRANDS or not queue:
        return summary

    log = load_log(io)
    done = 0
    for item in queue.get("items", []):
        if done >= MAX_PER_RUN:
            break
        if item.get("status") != "draft" or item.get("publish_policy") != seo_fix_queue.PUBLISH_AUTO:
            continue
        page_name = item.get("page")
        slugs = page_slugs(brand)
        if item.get("type") not in seo_fix_queue.AUTO_PUBLISH_TYPES or page_name not in slugs:
            continue

        if page_field_writable(wp, "meta_description") is False:
            summary["skipped"].append({"page": page_name, "why": PAGE_UNWRITABLE_WHY})
            continue

        page = fetch_page(wp, slugs[page_name])
        if not page:
            summary["skipped"].append({"page": page_name, "why": "page not found on the site"})
            continue
        before = current_description(page)
        if before:
            summary["skipped"].append({"page": page_name, "why": "already has a description written by a person"})
            continue
        after = propose(
            (page.get("content") or {}).get("rendered", ""),
            prefer=(brand.replace("-", " "), page_name),
        )
        if not after:
            summary["skipped"].append({"page": page_name, "why": "no safe wording found on the page"})
            continue

        entry = {
            "id": _entry_id(brand, page_name, now),
            "brand": brand,
            "page": page_name,
            "page_id": page.get("id"),
            "link": page.get("link"),
            "field": "meta_description",
            "before": before,
            "after": after,
            "at": now,
        }
        if run_mode == MODE_DRY:
            if _already_recorded(log, page_name, after, ("dry_run", "applied")):
                continue
            entry["status"] = "dry_run"
            log["entries"].append(entry)
            summary["dry_run"] += 1
            done += 1
            continue

        if _already_recorded(log, page_name, after, ("applied",)):
            continue
        result = write_description(wp, int(page["id"]), after, before)
        entry["status"] = "applied" if result["ok"] else "failed"
        entry["verified"] = result["verified"]
        if not result["ok"]:
            entry["error"] = result.get("error")
            summary["failed"].append({"page": page_name, "why": result.get("error")})
        else:
            summary["applied"] += 1
        log["entries"].append(entry)
        done += 1

    if done:
        _save_log(io, log, now)
    return summary


def undo(io: Any, brand: str, entry_id: str, wp: WpClient, now: str) -> dict:
    """Put an applied change back. Refuses if the description changed since."""
    if brand not in seo_fix_queue.QUEUE_BRANDS:
        return {"ok": False, "error": f"no SEO publishing for brand {brand!r}"}
    log = load_log(io)
    entry = next((e for e in log["entries"] if e.get("id") == entry_id), None)
    if not entry:
        return {"ok": False, "error": "change not found"}
    if entry.get("status") != "applied":
        return {"ok": False, "error": f"nothing to undo: this change is {entry.get('status')}"}

    field = entry.get("field") or "meta_description"
    current = _read_back(wp, int(entry["page_id"]), field)
    if current is None:
        return {"ok": False, "error": "could not read the page from WordPress"}
    if current != entry.get("after"):
        return {"ok": False, "error": f"the {FIELDS_META[field]['label'].lower()} has been edited since this change, so it was left alone"}

    # The fallback value is the restored one too: a failed undo must never put the automatic text back.
    restored = entry.get("before") or ""
    result = write_field(wp, int(entry["page_id"]), field, restored, restored)
    if not result["ok"]:
        return {"ok": False, "error": result.get("error") or "undo failed"}
    entry["status"] = "undone"
    entry["undone_at"] = now
    _save_log(io, log, now)
    return {"ok": True, "entry": entry}
