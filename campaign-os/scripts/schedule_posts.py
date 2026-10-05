#!/usr/bin/env python3
"""Turn rendered images into real posts: caption, date, state, Review queue.

render_post.py makes the picture. This makes it a *post* -- the thing that shows
up in Campaign OS with a caption and a date, in a state you can approve.

    python3 campaign-os/scripts/schedule_posts.py \
        --batch data/post-batches/week-2026-10-06.json

    # on Railway, against the volume
    DATA_DIR=/data/campaign-os python3 campaign-os/scripts/schedule_posts.py \
        --batch /app/data/post-batches/week-2026-10-06.json

## How a post is actually represented

There is no separate inbox store. `intelligence.review_inbox()` reads
campaign-data.json directly and buckets each asset by its own `approvalStatus`:

    approvalStatus == "approved"  -> Approved queue
    approvalStatus == "rejected"  -> Rejected queue
    anything else                 -> Pending review   <- where you approve it

So a post is one asset row under campaigns.<campaign_id>.assets.<asset_id>,
carrying the caption, the image URL, the platform and four independent states:

    captionStatus   draft | ready
    visualStatus    brief-written | composed
    approvalStatus  review | approved | rejected     <- the Review queue
    publishStatus   planned | released               <- whether it may go out

An agent adding a post should leave approvalStatus=review and
publishStatus=planned: the work is done, a human still releases it. Override per
post with `approval_status` / `publish_status` in the batch, or for every post
with --approval-status / --publish-status.

## Batch fields this reads

    brand, slug, archetype, channels   (as render_post.py)
    date              YYYY-MM-DD  -- the day it is for
    caption           the post copy
    approval_status   default "review"
    publish_status    default "planned"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
REPO = CAMPAIGN_OS.parent
sys.path.insert(0, str(CAMPAIGN_OS))

VALID_APPROVAL = ("review", "approved", "rejected")
VALID_PUBLISH = ("planned", "released")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def runtime_data_dir() -> Path:
    env = os.environ.get("DATA_DIR")
    return Path(env) if env else CAMPAIGN_OS / "data"


def brands_registry_path() -> Path:
    return runtime_data_dir() / "brands.json"


def register_campaign_ownership(brand: str, campaign_id: str) -> str:
    """Add campaign_id to brands.json -> brands.<brand>.campaign_ids.

    review_inbox() filters brand-scoped views through this list: a campaign
    absent from it is treated as unowned and hidden, so a post can exist in
    campaign-data.json and still never appear in the Review tab. Stick owned
    zero campaigns before this, which is why nothing Stick ever showed up.
    """
    path = brands_registry_path()
    if not path.is_file():
        # intelligence._runtime_data_file falls back to the bundled copy when
        # the runtime one is absent. Writing a fresh file here would shadow it
        # and silently drop every campaign already owned, so seed from bundled.
        bundled = REPO / "data" / "brands.json"
        if not bundled.is_file():
            return f"no brands.json at {path} or {bundled} -- post hidden in brand-scoped views"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(bundled.read_text())
    reg = json.loads(path.read_text())
    brands = reg.setdefault("brands", {})
    row = brands.setdefault(brand, {})
    cids = row.setdefault("campaign_ids", [])
    if not isinstance(cids, list):
        return f"brands.{brand}.campaign_ids is not a list -- left alone"
    if campaign_id in cids:
        return ""
    cids.append(campaign_id)
    path.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n")
    return ""


def campaign_data_path() -> Path:
    return runtime_data_dir() / "campaign-data.json"


def _campaign_id_for(brand: str, batch_name: str) -> str:
    return f"{brand}-{batch_name}"


def _asset_id_for(brand: str, slug: str) -> str:
    return f"{brand}-{slug}"


def _image_urls(brand: str, slug: str, channel: str) -> tuple[str, str]:
    """Where render_post --publish put the files, as the app serves them."""
    png = f"composed-{slug}-{channel}.png"
    jpg = f"composed-{slug}-{channel}-publish.jpg"
    return f"/brand-images/{brand}/{png}", f"/brand-images/{brand}/{jpg}"


def build_asset(spec: dict, batch_name: str, *, approval: str, publish: str) -> tuple[str, str, dict]:
    brand = spec["brand"]
    slug = spec["slug"]
    channel = (spec.get("channels") or ["instagram"])[0]
    campaign_id = _campaign_id_for(brand, batch_name)
    asset_id = _asset_id_for(brand, slug)
    visual_url, publish_url = _image_urls(brand, slug, channel)
    caption = spec.get("caption") or ""
    # The Review card shows `name`; a caption's first line reads far better
    # there than a slug, and reviewing is the whole point of this row.
    first_line = caption.split("\n", 1)[0].strip() or slug
    asset = {
        "assetId": asset_id,
        "campaignId": campaign_id,
        "brand": brand,
        "brand_id": brand,
        "name": first_line[:72],
        "assetType": "feed-post",
        "contentType": "feed-post",
        "platform": channel,
        "caption": caption,
        "visualUrl": visual_url,
        "publishUrl": publish_url,
        "image_url": visual_url,
        "composed": {channel: visual_url},
        "archetype": spec.get("archetype"),
        "scheduledFor": spec.get("date"),
        "captionStatus": "ready" if caption else "draft",
        "visualStatus": "composed",
        "approvalStatus": approval,
        "publishStatus": publish,
        "owner": "campaign-os",
        "qualityGateState": "pending",
        "renderMode": "deterministic-template",
        "createdAt": _now(),
        "updatedAt": _now(),
        "history": [{
            "action": "composed-and-scheduled",
            "by": "campaign-os/schedule_posts.py",
            "at": _now(),
            "note": f"rendered from {spec.get('archetype')} for {spec.get('date')}; "
                    f"awaiting human approval",
        }],
    }
    return campaign_id, asset_id, asset


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--approval-status", choices=VALID_APPROVAL,
                    help="override every post's approval state")
    ap.add_argument("--publish-status", choices=VALID_PUBLISH,
                    help="override every post's publish state")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    specs = json.loads(Path(a.batch).read_text())
    batch_name = Path(a.batch).stem

    cd_path = campaign_data_path()
    if not cd_path.is_file():
        raise SystemExit(f"no campaign-data.json at {cd_path}. Is DATA_DIR right?")
    data = json.loads(cd_path.read_text())
    campaigns = data.setdefault("campaigns", {})

    written, skipped = [], []
    for spec in specs:
        approval = a.approval_status or spec.get("approval_status") or "review"
        publish = a.publish_status or spec.get("publish_status") or "planned"
        if approval not in VALID_APPROVAL or publish not in VALID_PUBLISH:
            skipped.append(f"{spec.get('slug')}: bad state {approval}/{publish}")
            continue
        if not spec.get("caption"):
            skipped.append(f"{spec.get('slug')}: no caption -- a post needs copy")
            continue
        cid, aid, asset = build_asset(spec, batch_name, approval=approval, publish=publish)
        campaign = campaigns.setdefault(cid, {
            "identity": {"name": f"{spec['brand']} — {batch_name}"},
            "brand_id": spec["brand"],
            "assets": {},
        })
        assets = campaign.setdefault("assets", {})
        # Re-running must update in place, never duplicate the post.
        existing = assets.get(aid)
        if isinstance(existing, dict):
            asset["createdAt"] = existing.get("createdAt", asset["createdAt"])
            asset["history"] = (existing.get("history") or []) + asset["history"]
        assets[aid] = asset
        if not a.dry_run:
            warn = register_campaign_ownership(spec["brand"], cid)
            if warn:
                skipped.append(f"{spec.get('slug')}: {warn}")
        written.append((spec.get("date"), spec["brand"], aid, approval, publish))

    if not a.dry_run:
        data["updatedAt"] = _now()
        cd_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    verb = "would write" if a.dry_run else "wrote"
    print(f"{verb} {len(written)} posts into {cd_path}")
    for date, brand, aid, approval, publish in sorted(written):
        print(f"  {date}  {brand:<12} {aid:<34} {approval}/{publish}")
    for s in skipped:
        print(f"  SKIPPED {s}")
    print("\nThey appear in Review (pending) because approvalStatus is not "
          "'approved' or 'rejected'. Approving there is a human action.")
    return 1 if skipped else 0


if __name__ == "__main__":
    raise SystemExit(main())
