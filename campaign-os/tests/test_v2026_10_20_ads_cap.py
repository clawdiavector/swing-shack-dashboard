"""Hard stop via Meta's account spending limit: the maths, the plan, apply and release. Meta is faked."""
import pytest

from _lib import ads_actions as aa
from _lib import ads_cap as cap

SPENT = 3_492_103  # R34,921.03 lifetime, in cents (Swing Shack on 2026-10-20)


class Store:
    def __init__(self):
        self.data = {}

    def read(self, rel):
        return self.data.get(rel)

    def write(self, rel, obj):
        self.data[rel] = obj
        return True


class FakeMeta:
    def __init__(self, spend_cap=0):
        self.spend_cap = spend_cap
        self.posts = []

    def __call__(self, method, path, token, params=None):
        if method == "GET":
            return {"amount_spent": str(SPENT), "spend_cap": str(self.spend_cap), "currency": "ZAR", "account_status": 1}
        self.posts.append((path, dict(params)))
        self.spend_cap = int(params["spend_cap"])
        return {"success": True}


FIG = {"mtd_spend": 2229.97, "complete": True}
ACCT = {"amount_spent": SPENT, "spend_cap": 0, "currency": "ZAR"}


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("ADS_WRITES_ENABLED", "1")


def test_cap_is_lifetime_spend_at_month_start_plus_budget():
    # month started at 3,492,103 - 222,997 = 3,269,106; plus R3,000 of budget
    assert cap.desired_cap(SPENT, 2229.97, 3000) == 3_569_106


def test_budget_already_spent_stops_everything_now_not_below_spend():
    assert cap.desired_cap(SPENT, 2229.97, 1000) == SPENT


def test_first_of_the_month_gives_a_fresh_budget():
    assert cap.desired_cap(SPENT, 0.0, 1000) == SPENT + 100_000


def test_plan_does_nothing_unless_asked_and_able():
    assert cap.plan({"monthly_budget": 1000}, ACCT, FIG)["action"] == "none"            # off
    assert cap.plan({"hard_stop": True}, ACCT, FIG)["action"] == "none"                 # no budget
    assert cap.plan({"hard_stop": True, "monthly_budget": 1000}, ACCT, {"mtd_spend": 5, "complete": False})["action"] == "none"
    assert cap.plan({"hard_stop": True, "monthly_budget": 1000}, dict(ACCT, currency="USD"), FIG)["action"] == "none"


def test_plan_will_not_replace_a_limit_someone_else_set():
    p = cap.plan({"hard_stop": True, "monthly_budget": 3000}, dict(ACCT, spend_cap=5_000_000), FIG)
    assert p["action"] == "blocked" and "did not set" in p["reason"]


def test_plan_sets_and_says_when_it_stops_everything_now():
    p = cap.plan({"hard_stop": True, "monthly_budget": 1000}, ACCT, FIG)
    assert p["action"] == "set" and p["stops_now"] is True and p["cap"] == SPENT
    q = cap.plan({"hard_stop": True, "monthly_budget": 3000}, ACCT, FIG)
    assert q["stops_now"] is False and q["room"] == 3_569_106 - SPENT


def test_apply_sets_the_cap_logs_and_remembers_the_old_one(on):
    meta, store = FakeMeta(), Store()
    settings = {"hard_stop": True, "monthly_budget": 3000}
    p = cap.plan(settings, ACCT, FIG)
    entry = cap.apply_plan("stick", p, settings, graph=meta, token="t", account_id="act_1", read=store.read, write=store.write)
    assert meta.posts == [("act_1", {"spend_cap": "3569106"})]
    assert entry["kind"] == "set_spend_cap" and settings["cap_managed"]["previous_cap"] == 0
    assert len(aa.load_log("stick", store.read)) == 1


def test_apply_is_refused_while_changes_are_switched_off(monkeypatch):
    monkeypatch.delenv("ADS_WRITES_ENABLED", raising=False)
    meta, store = FakeMeta(), Store()
    settings = {"hard_stop": True, "monthly_budget": 3000}
    with pytest.raises(aa.ActionRefused):
        cap.apply_plan("stick", cap.plan(settings, ACCT, FIG), settings, graph=meta, token="t", account_id="a",
                       read=store.read, write=store.write)
    assert meta.posts == []


def test_a_second_run_with_the_same_numbers_changes_nothing(on):
    meta, store = FakeMeta(), Store()
    settings = {"hard_stop": True, "monthly_budget": 3000}
    cap.apply_plan("stick", cap.plan(settings, ACCT, FIG), settings, graph=meta, token="t", account_id="a",
                   read=store.read, write=store.write)
    again = cap.plan(settings, dict(ACCT, spend_cap=meta.spend_cap), FIG)
    assert again["action"] == "none" and again["reason"] == "The limit is already right."


def test_release_puts_back_the_previous_limit(on):
    meta, store = FakeMeta(), Store()
    settings = {"hard_stop": True, "monthly_budget": 3000}
    cap.apply_plan("stick", cap.plan(settings, ACCT, FIG), settings, graph=meta, token="t", account_id="a",
                   read=store.read, write=store.write)
    acct = cap.read_account(meta, "t", "a")
    entry = cap.release("stick", settings, acct, graph=meta, token="t", account_id="a", read=store.read, write=store.write)
    assert meta.spend_cap == 0 and entry["after"] == 0 and "cap_managed" not in settings


def test_release_refuses_if_the_limit_was_changed_elsewhere(on):
    meta, store = FakeMeta(), Store()
    settings = {"hard_stop": True, "monthly_budget": 3000}
    cap.apply_plan("stick", cap.plan(settings, ACCT, FIG), settings, graph=meta, token="t", account_id="a",
                   read=store.read, write=store.write)
    meta.spend_cap = 9_999_999
    with pytest.raises(aa.ActionRefused) as e:
        cap.release("stick", settings, cap.read_account(meta, "t", "a"), graph=meta, token="t", account_id="a",
                    read=store.read, write=store.write)
    assert e.value.status == 409
