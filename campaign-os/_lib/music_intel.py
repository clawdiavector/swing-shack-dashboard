"""Music intelligence — data foundation (phase 2).

Which audio goes with which post, how those posts performed, and whether the
audio may be used commercially. Nothing here scores or recommends yet; it
holds the evidence honestly so later phases have something true to stand on.

Storage (per brand, so one brand's data can never reach another's):
    data/brand-directory/<brand>/music/audio.json        audio identities
    data/brand-directory/<brand>/music/post-audio.json   post -> audio links
    data/brand-directory/<brand>/music/snapshots.json    raw metric snapshots

Rules baked in:
  * Unknown is None, never a guess.
  * Licensing defaults to UNVERIFIED and only ``VERIFIED`` rows with evidence
    pass ``commercially_usable`` — public availability proves nothing.
  * Writes are idempotent on natural keys; the original source ids are kept.
  * Metric names are per platform (``METRIC_DEFINITIONS``); they are never
    summed or compared across platforms.
  * Audio is not exposed by any source this repo has verified, so links come
    from ``import_post_audio`` (a person's CSV/JSON), tagged ``source="manual"``.
"""
from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import json
import re
import statistics
from pathlib import Path
from typing import Iterable, Optional

SCHEMA = "https://campaign-os/music-intel/v1"
BRAND_DIR = Path(__file__).resolve().parents[2] / "data" / "brand-directory"

PLATFORMS = ("instagram", "facebook", "tiktok", "youtube")
SNAPSHOT_AGES_HOURS = (1, 24, 72, 168, 720)  # 1h 24h 72h 7d 30d
LICENCE_STATUSES = ("VERIFIED", "UNVERIFIED", "RESTRICTED", "EXPIRED")
USES = ("organic", "paid")

# What each platform's number actually means. Deliberately not unified.
METRIC_DEFINITIONS = {
    "instagram": {"views": "Reel views (plays + replays, current Meta definition)",
                  "reach": "Unique accounts that saw the post",
                  "likes": "likes", "comments": "comments", "shares": "shares",
                  "saves": "saves", "avg_watch_seconds": "average watch time, seconds"},
    "facebook": {"views": "Reel/video views (Meta definition, 3s+ for legacy video)",
                 "reach": "Unique accounts reached", "likes": "reactions",
                 "comments": "comments", "shares": "shares"},
    "tiktok": {"views": "video views", "likes": "likes", "comments": "comments",
               "shares": "shares", "saves": "favourites",
               "avg_watch_seconds": "average watch time, seconds"},
    "youtube": {"views": "Shorts views (YouTube definition)", "likes": "likes",
                "comments": "comments", "shares": "shares",
                "avg_watch_seconds": "averageViewDuration, seconds"},
}

_AUDIO_FIELDS = (
    "title", "artist", "original_creator", "recording_id", "source_platform",
    "source_url", "duration_seconds", "category", "identification_confidence",
    "genre", "subgenre", "mood", "energy", "bpm", "vocal", "language",
)


class MusicIntelError(ValueError):
    pass


# ── paths and json ──────────────────────────────────────────────────────

def _dir(brand: str, root: Optional[Path] = None) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", brand or ""):
        raise MusicIntelError(f"bad brand id: {brand!r}")
    return (root or BRAND_DIR) / brand / "music"


def _load(brand, name, root=None, default=None):
    p = _dir(brand, root) / name
    if not p.exists():
        return default if default is not None else []
    return json.loads(p.read_text(encoding="utf-8"))


def _save(brand, name, data, root=None):
    d = _dir(brand, root)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / (name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    tmp.replace(d / name)


# ── audio identity ──────────────────────────────────────────────────────

def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def audio_id(platform: str, platform_audio_id: Optional[str] = None,
             title: Optional[str] = None, artist: Optional[str] = None) -> str:
    """Stable internal id. A platform's own audio id wins; otherwise the
    normalised title+artist, so spelling/case variants dedupe to one row."""
    if platform_audio_id:
        key = f"{platform}:{platform_audio_id}"
    elif title:
        key = f"name:{_norm(title)}|{_norm(artist)}"
    else:
        raise MusicIntelError("need a platform audio id or a title")
    return "aud_" + hashlib.sha1(key.encode()).hexdigest()[:12]


def upsert_audio(brand: str, *, platform: str, platform_audio_id: Optional[str] = None,
                 root: Optional[Path] = None, **fields) -> dict:
    """Insert or merge. Known values are never overwritten with None, and a
    conflicting known value is kept as-is (first evidence wins; see ``conflicts``)."""
    if platform not in PLATFORMS:
        raise MusicIntelError(f"unknown platform {platform!r}")
    unknown = set(fields) - set(_AUDIO_FIELDS)
    if unknown:
        raise MusicIntelError(f"unknown audio fields: {sorted(unknown)}")
    aid = audio_id(platform, platform_audio_id, fields.get("title"), fields.get("artist"))
    rows = {r["audio_id"]: r for r in _load(brand, "audio.json", root)}
    row = rows.get(aid) or {"audio_id": aid, "licence": [], "conflicts": [],
                            "platform_ids": {}, **{f: None for f in _AUDIO_FIELDS}}
    if platform_audio_id:
        row["platform_ids"][platform] = platform_audio_id
    for k, v in fields.items():
        if v is None:
            continue
        if row.get(k) is None:
            row[k] = v
        elif row[k] != v and {"field": k, "other": v} not in row["conflicts"]:
            row["conflicts"].append({"field": k, "other": v})
    rows[aid] = row
    _save(brand, "audio.json", sorted(rows.values(), key=lambda r: r["audio_id"]), root)
    return row


# ── licensing: a hard filter, never a score ─────────────────────────────

def record_licence(brand: str, aid: str, *, platform: str, country: str, status: str,
                   organic: bool = False, paid: bool = False,
                   business_account: bool = False, provider: Optional[str] = None,
                   evidence_url: Optional[str] = None, valid_until: Optional[str] = None,
                   verified_on: Optional[str] = None, root: Optional[Path] = None) -> dict:
    if status not in LICENCE_STATUSES:
        raise MusicIntelError(f"status must be one of {LICENCE_STATUSES}")
    if status == "VERIFIED" and not (evidence_url and verified_on):
        raise MusicIntelError("VERIFIED needs evidence_url and verified_on")
    rows = {r["audio_id"]: r for r in _load(brand, "audio.json", root)}
    if aid not in rows:
        raise MusicIntelError(f"unknown audio {aid}")
    entry = {"platform": platform, "country": country, "status": status,
             "organic": organic, "paid": paid, "business_account": business_account,
             "provider": provider, "evidence_url": evidence_url,
             "valid_until": valid_until, "verified_on": verified_on}
    lic = [e for e in rows[aid]["licence"]
           if (e["platform"], e["country"]) != (platform, country)]
    rows[aid]["licence"] = lic + [entry]
    _save(brand, "audio.json", sorted(rows.values(), key=lambda r: r["audio_id"]), root)
    return entry


def commercially_usable(audio: dict, *, platform: str, country: str, use: str,
                        today: Optional[_dt.date] = None) -> tuple[bool, str]:
    """(ok, reason). Anything not positively verified for this platform,
    country and use is refused."""
    if use not in USES:
        raise MusicIntelError(f"use must be one of {USES}")
    today = today or _dt.date.today()
    for e in audio.get("licence", []):
        if e["platform"] != platform or e["country"] != country:
            continue
        if e["status"] != "VERIFIED":
            return False, f"licence is {e['status']}"
        if e["valid_until"] and _dt.date.fromisoformat(e["valid_until"]) < today:
            return False, f"licence expired {e['valid_until']}"
        if not e["business_account"]:
            return False, "not verified for business accounts"
        if not e[use]:
            return False, f"not verified for {use} use"
        return True, f"verified {e['verified_on']} ({e['evidence_url']})"
    return False, "no licence evidence for this platform and country"


def usable_audio(brand, *, platform, country, use, root=None, today=None) -> list:
    return [a for a in _load(brand, "audio.json", root)
            if commercially_usable(a, platform=platform, country=country, use=use,
                                   today=today)[0]]


# ── post -> audio links (manual until a source is verified) ─────────────

def import_post_audio(brand: str, rows: Iterable[dict], *, root: Optional[Path] = None) -> dict:
    """Rows: platform, post_id, and either audio_id or title (+artist, bpm, …).
    Idempotent on (platform, post_id): re-importing changes nothing, and a
    different audio for the same post replaces the link with the newer one."""
    links = {(r["platform"], r["post_id"]): r for r in _load(brand, "post-audio.json", root)}
    added = updated = unchanged = skipped = 0
    for raw in rows:
        r = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
        plat, pid = r.get("platform"), r.get("post_id")
        if plat not in PLATFORMS or not pid or not (r.get("title") or r.get("audio_id")):
            skipped += 1
            continue
        if r.get("audio_id"):
            aid = r["audio_id"]
        else:
            extra = {k: r[k] for k in _AUDIO_FIELDS
                     if k not in ("title", "source_platform") and r.get(k) not in (None, "")}
            if "bpm" in extra:
                extra["bpm"] = float(extra["bpm"])
            aid = upsert_audio(brand, platform=plat, root=root, title=r["title"],
                               source_platform=plat, **extra)["audio_id"]
        new = {"platform": plat, "post_id": str(pid), "audio_id": aid, "source": "manual"}
        old = links.get((plat, str(pid)))
        if old is None:
            added += 1
        elif old == new:
            unchanged += 1
            continue
        else:
            updated += 1
        links[(plat, str(pid))] = new
    _save(brand, "post-audio.json", sorted(links.values(),
          key=lambda r: (r["platform"], r["post_id"])), root)
    return {"added": added, "updated": updated, "unchanged": unchanged, "skipped": skipped}


def load_csv(path: Path) -> list:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{k: (v or None) for k, v in row.items()} for row in csv.DictReader(f)]


def worksheet(brand: str, platform: str = "instagram", *, root: Optional[Path] = None,
              audit_path: Optional[Path] = None) -> list:
    """Reels from the real audit, still missing audio, ready for a person to
    fill in. Only video posts: that is where audio is a creative choice."""
    p = audit_path or (root or BRAND_DIR) / brand / "feedback" / "instagram-audit.json"
    posts = json.loads(Path(p).read_text(encoding="utf-8")).get("posts", [])
    done = {r["post_id"] for r in _load(brand, "post-audio.json", root)
            if r["platform"] == platform}
    rows = []
    for x in posts:
        if x.get("media_type") != "VIDEO" or x["id"] in done:
            continue
        ins = x.get("insights") or {}
        rows.append({"platform": platform, "post_id": x["id"], "permalink": x.get("permalink"),
                     "published": (x.get("timestamp") or "")[:10],
                     "reach": ins.get("reach"), "views": ins.get("views"),
                     "interactions": ins.get("total_interactions"), "saves": ins.get("saved"),
                     "caption_start": " ".join((x.get("caption") or "").split())[:80],
                     "title": "", "artist": "", "bpm": ""})
    # Biggest reach first: those reels teach the most per minute spent tagging.
    return sorted(rows, key=lambda r: -(r["reach"] or 0))


# ── raw metric snapshots ────────────────────────────────────────────────

def record_snapshot(brand: str, *, platform: str, post_id: str, age_hours: int,
                    metrics: dict, observed_at: str, root: Optional[Path] = None) -> bool:
    """Store one raw observation. Returns False if it was already stored.
    Metrics outside the platform's definitions are refused rather than
    silently reinterpreted."""
    if platform not in PLATFORMS:
        raise MusicIntelError(f"unknown platform {platform!r}")
    if age_hours not in SNAPSHOT_AGES_HOURS:
        raise MusicIntelError(f"age_hours must be one of {SNAPSHOT_AGES_HOURS}")
    bad = set(metrics) - set(METRIC_DEFINITIONS[platform])
    if bad:
        raise MusicIntelError(f"{platform} has no metric(s) {sorted(bad)}")
    snaps = _load(brand, "snapshots.json", root)
    key = (platform, str(post_id), age_hours)
    if any((s["platform"], s["post_id"], s["age_hours"]) == key for s in snaps):
        return False
    snaps.append({"platform": platform, "post_id": str(post_id), "age_hours": age_hours,
                  "observed_at": observed_at, "metrics": metrics})
    _save(brand, "snapshots.json", snaps, root)
    return True


def relative_reach(brand: str, platform: str, post_id: str, *, age_hours: int = 168,
                   metric: str = "reach", baseline_n: int = 10,
                   published: Optional[dict] = None, root: Optional[Path] = None) -> dict:
    """The post's metric over the median of the account's previous
    ``baseline_n`` posts at the same age. ``published`` maps post_id -> ISO
    date. Refuses to produce a ratio from fewer than 5 baseline posts."""
    published = published or {}
    snaps = {s["post_id"]: s["metrics"].get(metric) for s in _load(brand, "snapshots.json", root)
             if s["platform"] == platform and s["age_hours"] == age_hours
             and s["metrics"].get(metric) is not None}
    if post_id not in snaps or post_id not in published:
        return {"ratio": None, "reason": "no snapshot or publish date for this post"}
    earlier = sorted((d, p) for p, d in published.items() if d < published[post_id] and p in snaps)
    base = [snaps[p] for _, p in earlier[-baseline_n:]]
    if len(base) < 5:
        return {"ratio": None, "n_baseline": len(base),
                "reason": "fewer than 5 earlier posts at the same age"}
    med = statistics.median(base)
    if med == 0:
        return {"ratio": None, "n_baseline": len(base), "reason": "baseline median is 0"}
    return {"ratio": snaps[post_id] / med, "n_baseline": len(base), "baseline_median": med}


# ── data health ─────────────────────────────────────────────────────────

def health(brand: str, platform: str = "instagram", *, root: Optional[Path] = None,
           audit_path: Optional[Path] = None) -> dict:
    """Plain facts about what the evidence base can and cannot support."""
    p = audit_path or (root or BRAND_DIR) / brand / "feedback" / "instagram-audit.json"
    videos = ([x for x in json.loads(Path(p).read_text(encoding="utf-8")).get("posts", [])
               if x.get("media_type") == "VIDEO"] if Path(p).exists() else [])
    links = [r for r in _load(brand, "post-audio.json", root) if r["platform"] == platform]
    audio = _load(brand, "audio.json", root)
    snaps = [s for s in _load(brand, "snapshots.json", root) if s["platform"] == platform]
    linked = {r["post_id"] for r in links}
    with_snap = {s["post_id"] for s in snaps}
    by_audio = {}
    for r in links:
        by_audio[r["audio_id"]] = by_audio.get(r["audio_id"], 0) + 1
    return {
        "brand": brand, "platform": platform,
        "videos_in_feed": len(videos),
        "videos_with_audio": len(linked & {v["id"] for v in videos}),
        "posts_with_audio_and_metrics": len(linked & with_snap),
        "distinct_audio": len(audio),
        "audio_used_once": sum(1 for n in by_audio.values() if n == 1),
        "audio_with_verified_licence": sum(
            1 for a in audio if any(e["status"] == "VERIFIED" for e in a["licence"])),
        "audio_missing_bpm": sum(1 for a in audio if a["bpm"] is None),
        "can_compare_audio": sum(1 for n in by_audio.values() if n >= 3) >= 2
                             and len(linked & with_snap) >= 20,
        "note": "Comparing audio needs >=20 posts with both audio and metrics and "
                ">=2 sounds used >=3 times; below that, findings would be noise.",
    }
