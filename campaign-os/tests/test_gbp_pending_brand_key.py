"""
Today GBP pending must check Postiz on the active brand's key, not the shared key.

Run: python -m pytest campaign-os/tests/test_gbp_pending_brand_key.py
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

SS_GBP_INTEGRATION = "cmmdgju7f00tppk0y6bne9zrk"


class GbpPendingBrandKeyTests(unittest.TestCase):
    def setUp(self):
        import app as app_module  # noqa: PLC0415

        self.app_module = app_module
        self._gdp_patch = mock.patch.object(
            app_module._gdp,
            "latest_plan",
            return_value={
                "plan_id": "plan-1",
                "posts": [
                    {
                        "post_status": "PENDING",
                        "title": "Almost tee time.",
                        "body": "Book a bay.",
                        "keyword": "tee time",
                    }
                ],
            },
        )
        self._gdp_patch.start()
        self._pc = mock.MagicMock()
        self._pc._credentials_present.return_value = True

        def _list_integrations(*, brand_id=None):
            if brand_id == "swing-shack":
                return ([{"id": SS_GBP_INTEGRATION}], None)
            return ([{"id": "stick-only-channel"}], None)

        self._pc.list_integrations.side_effect = _list_integrations
        self._lib_pc_patch = mock.patch("_lib.postiz_client", self._pc)
        self._lib_pc_patch.start()
        self.client = app_module.app.test_client()

    def tearDown(self):
        self._lib_pc_patch.stop()
        self._gdp_patch.stop()

    def test_pending_uses_brand_postiz_key_for_integration_check(self):
        res = self.client.get("/api/gbp/daily-poster/pending?brand_id=swing-shack")
        self.assertEqual(res.status_code, 200, res.get_json())
        body = res.get_json()
        self.assertTrue(body.get("integration_verified"))
        self.assertIsNotNone(body.get("post"))
        self.assertNotEqual(body.get("reason"), "integration_not_found_on_postiz_key")
        self._pc._credentials_present.assert_called_with("swing-shack")
        self._pc.list_integrations.assert_called_with(brand_id="swing-shack")


if __name__ == "__main__":
    unittest.main()
