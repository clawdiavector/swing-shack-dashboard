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

import datetime
import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
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

def _read_meta_access_token() -> Optional[str]:
    """
    Resolve the Meta access token from (in order):
      1. META_ACCESS_TOKEN_FILE  — JSON file with {"access_token": "..."}
      2. META_ACCESS_TOKEN       — raw env value
      3. META_REFRESH_TOKEN      — present flag only (server-side refresh
         not implemented in this stage; we will not silently invent a token)

    Returns the token string, or None if no usable source exists.
    Never raises — caller decides how to treat absence.
    """
    from_file = os.environ.get("META_ACCESS_TOKEN_FILE")
    if from_file and from_file.strip():
        try:
            with open(from_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            tok = data.get("access_token")
            if isinstance(tok, str) and tok.strip():
                return tok.strip()
        except (OSError, json.JSONDecodeError):
            pass  # fall through to env
    raw = os.environ.get("META_ACCESS_TOKEN")
    if raw and raw.strip():
        return raw.strip()
    if os.environ.get("META_REFRESH_TOKEN"):
        # Presence-only acknowledgement. A refresh flow is a future step.
        # We do NOT silently fabricate an access token here.
        pass
    return None


def ga4_credentials_present() -> bool:
    """True iff GA4 credentials are configured."""
    return bool(os.environ.get("GA4_PROPERTY_ID")) and bool(
        os.environ.get("GA4_API_KEY") or os.environ.get("GA4_SERVICE_ACCOUNT_JSON_PATH")
    )


def meta_credentials_present() -> bool:
    """True iff Meta credentials are configured.

    Read-only path requirement (Step 76):
      - META_APP_ID is set
      - META_ACCESS_TOKEN_FILE points to a readable JSON file with a
        non-empty access_token field, OR META_ACCESS_TOKEN env var is set

    META_APP_SECRET is NOT required for the current read-only Graph API
    path. The 60-day long-lived Page Access Token already validated
    (Step 75 probes) carries its own validity window. App Secret is
    only needed at token exchange / refresh time — that path will be
    added in a future step (before the 2026-08-29 expiry).
    """
    if not os.environ.get("META_APP_ID"):
        return False
    return _read_meta_access_token() is not None


# ── Upstream fetches (real HTTP) ───────────────────────────────────────

def fetch_ga4_engagement(asset_id: str, channel: str, captured_at: str) -> dict:
    """
    Real GA4 fetch. Returns a dict matching the EngagementRecord schema's metric block.

    Reads GA4_PROPERTY_ID + (GA4_SERVICE_ACCOUNT_JSON_PATH | GA4_API_KEY) from env.
    Uses service-account OAuth2 token-exchange for the read-only Analytics Data API.
    Preserves the raw upstream response in `raw` for provenance.

    Supported fields (per Stage 4 §3):
      impressions, reach, engagementRate (numeric; null when unavailable;
      0 only when upstream explicitly reports zero — no inference, no defaults).

    Note: GA4 is a *website* analytics product. It does not report likes,
    comments, or shares. For asset-level Instagram/Facebook engagement,
    use fetch_meta_engagement(). This function returns None for those fields.
    """
    if not ga4_credentials_present():
        raise CredentialsMissingError("GA4 credentials not configured")

    property_id = os.environ.get("GA4_PROPERTY_ID", "").strip()
    sa_path = os.environ.get("GA4_SERVICE_ACCOUNT_JSON_PATH", "").strip()
    api_key = os.environ.get("GA4_API_KEY", "").strip()

    # ── Obtain bearer token ─────────────────────────────────────────────
    # Service-account path is the supported one (GA4_API_KEY is the legacy
    # Universal Analytics path; we attempt it but most modern GA4 setups
    # use service accounts).
    bearer = None
    if sa_path:
        try:
            from google.oauth2 import service_account as _sa  # noqa: WPS433
            from google.auth.transport.requests import Request as _GRequest  # noqa: WPS433
        except ImportError as e:
            raise UpstreamRejectedError(
                0,
                f"google-auth library not installed ({e}). Run: uv pip install -r requirements.txt",
            )
        try:
            with open(sa_path, "r", encoding="utf-8") as f:
                sa_info = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise CredentialsMissingError(f"GA4_SERVICE_ACCOUNT_JSON_PATH unreadable: {e}")
        scopes = ["https://www.googleapis.com/auth/analytics.readonly"]
        try:
            creds = _sa.Credentials.from_service_account_info(sa_info, scopes=scopes)
            creds.refresh(_GRequest())
            bearer = creds.token
        except Exception as e:
            raise UpstreamRejectedError(0, f"GA4 OAuth token-exchange failed: {e}")

    if not bearer and api_key:
        # Legacy API-key path. GA4 Data API does NOT support ?key= — this
        # path is reserved for the older Universal Analytics Reporting API.
        # We surface a truthful error so the operator knows to switch.
        raise UpstreamRejectedError(
            0,
            "GA4_API_KEY is set but GA4 Data API requires service-account auth. "
            "Use GA4_SERVICE_ACCOUNT_JSON_PATH instead.",
        )

    if not bearer:
        raise CredentialsMissingError("GA4 bearer token could not be obtained")

    # ── Query Analytics Data API ───────────────────────────────────────
    # Asset-level GA4 mapping is intentionally NOT invented here.
    # GA4 reports per-page or per-session, not per-social-post. The caller
    # passes asset_id + captured_at, but we request the property aggregate
    # for the captured_at day. The assetId is preserved in the provenance
    # chain, not in the upstream query.
    try:
        day = captured_at[:10]  # YYYY-MM-DD
    except (TypeError, ValueError):
        raise MalformedResponseError(f"captured_at not parseable as ISO date: {captured_at!r}")

    body = json.dumps({
        "dateRanges": [{"startDate": day, "endDate": day}],
        "metrics": [
            {"name": "sessions"},
            {"name": "totalUsers"},
            {"name": "screenPageViews"},
            {"name": "engagementRate"},
        ],
    }).encode("utf-8")

    url = f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport"
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {bearer}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_text = resp.read().decode("utf-8")
            raw = json.loads(raw_text)
            request_id = resp.headers.get("x-request-id") or resp.headers.get("X-Request-Id")
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8", errors="replace")[:400]
        if e.code in (401, 403):
            raise UpstreamRejectedError(e.code, f"GA4 unauthorized ({e.code}): {body_err}")
        if e.code == 429:
            raise UpstreamRejectedError(e.code, f"GA4 rate-limited: {body_err}")
        if 500 <= e.code < 600:
            raise  # retryable — let _with_retry handle
        raise UpstreamRejectedError(e.code, f"GA4 upstream error ({e.code}): {body_err}")
    except urllib.error.URLError as e:
        raise  # retryable

    # ── Map response ────────────────────────────────────────────────────
    # GA4 returns rows[].metricValues[].value as strings. Schema-validate
    # before parsing — malformed upstream is the truth-collector's call.
    try:
        rows = raw.get("rows", []) or []
    except AttributeError:
        raise MalformedResponseError(f"GA4 response not a dict: {raw_text[:200]}")

    sessions: Optional[int] = None
    users: Optional[int] = None
    pageviews: Optional[int] = None
    eng_rate: Optional[float] = None
    for row in rows:
        try:
            mv = row["metricValues"]
            s = int(mv[0]["value"]) if len(mv) > 0 and mv[0]["value"] not in (None, "") else None
            u = int(mv[1]["value"]) if len(mv) > 1 and mv[1]["value"] not in (None, "") else None
            pv = int(mv[2]["value"]) if len(mv) > 2 and mv[2]["value"] not in (None, "") else None
            er = float(mv[3]["value"]) if len(mv) > 3 and mv[3]["value"] not in (None, "") else None
        except (KeyError, IndexError, ValueError, TypeError) as e:
            raise MalformedResponseError(f"GA4 row malformed: {e}")

        # Sum across all rows (date dimension is single — should be 1 row)
        sessions = (sessions or 0) + (s or 0)
        users = (users or 0) + (u or 0)
        pageviews = (pageviews or 0) + (pv or 0)
        # engagementRate is a ratio, sum-and-divide would be wrong; average instead
        if eng_rate is None and er is not None:
            eng_rate = er
        elif eng_rate is not None and er is not None:
            eng_rate = (eng_rate + er) / 2  # simple average over rows

    # Build canonical EngagementRecord-shaped metric block.
    # NOTE: GA4 reports impressions-equivalent as sessions, reach as users,
    # and engagement as a rate. likes/comments/shares are NOT GA4 metrics —
    # they remain None (truthful absence, not zero).
    metrics = {
        "impressions": pageviews,        # GA4 closest analogue
        "reach": users if users and users > 0 else sessions,
        "likes": None,
        "comments": None,
        "shares": None,
        "engagementRate": eng_rate,
        "_request_id": request_id,
        # Preserve raw upstream + provenance for forensic / replay.
        "raw": raw,
    }

    return metrics


def fetch_meta_engagement(
    asset_id: str,
    channel: str,
    captured_at: str,
    platform_media_id: Optional[str] = None,
) -> dict:
    """
    Real Meta fetch. Returns a dict matching the EngagementRecord schema's metric block.

    Reads META_APP_ID + (META_ACCESS_TOKEN_FILE | META_ACCESS_TOKEN) from env.
    Uses the Graph API to read Instagram Business media insights.

    Supported fields (per Stage 4 §3):
      reach, likes, comments, shares, saved, engagementRate (numeric; null
      when unavailable; 0 only when upstream explicitly reports zero — no
      inference, no defaults).

    Step 80 Stage 3 — platform_media_id contract:
      When platform_media_id is provided, the fetcher makes a real Graph API
      call against that media ID. When platform_media_id is None, the fetcher
      returns the existing truthful MAPPING_BLOCKED response (no upstream call,
      no fabrication). This preserves backward compatibility — existing callers
      that don't supply a media_id see no behaviour change.

    Truth-before-cleverness: This fetcher does NOT invent a mapping from
    asset_id → Instagram media_id. The caller MUST supply a real
    platform_media_id. If we cannot resolve a real media_id, we return
    metrics with all-Null fields and a provenance note — never zeros, never
    inferred numbers.
    """
    if not meta_credentials_present():
        raise CredentialsMissingError("Meta credentials not configured")

    token = _read_meta_access_token()
    ig_account_id = os.environ.get("META_INSTAGRAM_BUSINESS_ACCOUNT_ID", "").strip()
    page_id = os.environ.get("META_PAGE_ID", "").strip()

    # Step 80 Stage 3 — when platform_media_id is provided, make a real Graph
    # API call. When None, return the truthful MAPPING_BLOCKED response (no
    # upstream call, no fabrication). Provider-specific dispatch by channel.
    if not platform_media_id:
        # Truthful absence: without a media_id we cannot call /insights.
        # We do NOT guess. We do NOT default to the latest media.
        return {
            "impressions": None,
            "reach": None,
            "likes": None,
            "comments": None,
            "shares": None,
            "saved": None,
            "engagementRate": None,
            "_request_id": None,
            "raw": {
                "reason": "no_media_id_resolved",
                "note": "fetch_meta_engagement requires a real platform_media_id. "
                        "Until the upstream lookup or caller supplies one, no upstream "
                        "call is made and no metrics are fabricated.",
                "ig_account_id": ig_account_id or None,
                "page_id": page_id or None,
                "asset_id": asset_id,
                "channel": channel,
                "captured_at": captured_at,
            },
        }

    # ── Real Graph API call ────────────────────────────────────────────
    # Provider-specific dispatch by channel. Each branch validates the media_id
    # shape (Instagram: numeric, Facebook: page-scoped id) and constructs the
    # appropriate Graph API request. Errors surface as UpstreamRejectedError
    # (non-retryable 4xx) or MalformedResponseError (cannot parse).
    channel_lower = (channel or "").lower()

    if channel_lower == "instagram":
        # Instagram media_id must be numeric (Graph API contract).
        if not platform_media_id.isdigit():
            raise MalformedResponseError(
                f"Instagram platform_media_id must be numeric, got: {platform_media_id!r}"
            )
        # GET /{ig-media-id}/insights?metric=reach,likes,comments,shares,saved
        # (engagementRate derived client-side from the four counts)
        url = (
            f"https://graph.facebook.com/v18.0/{platform_media_id}/insights"
            f"?metric=reach,likes,comments,shares,saved"
        )
        try:
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw_text = resp.read().decode("utf-8")
                raw = json.loads(raw_text)
                request_id = resp.headers.get("x-request-id") or resp.headers.get("X-Request-Id")
        except urllib.error.HTTPError as e:
            body_err = e.read().decode("utf-8", errors="replace")[:400]
            if e.code in (401, 403):
                raise UpstreamRejectedError(e.code, f"Meta unauthorized ({e.code}): {body_err}")
            if e.code == 429:
                raise UpstreamRejectedError(e.code, f"Meta rate-limited: {body_err}")
            if 500 <= e.code < 600:
                raise  # retryable — let _with_retry handle
            raise UpstreamRejectedError(e.code, f"Meta upstream error ({e.code}): {body_err}")
        except urllib.error.URLError:
            raise  # retryable

        # Parse insights response. Graph returns
        # {"data": [{"name": "reach", "period": "lifetime", "values": [{"value": N}]}, ...]}
        try:
            data_list = raw.get("data", []) or []
        except AttributeError:
            raise MalformedResponseError(f"Meta insights response not a dict: {raw_text[:200]}")

        def _metric(name):
            for entry in data_list:
                if entry.get("name") == name:
                    values = entry.get("values") or []
                    if values:
                        return values[0].get("value")
            return None

        reach = _metric("reach")
        likes = _metric("likes")
        comments = _metric("comments")
        shares = _metric("shares")
        saved = _metric("saved")

        # engagementRate = (likes + comments + shares + saved) / reach.
        # Only compute when reach is positive (avoid divide-by-zero + never
        # invent a ratio from zero reach).
        eng_rate: Optional[float] = None
        if reach and reach > 0:
            counts = [c for c in (likes, comments, shares, saved) if c is not None]
            if counts:
                eng_rate = sum(counts) / reach

        return {
            "impressions": reach,  # IG /insights has no impressions field; reach is the closest analogue
            "reach": reach,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "saved": saved,
            "engagementRate": eng_rate,
            "_request_id": request_id,
            "raw": raw,
        }

    if channel_lower == "facebook":
        # Facebook post id is page-scoped: {page-id}_{post-id}. Verify the
        # post exists by GET /{post-id}?fields=id,permalink_url
        if page_id and not platform_media_id.startswith(f"{page_id}_"):
            raise MalformedResponseError(
                f"Facebook platform_media_id {platform_media_id!r} does not start "
                f"with expected page_id prefix {page_id!r}"
            )
        url = (
            f"https://graph.facebook.com/v18.0/{platform_media_id}"
            f"?fields=id,permalink_url"
        )
        try:
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw_text = resp.read().decode("utf-8")
                raw = json.loads(raw_text)
                request_id = resp.headers.get("x-request-id") or resp.headers.get("X-Request-Id")
        except urllib.error.HTTPError as e:
            body_err = e.read().decode("utf-8", errors="replace")[:400]
            if e.code in (401, 403):
                raise UpstreamRejectedError(e.code, f"Meta unauthorized ({e.code}): {body_err}")
            if e.code == 429:
                raise UpstreamRejectedError(e.code, f"Meta rate-limited: {body_err}")
            if 500 <= e.code < 600:
                raise  # retryable
            raise UpstreamRejectedError(e.code, f"Meta upstream error ({e.code}): {body_err}")
        except urllib.error.URLError:
            raise  # retryable

        # Verification only. Facebook post metrics require different /insights
        # endpoints that depend on post type; for now we verify existence
        # truthfully and return None for engagement counters (no fabrication).
        return {
            "impressions": None,
            "reach": None,
            "likes": None,
            "comments": None,
            "shares": None,
            "saved": None,
            "engagementRate": None,
            "_request_id": request_id,
            "raw": {
                "verified": bool(raw.get("id")),
                "permalink_url": raw.get("permalink_url"),
                "note": "Facebook post verified. Engagement counters require type-specific "
                        "Graph API endpoints; deferred to Stage 5.",
            },
        }

    # GMB and TikTok — no IG/FB equivalent. Return truthful MAPPING_BLOCKED.
    return {
        "impressions": None,
        "reach": None,
        "likes": None,
        "comments": None,
        "shares": None,
        "saved": None,
        "engagementRate": None,
        "_request_id": None,
        "raw": {
            "reason": "channel_no_meta_equivalent",
            "note": f"channel={channel!r} has no Meta-equivalent Graph API endpoint. "
                    f"TikTok deferred; GMB uses Google Business API (not Meta).",
            "asset_id": asset_id,
            "channel": channel,
            "platform_media_id": platform_media_id,
            "captured_at": captured_at,
        },
    }


class CredentialsMissingError(Exception):
    pass


class UpstreamRejectedError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)


class MalformedResponseError(Exception):
    pass


# ── Step 80 Stage 3 — Lookup bridge ─────────────────────────────────
# These exceptions signal that the lookup bridge is in a state where the
# caller should NOT proceed with a real upstream call. IndexStale means the
# generated index is out of sync with canonical (defense-in-depth — publisher
# auto-regens, so this should never fire in normal operation). FixtureIdRejected
# means a cmFIXTURE* post ID reached production paths — fail loud, do not
# silently accept.
class IndexStale(Exception):
    def __init__(self, message: str, canonical_sha: Optional[str] = None,
                 index_sha: Optional[str] = None):
        self.canonical_sha = canonical_sha
        self.index_sha = index_sha
        super().__init__(message)


class FixtureIdRejected(Exception):
    def __init__(self, post_id: str):
        self.post_id = post_id
        super().__init__(
            f"Fixture post id {post_id!r} (cmFIXTURE* prefix) rejected. "
            f"Fixture IDs must never enter production paths."
        )


# ── Public API: the five Truth Collector functions ─────────────────────

def truth_collector_ingest_publish_event(postiz_payload: dict, store: EngagementStore) -> dict:
    """truthCollectorIngestPublishEvent(postizPayload).

    Triggered by Postiz publish webhook. Looks up the asset via postizPostId,
    fetches GA4/Meta engagement, writes via truth_collector_write_engagement.

    Step 80 Stage 3 — the lookup now reads data/publishing-references.json
    (regenerated by the publisher after every successful canonical write).
    platform_media_id flows through to fetch_meta_engagement when the channel
    is instagram/facebook/meta.
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

    # 2. Look up asset via postizPostId in the publishing-references index.
    #    Returns dict or None. Raises IndexStale / FixtureIdRejected.
    try:
        ref = _lookup_asset_by_postiz_post_id(post_id)
    except IndexStale as e:
        return {"ok": False, "reason": "index_stale", "postId": post_id, "detail": str(e)}
    except FixtureIdRejected as e:
        return {"ok": False, "reason": "fixture_id_rejected", "postId": post_id}
    if not ref:
        return {"ok": False, "reason": "asset_not_found_for_post", "postId": post_id}
    asset_id = ref["assetId"]
    campaign_id = ref["campaignId"]
    platform_media_id = ref.get("platformMediaId")

    # 3. Fetch with retry
    try:
        record = _fetch_and_build_record(
            asset_id=asset_id,
            campaign_id=campaign_id,
            channel=channel,
            captured_at=published_at,
            run_id=run_id,
            postiz_post_id=post_id,
            platform_media_id=platform_media_id,
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
                # Resolve platform_media_id from the regenerated publishing
                # references index (Step 80 Stage 3). Lookup may raise
                # IndexStale or FixtureIdRejected — both bubble up.
                platform_media_id = None
                if postiz_post_id:
                    try:
                        ref = _lookup_asset_by_postiz_post_id(postiz_post_id)
                    except (IndexStale, FixtureIdRejected):
                        failed += 1
                        continue
                    if ref:
                        platform_media_id = ref.get("platformMediaId")
                try:
                    record = _fetch_and_build_record(
                        asset_id=asset_id,
                        campaign_id=campaign_id,
                        channel=platform,
                        captured_at=item["publishedAt"],
                        run_id=run_id,
                        postiz_post_id=postiz_post_id,
                        platform_media_id=platform_media_id,
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
            # Resolve platform_media_id from the regenerated publishing
            # references index (Step 80 Stage 3).
            platform_media_id = None
            postiz_post_id = item.get("postizPostId")
            if postiz_post_id:
                try:
                    ref = _lookup_asset_by_postiz_post_id(postiz_post_id)
                except (IndexStale, FixtureIdRejected):
                    failed += 1
                    continue
                if ref:
                    platform_media_id = ref.get("platformMediaId")
            try:
                record = _fetch_and_build_record(
                    asset_id=asset_id,
                    campaign_id=campaign_id,
                    channel=platform,
                    captured_at=item["publishedAt"],
                    run_id=run_id,
                    postiz_post_id=postiz_post_id,
                    platform_media_id=platform_media_id,
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

def _lookup_asset_by_postiz_post_id(postiz_post_id: str) -> Optional[dict]:
    """Look up a publishing reference by postizPostId.

    Step 80 Stage 3 — reads data/publishing-references.json (generated by
    the publisher after every canonical write). Validates freshness by
    comparing data/state.json.canonicalSha256 against
    data/publishing-references.json.sourceCampaignSha256.

    Returns a dict of shape:
      {assetId, campaignId, integrationId, channel, platformMediaId,
       currentStatus, createdAt, rawResponseRefHash}

    Raises:
      IndexStale      — when state.json and index hash disagree
      FixtureIdRejected — when postiz_post_id starts with cmFIXTURE
    Returns None when the index is missing, malformed, or postiz_post_id
    is not present in the index.
    """
    # Fixture protection — fail loud. cmFIXTURE* must never enter production.
    if postiz_post_id and postiz_post_id.startswith("cmFIXTURE"):
        raise FixtureIdRejected(postiz_post_id)

    # Resolve paths. Default to <repo>/data/ for dev, $DATA_DIR/data/ for prod.
    data_dir = os.environ.get("DATA_DIR", "/data")
    if data_dir == "/data":
        # Dev fallback: repo-relative
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(repo_root, "data")

    index_path = os.path.join(data_dir, "publishing-references.json")
    state_path = os.path.join(data_dir, "state.json")

    # Freshness check — if state.json is missing, we cannot validate; skip
    # the check rather than block. The publisher auto-regens both files
    # together, so in normal operation they stay in sync.
    state = None
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError):
            state = None  # malformed state — skip check

    # Read the index.
    if not os.path.exists(index_path):
        return None
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    # Freshness validation: state.canonicalSha256 must equal index.sourceCampaignSha256.
    # Both are SHA-256 of the canonical FILE BYTES (per regenerate-publishing-index.js).
    if state and isinstance(state, dict):
        canonical_sha = state.get("canonicalSha256")
        index_sha = index.get("sourceCampaignSha256")
        if canonical_sha and index_sha and canonical_sha != index_sha:
            raise IndexStale(
                f"publishing-references.json out of sync with canonical: "
                f"index.sourceCampaignSha256={index_sha!r} != "
                f"state.canonicalSha256={canonical_sha!r}. "
                f"Run scripts/regenerate-publishing-index.js to rebuild.",
                canonical_sha=canonical_sha,
                index_sha=index_sha,
            )

    # Walk references, find the one with matching postizPostId.
    for ref in (index.get("references") or []):
        if ref.get("postizPostId") == postiz_post_id:
            return {
                "assetId": ref.get("assetId"),
                "campaignId": ref.get("campaignId"),
                "integrationId": ref.get("integrationId"),
                "channel": ref.get("channel"),
                "platformMediaId": ref.get("platformMediaId"),
                "currentStatus": ref.get("currentStatus"),
                "createdAt": ref.get("createdAt"),
                "rawResponseRefHash": (
                    (ref.get("provenance") or {}).get("rawResponseRef") or {}
                ).get("hash"),
            }
    return None


def _fetch_and_build_record(asset_id: str, campaign_id: str, channel: str,
                            captured_at: str, run_id: str, postiz_post_id: Optional[str],
                            platform_media_id: Optional[str] = None) -> dict:
    """
    Fetch upstream engagement with retry, build the canonical EngagementRecord.
    Raises CredentialsMissingError, UpstreamRejectedError, MalformedResponseError,
    or generic Exception for retryable network failures.

    Step 80 Stage 3 — platform_media_id flows through to fetch_meta_engagement
    when channel is instagram/facebook/meta. None → MAPPING_BLOCKED preserved.
    """
    captured_at_iso = captured_at  # upstream-supplied timestamp

    def do_fetch():
        # Choose fetcher by channel
        if channel in ("instagram", "facebook", "meta"):
            return fetch_meta_engagement(
                asset_id, channel, captured_at_iso,
                platform_media_id=platform_media_id,
            )
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
