"""Re-export campaign-os auth patch for the root tests/ tree (t25-F).

pytest only loads conftest.py between rootdir and the collected path.
Root `tests/` would otherwise miss campaign-os/tests/conftest.py when
run alone. One implementation; this file only re-exports it.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "campaign-os" / "tests" / "conftest.py"
_SPEC = importlib.util.spec_from_file_location("cos_campaign_os_tests_conftest", _PATH)
_MOD = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_MOD)

pytest_configure = _MOD.pytest_configure
pytest_unconfigure = _MOD.pytest_unconfigure
cos_login = _MOD.cos_login
cos_app = _MOD.cos_app
cos_session = _MOD.cos_session
cos_anon_client = _MOD.cos_anon_client
