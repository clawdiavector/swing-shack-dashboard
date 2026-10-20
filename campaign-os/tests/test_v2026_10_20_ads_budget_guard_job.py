"""The hourly guard job: dry run by default, acts only when switched on, never on a failed read."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_10_08_ads_brain as fx  # noqa: E402
import test_v2026_10_08_ads_brief as base  # noqa: E402
import test_v2026_10_20_ads_guard as gt  # noqa: E402

DAY = base.DAY
NOW = dt.datetime(2026, 10, 8, 12, 0, tzinfo=dt.timezone.utc)
ADSETS = [{"id": "S1", "name": "Traffic set", "effective_status": "ACTIVE", "daily_budget": "5000",
           "lifetime_budget": "0", "start_time": "2026-09-01T00:00:00+0200", "end_time": None,
           "campaign_id": "c1", "campaign": {"id": "c1", "name": "Camp"}},
          {"id": "S2", "name": "Leads set", "effective_status": "ACTIVE", "daily_budget": "3000",
           "lifetime_budget": "0", "start_time": "2026-09-01T00:00:00+0200", "end_time": None,
           "campaign_id": "c2", "campaign": {"id": "c2", "name": "Camp2"}}]


def _get(spend="2400.00", fail_sets=False):
    def get(path, params):
        if params.get("fields") == "spend":
            return {"data": [{"spend": spend}]}, None
        if path.endswith("/adsets"):
            return (None, "HTTP 500") if fail_sets else ({"data": ADSETS}, None)
        return None, "unexpected"
    return get


class GuardJob(base._JobCase):
    def setUp(self):
        super().setUp()
        self.lane = Path(self.tmp.name) / "brands" / "stick" / "ads-budget"
        self.lane.mkdir(parents=True, exist_ok=True)

    def settings(self, **kw):
        (self.lane / "settings.json").write_text(json.dumps(kw), encoding="utf-8")

    def run_job(self, graph=None, **kw):
        return self.job_guard.run(brand="stick", today=DAY, now=NOW, get=_get(**kw), graph=graph)

    @property
    def job_guard(self):
        from _lib.jobs.layer7 import ads_budget_guard
        return ads_budget_guard

    def account_number(self):
        from _lib import ads_brain
        return ads_brain.resolve_credentials("stick")[0].replace("act_", "")

    def guard_file(self):
        return json.loads((self.lane / "guard.json").read_text(encoding="utf-8"))

    def test_a_dry_run_is_recorded_and_nothing_is_paused_when_auto_pause_is_off(self):
        os.environ["ADS_WRITES_ENABLED"] = "1"
        self.addCleanup(os.environ.pop, "ADS_WRITES_ENABLED", None)
        self.settings(monthly_budget=1500)
        meta = gt.FakeMeta(account=self.account_number())
        out = self.run_job(graph=meta)
        self.assertTrue(out["ok"], out)
        self.assertEqual((out["enabled"], out["trigger"], out["would_pause"], out["paused"]), (False, True, 2, 0))
        self.assertEqual(meta.posts, [])
        self.assertEqual(len(self.guard_file()["plan"]["targets"]), 2)

    def test_pauses_and_logs_when_switched_on(self):
        os.environ["ADS_WRITES_ENABLED"] = "1"
        self.addCleanup(os.environ.pop, "ADS_WRITES_ENABLED", None)
        self.settings(monthly_budget=1500, auto_pause=True)
        meta = gt.FakeMeta(account=self.account_number())
        out = self.run_job(graph=meta)
        self.assertEqual((out["enabled"], out["paused"]), (True, 2))
        self.assertEqual([p[0] for p in meta.posts], ["S1", "S2"])
        log = json.loads((Path(self.tmp.name) / "brands" / "stick" / "ads-actions" / "log.json").read_text(encoding="utf-8"))
        self.assertEqual([e["kind"] for e in log["entries"]], ["pause_adset", "pause_adset"])

    def test_within_budget_it_does_nothing(self):
        os.environ["ADS_WRITES_ENABLED"] = "1"
        self.addCleanup(os.environ.pop, "ADS_WRITES_ENABLED", None)
        self.settings(monthly_budget=9000, auto_pause=True)
        meta = gt.FakeMeta(account=self.account_number())
        out = self.run_job(graph=meta, spend="300.00")
        self.assertEqual((out["trigger"], out["paused"]), (False, 0))
        self.assertEqual(meta.posts, [])

    def test_a_failed_read_never_pauses(self):
        os.environ["ADS_WRITES_ENABLED"] = "1"
        self.addCleanup(os.environ.pop, "ADS_WRITES_ENABLED", None)
        self.settings(monthly_budget=1500, auto_pause=True)
        meta = gt.FakeMeta(account=self.account_number())
        out = self.run_job(graph=meta, fail_sets=True)
        self.assertEqual((out["trigger"], out["paused"]), (False, 0))
        self.assertEqual(meta.posts, [])
        self.assertIn("could not be read", out["reason"])

    def test_registered_with_an_hourly_schedule_and_a_description(self):
        from _lib.jobs import descriptions, schedules
        from _lib.jobs.layer7 import layer7_specs
        spec = next(s for s in layer7_specs() if s.name == "ads_budget_guard")
        self.assertEqual(spec.every_seconds, 3600)
        self.assertEqual(schedules.schedule_for("ads_budget_guard")["cadence"], "hourly")
        self.assertEqual(descriptions.description_for("ads_budget_guard")["title"], "Ads budget guard")
