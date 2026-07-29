#!/usr/bin/env python3
"""
back_map_postiz_to_ig.py — Back-map Postiz publishing records to IG media IDs.

Walks every Postiz event + publishing reference and resolves platformMediaId.
Two passes:

  Pass 1 (canonical): Read data/publishing-references.json — keys include
    'platformMediaId' directly when Postiz wrote it back at publish time.
  Pass 2 (fallback): For any reference where platformMediaId is still null,
    walk data/events/postiz/<id>.json — sometimes the actual Postiz response
    has the media id even when the regenerated index didn't carry it forward.

Writes data/meta-post-index.json:
  {
    generated: ISO timestamp,
    count: <int>,
    by_asset_id: { <asset_id>: { postiz_post_id, platform_media_id, channel, ... } },
    by_media_id: { <numeric_id>: { asset_id, postiz_post_id, ... } }
  }

Truth-before-cleverness:
  - References without a platform_media_id are SKIPPED, not invented.
  - The index only contains what Postiz actually wrote back.
  - For manually-uploaded IG posts (no Postiz reference), this script does
    nothing — those posts need a separate "force resolve by hashtag/date"
    pass once Meta is connected.

USAGE:
    .venv/bin/python scripts/back_map_postiz_to_ig.py             # write index
    .venv/bin/python scripts/back_map_postiz_to_ig.py --dry-run   # report only
    .venv/bin/python scripts/back_map_postiz_to_ig.py --verbose
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PUB_REFS_FILE = REPO / "data" / "publishing-references.json"
EVENTS_DIR = REPO / "data" / "events" / "postiz"
OUTPUT_FILE = REPO / "data" / "meta-post-index.json"


def _load_pub_refs() -> list[dict]:
    if not PUB_REFS_FILE.exists():
        return []
    try:
        with open(PUB_REFS_FILE) as f:
            d = json.load(f)
        return d.get("references", []) or []
    except Exception as e:
        print(f"!! could not read {PUB_REFS_FILE}: {e}", file=sys.stderr)
        return []


def _scan_events_for_media_ids() -> dict[str, str]:
    """Pass 2 fallback: walk event JSONs and extract any platform_media_id
    that the regenerated index missed. Returns dict[postiz_post_id → media_id].
    """
    out: dict[str, str] = {}
    if not EVENTS_DIR.exists():
        return out
    for ev_file in EVENTS_DIR.glob("*.json"):
        try:
            with open(ev_file) as f:
                ev = json.load(f)
            pid = ev.get("id") or ev.get("postId") or ev.get("postizPostId")
            if not pid:
                continue
            # Postiz returns the published media id in different shapes depending on
            # the version + provider. Try a few common locations.
            candidates = []
            for key in ("platformMediaId", "platform_media_id", "igMediaId", "mediaId", "id_on_platform"):
                v = ev.get(key)
                if v:
                    candidates.append(str(v))
            # Also check inside release object
            release = ev.get("release") or {}
            for key in ("id", "mediaId", "media_id"):
                v = release.get(key)
                if v and str(v).isdigit():
                    candidates.append(str(v))
            # And nested under integrations[i].post / similar
            for integ in ev.get("integrations", []) or []:
                post = integ.get("post") or {}
                for key in ("platformMediaId", "mediaId", "id"):
                    v = post.get(key)
                    if v and str(v).isdigit():
                        candidates.append(str(v))
            # Take the first numeric-looking id
            for c in candidates:
                if c.isdigit():
                    out[pid] = c
                    break
        except Exception as e:
            print(f"  !! {ev_file.name}: parse error: {e}", file=sys.stderr)
    return out


def build_index(verbose: bool = False) -> dict:
    refs = _load_pub_refs()
    if verbose:
        print(f"  loaded {len(refs)} references from {PUB_REFS_FILE.name}")

    fallback_ids = _scan_events_for_media_ids()
    if verbose:
        print(f"  scanned events dir: {len(fallback_ids)} extra media_ids recovered")

    by_asset_id: dict[str, dict] = {}
    by_media_id: dict[str, dict] = {}
    unresolved: list[dict] = []

    for r in refs:
        postiz_id = r.get("postizPostId")
        asset_id = r.get("assetId")
        channel = r.get("channel") or r.get("integrationProvider")
        if not postiz_id and not asset_id:
            continue

        # Resolve media_id: prefer canonical, fall back to events scan
        media_id = r.get("platformMediaId")
        source = "publishing-references.json"
        if not media_id and postiz_id:
            media_id = fallback_ids.get(postiz_id)
            if media_id:
                source = "events/postiz/<id>.json (fallback)"

        record = {
            "publishing_id": r.get("publishingId"),
            "asset_id": asset_id,
            "campaign_id": r.get("campaignId"),
            "postiz_post_id": postiz_id,
            "platform_media_id": media_id,
            "channel": channel,
            "current_status": r.get("currentStatus"),
            "release_url": r.get("releaseURL"),
            "published_at": r.get("publishedAt"),
            "media_id_source": source if media_id else None,
        }

        if media_id and str(media_id).isdigit():
            if asset_id:
                by_asset_id[asset_id] = record
            by_media_id[str(media_id)] = record
            if verbose:
                print(f"  ✓ asset={asset_id} media_id={media_id} status={record['current_status']}")
        else:
            unresolved.append(record)
            if verbose:
                print(f"  · asset={asset_id} status={record['current_status']} (no media_id yet)")

    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "count": len(by_media_id),
        "unresolved_count": len(unresolved),
        "by_asset_id": by_asset_id,
        "by_media_id": by_media_id,
        "unresolved": unresolved,
        "_meta": {
            "source_files": [
                str(PUB_REFS_FILE.relative_to(REPO)) if PUB_REFS_FILE.exists() else None,
                str(EVENTS_DIR.relative_to(REPO)) + "/*.json" if EVENTS_DIR.exists() else None,
            ],
            "schema_version": "1.0",
            "purpose": "asset_id → platform_media_id lookup for truth_collector.fetch_meta_engagement and /api/meta/posts/<id>/insights callers",
        },
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="Print summary, do not write index")
    p.add_argument("--verbose", "-v", action="store_true", help="Per-record output")
    args = p.parse_args()

    index = build_index(verbose=args.verbose or True)
    print()
    print(f"Summary:")
    print(f"  resolved (have platform_media_id): {index['count']}")
    print(f"  unresolved (no media_id yet):     {index['unresolved_count']}")
    if args.dry_run:
        print(f"  [dry-run] NOT writing {OUTPUT_FILE.relative_to(REPO)}")
        return 0
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(index, f, indent=2)
    print(f"  wrote: {OUTPUT_FILE.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
