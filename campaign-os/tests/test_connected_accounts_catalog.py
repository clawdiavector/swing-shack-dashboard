"""Connected Accounts catalog helpers."""

from _lib.connected_accounts_catalog import infer_postiz_provider, build_catalog_extras


def test_infer_postiz_provider_from_identifier():
    assert infer_postiz_provider({"providerIdentifier": "instagram", "name": "Swing Shack"}) == "instagram"


def test_infer_postiz_provider_name_is_platform():
    assert infer_postiz_provider({"name": "gmb"}) == "gmb"


def test_infer_postiz_provider_fallback_channel():
    assert infer_postiz_provider({"name": "Swing Shack"}) == "channel"


def test_build_catalog_extras_shape():
    out = build_catalog_extras()
    assert "categories" in out
    assert "summary" in out
    assert isinstance(out["integrations"], list)
    ids = {x["id"] for x in out["integrations"]}
    assert "ga4" in ids
    assert "publish_mode" in ids
