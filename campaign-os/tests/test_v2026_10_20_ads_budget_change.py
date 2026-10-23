"""Changing an ad set's daily budget: preview, apply, undo. Meta is faked."""
import pytest
from itsdangerous import URLSafeTimedSerializer

from _lib import ads_actions as aa

ACCT = "act_111"


class FakeMeta:
    def __init__(self, daily="3700", lifetime="0", status="ACTIVE", account="111"):
        self.adset = {"id": "777", "name": "Leads set", "account_id": account, "effective_status": status,
                      "daily_budget": daily, "lifetime_budget": lifetime, "campaign": {"name": "Fit Fact"}}
        self.ad = {"id": "555", "account_id": account, "adset_id": "777"}
        self.posts = []

    def __call__(self, method, path, token, params=None):
        if method == "GET":
            return dict(self.adset) if path == "777" else dict(self.ad)
        self.posts.append((path, dict(params)))
        self.adset["daily_budget"] = params["daily_budget"]
        return {"success": True}


class Store:
    def __init__(self):
        self.data = {}

    def read(self, rel):
        return self.data.get(rel)

    def write(self, rel, obj):
        self.data[rel] = obj
        return True


@pytest.fixture
def signer():
    return URLSafeTimedSerializer("s3cret", salt=aa.TICKET_SALT)


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("ADS_WRITES_ENABLED", "1")


def _pv(meta, signer, **kw):
    kw.setdefault("ad_id", "555")
    return aa.preview_budget("stick", graph=meta, token="t", account_id=ACCT, signer=signer, **kw)


def test_a_fifth_up_from_an_ad_id_reads_the_ad_set_and_changes_nothing(signer):
    meta = FakeMeta()
    p = _pv(meta, signer, pct=0.2)
    assert (p["before"], p["after"], p["change_pct"], p["per_day"]) == (37.0, 44.0, 18.9, 7.0)
    assert p["adset_name"] == "Leads set" and meta.posts == []


def test_an_exact_amount_and_the_ad_set_id_directly(signer):
    p = _pv(FakeMeta(), signer, ad_id=None, adset_id="777", daily_budget=40)
    assert p["after"] == 40.0


def test_refuses_steps_over_half_and_no_ops_and_foreign_accounts_and_lifetime_budgets(signer):
    with pytest.raises(aa.ActionRefused):
        _pv(FakeMeta(), signer, daily_budget=100)           # +170%
    with pytest.raises(aa.ActionRefused):
        _pv(FakeMeta(), signer, daily_budget=37)            # no change
    with pytest.raises(aa.ActionRefused):
        _pv(FakeMeta(account="999"), signer, pct=0.2)       # other brand's account
    with pytest.raises(aa.ActionRefused):
        _pv(FakeMeta(daily="0", lifetime="50000"), signer, pct=0.2)
    with pytest.raises(aa.ActionRefused):
        _pv(FakeMeta(), signer)                              # neither pct nor amount


def test_apply_is_off_by_default(signer, monkeypatch):
    monkeypatch.delenv("ADS_WRITES_ENABLED", raising=False)
    meta, store = FakeMeta(), Store()
    t = _pv(meta, signer, pct=0.2)["ticket"]
    with pytest.raises(aa.ActionRefused) as e:
        aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer, read=store.read, write=store.write)
    assert e.value.status == 403 and meta.posts == []


def test_apply_sets_the_budget_in_cents_logs_and_undo_puts_it_back(signer, on):
    meta, store = FakeMeta(), Store()
    t = _pv(meta, signer, pct=0.2)["ticket"]
    entry = aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer, read=store.read, write=store.write)
    assert meta.posts == [("777", {"daily_budget": "4400"})]
    assert (entry["kind"], entry["before"], entry["after"]) == ("set_adset_budget", 37.0, 44.0)
    done = aa.undo("stick", entry["id"], graph=meta, token="t", account_id=ACCT, read=store.read, write=store.write)
    assert meta.adset["daily_budget"] == "3700" and done["undone_at"]


def test_apply_refuses_if_the_budget_moved_since_the_preview(signer, on):
    meta, store = FakeMeta(), Store()
    t = _pv(meta, signer, pct=0.2)["ticket"]
    meta.adset["daily_budget"] = "5000"
    with pytest.raises(aa.ActionRefused) as e:
        aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer, read=store.read, write=store.write)
    assert e.value.status == 409 and meta.posts == []


def test_undo_refuses_if_the_budget_was_changed_elsewhere(signer, on):
    meta, store = FakeMeta(), Store()
    t = _pv(meta, signer, pct=0.2)["ticket"]
    entry = aa.apply("stick", t, graph=meta, token="t", account_id=ACCT, signer=signer, read=store.read, write=store.write)
    meta.adset["daily_budget"] = "9999"
    with pytest.raises(aa.ActionRefused) as e:
        aa.undo("stick", entry["id"], graph=meta, token="t", account_id=ACCT, read=store.read, write=store.write)
    assert e.value.status == 409
