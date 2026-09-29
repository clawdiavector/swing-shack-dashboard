"""
patch_brand_bible_v211.py — One-time volume patch for V2.11 brand-bible language rule.

Per operator directive (2026-09-29):
  1. Add the 'Coaching not lessons' language rule to both Swing Shack + Stick.
  2. Add the immediate-goal metrics (100 fittings/month @ 60% conversion,
     30-40 coaching sessions/week per coach) to both brands.
  3. Collapse Swing Shack's LESSONS operating_area into COACHING.

This script is idempotent — running it twice is a no-op. It writes
brand-new content only when the on-volume data file is missing the new
keys. Once all target markers are present it removes itself.

Run from: python3 /app/campaign-os/patch_brand_bible_v211.py
Safe to run on startup; fast (<50ms).
"""
from __future__ import annotations
import json
import os
import sys
from typing import Any, Dict, Tuple

DATA_DIR = os.environ.get("DATA_DIR", "/data/campaign-os")

BAKED_DIR = "/app/data"  # the Dockerfile copies the repo data/ here

LANGUAGE_RULE_COACHING = (
    "Per Swing Shack / Stick brand bible + operator directive (2026-09-29): "
    "always say 'Coaching' — never 'lesson' or 'lessons'. A coaching session "
    "is a coaching session."
)

IMMEDIATE_FITTINGS = {
    "id": "immediate_fittings_monthly",
    "label": "Fittings (immediate goal)",
    "metric": "100 fittings / month with 60% conversion rate",
    "category": "operational_throughput",
    "outcome_measurement": "PENDING",
    "connector_status": "not_connected",
    "missing_connector": "Fitting booking system not integrated with reporting",
    "marketing_support_signal": "Fitting-booking page sessions + IG/FB engagement on fitting content",
    "do_not_fabricate_progress": True,
    "source": "operator directive (Discord, 2026-09-29)",
    "set_at": "2026-09-29",
}

IMMEDIATE_COACHING_PER_COACH = {
    "id": "immediate_coaching_sessions_per_coach_per_week",
    "label": "Coaching sessions per coach (immediate goal)",
    "metric": "30–40 coaching sessions / week / coach",
    "category": "operational_throughput",
    "outcome_measurement": "PENDING",
    "connector_status": "not_connected",
    "missing_connector": "Coaching scheduling system not integrated with reporting",
    "marketing_support_signal": "Coaching-page sessions + IG/FB engagement on coach content",
    "do_not_fabricate_progress": True,
    "source": "operator directive (Discord, 2026-09-29)",
    "set_at": "2026-09-29",
}


def _resolve(brand_id: str, *parts: str) -> Tuple[str, str]:
    """Return (volume_path, baked_path) for a data file."""
    vol = os.path.join(DATA_DIR, *parts, f"{brand_id}.json")
    bak = os.path.join(BAKED_DIR, *parts, f"{brand_id}.json")
    return vol, bak


def _read(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _has_immediate_fittings(records: list) -> bool:
    return any(r.get("id") == "immediate_fittings_monthly" for r in (records or []))


def _has_immediate_coaching(records: list) -> bool:
    return any(r.get("id") == "immediate_coaching_sessions_per_coach_per_week" for r in (records or []))


def patch_swing_shack() -> bool:
    """Swing Shack planning: language rule, LESSONS→COACHING merge, immediate goals."""
    vol, bak = _resolve("swing-shack", "brand-planning")
    src = vol if os.path.exists(vol) else bak
    if not os.path.exists(src):
        print(f"[ss] source not found at {src}; skipping")
        return False
    data = _read(src)
    changed = False

    # 1) language_rules
    if not data.get("language_rules", {}).get("use_coaching_never_lesson"):
        data.setdefault("language_rules", {})
        data["language_rules"]["use_coaching_never_lesson"] = LANGUAGE_RULE_COACHING
        data["language_rules"]["coaching_subsumes_lessons"] = (
            "The historic lane 'shack-sessions' is folded into Coaching. "
            "'Lessons' survives only in historical record (calendar titles, OG social posts)."
        )
        changed = True

    # 2) Collapse LESSONS into COACHING
    areas = data.get("operating_areas") or []
    if any(a.get("key") == "LESSONS" for a in areas):
        new_areas = []
        for a in areas:
            if a.get("key") == "LESSONS":
                continue  # drop
            if a.get("key") == "COACHING":
                a["tagline"] = (
                    "TrackMan-backed sessions, real numbers — covers lessons, "
                    "packages, junior coaching, and on-course coaching"
                )
            new_areas.append(a)
        data["operating_areas"] = new_areas
        changed = True

    # 3) operating_goals (read from strategy/swing-shack.json, not planning)
    svol, sbak = _resolve("swing-shack", "strategy")
    ssrc = svol if os.path.exists(svol) else sbak
    if os.path.exists(ssrc):
        sdata = _read(ssrc)
        goals = sdata.get("operating_goals") or []
        if not _has_immediate_fittings(goals):
            goals.insert(0, dict(IMMEDIATE_FITTINGS, missing_connector="Swing Shack fitting booking system not integrated with reporting"))
            changed = True
        if not _has_immediate_coaching(goals):
            goals.insert(1 if _has_immediate_fittings(goals) else 0, dict(IMMEDIATE_COACHING_PER_COACH, missing_connector="Swing Shack coaching scheduling system not integrated with reporting"))
            changed = True
        # Rewrite the legacy "lessons" wording in the existing metrics
        for g in goals:
            if g.get("metric", "").startswith("160 lessons"):
                g["metric"] = "160 coaching sessions / month"
                changed = True
            if g.get("metric", "").startswith("20 lessons"):
                g["metric"] = "20 coaching sessions / month"
                changed = True
        if changed:
            sdata["operating_goals"] = goals
            _write(svol, sdata)
            print(f"[ss] wrote {svol}")

    if changed:
        _write(vol, data)
        print(f"[ss] wrote {vol}")
    return changed


def patch_stick() -> bool:
    """Stick north_stars: language rule + immediate goals."""
    vol = os.path.join(DATA_DIR, "brand-directory", "stick", "north_stars.json")
    bak = os.path.join(BAKED_DIR, "brand-directory", "stick", "north_stars.json")
    src = vol if os.path.exists(vol) else bak
    if not os.path.exists(src):
        print(f"[stick] source not found at {src}; skipping")
        return False
    data = _read(src)
    changed = False

    # 1) language_rules
    if not data.get("language_rules", {}).get("use_coaching_never_lesson"):
        data.setdefault("language_rules", {})
        data["language_rules"]["use_coaching_never_lesson"] = LANGUAGE_RULE_COACHING
        changed = True

    # 2) immediate goals in north_stars
    stars = data.get("north_stars") or []
    if not _has_immediate_fittings(stars):
        stars.insert(0, dict(IMMEDIATE_FITTINGS, missing_connector="Stick fitting booking system not integrated with reporting"))
        changed = True
    if not _has_immediate_coaching(stars):
        stars.insert(1 if _has_immediate_fittings(stars) else 0, dict(IMMEDIATE_COACHING_PER_COACH, missing_connector="Stick coaching scheduling system not integrated with reporting"))
        changed = True
    # Bump updated
    if changed:
        data["updated"] = "2026-09-29"
        data["source"] = "operator directive (Discord, 2026-09-22; immediate goals added 2026-09-29)"
        data["north_stars"] = stars
        _write(vol, data)
        print(f"[stick] wrote {vol}")
    return changed


def main() -> int:
    # Idempotent: skip if the v2.11 marker is already on the volume.
    marker = os.path.join(DATA_DIR, ".patches", "v211_brand_bible.applied")
    if os.path.exists(marker):
        print(f"[v2.11] already applied ({marker}); skipping")
        return 0
    ss = patch_swing_shack()
    sk = patch_stick()
    if ss or sk:
        # Write the marker so subsequent boots are no-ops.
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        with open(marker, "w") as f:
            f.write("v2.11 brand-bible language patch + immediate-goal metrics\n")
            f.write(f"applied_at={os.environ.get('RAILWAY_DEPLOYMENT_ID', 'local')}\n")
        print(f"[v2.11] patched — marker written to {marker}")
    else:
        # No-op: also write the marker so we never re-walk the data files.
        os.makedirs(os.path.dirname(marker), exist_ok=True)
        with open(marker, "w") as f:
            f.write("v2.11 brand-bible patch — already up to date\n")
        print("[v2.11] nothing to patch (already up to date)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
