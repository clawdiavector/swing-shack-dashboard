"""
Truth Collector tests — Stage 4 server-side.

Tests the truth_collector module directly without requiring live GA4/Meta
credentials. Mocks the upstream fetcher via monkey-patching fetch_ga4_engagement
and fetch_meta_engagement to return synthetic-but-truthful metrics.

The mock fixtures are isolated to this test file. Production code never
references them.

Run: cd campaign-os && ../.venv/bin/python tests/test_truth_collector.py
"""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

# Ensure we can import truth_collector from the campaign-os dir
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import truth_collector as tc
from truth_collector import (
    EngagementStore,
    truth_collector_ingest_publish_event,
    truth_collector_ingest_cron_tick,
    truth_collector_ingest_manual_trigger,
    truth_collector_write_engagement,
    truth_collector_get_engagement_history,
    ga4_credentials_present,
    meta_credentials_present,
    CredentialsMissingError,
    TRUTH_EVENT_TYPES,
)


# ── Test fixtures ─────────────────────────────────────────────────────

def make_record(asset_id="a1", campaign_id="c1", source="ga4",
                captured_at="2026-07-20T08:00:00Z", run_id="run-test",
                postiz_post_id=None, metrics=None):
    """Build a valid EngagementRecord for tests."""
    if metrics is None:
        metrics = {
            "impressions": 1000, "reach": 800, "likes": 50,
            "comments": 10, "shares": 5, "engagementRate": 0.065,
        }
    return {
        "historyId": f"eh-{asset_id}-{captured_at}",
        "assetId": asset_id,
        "campaignId": campaign_id,
        "verified": True,
        "source": source,
        "verificationAt": "2026-07-20T08:00:01Z",
        "verificationError": None,
        "capturedAt": captured_at,
        "collectedAt": "2026-07-20T08:00:01Z",
        "collectedBy": "truth-collector",
        "collectionRunId": run_id,
        "impressions": metrics.get("impressions"),
        "reach": metrics.get("reach"),
        "likes": metrics.get("likes"),
        "comments": metrics.get("comments"),
        "shares": metrics.get("shares"),
        "engagementRate": metrics.get("engagementRate"),
        "raw": dict(metrics, _request_id="req-test"),
        "provenance": {
            "source": "truth-collector",
            "upstreamSource": source,
            "upstreamRequestId": "req-test",
            "postizPostId": postiz_post_id,
            "publishedAt": captured_at,
            "chain": ["truth-collector", source],
        },
    }


class TestEngagementStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = EngagementStore(self.tmpdir)

    def test_append_new_record(self):
        rec = make_record()
        result = self.store.append(rec)
        self.assertTrue(result["ok"])
        self.assertTrue(result["written"])
        self.assertEqual(result["historyId"], rec["historyId"])

    def test_idempotent_same_captured_at(self):
        rec = make_record(captured_at="2026-07-20T08:00:00Z")
        self.store.append(rec)
        rec2 = make_record(captured_at="2026-07-20T08:00:00Z", run_id="run-2")
        result = self.store.append(rec2)
        self.assertTrue(result["ok"])
        self.assertFalse(result["written"])
        self.assertEqual(result["reason"], "duplicate_capturedAt")
        self.assertEqual(result["historyId"], rec["historyId"])

    def test_idempotent_older_captured_at(self):
        rec = make_record(captured_at="2026-07-20T08:00:00Z")
        self.store.append(rec)
        rec_older = make_record(captured_at="2026-07-20T07:00:00Z", run_id="run-2")
        result = self.store.append(rec_older)
        self.assertTrue(result["ok"])
        self.assertFalse(result["written"])
        self.assertEqual(result["reason"], "older_capturedAt")

    def test_append_newer_captured_at(self):
        rec = make_record(captured_at="2026-07-20T08:00:00Z")
        self.store.append(rec)
        rec_newer = make_record(captured_at="2026-07-20T09:00:00Z", run_id="run-2")
        result = self.store.append(rec_newer)
        self.assertTrue(result["ok"])
        self.assertTrue(result["written"])
        self.assertEqual(self.store.for_asset("a1")[0]["capturedAt"], "2026-07-20T08:00:00Z")
        self.assertEqual(self.store.for_asset("a1")[1]["capturedAt"], "2026-07-20T09:00:00Z")

    def test_append_only_history_grows(self):
        for i in range(5):
            rec = make_record(captured_at=f"2026-07-20T08:0{i}:00Z", run_id=f"r{i}")
            self.store.append(rec)
        self.assertEqual(len(self.store.for_asset("a1")), 5)
        # Monotonically increasing collectedAt
        records = self.store.for_asset("a1")
        for i in range(1, len(records)):
            self.assertGreaterEqual(records[i]["collectedAt"], records[i - 1]["collectedAt"])

    def test_invalid_record_rejected(self):
        rec = make_record()
        rec["verified"] = False
        result = self.store.append(rec)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "invalid_record")

    def test_invalid_source_rejected(self):
        rec = make_record()
        rec["source"] = "manual"
        result = self.store.append(rec)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "invalid_record")

    def test_invalid_collected_by_rejected(self):
        rec = make_record()
        rec["collectedBy"] = "manual-writer"
        result = self.store.append(rec)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "invalid_record")

    def test_missing_required_field_rejected(self):
        rec = make_record()
        del rec["raw"]
        result = self.store.append(rec)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "invalid_record")
        self.assertEqual(result["missing"], "raw")

    def test_get_history_returns_list(self):
        self.store.append(make_record())
        history = self.store.for_asset("a1")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["assetId"], "a1")

    def test_get_history_empty_for_unknown_asset(self):
        self.assertEqual(self.store.for_asset("unknown"), [])

    def test_state_persisted(self):
        self.store.mark_state(last_run_at="2026-07-20T08:00:00Z")
        # Re-read by constructing a fresh store from the same dir
        store2 = EngagementStore(self.tmpdir)
        self.assertEqual(store2._read()["lastRunAt"], "2026-07-20T08:00:00Z")


class TestCredentials(unittest.TestCase):
    def test_ga4_creds_absent(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("GA4_PROPERTY_ID", "GA4_API_KEY", "GA4_SERVICE_ACCOUNT_JSON_PATH")}
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(ga4_credentials_present())

    def test_meta_creds_absent(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("META_APP_ID", "META_APP_SECRET", "META_ACCESS_TOKEN", "META_REFRESH_TOKEN")}
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(meta_credentials_present())

    def test_ga4_creds_present(self):
        with patch.dict(os.environ, {"GA4_PROPERTY_ID": "123", "GA4_API_KEY": "abc"}, clear=False):
            self.assertTrue(ga4_credentials_present())

    def test_meta_creds_present(self):
        with patch.dict(os.environ, {
            "META_APP_ID": "x", "META_APP_SECRET": "y", "META_ACCESS_TOKEN": "z"
        }, clear=False):
            self.assertTrue(meta_credentials_present())


class TestEventTypes(unittest.TestCase):
    def test_three_keys_present(self):
        self.assertEqual(len(TRUTH_EVENT_TYPES), 3)
        self.assertIn("ENGAGEMENT_COLLECTED", TRUTH_EVENT_TYPES)
        self.assertIn("COLLECTION_FAILED", TRUTH_EVENT_TYPES)
        self.assertIn("COLLECTION_SKIPPED", TRUTH_EVENT_TYPES)

    def test_values_are_namespaced(self):
        self.assertTrue(TRUTH_EVENT_TYPES["ENGAGEMENT_COLLECTED"].startswith("truth."))
        self.assertTrue(TRUTH_EVENT_TYPES["COLLECTION_FAILED"].startswith("truth."))
        self.assertTrue(TRUTH_EVENT_TYPES["COLLECTION_SKIPPED"].startswith("truth."))

    def test_no_learning_prefix(self):
        for v in TRUTH_EVENT_TYPES.values():
            self.assertFalse(v.startswith("learning."),
                             f"Truth Collector must not use learning.* namespace: {v}")


class TestIngestPublishEvent(unittest.TestCase):
    """Test the publish-event entry point. Mocks GA4/Meta fetchers."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = EngagementStore(self.tmpdir)

    def test_invalid_payload(self):
        result = truth_collector_ingest_publish_event({}, self.store)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "invalid_payload")

    def test_missing_post_id(self):
        result = truth_collector_ingest_publish_event(
            {"status": "published", "published_at": "2026-07-20T08:00:00Z", "channel": "instagram"},
            self.store,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "invalid_payload")

    def test_wrong_status(self):
        result = truth_collector_ingest_publish_event(
            {"post_id": "p1", "status": "draft", "published_at": "2026-07-20T08:00:00Z", "channel": "instagram"},
            self.store,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "invalid_payload")

    def test_asset_not_found_returns_skip_reason(self):
        # post_id p1 isn't in any campaign
        with patch.object(tc, "_lookup_asset_by_postiz_post_id", return_value=None):
            result = truth_collector_ingest_publish_event(
                {"post_id": "p1", "status": "published", "published_at": "2026-07-20T08:00:00Z", "channel": "instagram"},
                self.store,
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "asset_not_found_for_post")

    def test_credentials_missing_returns_blocked(self):
        with patch.object(tc, "_lookup_asset_by_postiz_post_id", return_value=("a1", "c1")):
            with patch.object(tc, "_fetch_and_build_record",
                              side_effect=CredentialsMissingError("test")):
                result = truth_collector_ingest_publish_event(
                    {"post_id": "p1", "status": "published", "published_at": "2026-07-20T08:00:00Z", "channel": "instagram"},
                    self.store,
                )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "credentials_missing")

    def test_successful_ingest_writes_record(self):
        def fake_fetch(asset_id, campaign_id, channel, captured_at, run_id, postiz_post_id):
            return make_record(
                asset_id=asset_id, campaign_id=campaign_id,
                source="meta" if channel in ("instagram", "facebook", "meta") else "ga4",
                captured_at=captured_at, run_id=run_id, postiz_post_id=postiz_post_id,
            )
        with patch.object(tc, "_lookup_asset_by_postiz_post_id", return_value=("a1", "c1")):
            with patch.object(tc, "_fetch_and_build_record", side_effect=fake_fetch):
                result = truth_collector_ingest_publish_event(
                    {"post_id": "p1", "status": "published",
                     "published_at": "2026-07-20T08:00:00Z", "channel": "instagram"},
                    self.store,
                )
        self.assertTrue(result["ok"])
        self.assertEqual(result["assetId"], "a1")
        self.assertEqual(len(self.store.for_asset("a1")), 1)

    def test_duplicate_publish_event_skips(self):
        def fake_fetch(asset_id, campaign_id, channel, captured_at, run_id, postiz_post_id):
            return make_record(
                asset_id=asset_id, campaign_id=campaign_id,
                source="meta" if channel in ("instagram", "facebook", "meta") else "ga4",
                captured_at=captured_at, run_id=run_id, postiz_post_id=postiz_post_id,
            )
        with patch.object(tc, "_lookup_asset_by_postiz_post_id", return_value=("a1", "c1")):
            with patch.object(tc, "_fetch_and_build_record", side_effect=fake_fetch):
                # First call
                truth_collector_ingest_publish_event(
                    {"post_id": "p1", "status": "published",
                     "published_at": "2026-07-20T08:00:00Z", "channel": "instagram"},
                    self.store,
                )
                # Second call (same captured_at)
                result = truth_collector_ingest_publish_event(
                    {"post_id": "p1", "status": "published",
                     "published_at": "2026-07-20T08:00:00Z", "channel": "instagram"},
                    self.store,
                )
        self.assertTrue(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "duplicate_capturedAt")
        self.assertEqual(len(self.store.for_asset("a1")), 1)


class TestIngestCronTick(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = EngagementStore(self.tmpdir)

    def test_cron_with_no_assets(self):
        result = truth_collector_ingest_cron_tick(self.store, {"campaigns": {}})
        self.assertTrue(result["ok"])
        self.assertEqual(result["scanned"], 0)

    def test_cron_skips_cancelled_campaign(self):
        campaign_data = {
            "campaigns": {
                "c1": {"identity": {"status": "cancelled"}, "channels": []}
            }
        }
        result = truth_collector_ingest_cron_tick(self.store, campaign_data)
        self.assertEqual(result["scanned"], 0)

    def test_cron_skips_archived_campaign(self):
        campaign_data = {
            "campaigns": {
                "c1": {"identity": {"status": "archived"}, "channels": []}
            }
        }
        result = truth_collector_ingest_cron_tick(self.store, campaign_data)
        self.assertEqual(result["scanned"], 0)

    def test_cron_skips_unpublished_items(self):
        campaign_data = {
            "campaigns": {
                "c1": {
                    "identity": {"status": "active"},
                    "channels": [{
                        "platform": "instagram",
                        "plannedItems": [{"asset": {"id": "a1"}, "publishedAt": None}]
                    }]
                }
            }
        }
        result = truth_collector_ingest_cron_tick(self.store, campaign_data)
        self.assertEqual(result["scanned"], 0)


class TestIngestManualTrigger(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = EngagementStore(self.tmpdir)

    def test_invalid_campaign(self):
        result = truth_collector_ingest_manual_trigger("nonexistent", self.store, {"campaigns": {}})
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "invalid_campaign")

    def test_cancelled_campaign(self):
        campaign_data = {"campaigns": {"c1": {"identity": {"status": "cancelled"}}}}
        result = truth_collector_ingest_manual_trigger("c1", self.store, campaign_data)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "cancelled")

    def test_empty_campaign(self):
        campaign_data = {"campaigns": {"c1": {"identity": {"status": "active"}, "channels": []}}}
        result = truth_collector_ingest_manual_trigger("c1", self.store, campaign_data)
        self.assertTrue(result["ok"])
        self.assertEqual(result["scanned"], 0)


class TestReadWriteContracts(unittest.TestCase):
    """Verify the single-write path and read accessor."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = EngagementStore(self.tmpdir)

    def test_write_then_get_history(self):
        rec = make_record(asset_id="a1")
        result = truth_collector_write_engagement("a1", rec, self.store)
        self.assertTrue(result["ok"])
        self.assertTrue(result["written"])

        history = truth_collector_get_engagement_history("a1", self.store)
        self.assertIsNotNone(history)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["capturedAt"], "2026-07-20T08:00:00Z")

    def test_get_history_returns_none_for_unknown_asset(self):
        history = truth_collector_get_engagement_history("nonexistent", self.store)
        self.assertIsNone(history)

    def test_write_rejects_invalid_record(self):
        bad = make_record()
        bad["source"] = "manual"
        result = truth_collector_write_engagement("a1", bad, self.store)
        self.assertFalse(result["ok"])


class TestNoFakeAnalytics(unittest.TestCase):
    """Stage 4 must never fabricate metrics. The fetcher stubs raise NotImplementedError."""

    def test_ga4_raises_not_implemented_without_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(CredentialsMissingError):
                tc.fetch_ga4_engagement("a1", "instagram", "2026-07-20T08:00:00Z")

    def test_meta_raises_not_implemented_without_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(CredentialsMissingError):
                tc.fetch_meta_engagement("a1", "instagram", "2026-07-20T08:00:00Z")

    def test_ga4_raises_not_implemented_with_credentials(self):
        """Even with credentials, the placeholder raises NotImplementedError — no fake metrics."""
        with patch.dict(os.environ, {"GA4_PROPERTY_ID": "123", "GA4_API_KEY": "abc"}):
            with self.assertRaises(NotImplementedError):
                tc.fetch_ga4_engagement("a1", "web", "2026-07-20T08:00:00Z")

    def test_meta_raises_not_implemented_with_credentials(self):
        with patch.dict(os.environ, {
            "META_APP_ID": "x", "META_APP_SECRET": "y", "META_ACCESS_TOKEN": "z"
        }):
            with self.assertRaises(NotImplementedError):
                tc.fetch_meta_engagement("a1", "instagram", "2026-07-20T08:00:00Z")


class TestNoMutationOfStageTruth(unittest.TestCase):
    """Truth Collector must not write to campaign.memory.* or modify Stage 2/3 paths."""

    def test_truth_collector_does_not_import_performance_paths(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "truth_collector.py")) as f:
            src = f.read()
        # Strip the module docstring before scanning — it references Stage names
        # as documentation, not as call sites.
        import re
        stripped = re.sub(r'"""[\s\S]*?"""', "", src, count=1)
        # It must NOT call or import Stage 2/3 functions
        self.assertNotIn("performancePromote", stripped)
        self.assertNotIn("performanceDerive", stripped)
        self.assertNotIn("performanceAggregate", stripped)
        self.assertNotIn("specifyLearningsForCampaign", stripped)
        self.assertNotIn("EVIDENCE_PACKS_KEY", stripped)
        self.assertNotIn("campaign.memory", stripped)
        # And no Learning events
        self.assertNotIn("LEARNING_", stripped)


if __name__ == "__main__":
    unittest.main(verbosity=2)
