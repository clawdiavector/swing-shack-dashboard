"""Weekly retail campaign: stock + approved photos → rendered posts as review drafts.

Swing Shack uses product_post_templates (three layouts via layout_for). Stick uses
measured archetypes (maker stack or partner plate when the approved photo is lifestyle).
Nothing runs without an approved product photo — gaps are reported, not guessed.
"""
from __future__ import annotations

import io
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from _lib import product_post_templates as pt

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

TZ = ZoneInfo("Africa/Johannesburg")

LAYOUT_TO_ARCHETYPE = {
    "type-hero": "ss-product-type-hero",
    "one-hero": "ss-product-one-hero",
    "pick-yours": "ss-product-pick-yours",
}
ARCHETYPE_TO_LAYOUT = {v: k for k, v in LAYOUT_TO_ARCHETYPE.items()}

RETAIL_BRANDS = ("swing-shack", "stick")
WEEKDAY_COUNT = 5
CREATED_BY = "campaign-os/retail_campaign"


def archetype_for_layout(layout: str) -> str:
    return LAYOUT_TO_ARCHETYPE.get(layout, LAYOUT_TO_ARCHETYPE["type-hero"])


def suggest_product_layout(n_products: int, history: Sequence[str] = ()) -> str:
    return pt.layout_for(n_products, history)


def product_layout_history(brand_id: str, *, limit: int = 12) -> List[str]:
    """Layouts of recent product posts, oldest first (for layout_for rotation)."""
    from _lib.marketing_calendar import canonical_records  # noqa: PLC0415

    layouts: List[str] = []
    for rec in reversed(list(canonical_records(brand_id))):
        layout = _layout_from_record(rec)
        if layout:
            layouts.append(layout)
        if len(layouts) >= limit:
            break
    layouts.reverse()
    return layouts


def _layout_from_record(rec: dict[str, Any]) -> str:
    rs = rec.get("render_spec") if isinstance(rec.get("render_spec"), dict) else {}
    arch = str(rs.get("archetype") or rec.get("post_type") or rec.get("template_id") or "")
    if arch in ARCHETYPE_TO_LAYOUT:
        return ARCHETYPE_TO_LAYOUT[arch]
    if arch in pt.LAYOUTS:
        return arch
    fields = rs.get("fields") if isinstance(rs.get("fields"), dict) else {}
    layout = str(rs.get("product_layout") or fields.get("product_layout") or "").strip()
    return layout if layout in pt.LAYOUTS else ""


def _maker_name(product_name: str) -> str:
    tokens = product_name.split()
    return tokens[0] if tokens else product_name


def _headline_lines(product_name: str) -> Tuple[str, str]:
    """Two headline lines, each <= 14 chars (product_post_templates rule)."""
    maker = _maker_name(product_name)
    rest = product_name[len(maker) :].strip(" -")
    line1 = (maker.upper()[:14] or "IN STOCK").strip()
    if rest:
        words = rest.upper().split()
        line2 = " ".join(words)[:14].strip() or "NOW."
    else:
        line2 = "NOW."
    if len(line2) > 14:
        line2 = line2[:14].rstrip()
    return line1, line2


def _default_cta(brand_id: str) -> str:
    if brand_id == "swing-shack":
        return "DM us to order or book a ball fitting"
    return "DM us for details"


def _hook_max_chars(brand_id: str) -> int | None:
    import caption_lint  # noqa: PLC0415

    rules = caption_lint.load_rules(brand_id)
    hook_max = rules.get("hook_max_chars")
    return int(hook_max) if hook_max else None


def _fit_hook(hook: str, max_chars: int) -> str:
    hook = hook.strip()
    if len(hook) <= max_chars:
        return hook
    trimmed = hook[:max_chars].rstrip()
    if " " in trimmed:
        trimmed = trimmed.rsplit(" ", 1)[0]
    return trimmed.rstrip(".,;:- ")


def build_caption(brand_id: str, product_name: str, idea: str = "", status: str = "", angle: str | None = None) -> str:
    """Product caption. With an ``angle`` (product_angle.ANGLES) it carries only that angle's line."""
    hook = idea.strip() or f"{product_name} is in store now."
    if status == "new":
        hook = f"Just landed: {product_name}."
    elif status == "back":
        hook = f"Back in stock: {product_name}."
    hook = hook.rstrip(".")
    hook_max = _hook_max_chars(brand_id)
    if hook_max:
        hook = _fit_hook(hook, hook_max)
    cta = _default_cta(brand_id)
    if angle:
        from _lib.product_angle import apply_angle  # noqa: PLC0415
        from _lib.service_tiein import service_tiein_line  # noqa: PLC0415

        # The service line is the post's one ask, so it takes the CTA's place.
        ask = (service_tiein_line(product_name, brand_id) if angle == "service" else None) or f"{cta}."
        base = f"{hook}.\n{ask}\nBetter begins here." if brand_id == "stick" else f"{hook}.\n{ask}"
        return base if angle == "service" else (apply_angle(base, angle, product_name, brand_id) or base)
    if brand_id == "stick":
        return f"{hook}.\nBook a fitting at Stick.\nBetter begins here."
    return f"{hook}.\n{cta}."


def caption_hard_fails(brand_id: str, caption: str) -> List[str]:
    import caption_lint  # noqa: PLC0415, E402

    try:
        res = caption_lint.lint(brand_id, caption, cross_brand=False)
    except Exception as exc:
        return [f"lint_error:{exc}"]
    return [
        str(f.get("message") or f.get("code") or "hard")
        for f in res.get("findings") or []
        if f.get("level") == caption_lint.HARD
    ]


def _approved_photo_entries(brand_id: str) -> Dict[str, List[dict[str, Any]]]:
    from _lib import photo_map as pm  # noqa: PLC0415

    by_product: Dict[str, List[dict[str, Any]]] = {}
    for e in pm.load(brand_id):
        if e.get("status") != "approved":
            continue
        by_product.setdefault(str(e.get("product") or ""), []).append(e)
    return by_product


def _stock_lines(brand_id: str) -> List[dict[str, Any]]:
    from _lib import stock_pulse as sp  # noqa: PLC0415

    snaps = sp.load_snapshots(brand_id)
    if not snaps:
        return []
    return sp.candidates(sp.analyse(snaps))


def eligible_retail_lines(brand_id: str) -> Tuple[List[dict[str, Any]], List[dict[str, Any]]]:
    """Lines with stock and at least one approved photo. Returns (eligible, gaps)."""
    photos = _approved_photo_entries(brand_id)
    eligible, gaps = [], []
    seen_names: set[str] = set()
    for row in _stock_lines(brand_id):
        name = str(row.get("name") or "").strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        if name not in photos:
            gaps.append({"product": name, "reason": "no_approved_photo"})
            continue
        eligible.append({**row, "photo_entries": photos[name]})
    return eligible, gaps


def pick_week_products(
    brand_id: str,
    *,
    start: date,
    days: int = WEEKDAY_COUNT,
    exclude_names: Sequence[str] = (),
) -> Tuple[List[dict[str, Any]], List[dict[str, Any]]]:
    """Up to `days` distinct products, mixing makers where possible."""
    eligible, gaps = eligible_retail_lines(brand_id)
    blocked = {n.lower() for n in exclude_names}
    pool = [e for e in eligible if e["name"].lower() not in blocked]
    makers_seen: set[str] = set()
    chosen: List[dict[str, Any]] = []
    publish_days = _weekdays_from(start, days)
    idx = 0
    while len(chosen) < len(publish_days) and pool:
        if idx >= len(pool) * 3:
            break
        cand = pool[idx % len(pool)]
        idx += 1
        maker = _maker_name(cand["name"]).lower()
        if maker in makers_seen and len(chosen) + len(pool) > len(publish_days):
            continue
        makers_seen.add(maker)
        chosen.append({**cand, "date": publish_days[len(chosen)].isoformat()})
        pool = [p for p in pool if p["name"] != cand["name"]]
        idx = 0
    return chosen, gaps


def _weekdays_from(start: date, count: int) -> List[date]:
    out: List[date] = []
    d = start
    while len(out) < count:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
        if (d - start).days > count + 7:
            break
    return out


def _slug(product_name: str, day: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", product_name.lower()).strip("-")[:40]
    return f"retail-{base}-{day[5:].replace('-', '')}"


def _pick_photo_path(brand_id: str, entries: List[dict[str, Any]]) -> Optional[str]:
    from _lib import photo_map as pm  # noqa: PLC0415

    root = pm.images_dir(brand_id)
    for e in entries:
        rel = str(e.get("file") or "")
        path = root / rel
        if path.is_file():
            return str(path)
    return None


def _stick_template(entries: List[dict[str, Any]]) -> str:
    for e in entries:
        view = str(e.get("view") or "").lower()
        if any(k in view for k in ("lifestyle", "venue", "course", "instore", "store")):
            return "stick-venue-post"
    return "stick-product-post"


def render_swing_shack_item(item: dict[str, Any], layout: str) -> bytes:
    photo = _pick_photo_path("swing-shack", item["photo_entries"])
    if not photo:
        raise ValueError("no photo path")
    line1, line2 = _headline_lines(item["name"])
    post = {
        "layout": layout,
        "brand": _maker_name(item["name"]),
        "headline": [line1, line2],
        "models": [{"label": item["name"].split()[-1][:20], "image": photo}],
        "accent": "green",
        "cta": _default_cta("swing-shack"),
    }
    im = pt.render(post)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def plan_week(
    brand_id: str,
    *,
    start: date | None = None,
    days: int = WEEKDAY_COUNT,
) -> dict[str, Any]:
    start = start or date.today()
    picks, gaps = pick_week_products(brand_id, start=start, days=days)
    from _lib import product_angle  # noqa: PLC0415

    history = product_layout_history(brand_id) if brand_id == "swing-shack" else []
    posts: List[dict[str, Any]] = []
    for item in picks:
        angle = product_angle.next_angle(brand_id, item["name"], product_angle.recent_angles(brand_id))
        caption = build_caption(brand_id, item["name"], item.get("idea") or "", item.get("status") or "", angle)
        hard = caption_hard_fails(brand_id, caption)
        slot: dict[str, Any] = {
            "date": item["date"],
            "product": item["name"],
            "slug": _slug(item["name"], item["date"]),
            "caption": caption,
            "angle": angle,
            "skipped": bool(hard),
            "lint_hard": hard,
        }
        if hard:
            posts.append(slot)
            continue
        product_angle.remember(brand_id, angle)
        if brand_id == "swing-shack":
            layout = suggest_product_layout(1, history)
            history.append(layout)
            slot["layout"] = layout
            slot["archetype_id"] = archetype_for_layout(layout)
            slot["photo_entries"] = item["photo_entries"]
        else:
            slot["archetype_id"] = _stick_template(item["photo_entries"])
            photo = _pick_photo_path(brand_id, item["photo_entries"])
            if not photo:
                slot["skipped"] = True
                slot["gap"] = "no_approved_photo"
            else:
                slot["photo"] = photo
        posts.append(slot)
    return {
        "ok": True,
        "brand_id": brand_id,
        "start": start.isoformat(),
        "gaps": gaps,
        "posts": posts,
        "planned": sum(1 for p in posts if not p.get("skipped")),
    }


def lodge_plan(brand_id: str, plan: dict[str, Any], *, approve: bool = False) -> dict[str, Any]:
    from _lib.post_lodge import LodgeError, lodge_post  # noqa: PLC0415

    lodged, skipped = [], []
    for slot in plan.get("posts") or []:
        if slot.get("skipped"):
            skipped.append(slot)
            continue
        try:
            if brand_id == "swing-shack":
                layout = slot["layout"]
                image_bytes = render_swing_shack_item(
                    {"name": slot["product"], "photo_entries": slot["photo_entries"]},
                    layout,
                )
                out = lodge_post(
                    brand=brand_id,
                    slug=slot["slug"],
                    date=slot["date"],
                    caption=slot["caption"],
                    image_bytes=image_bytes,
                    created_by=CREATED_BY,
                    approve=approve,
                    product_layout=layout,
                )
            else:
                fields = {
                    "vendor_name": _maker_name(slot["product"]),
                    "product_name": slot["product"].upper()[:22],
                    "cta": "DM US FOR DETAILS",
                }
                out = lodge_post(
                    brand=brand_id,
                    slug=slot["slug"],
                    date=slot["date"],
                    caption=slot["caption"],
                    archetype=slot["archetype_id"],
                    fields=fields,
                    photo=slot.get("photo"),
                    created_by=CREATED_BY,
                    approve=approve,
                )
            lodged.append({"slug": slot["slug"], "date": slot["date"], "state": out.get("state")})
        except LodgeError as exc:
            skipped.append({**slot, "lodge_error": str(exc)})
    return {"lodged": lodged, "skipped": skipped}


def run(*, brand: str | None = None, today: date | None = None, lodge: bool = True) -> dict[str, Any]:
    """Weekly retail draft generator. ``lodge=False`` plans only (for tests)."""
    if not brand:
        return {"ok": False, "error": "brand required"}
    if brand not in RETAIL_BRANDS:
        return {"ok": False, "error": f"retail campaign supports {RETAIL_BRANDS}, not {brand!r}"}
    today = today or date.today()
    # Run on Monday for the coming Mon–Fri; other days still plan from today.
    start = today
    if today.weekday() == 0:
        start = today
    plan = plan_week(brand, start=start)
    result = {
        "ok": True,
        "brand_id": brand,
        "today": today.isoformat(),
        "plan": plan,
    }
    if lodge:
        result["lodge"] = lodge_plan(brand, plan, approve=False)
    from _lib.jobs.layer1._io import io_for_job  # noqa: PLC0415

    io = io_for_job("retail_campaign", brand)
    io.write("retail-campaign/latest.json", result)
    return result
