"""The ads_brief job keeps the month's figures and puts an over-budget warning first. No network, no token."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

CAMPAIGN_OS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAMPAIGN_OS))
sys.path.insert(0, str(CAMPAIGN_OS / "tests"))

import test_v2026_10_08_ads_brain as fx  # noqa: E402
import test_v2026_10_08_ads_brief as base  # noqa: E402

ADSETS = [{"id": "s1", "name": "Traffic set", "effective_status": "ACTIVE", "daily_budget": "5000",
           "lifetime_budget": "0", "start_time": "2026-09-01T00:00:00+0200", "end_time": None,
           "campaign_id": "c1", "campaign": {"id": "c1"}}]


def _get_with_budget(account, recent, mtd="300.00"):
    inner = base._get(account, recent)

    def get(path, params):
        if params.get("fields") == "spend":
            return {"data": [{"spend": mtd}]}, None
        if path.endswith("/adsets"):
            return {"data": ADSETS}, None
        return inner(path, params)
    return get


class BudgetInTheBrief(base._JobCase):
    def run_budget_job(self, budget=None):
        if budget is not None:
            lane = Path(self.tmp.name) / "brands" / "stick" / "ads-budget"
            lane.mkdir(parents=True, exist_ok=True)
            (lane / "settings.json").write_text(json.dumps({"monthly_budget": budget}), encoding="utf-8")
        return self.job.run(brand="stick", today=base.DAY, get=_get_with_budget(fx.STICK, base.RECENT["stick"]),
                            get_as=fx._fake_get_as(fx.STICK))

    def test_figures_are_kept_and_no_budget_is_said_plainly(self):
        out = self.run_budget_job()
        self.assertTrue(out["ok"], out)
        brief = self.read("latest.json")
        self.assertEqual(brief["budget"]["status"], "NO_BUDGET")
        figs = json.loads((Path(self.tmp.name) / "brands" / "stick" / "ads-budget" / "figures.json")
                          .read_text(encoding="utf-8"))
        self.assertEqual((figs["mtd_spend"], figs["daily_run_rate"], figs["complete"]), (300.0, 50.0, True))
        self.assertNotEqual((brief["top_actions"] or [{}])[0].get("rule"), "monthly_budget")

    def test_a_budget_the_month_will_overshoot_comes_first(self):
        # 300 spent + 50 a day for 23 more days (plus today) is about 1,550
        self.run_budget_job(budget=1000)
        brief = self.read("latest.json")
        self.assertEqual(brief["budget"]["status"], "AT_RISK")
        top = brief["top_actions"][0]
        self.assertEqual((top["rule"], top["severity"]), ("monthly_budget", "high"))
        self.assertLessEqual(len(brief["top_actions"]), 3)

    def test_a_budget_that_fits_adds_no_action(self):
        self.run_budget_job(budget=5000)
        brief = self.read("latest.json")
        self.assertEqual(brief["budget"]["status"], "OK")
        self.assertTrue(all(a.get("rule") != "monthly_budget" for a in brief["top_actions"]))
