"""Budget guard: when it triggers, what it pauses, the fallback, undo, and that off means off. Meta is faked."""
import datetime as dt

import pytest

from _lib import ads_actions as aa
from _lib import ads_guard as g

NOW = dt.datetime(2026, 10, 20, 12, 0, tzinfo=dt.timezone.utc)
ACCT = "act_9"


class Store:
    def __init__(self):
        self.data = {}

    def read(self, rel):
        return self.data.get(rel)

    def write(self, rel, obj):
        self.data[rel] = obj
        return True


class FakeMeta:
    """Ad sets and ads with a status; set refuse_sets to make Meta refuse an ad set edit (budget under its minimum)."""

    def __init__(self, refuse_sets=False, account="9"):
        self.account = account
        self.sets = {"S1": {"status": "ACTIVE", "ads": ["A1", "A2"]}, "S2": {"status": "ACTIVE", "ads": ["A3"]}}
        self.ads = {"A1": "ACTIVE", "A2": "PAUSED", "A3": "ACTIVE"}
        self.refuse_sets = refuse_sets
        self.posts = []

    def __call__(self, method, path, token, params=None):
        if method == "GET":
            if path.endswith("/ads"):
                sid = path.split("/")[0]
                return {"data": [{"id": a, "name": a, "status": self.ads[a]} for a in self.sets[sid]["ads"]]}
            if path in self.sets:
                return {"id": path, "name": path, "status": self.sets[path]["status"], "account_id": self.account}
            return {"id": path, "name": path, "status": self.ads[path], "account_id": self.account}
        self.posts.append((path, dict(params)))
        if path in self.sets:
            if self.refuse_sets:
                raise aa.ActionRefused("Meta said: Budget is too low", 502)
            self.sets[path]["status"] = params["status"]
        else:
            self.ads[path] = params["status"]
        return {"success": True}


FIG_OVER = {"mtd_spend": 2400.0, "daily_run_rate": 100.0, "complete": True}
RUNNING = [{"id": "S1", "name": "Set one", "campaign": "C"}, {"id": "S2", "name": "Set two", "campaign": "C"}]


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("ADS_WRITES_ENABLED", "1")


def test_triggers_when_the_budget_is_used_up():
    assert g.trigger(FIG_OVER, 1500)["go"] is True
    assert g.trigger({"mtd_spend": 1500.0, "daily_run_rate": 0, "complete": True}, 1500)["go"] is True


def test_triggers_when_the_next_hour_would_use_it_up():
    # R100 a day with a quarter extra is about R5.2 an hour
    near = {"mtd_spend": 1496.0, "daily_run_rate": 100.0, "complete": True}
    assert g.trigger(near, 1500)["go"] is True
    far = {"mtd_spend": 1400.0, "daily_run_rate": 100.0, "complete": True}
    assert g.trigger(far, 1500)["go"] is False


def test_never_triggers_without_a_budget_or_on_a_failed_read():
    assert g.trigger(FIG_OVER, None)["go"] is False
    assert g.trigger(dict(FIG_OVER, complete=False), 1500)["go"] is False
    assert g.trigger(None, 1500)["go"] is False


def test_running_sets_skips_paused_and_ended():
    rows = [{"id": 1, "name": "a", "effective_status": "ACTIVE", "campaign": {"name": "c"}},
            {"id": 2, "name": "b", "effective_status": "PAUSED"},
            {"id": 3, "name": "c", "effective_status": "ACTIVE", "end_time": "2026-09-01T00:00:00+0200"},
            {"id": 4, "name": "d", "effective_status": "ACTIVE", "end_time": "2026-12-01T00:00:00+0200"}]
    assert [r["id"] for r in g.running_sets(rows, NOW)] == ["1", "4"]


def test_plan_is_a_dry_run_unless_auto_pause_is_on_and_writes_are_enabled(monkeypatch):
    monkeypatch.setenv("ADS_WRITES_ENABLED", "1")
    off = g.plan({"monthly_budget": 1500}, FIG_OVER, RUNNING)
    assert off["trigger"] and len(off["targets"]) == 2 and off["enabled"] is False
    assert g.plan({"monthly_budget": 1500, "auto_pause": True}, FIG_OVER, RUNNING)["enabled"] is True
    monkeypatch.delenv("ADS_WRITES_ENABLED")
    assert g.plan({"monthly_budget": 1500, "auto_pause": True}, FIG_OVER, RUNNING)["enabled"] is False


def test_nothing_is_paused_when_not_enabled(on):
    meta, store = FakeMeta(), Store()
    p = g.plan({"monthly_budget": 1500}, FIG_OVER, RUNNING)  # auto_pause off
    assert g.act("stick", p, graph=meta, token="t", account_id=ACCT, read=store.read, write=store.write) == []
    assert meta.posts == []


def test_pauses_every_running_ad_set_and_logs_each(on):
    meta, store = FakeMeta(), Store()
    p = g.plan({"monthly_budget": 1500, "auto_pause": True}, FIG_OVER, RUNNING)
    made = g.act("stick", p, graph=meta, token="t", account_id=ACCT, read=store.read, write=store.write)
    assert meta.posts == [("S1", {"status": "PAUSED"}), ("S2", {"status": "PAUSED"})]
    assert [m["kind"] for m in made] == ["pause_adset", "pause_adset"] and all(m["by"] == "budget guard" for m in made)
    assert len(aa.load_log("stick", store.read)) == 2


def test_falls_back_to_pausing_the_running_ads_when_meta_refuses_the_ad_set(on):
    meta, store = FakeMeta(refuse_sets=True), Store()
    p = g.plan({"monthly_budget": 1500, "auto_pause": True}, FIG_OVER, RUNNING)
    made = g.act("stick", p, graph=meta, token="t", account_id=ACCT, read=store.read, write=store.write)
    # S1 has one active ad (A1; A2 was already paused), S2 has A3
    assert sorted(m["ad_id"] for m in made) == ["A1", "A3"] and all(m["kind"] == "pause_ad" for m in made)
    assert meta.ads == {"A1": "PAUSED", "A2": "PAUSED", "A3": "PAUSED"}


def test_a_paused_ad_set_is_left_alone_and_other_accounts_are_refused(on):
    meta, store = FakeMeta(), Store()
    meta.sets["S1"]["status"] = "PAUSED"
    p = g.plan({"monthly_budget": 1500, "auto_pause": True}, FIG_OVER, RUNNING)
    made = g.act("stick", p, graph=meta, token="t", account_id=ACCT, read=store.read, write=store.write)
    assert [m["ad_id"] for m in made] == ["S2"]
    made = g.act("stick", p, graph=meta, token="t", account_id="act_other", read=Store().read, write=Store().write)
    assert all("error" in m for m in made)


def test_each_pause_can_be_undone_and_only_if_still_paused(on):
    meta, store = FakeMeta(), Store()
    p = g.plan({"monthly_budget": 1500, "auto_pause": True}, FIG_OVER, RUNNING)
    made = g.act("stick", p, graph=meta, token="t", account_id=ACCT, read=store.read, write=store.write)
    done = aa.undo("stick", made[0]["id"], graph=meta, token="t", account_id=ACCT, read=store.read, write=store.write)
    assert meta.sets["S1"]["status"] == "ACTIVE" and done["undone_at"]
    meta.sets["S2"]["status"] = "ACTIVE"  # someone resumed it in Ads Manager
    with pytest.raises(aa.ActionRefused) as e:
        aa.undo("stick", made[1]["id"], graph=meta, token="t", account_id=ACCT, read=store.read, write=store.write)
    assert e.value.status == 409
    assert [x["ad_id"] for x in g.guarded(aa.load_log("stick", store.read))] == ["S2"]
