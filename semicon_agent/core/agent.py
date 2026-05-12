from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from semicon_agent.llm.base import BaseLLM
from semicon_agent.models import AgentPlan, ToolResult
from semicon_agent.tools.registry import ToolRegistry, build_default_registry


@dataclass
class AgentRun:
    request: str
    plan: AgentPlan
    tool_results: list[ToolResult]
    final_answer: str


class SemiconductorAgent:
    def __init__(self, llm: BaseLLM, registry: ToolRegistry | None = None) -> None:
        self.llm = llm
        self.registry = registry or build_default_registry()

    def run(self, user_request: str, data_path: str | None = None, **context: Any) -> AgentRun:
        run_context: dict[str, object] = dict(context)
        if data_path:
            run_context["data_path"] = data_path

        plan = self.llm.plan(user_request, self.registry.list(), run_context)
        tool_results: list[ToolResult] = []
        for call in plan.tool_calls:
            arguments = dict(call.arguments)
            if "path" not in arguments and data_path:
                arguments["path"] = data_path
            try:
                output = self.registry.run(call.name, arguments)
                tool_results.append(
                    ToolResult(name=call.name, arguments=arguments, output=output)
                )
            except Exception as exc:
                tool_results.append(
                    ToolResult(name=call.name, arguments=arguments, error=str(exc))
                )

        if tool_results:
            final_answer = self.llm.synthesize(user_request, tool_results, run_context)
        else:
            final_answer = plan.final_answer or "No answer was produced."

        return AgentRun(
            request=user_request,
            plan=plan,
            tool_results=tool_results,
            final_answer=final_answer,
        )
