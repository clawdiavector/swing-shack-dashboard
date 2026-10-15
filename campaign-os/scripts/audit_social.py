#!/usr/bin/env python3
"""Full Instagram audit for an operating brand — every post, not the first page.

Why this exists: logged-out scraping returns 12 posts as 640px centre-crops with
no captions and no engagement. The Graph API returns the whole catalogue at full
resolution with insights. This walks `paging.next` to the end rather than taking
one page, and lands the result where the feedback loop can read it.

    python3 scripts/audit_social.py stick [--max-pages N] [--no-images]

Writes:
    data/brand-directory/<brand>/feedback/instagram-audit.json
    data/brand-directory/<brand>/images/posts/<id>.jpg   (full-res, --no-images skips)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "campaign-os"))

from _lib import meta_api  # noqa: E402

FIELDS = ["id", "caption", "media_type", "media_url", "permalink",
          "thumbnail_url", "timestamp", "username", "like_count", "comments_count"]
# The Graph API 400s when a metric does not apply to a media type, so insights
# are fetched per-post with the set that matches that post. Asking for the image
# set on a reel returns nothing — on Stick that silently blanked 130 of 261
# posts, which is most of the feed.
METRICS_BY_MEDIA_TYPE = {
    "IMAGE": "reach,saved,total_interactions",
    "CAROUSEL_ALBUM": "reach,saved,total_interactions",
    "VIDEO": "reach,saved,total_interactions,views",
    "REELS": "reach,saved,total_interactions,views",
}
# Dropped one at a time when the API rejects the set, so an unknown media type
# or a renamed metric degrades to partial data instead of no data.
_METRIC_FALLBACK = ["views", "saved", "reach"]

IMAGE_METRICS = METRICS_BY_MEDIA_TYPE["IMAGE"]  # back-compat for importers


def _creds(brand: str) -> tuple[str, str]:
    cfg = meta_api.load_brand_integration(brand)
    resolved = meta_api.resolve_credentials_for_brand(brand, cfg)
    token = resolved.get("token")
    ig_id = cfg.get("ig_business_account_id")
    if not token:
        raise SystemExit(
            f"No token for {brand}. Errors: {resolved.get('errors')}\n"
            f"Set credential_env in data/integrations/{brand}/instagram.json "
            f"and export that variable."
        )
    if not ig_id:
        raise SystemExit(
            f"No ig_business_account_id for {brand} — fill it into "
            f"data/integrations/{brand}/instagram.json"
        )
    print(f"  credentials: {resolved.get('source')}  account: {ig_id}")
    return str(ig_id), str(token)


def fetch_all_media(ig_id: str, token: str, max_pages: int = 50) -> list[dict]:
    posts, after, page = [], None, 0
    while page < max_pages:
        params = {"fields": ",".join(FIELDS), "limit": 100, "access_token": token}
        if after:
            params["after"] = after
        body = meta_api._graph_get(f"/{ig_id}/media", params, token_override=token)
        batch = body.get("data") or []
        posts.extend(batch)
        page += 1
        print(f"  page {page}: +{len(batch)} (total {len(posts)})")
        after = ((body.get("paging") or {}).get("cursors") or {}).get("after")
        if not batch or not (body.get("paging") or {}).get("next"):
            break
    return posts


def _fetch_insights(post_id: str, metrics: str, token: str) -> dict:
    """Fetch one post's insights, shrinking the metric set until it is accepted."""
    wanted = metrics.split(",")
    last_error: Exception | None = None
    while wanted:
        try:
            body = meta_api._graph_get(
                f"/{post_id}/insights",
                {"metric": ",".join(wanted), "access_token": token},
                token_override=token,
            )
            return {m["name"]: (m.get("values") or [{}])[0].get("value")
                    for m in body.get("data", [])}
        except Exception as e:  # noqa: BLE001 - narrow the ask and retry
            last_error = e
            droppable = [m for m in _METRIC_FALLBACK if m in wanted]
            if not droppable:
                break
            wanted.remove(droppable[0])
    raise last_error if last_error else RuntimeError("no metrics requested")


def add_insights(posts: list[dict], token: str) -> None:
    for i, p in enumerate(posts, 1):
        media_type = (p.get("media_type") or "").upper()
        metrics = METRICS_BY_MEDIA_TYPE.get(media_type)
        if not metrics:
            # Unknown type: try the broadest set rather than skipping the post.
            metrics = METRICS_BY_MEDIA_TYPE["REELS"]
            p["insights_media_type_unknown"] = media_type or "(absent)"
        try:
            p["insights"] = _fetch_insights(p["id"], metrics, token)
        except Exception as e:  # a single post failing must not abort the audit
            p["insights_error"] = str(e)[:140]
        if i % 20 == 0:
            print(f"  insights: {i}/{len(posts)}")
            time.sleep(1)


def download_images(posts: list[dict], out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in posts:
        url = p.get("media_url") or p.get("thumbnail_url")
        if not url:
            continue
        dest = out_dir / f"{p['id']}.jpg"
        if dest.exists():
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "campaign-os-audit"})
            with urllib.request.urlopen(req, timeout=30) as r:
                dest.write_bytes(r.read())
            n += 1
        except Exception:
            continue
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("brand")
    ap.add_argument("--max-pages", type=int, default=50)
    ap.add_argument("--no-images", action="store_true")
    a = ap.parse_args()

    print(f"auditing {a.brand}")
    ig_id, token = _creds(a.brand)

    posts = fetch_all_media(ig_id, token, a.max_pages)
    print(f"  {len(posts)} posts")
    add_insights(posts, token)

    brand_dir = REPO / "data" / "brand-directory" / a.brand
    images = 0
    if not a.no_images:
        images = download_images(posts, brand_dir / "images" / "posts")
        print(f"  {images} images downloaded")

    by_type: dict[str, int] = {}
    for p in posts:
        by_type[p.get("media_type", "?")] = by_type.get(p.get("media_type", "?"), 0) + 1

    # Coverage is the number that catches the reels bug class: if a media type
    # shows 0 with_insights, its metric set is wrong, not its engagement.
    coverage: dict[str, dict[str, int]] = {}
    for p in posts:
        mt = p.get("media_type", "?")
        row = coverage.setdefault(mt, {"posts": 0, "with_insights": 0, "errored": 0})
        row["posts"] += 1
        if isinstance(p.get("insights"), dict) and p["insights"]:
            row["with_insights"] += 1
        if p.get("insights_error"):
            row["errored"] += 1

    out = brand_dir / "feedback" / "instagram-audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "schema": "campaign-os/instagram-audit/v1",
        "brand_id": a.brand,
        "ig_account_id": ig_id,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "post_count": len(posts),
        "by_media_type": by_type,
        "insights_coverage": coverage,
        "images_downloaded": images,
        "posts": posts,
    }, indent=2) + "\n")
    print(f"  wrote {out.relative_to(REPO)}")

    print("\n  insights coverage by media type:")
    for mt, row in sorted(coverage.items(), key=lambda kv: -kv[1]["posts"]):
        flag = "  <-- NO INSIGHTS" if row["posts"] and not row["with_insights"] else ""
        print(f"    {mt:<16} {row['with_insights']:>4}/{row['posts']:<4}"
              f" errored={row['errored']}{flag}")

    ranked = sorted(
        (p for p in posts if isinstance(p.get("insights"), dict)),
        key=lambda p: p["insights"].get("total_interactions") or 0, reverse=True)[:10]
    if ranked:
        print("\n  top 10 by interactions:")
        for p in ranked:
            cap = (p.get("caption") or "").replace("\n", " ")[:58]
            print(f"    {p['insights'].get('total_interactions'):>6}  {p.get('timestamp','')[:10]}  {cap}")


if __name__ == "__main__":
    main()
