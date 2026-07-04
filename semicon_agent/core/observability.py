from __future__ import annotations

import hashlib
import uuid
from typing import Any


def export_events_as_spans(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        run_id = str(event.get("run_id", ""))
        event_type = str(event.get("event_type", "event"))
        timestamp = float(event.get("created_at", 0.0) or 0.0)
        start_ns = int(timestamp * 1_000_000_000)
        spans.append(
            {
                "trace_id": _trace_id(run_id),
                "span_id": _span_id(run_id, index, event_type),
                "parent_span_id": None,
                "name": event_type,
                "kind": "INTERNAL",
                "start_time_unix_nano": start_ns,
                "end_time_unix_nano": start_ns + 1,
                "attributes": _attributes(event),
            }
        )
    return spans


def _trace_id(run_id: str) -> str:
    try:
        return uuid.UUID(run_id).hex
    except ValueError:
        return hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:32]


def _span_id(run_id: str, index: int, event_type: str) -> str:
    source = f"{run_id}:{index}:{event_type}".encode("utf-8")
    return hashlib.sha256(source).hexdigest()[:16]


def _attributes(event: dict[str, Any]) -> dict[str, object]:
    payload = event.get("payload", {})
    attrs: dict[str, object] = {
        "agent.system": "semicon-agent",
        "agent.event.type": str(event.get("event_type", "")),
        "agent.event.message": str(event.get("message", "")),
    }
    if isinstance(payload, dict):
        for key, value in payload.items():
            simple = _simple_value(value)
            if simple is not None:
                attrs[f"agent.payload.{key}"] = simple
    return attrs


def _simple_value(value: Any) -> object | None:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return None
