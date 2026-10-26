"""SEO fix buttons: propose, edit, apply, undo, for any finding type in the catalogue.

A person clicks Fix (something is missing) or Improve (it exists but is weak).
The page asks for a draft, the person edits it, and one click writes it to
WordPress, reads it back and keeps the change in the history with an undo.

Policy (wiki decisions/seo-geo-automation-tiers-2026-10-19): the click is the
approval, so anything that asks first may be applied here, the homepage
included. Nothing in this module runs by itself.

The switch is the same as automatic publishing (SEO_AUTOPUBLISH):
  off      buttons refuse, nothing is written
  dry-run  buttons record what would be written, nothing is written
  on       buttons write

Which finding types have a button is `seo_fix_queue.FIX_BUTTONS`. To teach the
page a new kind of fix, add the type there and a drafter in DRAFTERS below.
"""
from __future__ import annotations

import html as _html
import re
from typing import Any, Callable

from . import seo_fix_queue
from . import seo_meta_publish as smp

QUEUE_FILE = "seo-fix-queue.json"

# Page name in the audit -> WordPress page slug. Unlike automatic publishing,
# a person's click may change the homepage.
BUTTON_SLUGS = {**smp.PAGE_SLUGS, "Homepage": "home"}

BRAND_NAMES = {"swing-shack": "Swing Shack"}

# Names of the other companies. Never allowed in Swing Shack text.
_OTHER_BRANDS = re.compile(r"\b(stick|bag\s?drop)\b", re.I)
# Claims and details that nobody has signed off: allowed only after an explicit confirm.
_CLAIMS = re.compile(
    r"(\bR\s?\d)|%|\bfree\b|\bguarantee|\bbest\b|\bcheapest\b|\b(no\.?|number)\s?1\b|#1|\bfirst\b",
    re.I,
)
_CONTACT = re.compile(r"https?:|www\.|@|\d{3}[\s-]?\d{3}")

_HEADING = re.compile(r"<h[1-3][^>]*>(.*?)</h[1-3]\s*>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")


# ── Drafting ────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(_TAG.sub(" ", text))).strip()


def _headings(raw_html: str) -> list[str]:
    cleaned = smp._NOISE.sub(" ", raw_html or "")
    out = []
    for m in _HEADING.finditer(cleaned):
        text = _clean(m.group(1))
        if text and text not in out:
            out.append(text)
    return out


def _first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", text.strip())[0].rstrip(".!?:, ")


def draft_description(raw_html: str, brand: str, page_name: str, current: str) -> str | None:
    return smp.propose(raw_html, prefer=(BRAND_NAMES.get(brand, ""), page_name), avoid=current)


def draft_title(raw_html: str, brand: str, page_name: str, current: str) -> str | None:
    """Page name, a short phrase from the page's own first heading, then the brand.
    Never adds a place, a price or a claim the page does not already make."""
    field = smp.FIELDS_META["title"]
    brand_name = BRAND_NAMES.get(brand, "")
    for heading in _headings(raw_html):
        phrase = _first_sentence(heading)
        if len(phrase.split()) < 2 or len(phrase.split()) > 8:
            continue
        if smp._REJECT.search(phrase) or _OTHER_BRANDS.search(phrase):
            continue
        if page_name == seo_fix_queue.HOMEPAGE:
            title = f"{brand_name} | {phrase}"
        elif phrase.lower().startswith(page_name.lower()):
            title = f"{phrase} | {brand_name}"
        else:
            title = f"{page_name}: {phrase} | {brand_name}"
        if field["min"] <= len(title) <= field["max"] and title != current:
            return title
    return None


DRAFTERS: dict[str, Callable[[str, str, str, str], str | None]] = {
    "meta_description": draft_description,
    "title": draft_title,
}


# ── Checking text ───────────────────────────────────────────────────────────

def notes_for(field: str, text: str, brand: str, page_name: str) -> list[str]:
    """Plain reasons the current text could be better. Empty when it is fine."""
    f = smp.FIELDS_META[field]
    label = f["label"].lower()
    text = (text or "").strip()
    if not text:
        return [f"There is no {label}."]
    notes = []
    if len(text) < f["min"]:
        notes.append(f"{len(text)} characters: shorter than the {f['min']} Google likes to see.")
    if len(text) > f["max"]:
        notes.append(f"{len(text)} characters: Google cuts it off after about {f['max']}.")
    name = BRAND_NAMES.get(brand, "")
    if name and name.lower() not in text.lower() and page_name.lower() not in text.lower():
        notes.append(f"It does not mention {name} or the page name.")
    return notes


def check_text(field: str, text: str, brand: str) -> dict[str, list[str]]:
    """{'errors': stop, 'warnings': need an explicit confirm}."""
    f = smp.FIELDS_META[field]
    errors: list[str] = []
    warnings: list[str] = []
    if not text:
        errors.append("The text is empty.")
        return {"errors": errors, "warnings": warnings}
    if len(text) < f["min"]:
        errors.append(f"{len(text)} characters. It needs at least {f['min']}.")
    if len(text) > f["max"]:
        errors.append(f"{len(text)} characters. It needs at most {f['max']}, or Google cuts it off.")
    if "<" in text or ">" in text:
        errors.append("Plain text only, no HTML.")
    if "�" in text:
        errors.append("The text has a broken character.")
    if _OTHER_BRANDS.search(text):
        errors.append("It names another company. Swing Shack text must only name Swing Shack.")
    if _CONTACT.search(text):
        errors.append("No links, emails or phone numbers in a search result.")
    if _CLAIMS.search(text):
        warnings.append(
            "It makes a claim or gives a price or percentage (for example free, best, first, a rand amount). "
            "Make sure it is true and signed off."
        )
    return {"errors": errors, "warnings": warnings}


# ── Lookups ─────────────────────────────────────────────────────────────────

def _item(io: Any, item_id: str) -> dict | None:
    queue = io.read(QUEUE_FILE) or {}
    return next((i for i in queue.get("items", []) if i.get("id") == item_id), None)


def _resolve(io: Any, brand: str, item_id: str) -> tuple[dict | None, dict | None, str | None]:
    """(item, button, error)"""
    if brand not in seo_fix_queue.QUEUE_BRANDS:
        return None, None, f"no SEO fixes for brand {brand!r}"
    item = _item(io, item_id)
    if not item:
        return None, None, "that fix is not in the list any more, reload the page"
    button = seo_fix_queue.FIX_BUTTONS.get(item.get("type"))
    if not button or item.get("page") not in BUTTON_SLUGS:
        return item, None, "this kind of fix has no button yet"
    return item, button, None


# ── Draft ───────────────────────────────────────────────────────────────────

def build_draft(io: Any, brand: str, item_id: str, wp: smp.WpClient) -> dict:
    """Read the live page and propose text. Writes nothing."""
    item, button, err = _resolve(io, brand, item_id)
    if err:
        return {"ok": False, "error": err}
    page_name = item["page"]
    field = button["field"]
    page = smp.fetch_page(wp, BUTTON_SLUGS[page_name])
    if not page:
        return {"ok": False, "error": "could not find that page on the website"}
    current = smp.current_value(page, field)
    html = (page.get("content") or {}).get("rendered", "")
    proposal = DRAFTERS[field](html, brand, page_name, current)
    f = smp.FIELDS_META[field]
    writable = smp.page_field_writable(wp, field)
    return {
        "ok": True,
        "writable": writable,
        "unwritable_reason": smp.PAGE_UNWRITABLE_WHY if writable is False else None,
        "item_id": item_id,
        "page": page_name,
        "page_id": page.get("id"),
        "link": page.get("link"),
        "field": field,
        "field_label": f["label"],
        "button": button["label"],
        "current": current,
        "proposal": proposal,
        "min": f["min"],
        "max": f["max"],
        "notes": notes_for(field, current, brand, page_name),
    }


# ── Apply ───────────────────────────────────────────────────────────────────

def apply_fix(
    io: Any,
    brand: str,
    item_id: str,
    text: str,
    wp: smp.WpClient,
    now: str,
    *,
    expected_current: str | None = None,
    confirm: bool = False,
    run_mode: str | None = None,
) -> dict:
    """Write the person's text (after checks), read it back, log it."""
    run_mode = run_mode or smp.mode()
    if run_mode == smp.MODE_OFF:
        return {"ok": False, "status": 409, "error": "Fixing from this page is switched off, so nothing was changed."}
    item, button, err = _resolve(io, brand, item_id)
    if err:
        return {"ok": False, "status": 404, "error": err}
    field = button["field"]
    page_name = item["page"]
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if smp.page_field_writable(wp, field) is False:
        return {"ok": False, "status": 409, "error": smp.PAGE_UNWRITABLE_WHY}

    checks = check_text(field, text, brand)
    if checks["errors"]:
        return {"ok": False, "status": 422, "error": checks["errors"][0], "errors": checks["errors"]}

    page = smp.fetch_page(wp, BUTTON_SLUGS[page_name])
    if not page:
        return {"ok": False, "status": 404, "error": "could not find that page on the website"}
    before = smp.current_value(page, field)
    if expected_current is not None and expected_current.strip() != before:
        return {"ok": False, "status": 409,
                "error": "The page changed since this draft was made. Reload the page and look again."}
    if text == before:
        return {"ok": False, "status": 422, "error": "That is what the page already says."}
    if checks["warnings"] and not confirm:
        return {"ok": False, "status": 422, "needs_confirm": True, "warnings": checks["warnings"],
                "error": checks["warnings"][0]}

    log = smp.load_log(io)
    entry = {
        "id": smp._entry_id(brand, f"{page_name}|{field}|{text}", now),
        "brand": brand,
        "page": page_name,
        "page_id": page.get("id"),
        "link": page.get("link"),
        "field": field,
        "before": before,
        "after": text,
        "at": now,
        "source": "button",
        "item_id": item_id,
    }
    if run_mode == smp.MODE_DRY:
        entry["status"] = "dry_run"
    else:
        result = smp.write_field(wp, int(page["id"]), field, text, before)
        entry["status"] = "applied" if result["ok"] else "failed"
        entry["verified"] = result["verified"]
        if not result["ok"]:
            entry["error"] = result.get("error")
    log["entries"].append(entry)
    smp._save_log(io, log, now)
    if entry["status"] == "failed":
        return {"ok": False, "status": 502, "error": entry.get("error") or "the change did not work", "entry": entry}
    return {"ok": True, "mode": run_mode, "entry": entry}
