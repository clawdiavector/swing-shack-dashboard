"""The ads_brief job keeps Meta's account limit at the month's budget, but only when the hard stop is on."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_10_08_ads_brain as fx  # noqa: E402
import test_v2026_10_08_ads_brief as base  # noqa: E402
from _lib import ads_cap  # noqa: E402

ADSETS = [{"id": "s1", "name": "Traffic set", "effective_status": "ACTIVE", "daily_budget": "5000",
           "lifetime_budget": "0", "start_time": "2026-09-01T00:00:00+0200", "end_time": None,
           "campaign_id": "c1", "campaign": {"id": "c1"}}]


def _get(account, spend_cap="0"):
    inner = base._get(account, base.RECENT["stick"])

    def get(path, params):
        if params.get("fields") == ads_cap.FIELDS:
            return {"amount_spent": "1000000", "spend_cap": spend_cap, "currency": "ZAR", "account_status": 1}, None
        if params.get("fields") == "spend":
            return {"data": [{"spend": "300.00"}]}, None
        if path.endswith("/adsets"):
            return {"data": ADSETS}, None
        return inner(path, params)
    return get


class HardStopInTheJob(base._JobCase):
    def _settings(self, **kw):
        lane = Path(self.tmp.name) / "brands" / "stick" / "ads-budget"
        lane.mkdir(parents=True, exist_ok=True)
        (lane / "settings.json").write_text(json.dumps(kw), encoding="utf-8")
        return lane

    def _run(self, **kw):
        return self.job.run(brand="stick", today=base.DAY, get=_get(fx.STICK, **kw), get_as=fx._fake_get_as(fx.STICK))

    def test_off_by_default_it_reads_the_account_and_writes_nothing(self):
        lane = self._settings(monthly_budget=2000)
        with mock.patch("_lib.ads_actions.graph_call") as post:
            self.assertTrue(self._run()["ok"])
        post.assert_not_called()
        figs = json.loads((lane / "figures.json").read_text(encoding="utf-8"))
        self.assertEqual(figs["account"]["amount_spent"], 1_000_000)
        self.assertFalse(self.read("latest.json")["budget"]["hard_stop"]["on"])

    def test_on_it_sets_the_limit_to_month_start_plus_budget_and_logs_it(self):
        os.environ["ADS_WRITES_ENABLED"] = "1"
        self.addCleanup(os.environ.pop, "ADS_WRITES_ENABLED", None)
        lane = self._settings(monthly_budget=2000, hard_stop=True)
        with mock.patch("_lib.ads_actions.graph_call", return_value={"success": True}) as post:
            self.assertTrue(self._run()["ok"])
        # lifetime 1,000,000 cents, 300.00 spent this month, budget 2000.00: cap = 1,000,000 - 30,000 + 200,000
        self.assertEqual(post.call_args[0][3], {"spend_cap": "1170000"})
        settings = json.loads((lane / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["cap_managed"]["last_set"], 1_170_000)
        log = json.loads((Path(self.tmp.name) / "brands" / "stick" / "ads-actions" / "log.json").read_text(encoding="utf-8"))
        self.assertEqual(log["entries"][0]["kind"], "set_spend_cap")
        self.assertEqual(self.read("latest.json")["budget"]["hard_stop"]["set"], True)

    def test_a_limit_someone_else_set_is_left_alone(self):
        os.environ["ADS_WRITES_ENABLED"] = "1"
        self.addCleanup(os.environ.pop, "ADS_WRITES_ENABLED", None)
        self._settings(monthly_budget=2000, hard_stop=True)
        with mock.patch("_lib.ads_actions.graph_call") as post:
            self.assertTrue(self._run(spend_cap="5000000")["ok"])
        post.assert_not_called()
        self.assertEqual(self.read("latest.json")["budget"]["hard_stop"]["plan"]["action"], "blocked")
