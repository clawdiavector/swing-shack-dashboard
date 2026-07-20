"""
Truth Collector — Stage 4 server-side module.

The Truth Collector is the ingest layer of the Performance → Learning pipeline.
It reads real analytics (GA4 + Meta) and writes append-only engagement history.
Stage 2 (evidencePack) reads the latest engagement snapshot to propose candidates.
Stage 3 (performancePromote) decides which become durable Learning truth.

SERVER-SIDE ONLY. The browser does NOT call GA4/Meta. The browser does NOT
hold credentials. The browser only reads already-persisted engagement truth
via the GET /api/engagement/<assetId> endpoint.

Credentials (read at call-time, never at boot):
- GA4: GA4_PROPERTY_ID, GA4_API_KEY (or GA4_SERVICE_ACCOUNT_JSON_PATH)
- Meta: META_APP_ID, META_APP_SECRET, META_ACCESS_TOKEN

Storage:
- Append-only file at <DATA_DIR>/engagement_history.json
- Schema: { "history": [EngagementRecord, ...], "lastRunAt": ISO8601 }

EngagementRecord shape (see §3 of Stage 4 spec):
{
  historyId: str (ulid/uuid), assetId: str, campaignId: str,
  verified: true,  # always true on success
  source: 'ga4'|'meta',
  verificationAt: ISO8601,
  capturedAt: ISO8601,  # upstream clock
  collectedAt: ISO8601,  # local clock
  collectedBy: 'truth-collector',
  collectionRunId: str (ulid/uuid),
  impressions: number|null,
  reach: number|null,
  likes: number|null,
  comments: number|null,
  shares: number|null,
  engagementRate: number|null,
  raw: dict (frozen at write),
  provenance: { source: 'truth-collector', upstreamSource, upstreamRequestId,
                postizPostId, publishedAt, chain: [...] }
}
"""
from __future__ import annotations

import json
import os
import time
import uuid
import datetime
import logging
from typing import Any, Optional

LOG = logging.getLogger("truth_collector")

# ── Constants ───────────────────────────────────────────────────────────

TRUTH_EVENT_TYPES = {
    "ENGAGEMENT_COLLECTED": "truth.engagement.collected",
    "COLLECTION_FAILED":    "truth.collection.failed",
    "COLLECTION_SKIPPED":   "truth.collection.skipped",
}

BACKOFF_SCHEDULE_S = [1, 5, 25]  # 1s, 5s, 25s
MAX_RETRIES = 3
CRON_GA4_BUDGET = 10
CRON_META_BUDGET = 10

# Failure reasons (mirrors the JS spec)
REASON_NETWORK = "network"
REASON_UPSTREAM_REJECTED = "upstream_rejected"
REASON_MALFORMED = "malformed_upstream_response"
REASON_CREDENTIALS_MISSING = "credentials_missing"
REASON_GA4_UNAUTHORIZED = "ga4_unauthorized"
REASON_META_UNAUTHORIZED = "meta_unauthorized"
REASON_GA4_RATE_LIMIT = "ga4_rate_limit"
REASON_META_RATE_LIMIT = "meta_rate_limit"

SKIP_REASONS = {
    "duplicate_capturedAt",
    "older_capturedAt",
    "asset_not_found_for_post",
    "asset_deleted",
    "campaign_deleted",
    "invalid_payload",
    "asset_status_not_collectable",
}


def _now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _ulid(prefix: str = "eh") -> str:
    """Local id generator. Not a real ulid, but unique-enough for an MVP."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _is_retryable(exc: Exception) -> bool:
    """Network errors and HTTP 5xx are retryable. 4xx (except 429) is not."""
    name = type(exc).__name__
    if name in ("Timeout", "ConnectionError", "HTTPError"):
        code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if code is None:
            return True  # raw network error
        if 500 <= code < 600:
            return True
        if code == 429:
            return True
        return False
    return False


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _with_retry(fn, max_attempts: int = MAX_RETRIES):
    """Retry fn with bounded exponential backoff. Non-retryable errors raise immediately."""
    last_exc: Optional[Exception] = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if not _is_retryable(e):
                raise
            if attempt < max_attempts - 1:
                _sleep(BACKOFF_SCHEDULE_S[attempt])
    raise last_exc  # type: ignore[misc]


# ── Storage ─────────────────────────────────────────────────────────────

class EngagementStore:
    """
    Append-only file-backed engagement history.

    Storage path: <DATA_DIR>/engagement_history.json
    Schema:
      {
        "history": [EngagementRecord, ...],
        "lastRunAt": ISO8601 | null,
        "lastSuccessAt": ISO8601 | null,
        "lastErrorAt": ISO8601 | null
      }
    """

    def __init__(self, data_dir: str):
        self.path = os.path.join(data_dir, "engagement_history.json")
        os.makedirs(data_dir, exist_ok=True)

    def _read(self) -> dict:
        if not os.path.exists(self.path):
            return {"history": [], "lastRunAt": None, "lastSuccessAt": None, "lastErrorAt": None}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "history" not in data:
                data["history"] = []
            for k in ("lastRunAt", "lastSuccessAt", "lastErrorAt"):
                data.setdefault(k, None)
            return data
        except (json.JSONDecodeError, OSError) as e:
            LOG.warning("engagement_history.json unreadable, starting fresh: %s", e)
            return {"history": [], "lastRunAt": None, "lastSuccessAt": None, "lastErrorAt": None}

    def _write(self, data: dict) -> None:
        # Write atomically: write to temp file, then rename. Avoids half-written state.
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    def all(self) -> list[dict]:
        return list(self._read()["history"])

    def for_asset(self, asset_id: str) -> list[dict]:
        return [r for r in self.all() if r.get("assetId") == asset_id]

    def latest_for_asset(self, asset_id: str) -> Optional[dict]:
        history = self.for_asset(asset_id)
        if not history:
            return None
        # History is append-only, so the last element is the latest.
        return history[-1]

    def append(self, record: dict) -> dict:
        """Append a new engagement record. Idempotent on (source, capturedAt).

        Returns:
            { ok: True, written: True, historyId } on new append
            { ok: True, written: False, reason: 'duplicate_capturedAt'|'older_capturedAt', historyId: <existing> }
            { ok: False, reason: 'invalid_record' }
        """
        # Validate required fields (§3 of Stage 4 spec)
        required = ("assetId", "campaignId", "verified", "source", "capturedAt",
                    "collectedAt", "collectedBy", "collectionRunId", "raw", "provenance")
        for f in required:
            if f not in record:
                return {"ok": False, "reason": "invalid_record", "missing": f}

        if record["verified"] is not True:
            return {"ok": False, "reason": "invalid_record", "missing": "verified"}

        if record["source"] not in ("ga4", "meta"):
            return {"ok": False, "reason": "invalid_record", "missing": "source"}

        if record["collectedBy"] != "truth-collector":
            return {"ok": False, "reason": "invalid_record", "missing": "collectedBy"}

        data = self._read()
        history = data["history"]
        asset_history = [r for r in history if r.get("assetId") == record["assetId"]]

        # Idempotency: same source + same capturedAt → skip; older → skip.
        if asset_history:
            latest = asset_history[-1]
            if latest.get("source") == record["source"] and latest.get("capturedAt") == record["capturedAt"]:
                return {"ok": True, "written": False, "reason": "duplicate_capturedAt", "historyId": latest["historyId"]}
            if latest.get("capturedAt", "") > record["capturedAt"]:
                return {"ok": True, "written": False, "reason": "older_capturedAt", "historyId": latest["historyId"]}

        # Append
        history.append(record)
        data["history"] = history
        data["lastSuccessAt"] = _now_iso()
        try:
            self._write(data)
        except OSError as e:
            return {"ok": False, "reason": "persistence_failed", "error": str(e)}

        return {"ok": True, "written": True, "historyId": record["historyId"]}

    def mark_state(self, last_run_at: Optional[str] = None,
                   last_success_at: Optional[str] = None,
                   last_error_at: Optional[str] = None) -> None:
        data = self._read()
        if last_run_at is not None:
            data["lastRunAt"] = last_run_at
        if last_success_at is not None:
            data["lastSuccessAt"] = last_success_at
        if last_error_at is not None:
            data["lastErrorAt"] = last_error_at
        try:
            self._write(data)
        except OSError as e:
            LOG.warning("Failed to write Truth Collector state: %s", e)


# ── Credentials ────────────────────────────────────────────────────────

def ga4_credentials_present() -> bool:
    """True iff GA4 credentials are configured."""
    return bool(os.environ.get("GA4_PROPERTY_ID")) and bool(
        os.environ.get("GA4_API_KEY") or os.environ.get("GA4_SERVICE_ACCOUNT_JSON_PATH")
    )


def meta_credentials_present() -> bool:
    """True iff Meta credentials are configured."""
    return bool(os.environ.get("META_APP_ID")) and bool(os.environ.get("META_APP_SECRET")) and bool(
        os.environ.get("META_ACCESS_TOKEN") or os.environ.get("META_REFRESH_TOKEN")
    )


# ── Upstream fetches (real HTTP) ───────────────────────────────────────

def fetch_ga4_engagement(asset_id: str, channel: str, captured_at: str) -> dict:
    """
    Real GA4 fetch. Returns a dict matching the EngagementRecord schema's metric block.

    Reads GA4_PROPERTY_ID and GA4_API_KEY from env. If credentials are missing,
    raises an exception with reason='credentials_missing'.

    This is a placeholder for the real GA4 Data API call (analyticsdata.googleapis.com).
    The real implementation would use the google-analytics-data Python client or
    a direct HTTP call to https://analyticsdata.googleapis.com/v1beta/properties/{id}:runReport.
    """
    if not ga4_credentials_present():
        raise CredentialsMissingError("GA4 credentials not configured")
    # Placeholder: real implementation goes here. This stub exists so the wiring is
    # truthful — it returns NO fake metrics and NO mock data. Tests that need GA4
    # behaviour either mock fetch_ga4_engagement OR run with real credentials.
    raise NotImplementedError(
        "fetch_ga4_engagement: real GA4 Data API client must be wired here. "
        "No mock metrics, no fabricated analytics. See Stage 4 spec §3 §6."
    )


def fetch_meta_engagement(asset_id: str, channel: str, captured_at: str) -> dict:
    """
    Real Meta fetch. Returns a dict matching the EngagementRecord schema's metric block.

    Reads META_APP_ID, META_APP_SECRET, META_ACCESS_TOKEN from env.
    """
    if not meta_credentials_present():
        raise CredentialsMissingError("Meta credentials not configured")
    raise NotImplementedError(
        "fetch_meta_engagement: real Meta Graph API client must be wired here. "
        "No mock metrics, no fabricated analytics. See Stage 4 spec §3 §6."
    )


class CredentialsMissingError(Exception):
    pass


class UpstreamRejectedError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)


class MalformedResponseError(Exception):
    pass


# ── Public API: the five Truth Collector functions ─────────────────────

def truth_collector_ingest_publish_event(postiz_payload: dict, store: EngagementStore) -> dict:
    """truthCollectorIngestPublishEvent(postizPayload).

    Triggered by Postiz publish webhook. Looks up the asset via postizPostId,
    fetches GA4/Meta engagement, writes via truth_collector_write_engagement.
    """
    started_at = _now_iso()
    run_id = _ulid("run")

    # 1. Validate payload
    if not isinstance(postiz_payload, dict):
        return {"ok": False, "reason": "invalid_payload"}
    post_id = postiz_payload.get("post_id")
    if not post_id or not isinstance(post_id, str):
        return {"ok": False, "reason": "invalid_payload"}
    if postiz_payload.get("status") != "published":
        return {"ok": False, "reason": "invalid_payload"}
    published_at = postiz_payload.get("published_at")
    channel = postiz_payload.get("channel")
    if not published_at or not channel:
        return {"ok": False, "reason": "invalid_payload"}

    # 2. Look up asset via postizPostId in the campaign data
    lookup = _lookup_asset_by_postiz_post_id(post_id)
    if not lookup:
        return {"ok": False, "reason": "asset_not_found_for_post", "postId": post_id}
    asset_id, campaign_id = lookup

    # 3. Fetch with retry
    try:
        record = _fetch_and_build_record(
            asset_id=asset_id,
            campaign_id=campaign_id,
            channel=channel,
            captured_at=published_at,
            run_id=run_id,
            postiz_post_id=post_id,
        )
    except CredentialsMissingError:
        return {"ok": False, "reason": REASON_CREDENTIALS_MISSING, "postId": post_id, "assetId": asset_id}
    except UpstreamRejectedError as e:
        reason = REASON_GA4_UNAUTHORIZED if channel.startswith("ga4") else REASON_META_UNAUTHORIZED
        if e.status_code == 429:
            reason = REASON_GA4_RATE_LIMIT if channel.startswith("ga4") else REASON_META_RATE_LIMIT
        return {"ok": False, "reason": reason, "postId": post_id, "assetId": asset_id}
    except MalformedResponseError:
        return {"ok": False, "reason": REASON_MALFORMED, "postId": post_id, "assetId": asset_id}
    except Exception:  # noqa: BLE001
        return {"ok": False, "reason": REASON_NETWORK, "postId": post_id, "assetId": asset_id}

    # 4. Write (idempotent)
    result = store.append(record)
    if not result["ok"]:
        return {"ok": False, "reason": result.get("reason", "persistence_failed"), "postId": post_id, "assetId": asset_id}
    if not result["written"]:
        return {"ok": True, "postId": post_id, "assetId": asset_id, "skipped": True,
                "reason": result["reason"], "historyId": result["historyId"]}

    return {"ok": True, "postId": post_id, "assetId": asset_id, "historyId": result["historyId"],
            "engagementRef": {"assetId": asset_id, "historyId": result["historyId"], "capturedAt": record["capturedAt"]},
            "startedAt": started_at, "completedAt": _now_iso()}


def truth_collector_ingest_cron_tick(store: EngagementStore, campaign_data: dict) -> dict:
    """truthCollectorIngestCronTick().

    Iterates all published assets across all campaigns. Idempotent per-asset.
    Rate-limited (10 GA4 + 10 Meta calls per tick).
    """
    started_at = _now_iso()
    scanned = 0
    written = 0
    skipped = 0
    failed = 0
    ga4_used = 0
    meta_used = 0
    aborted = False
    abort_reason = None

    store.mark_state(last_run_at=started_at)

    for campaign_id, campaign in (campaign_data.get("campaigns") or {}).items():
        identity = campaign.get("identity") or {}
        if identity.get("status") in ("cancelled", "archived"):
            continue
        for ch in campaign.get("channels", []) or []:
            platform = ch.get("platform", "")
            if not platform:
                continue
            for item in ch.get("plannedItems", []) or []:
                if not item.get("publishedAt"):
                    continue
                postiz_post_id = item.get("postizPostId")
                asset_ref = item.get("asset") or {}
                asset_id = asset_ref.get("id") if isinstance(asset_ref, dict) else None
                if not asset_id:
                    continue
                scanned += 1
                # Rate limit
                if platform.startswith("instagram") or platform in ("facebook", "meta"):
                    if meta_used >= CRON_META_BUDGET:
                        skipped += 1
                        continue
                else:
                    if ga4_used >= CRON_GA4_BUDGET:
                        skipped += 1
                        continue

                run_id = _ulid("run")
                try:
                    record = _fetch_and_build_record(
                        asset_id=asset_id,
                        campaign_id=campaign_id,
                        channel=platform,
                        captured_at=item["publishedAt"],
                        run_id=run_id,
                        postiz_post_id=postiz_post_id,
                    )
                except CredentialsMissingError:
                    failed += 1
                    continue
                except UpstreamRejectedError:
                    failed += 1
                    continue
                except MalformedResponseError:
                    failed += 1
                    continue
                except Exception:  # noqa: BLE001
                    failed += 1
                    continue

                result = store.append(record)
                if not result["ok"]:
                    failed += 1
                    if result.get("reason") == "persistence_failed":
                        aborted = True
                        abort_reason = "quota_exceeded"
                        break
                elif result["written"]:
                    written += 1
                    if platform.startswith("instagram") or platform in ("facebook", "meta"):
                        meta_used += 1
                    else:
                        ga4_used += 1
                else:
                    skipped += 1
            if aborted:
                break
        if aborted:
            break

    completed_at = _now_iso()
    if failed > 0:
        store.mark_state(last_error_at=completed_at)
    if written > 0:
        store.mark_state(last_success_at=completed_at)

    return {
        "ok": not aborted,
        "aborted": aborted,
        "reason": abort_reason,
        "scanned": scanned,
        "written": written,
        "skipped": skipped,
        "failed": failed,
        "startedAt": started_at,
        "completedAt": completed_at,
    }


def truth_collector_ingest_manual_trigger(campaign_id: str, store: EngagementStore, campaign_data: dict) -> dict:
    """truthCollectorIngestManualTrigger(campaignId)."""
    campaigns = campaign_data.get("campaigns") or {}
    if campaign_id not in campaigns:
        return {"ok": False, "campaignId": campaign_id, "reason": "invalid_campaign"}
    identity = campaigns[campaign_id].get("identity") or {}
    if identity.get("status") in ("cancelled", "archived"):
        return {"ok": False, "campaignId": campaign_id, "reason": identity.get("status")}

    scanned = 0
    written = 0
    skipped = 0
    failed = 0
    started_at = _now_iso()

    campaign = campaigns[campaign_id]
    for ch in campaign.get("channels", []) or []:
        platform = ch.get("platform", "")
        if not platform:
            continue
        for item in ch.get("plannedItems", []) or []:
            if not item.get("publishedAt"):
                continue
            asset_ref = item.get("asset") or {}
            asset_id = asset_ref.get("id") if isinstance(asset_ref, dict) else None
            if not asset_id:
                continue
            scanned += 1
            run_id = _ulid("run")
            try:
                record = _fetch_and_build_record(
                    asset_id=asset_id,
                    campaign_id=campaign_id,
                    channel=platform,
                    captured_at=item["publishedAt"],
                    run_id=run_id,
                    postiz_post_id=item.get("postizPostId"),
                )
            except Exception:  # noqa: BLE001
                failed += 1
                continue
            result = store.append(record)
            if not result["ok"]:
                failed += 1
            elif result["written"]:
                written += 1
            else:
                skipped += 1

    return {
        "ok": True,
        "campaignId": campaign_id,
        "scanned": scanned,
        "written": written,
        "skipped": skipped,
        "failed": failed,
        "startedAt": started_at,
        "completedAt": _now_iso(),
    }


def truth_collector_write_engagement(asset_id: str, engagement_record: dict, store: EngagementStore) -> dict:
    """truthCollectorWriteEngagement(assetId, engagementRecord).

    The single write path. Validates, applies idempotency, appends.
    """
    return store.append(engagement_record)


def truth_collector_get_engagement_history(asset_id: str, store: EngagementStore) -> Optional[list]:
    """truthCollectorGetEngagementHistory(assetId).

    Returns a list of engagement records for the asset, or None if the asset
    has no history. The returned list is a fresh copy (safe to return to callers).
    """
    history = store.for_asset(asset_id)
    return history if history else None


# ── Internal helpers ───────────────────────────────────────────────────

def _lookup_asset_by_postiz_post_id(postiz_post_id: str) -> Optional[tuple]:
    """Look up (assetId, campaignId) by postizPostId in the campaign data.

    Reads DATA_DIR/campaign-data.json. Returns None if not found or if file
    is missing/malformed.
    """
    data_dir = os.environ.get("DATA_DIR", "/data")
    campaign_file = os.path.join(data_dir, "campaign-data.json")
    if not os.path.exists(campaign_file):
        return None
    try:
        with open(campaign_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    for campaign_id, campaign in (data.get("campaigns") or {}).items():
        for ch in campaign.get("channels", []) or []:
            for item in ch.get("plannedItems", []) or []:
                if item.get("postizPostId") == postiz_post_id:
                    asset_ref = item.get("asset") or {}
                    if isinstance(asset_ref, dict):
                        asset_id = asset_ref.get("id")
                        if asset_id:
                            return (asset_id, campaign_id)
    return None


def _fetch_and_build_record(asset_id: str, campaign_id: str, channel: str,
                            captured_at: str, run_id: str, postiz_post_id: Optional[str]) -> dict:
    """
    Fetch upstream engagement with retry, build the canonical EngagementRecord.
    Raises CredentialsMissingError, UpstreamRejectedError, MalformedResponseError,
    or generic Exception for retryable network failures.
    """
    captured_at_iso = captured_at  # upstream-supplied timestamp

    def do_fetch():
        # Choose fetcher by channel
        if channel in ("instagram", "facebook", "meta"):
            return fetch_meta_engagement(asset_id, channel, captured_at_iso)
        # Default: GA4 (tiktok, youtube, gmb, x, linkedin, web)
        return fetch_ga4_engagement(asset_id, channel, captured_at_iso)

    metrics = _with_retry(do_fetch)
    if not isinstance(metrics, dict):
        raise MalformedResponseError("upstream returned non-dict metrics")

    # Build canonical record (matches Stage 4 §3 schema)
    now = _now_iso()
    record = {
        "historyId": _ulid("eh"),
        "assetId": asset_id,
        "campaignId": campaign_id,
        "verified": True,
        "source": "meta" if channel in ("instagram", "facebook", "meta") else "ga4",
        "verificationAt": now,
        "verificationError": None,
        "capturedAt": captured_at_iso,
        "collectedAt": now,
        "collectedBy": "truth-collector",
        "collectionRunId": run_id,
        "impressions": metrics.get("impressions"),
        "reach": metrics.get("reach"),
        "likes": metrics.get("likes"),
        "comments": metrics.get("comments"),
        "shares": metrics.get("shares"),
        "engagementRate": metrics.get("engagementRate"),
        "raw": metrics,
        "provenance": {
            "source": "truth-collector",
            "upstreamSource": "meta" if channel in ("instagram", "facebook", "meta") else "ga4",
            "upstreamRequestId": metrics.get("_request_id"),
            "postizPostId": postiz_post_id,
            "publishedAt": captured_at_iso,
            "chain": ["truth-collector", "ga4" if channel not in ("instagram", "facebook", "meta") else "meta"],
        },
    }
    return record
