from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunEvent:
    run_id: str
    event_type: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "event_type": self.event_type,
            "message": self.message,
            "payload": _safe_json(self.payload),
            "created_at": self.created_at,
        }


class TraceRecorder:
    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or str(uuid.uuid4())
        self.events: list[RunEvent] = []

    def emit(self, event_type: str, message: str, **payload: Any) -> RunEvent:
        event = RunEvent(
            run_id=self.run_id,
            event_type=event_type,
            message=message,
            payload=redact(payload),
        )
        self.events.append(event)
        return event


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lower = str(key).lower()
            if any(token in lower for token in ["api_key", "token", "authorization", "secret", "password"]):
                redacted[str(key)] = "<redacted>"
            elif lower in {"path", "data_path"}:
                redacted[str(key)] = _redact_path(item)
            else:
                redacted[str(key)] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    return value


def _redact_path(value: Any) -> str:
    text = str(value)
    if not text:
        return text
    return text.replace("\\", "/").split("/")[-1]


def _safe_json(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False, default=str)
        return value
    except TypeError:
        return str(value)
