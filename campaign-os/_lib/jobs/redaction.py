"""Redact secrets from diagnostic free-text fields (t39)."""

from __future__ import annotations

import os
import re
from typing import Any

_ENV_NAME_RE = re.compile(r"(TOKEN|SECRET|KEY|PASSWORD|CREDENTIAL|_SA_|PRIVATE)", re.I)

_SHAPES: list[tuple[str, re.Pattern[str]]] = [
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}")),
    ("meta", re.compile(r"EAA[A-Za-z0-9]{20,}")),
    ("pem", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*KEY-----")),
    ("google", re.compile(r"AIza[0-9A-Za-z_\-]{20,}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")),
    ("hex", re.compile(r"\b[0-9a-fA-F]{32,}\b")),
    ("b64", re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b")),
]

FIELD_LIMITS = {
    "message": 500,
    "traceback_tail": None,  # last 30 lines
    "stderr_tail": 4096,
    "body_head": 200,
}


def _env_secret_values() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for name, value in os.environ.items():
        if not _ENV_NAME_RE.search(name):
            continue
        if not isinstance(value, str) or len(value) < 8:
            continue
        out.append((name, value))
    # longest first so nested substrings strip cleanly
    out.sort(key=lambda pair: len(pair[1]), reverse=True)
    return out


def redact(text: Any) -> str:
    if text is None:
        return ""
    s = str(text)
    for name, value in _env_secret_values():
        if value and value in s:
            s = s.replace(value, f"«redacted:{name}»")
    for _label, pattern in _SHAPES:
        s = pattern.sub("«redacted»", s)
    return s


def truncate_field(field: str, text: str) -> str:
    if field == "traceback_tail":
        lines = text.splitlines()
        if len(lines) > 30:
            return "\n".join(lines[-30:])
        return text
    limit = FIELD_LIMITS.get(field)
    if limit is None:
        return text
    if len(text) <= limit:
        return text
    return text[:limit]


def redact_obj(obj: Any) -> Any:
    """Recursively redact string leaves. Truncation applied to known field names."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if isinstance(value, str):
                redacted = redact(value)
                if key in FIELD_LIMITS or key in ("message", "traceback_tail", "stderr_tail", "body_head"):
                    out[key] = truncate_field(key if key in FIELD_LIMITS else key, redacted)
                else:
                    out[key] = redacted
            elif key == "exception" and isinstance(value, dict):
                exc = dict(value)
                if "message" in exc:
                    exc["message"] = truncate_field("message", redact(exc.get("message")))
                if "traceback_tail" in exc:
                    exc["traceback_tail"] = truncate_field(
                        "traceback_tail", redact(exc.get("traceback_tail"))
                    )
                if "type" in exc and isinstance(exc["type"], str):
                    exc["type"] = redact(exc["type"])
                out[key] = exc
            elif key == "upstream" and isinstance(value, list):
                items = []
                for item in value:
                    if isinstance(item, dict):
                        row = dict(item)
                        if "body_head" in row:
                            row["body_head"] = truncate_field(
                                "body_head", redact(row.get("body_head"))
                            )
                        if "url" in row and isinstance(row["url"], str):
                            row["url"] = redact(row["url"])
                        items.append(row)
                    else:
                        items.append(redact_obj(item))
                out[key] = items
            else:
                out[key] = redact_obj(value)
        return out
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    if isinstance(obj, str):
        return redact(obj)
    return obj
