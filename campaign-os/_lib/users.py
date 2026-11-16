"""Named logins stored in DATA_DIR/users.json."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

ROLES = ("admin", "editor", "approver", "contributor")

# Actions a signed-in login may take. Free range for now (Kyle, 9 Nov 2026): every
# enabled login may take every one, whatever its role; only "users_admin" is the
# admin's. The role is stored so limits can be switched on later without a migration.
ACTIONS = frozenset({"approve", "move", "share", "catalog_make", "campaign_approve", "comment", "upload"})

_LOCK = threading.Lock()


def _data_dir() -> str:
    return os.environ.get("DATA_DIR") or "/data/campaign-os"


def _path() -> str:
    return os.path.join(_data_dir(), "users.json")


def _load_raw() -> dict[str, Any]:
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {"users": []}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"users": []}


def _save_raw(data: dict[str, Any]) -> None:
    path = _path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _public(user: dict[str, Any]) -> dict[str, Any]:
    out = {k: user[k] for k in ("id", "name", "email", "role", "brands", "created_at", "disabled") if k in user}
    return out


def ensure_bootstrap() -> None:
    """If users.json is missing, create the admin from COS_ADMIN_EMAIL + COS_ADMIN_PASSWORD."""
    with _LOCK:
        if os.path.isfile(_path()):
            return
        email = (os.environ.get("COS_ADMIN_EMAIL") or "").strip().lower()
        password = os.environ.get("COS_ADMIN_PASSWORD") or ""
        if not email or not password:
            return
        data = {
            "users": [
                {
                    "id": f"usr-{uuid.uuid4().hex[:12]}",
                    "name": "Admin",
                    "email": email,
                    "role": "admin",
                    "brands": ["*"],
                    "password_hash": generate_password_hash(password),
                    "created_at": _now(),
                    "disabled": False,
                }
            ]
        }
        _save_raw(data)


def create_user(
    name: str,
    email: str,
    role: str,
    brands: list[str],
    password: str,
) -> dict[str, Any]:
    email = (email or "").strip().lower()
    name = (name or "").strip()
    role = (role or "").strip()
    if not email or not name or not password:
        raise ValueError("Name, email and a starting password are all required.")
    if role not in ROLES:
        raise ValueError(f"Role must be one of: {', '.join(ROLES)}.")
    if not brands:
        raise ValueError("Pick at least one brand, or all brands.")
    with _LOCK:
        data = _load_raw()
        users = data.setdefault("users", [])
        if any(u.get("email") == email for u in users):
            raise ValueError("Someone already uses that email.")
        row = {
            "id": f"usr-{uuid.uuid4().hex[:12]}",
            "name": name,
            "email": email,
            "role": role,
            "brands": list(brands),
            "password_hash": generate_password_hash(password),
            "created_at": _now(),
            "disabled": False,
        }
        users.append(row)
        _save_raw(data)
        return _public(row)


def authenticate(email: str, password: str) -> dict[str, Any] | None:
    email = (email or "").strip().lower()
    if not email or not password:
        return None
    ensure_bootstrap()
    for user in _load_raw().get("users") or []:
        if user.get("email") != email or user.get("disabled"):
            continue
        if check_password_hash(user.get("password_hash") or "", password):
            return _public(user)
    return None


def get_user(user_id: str) -> dict[str, Any] | None:
    if not user_id:
        return None
    ensure_bootstrap()
    for user in _load_raw().get("users") or []:
        if user.get("id") == user_id:
            return _public(user)
    return None


def list_users() -> list[dict[str, Any]]:
    ensure_bootstrap()
    return [_public(u) for u in _load_raw().get("users") or []]


def update_user(user_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    allowed = {"name", "email", "role", "brands", "disabled"}
    clean = {k: patch[k] for k in allowed if k in patch}
    if "role" in clean and clean["role"] not in ROLES:
        raise ValueError(f"Role must be one of: {', '.join(ROLES)}.")
    if "email" in clean:
        clean["email"] = str(clean["email"]).strip().lower()
    with _LOCK:
        data = _load_raw()
        users = data.get("users") or []
        for i, user in enumerate(users):
            if user.get("id") != user_id:
                continue
            if "email" in clean:
                clash = any(
                    u.get("email") == clean["email"] and u.get("id") != user_id for u in users
                )
                if clash:
                    raise ValueError("Someone else already uses that email.")
            users[i] = {**user, **clean}
            _save_raw(data)
            return _public(users[i])
    raise ValueError("That person is not in the list.")


def set_password(user_id: str, new_password: str) -> None:
    if not (new_password or "").strip():
        raise ValueError("Choose a new password.")
    with _LOCK:
        data = _load_raw()
        users = data.get("users") or []
        for i, user in enumerate(users):
            if user.get("id") == user_id:
                users[i] = {**user, "password_hash": generate_password_hash(new_password)}
                _save_raw(data)
                return
    raise ValueError("That person is not in the list.")


def can(user: dict[str, Any] | None, action: str) -> bool:
    """Free range for now (Kyle, 9 Nov 2026): every signed-in, enabled login can do
    everything in the app, whatever its role. Only managing logins is Kyle's (admin).
    The role is still stored and shown, so limits can be switched on later without
    a data change. Signed-out visitors and guest links never reach this."""
    if not user or user.get("disabled"):
        return False
    if action == "users_admin":
        return user.get("role") == "admin"
    return action in ACTIONS
