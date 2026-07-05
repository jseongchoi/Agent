from __future__ import annotations

from pathlib import Path
from typing import Any

from semicon_agent.models import ToolResult


SENSITIVE_KEY_PARTS = {"api_key", "authorization", "password", "secret", "token"}
MAX_SUMMARY_ITEMS = 10
MAX_SUMMARY_TEXT = 500


def redact_for_llm(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lower = str(key).lower()
            if any(part in lower for part in SENSITIVE_KEY_PARTS):
                redacted[str(key)] = "<redacted>"
            elif lower in {"path", "data_path"}:
                redacted[str(key)] = _basename(item)
            elif lower == "tool_results":
                redacted[str(key)] = summarize_tool_results(item)
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


def summarize_tool_results(results: Any) -> list[dict[str, Any]]:
    if not isinstance(results, list):
        return []
    return [_summarize_tool_result(result) for result in results]


def _summarize_tool_result(result: Any) -> dict[str, Any]:
    if isinstance(result, ToolResult):
        payload = result.model_dump()
    elif isinstance(result, dict):
        payload = result
    else:
        return {"name": "unknown", "summary": _compact_value(result)}

    output = payload.get("output")
    summary = _summarize_tool_output(output)
    return {
        "name": payload.get("name"),
        "arguments": redact_for_llm(payload.get("arguments", {})),
        "error": payload.get("error"),
        "summary": summary,
    }


def _summarize_tool_output(output: Any) -> Any:
    if not isinstance(output, dict):
        return _compact_value(output)
    kind = output.get("kind")
    if kind == "dataset_profile":
        return {
            "kind": kind,
            "row_count": output.get("row_count"),
            "column_count": output.get("column_count"),
            "measurement_columns": _limit_list(output.get("measurement_columns")),
            "numeric_columns": _limit_list(output.get("numeric_columns")),
            "missing_cells": output.get("missing_cells"),
            "role_guess": output.get("role_guess"),
        }
    if kind == "yield_summary":
        return {
            "kind": kind,
            "total_count": output.get("total_count"),
            "pass_count": output.get("pass_count"),
            "fail_count": output.get("fail_count"),
            "yield_pct": output.get("yield_pct"),
            "pass_source": output.get("pass_source"),
            "by_lot": _limit_list(output.get("by_lot")),
            "by_wafer": _limit_list(output.get("by_wafer")),
        }
    if kind == "spc_summary":
        return {"kind": kind, "columns": _limit_list(output.get("columns"))}
    if kind == "anomaly_scan":
        columns = output.get("columns") if isinstance(output.get("columns"), list) else []
        return {
            "kind": kind,
            "z_threshold": output.get("z_threshold"),
            "total_anomaly_count": output.get("total_anomaly_count"),
            "columns": [
                {"column": item.get("column"), "anomaly_count": item.get("anomaly_count")}
                for item in columns[:MAX_SUMMARY_ITEMS]
                if isinstance(item, dict)
            ],
        }
    if kind == "correlation_scan":
        return {
            "kind": kind,
            "pass_correlations": _limit_list(output.get("pass_correlations")),
            "pairwise_correlations": _limit_list(output.get("pairwise_correlations")),
        }
    if kind == "markdown_report":
        sections = output.get("sections") if isinstance(output.get("sections"), dict) else {}
        return {
            "kind": kind,
            "profile": _summarize_tool_output(sections.get("profile")),
            "yield": _summarize_tool_output(sections.get("yield")),
            "spc": _summarize_tool_output(sections.get("spc")),
            "anomalies": _summarize_tool_output(sections.get("anomalies")),
            "correlations": _summarize_tool_output(sections.get("correlations")),
        }
    return {"kind": kind or "unknown", "shape": _shape(output)}


def _limit_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [redact_for_llm(item) for item in value[:MAX_SUMMARY_ITEMS]]


def _compact_value(value: Any) -> Any:
    if isinstance(value, str):
        return value[:MAX_SUMMARY_TEXT]
    if isinstance(value, int | float | bool) or value is None:
        return value
    return _shape(value)


def _shape(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {"type": "dict", "keys": list(value.keys())[:MAX_SUMMARY_ITEMS]}
    if isinstance(value, list):
        return {"type": "list", "length": len(value)}
    return {"type": type(value).__name__}
