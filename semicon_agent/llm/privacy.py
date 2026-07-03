from __future__ import annotations

from pathlib import Path
from typing import Any


SENSITIVE_KEY_PARTS = {"api_key", "authorization", "password", "secret", "token"}


def redact_for_llm(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lower = str(key).lower()
            if any(part in lower for part in SENSITIVE_KEY_PARTS):
                redacted[str(key)] = "<redacted>"
            elif lower in {"path", "data_path"}:
                redacted[str(key)] = _basename(item)
            else:
                redacted[str(key)] = redact_for_llm(item)
        return redacted
    if isinstance(value, list):
        return [redact_for_llm(item) for item in value]
    if isinstance(value, tuple):
        return [redact_for_llm(item) for item in value]
    return value


def _basename(value: Any) -> str:
    return Path(str(value)).name
