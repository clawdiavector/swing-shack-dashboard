"""drive_bridge.py — the app's only way to write to Drive.

Campaign OS reads Drive through public folders; it has no Drive login. The bridge is a small Google
Apps Script web app (docs/drive-bridge/drive-bridge.gs), deployed by the person who owns the folders.
It can move a file, change a .txt caption and create a .txt caption inside the brand folders, and
nothing else. Setup: docs/drive-bridge/SETUP.md.

Needs DRIVE_BRIDGE_URL and DRIVE_BRIDGE_TOKEN in the environment; without them every call refuses.
"""
from __future__ import annotations

import os
from typing import Any, Dict

TIMEOUT = 60


class BridgeError(RuntimeError):
    pass


def configured() -> bool:
    return bool((os.environ.get("DRIVE_BRIDGE_URL") or "").strip() and (os.environ.get("DRIVE_BRIDGE_TOKEN") or "").strip())


def _call(brand: str, action: str, **payload: Any) -> Dict[str, Any]:
    if not configured():
        raise BridgeError("the Drive bridge is not set up yet")
    import requests
    body = {"token": os.environ["DRIVE_BRIDGE_TOKEN"].strip(), "brand": brand, "action": action, **payload}
    try:
        # Apps Script answers a POST with a redirect to the result; requests follows it.
        resp = requests.post(os.environ["DRIVE_BRIDGE_URL"].strip(), json=body, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException as exc:
        raise BridgeError("could not reach the Drive bridge: %s" % exc) from None
    try:
        data = resp.json()
    except ValueError:
        raise BridgeError("the Drive bridge answered with something unexpected (is it deployed with access set to Anyone?)") from None
    if not isinstance(data, dict) or not data.get("ok"):
        raise BridgeError(str((data or {}).get("error") or "the Drive bridge refused"))
    return data


def move_file(brand: str, file_id: str, dest_path: str) -> Dict[str, Any]:
    """Move a file to a folder named by its path under the brand root, e.g. 'Video/3-published'."""
    return _call(brand, "move", file_id=file_id, dest_path=dest_path)


def set_text(brand: str, file_id: str, text: str) -> Dict[str, Any]:
    """Replace the text of an existing .txt file."""
    return _call(brand, "set_text", file_id=file_id, text=text)


def create_text(brand: str, folder_path: str, name: str, text: str) -> Dict[str, Any]:
    """Create a new .txt file in a folder named by its path under the brand root."""
    return _call(brand, "create_text", folder_path=folder_path, name=name, text=text)
