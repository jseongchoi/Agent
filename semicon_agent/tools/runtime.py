from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from semicon_agent.core.policy import ExecutionPolicy
from semicon_agent.core.trace import TraceRecorder
from semicon_agent.models import ToolResult
from semicon_agent.tools.registry import ToolRegistry
from semicon_agent.tools.validation import ToolValidationError, validate_arguments


@dataclass
class ToolRuntime:
    registry: ToolRegistry
    policy: ExecutionPolicy
    trace: TraceRecorder

    def run(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        started = time.perf_counter()
        try:
            tool = self.registry.get(name)
        except KeyError as exc:
            self.trace.emit("tool.error", "Unknown tool requested.", tool=name, error=str(exc))
            return ToolResult(name=name, arguments=dict(arguments), error=str(exc))

        self.trace.emit("tool.policy", "Evaluating tool policy.", tool=name, risk_level=tool.risk_level)
        decision = self.policy.evaluate_tool(tool)
        if not decision.allowed:
            self.trace.emit("tool.denied", decision.reason, tool=name, decision=decision.action)
            return ToolResult(name=name, arguments=dict(arguments), error=decision.reason)

        try:
            validated = validate_arguments(tool.parameters, arguments)
            if "path" in validated:
                validated["path"] = str(self.policy.resolve_data_path(str(validated["path"])))
        except (ToolValidationError, PermissionError, OSError) as exc:
            self.trace.emit("tool.validation_error", str(exc), tool=name, arguments=arguments)
            return ToolResult(name=name, arguments=dict(arguments), error=str(exc))

        self.trace.emit("tool.start", "Starting tool execution.", tool=name, arguments=validated)
        try:
            output = tool.run(validated)
            duration_ms = int((time.perf_counter() - started) * 1000)
            self.trace.emit("tool.end", "Tool execution completed.", tool=name, duration_ms=duration_ms)
            return ToolResult(name=name, arguments=validated, output=output)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            self.trace.emit("tool.error", str(exc), tool=name, duration_ms=duration_ms)
            return ToolResult(name=name, arguments=validated, error=str(exc))
