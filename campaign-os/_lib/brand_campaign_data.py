"""Brand-scoped access to campaign-data.json.

WHY THIS EXISTS
---------------
`campaign-data.json` is a SINGLE shared portfolio file. Every campaign in it
carries a `brand_id` field, but that field is unreliable: data-delegation makes
every campaign point at `swing-shack` even when the campaign conceptually
belongs elsewhere (see the identical comment already in `intelligence.py`).

The CANONICAL ownership source is `data/brands.json` →
`brands.<brand_id>.campaign_ids`. `intelligence.py` already implements the
ownership lookup (`_brands_for_campaign` / `_owns_campaign`).

THE BUG THIS FIXES
------------------
`audit.py` and `portfolio.py` each loaded `campaign-data.json` with their own
private `_load_campaign_data()` that applied NO brand filter. A brand-scoped
consumer (e.g. the Stick Monday brief) therefore saw every campaign in the
portfolio — Swing Shack's Winter Golf / TrackMan Intelligence / Takomo 101T —
as its own items. The Stick brief told the operator to RETIRE three Swing
Shack campaigns.

`intelligence.py` was already correct (it filters by ownership). It just had
no reusable entry point for the other modules.

THIS MODULE
-----------
The single canonical resolver. It:
  1. loads campaign-data.json from runtime then bundled,
  2. filters campaigns by the brand's OWNERSHIP list in brands.json,
  3. filters recurring themes + content ideas by the campaigns that survived,
  4. repairs `activeCampaignId` when it points at another brand's campaign.

Brand scoping is STRICT: a brand with an empty `campaign_ids` list owns no
campaigns and therefore sees none. Unscoped access (`brand_id=None`) returns
everything, matching `intelligence._owns_campaign`.

The ownership helpers are imported from `intelligence` so there is exactly ONE
implementation of "does this brand own this campaign" in the codebase.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

# `intelligence` owns the canonical brand→campaign ownership helpers.
# It has no module-level side effects that import audit/portfolio/weekly_brief,
# so this import cannot cycle.
from intelligence import _brands_for_campaign, _owns_campaign  # noqa: E402


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _candidate_paths() -> list[Path]:
    """Runtime DATA_DIR first, then the bundled repo data dir."""
    out: list[Path] = []
    data_dir = os.environ.get("DATA_DIR", "").strip()
    if data_dir:
        out.append(Path(data_dir) / "campaign-data.json")
    out.append(_repo_root() / "data" / "campaign-data.json")
    # Bundled copy shipped inside campaign-os/ (legacy location).
    out.append(Path(__file__).resolve().parents[1] / "campaign-data.json")
    return out


def load_campaign_data_raw() -> Optional[dict]:
    """Load campaign-data.json unscoped. Returns the first file that parses."""
    for path in _candidate_paths():
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
    return None


def _scoped_active_campaign_id(raw: dict, owned: dict) -> Optional[str]:
    """Return an activeCampaignId that belongs to this brand (or None)."""
    active = raw.get("activeCampaignId")
    if active and active in owned:
        return active
    return next(iter(owned.keys()), None)


def load_campaign_data(brand_id: Optional[str] = None) -> dict:
    """Load campaign-data.json, scoped to `brand_id`.

    `brand_id=None` → unscoped: every campaign/theme/idea is returned.
    A brand with no campaigns in brands.json → empty campaigns, themes, ideas.

    The returned dict always has the shape:
        {"campaigns": {...}, "activeCampaignId": str|None,
         "recurringThemes": {...}, "ideas": [...]}
    """
    raw = load_campaign_data_raw()
    if not isinstance(raw, dict):
        raw = {"campaigns": {}, "activeCampaignId": None,
               "recurringThemes": {}, "ideas": []}

    all_campaigns = raw.get("campaigns") or {}
    all_themes = raw.get("recurringThemes") or {}
    all_ideas = raw.get("ideas") or []

    # Unscoped → everything, unchanged shape.
    if not brand_id:
        return {
            "campaigns": dict(all_campaigns),
            "activeCampaignId": raw.get("activeCampaignId"),
            "recurringThemes": dict(all_themes),
            "ideas": list(all_ideas),
        }

    # STRICT ownership: only campaigns this brand explicitly owns.
    owned = {
        cid: c for cid, c in all_campaigns.items()
        if _owns_campaign(cid, brand_id)
    }

    # recurringThemes / ideas are flat in the file. Keep only the ones that
    # reference a campaign this brand owns (or that carry no campaign link at
    # all — those are brand-agnostic and stay).
    owned_ids = set(owned.keys())

    def _theme_belongs(theme: dict) -> bool:
        ref = theme.get("campaign_id") or theme.get("campaignId")
        if not ref:
            return True  # brand-agnostic theme
        return ref in owned_ids

    def _idea_belongs(idea: dict) -> bool:
        ref = idea.get("campaign_id") or idea.get("campaignId")
        if not ref:
            return True  # brand-agnostic idea
        return ref in owned_ids

    scoped_themes = {tid: t for tid, t in all_themes.items() if _theme_belongs(t or {})}
    scoped_ideas = [i for i in all_ideas if _idea_belongs(i or {})]

    return {
        "campaigns": owned,
        "activeCampaignId": _scoped_active_campaign_id(raw, owned),
        "recurringThemes": scoped_themes,
        "ideas": scoped_ideas,
    }


def owns_campaign(campaign_id: str, brand_id: Optional[str]) -> bool:
    """True iff `brand_id` explicitly owns `campaign_id`."""
    return _owns_campaign(campaign_id, brand_id)


def brand_campaign_ids(brand_id: str) -> list:
    """The campaign_ids this brand owns (from brands.json)."""
    return list(_brands_for_campaign(brand_id))
