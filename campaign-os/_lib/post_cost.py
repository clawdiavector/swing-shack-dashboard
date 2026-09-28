"""Post-level cost ledger lines (parallel to llm_spend cap counter)."""

from __future__ import annotations

import hashlib
from typing import Any, Optional

from _lib import cost_ledger


def derive_post_cost_key(*, inbox_item_id: str, event_key: Optional[str] = None) -> str:
    """Stable post grouping key (pck-*), shared by all lines for one publishable post."""
    base = (event_key or "").strip() or (inbox_item_id or "").strip()
    if not base:
        return ""
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
    return f"pck-{digest}"


def record_line(
    *,
    usd: float,
    brand_id: str,
    kind: str,
    route: str,
    inbox_item_id: str,
    action: str,
    cost_source: str = "estimate",
    model: Optional[str] = None,
    provider: Optional[str] = None,
    event_key: Optional[str] = None,
    draft_asset_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    queue_row_id: Optional[str] = None,
    retry_of: Optional[str] = None,
    provider_job_id: Optional[str] = None,
    line_id: Optional[str] = None,
    post_cost_key: Optional[str] = None,
    day: Optional[str] = None,
) -> Optional[str]:
    """Append one cost line + refresh cached post summary. Does not touch llm_spend."""
    pck = (post_cost_key or "").strip() or derive_post_cost_key(
        inbox_item_id=inbox_item_id, event_key=event_key
    )
    if not pck:
        return None
    lid = cost_ledger.append_line(
        usd=usd,
        brand_id=brand_id,
        kind=kind,
        route=route,
        inbox_item_id=inbox_item_id,
        action=action,
        cost_source=cost_source,
        model=model,
        provider=provider,
        event_key=event_key,
        draft_asset_id=draft_asset_id,
        campaign_id=campaign_id,
        queue_row_id=queue_row_id,
        retry_of=retry_of,
        provider_job_id=provider_job_id,
        line_id=line_id,
        post_cost_key=pck,
        day=day,
    )
    if lid:
        cost_ledger.refresh_post_summary_cache(pck)
    return lid


def record_spend_and_line(
    usd: float,
    *,
    route: str,
    model: Optional[str] = None,
    kind: str = "image",
    brand_id: Optional[str] = None,
    inbox_item_id: Optional[str] = None,
    action: Optional[str] = None,
    cost_source: Optional[str] = None,
    event_key: Optional[str] = None,
    draft_asset_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    queue_row_id: Optional[str] = None,
    retry_of: Optional[str] = None,
    provider_job_id: Optional[str] = None,
    line_id: Optional[str] = None,
    post_cost_key: Optional[str] = None,
) -> dict[str, Any]:
    """llm_spend.record() then post_cost.record_line() when post context is complete."""
    from _lib import llm_spend

    st = llm_spend.record(
        usd,
        route=route,
        model=model,
        kind=kind,
        brand_id=brand_id,
    )
    if brand_id and inbox_item_id and action:
        record_line(
            usd=usd,
            brand_id=brand_id,
            kind=kind or "image",
            route=route,
            inbox_item_id=inbox_item_id,
            action=action,
            cost_source=cost_source or "estimate",
            model=model,
            event_key=event_key,
            draft_asset_id=draft_asset_id,
            campaign_id=campaign_id,
            queue_row_id=queue_row_id,
            retry_of=retry_of,
            provider_job_id=provider_job_id,
            line_id=line_id,
            post_cost_key=post_cost_key,
        )
    return st
