from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from semicon_agent.llm.base import BaseLLM
from semicon_agent.models import AgentPlan, ToolResult
from semicon_agent.core.policy import ExecutionPolicy, RiskLevel
from semicon_agent.core.session import SQLiteRunStore
from semicon_agent.core.trace import RunEvent, TraceRecorder
from semicon_agent.tools.registry import ToolRegistry, build_default_registry
from semicon_agent.tools.runtime import ToolRuntime


@dataclass
class AgentRun:
    run_id: str
    request: str
    plan: AgentPlan
    tool_results: list[ToolResult]
    final_answer: str
    events: list[RunEvent]


class SemiconductorAgent:
    def __init__(
        self,
        llm: BaseLLM,
        registry: ToolRegistry | None = None,
        policy: ExecutionPolicy | None = None,
        run_store: SQLiteRunStore | None = None,
    ) -> None:
        self.llm = llm
        self.registry = registry or build_default_registry()
        self.policy = policy or ExecutionPolicy(allowed_roots=(Path.cwd(),))
        self.run_store = run_store

    def run(
        self,
        user_request: str,
        data_path: str | None = None,
        approved_risks: set[RiskLevel] | None = None,
        **context: Any,
    ) -> AgentRun:
        trace = TraceRecorder()
        run_context: dict[str, object] = dict(context)
        policy = self.policy
        if data_path:
            run_context["data_path"] = data_path
            policy = policy.with_allowed_root(Path(data_path).expanduser().resolve().parent)

        if approved_risks:
            policy = ExecutionPolicy(
                approved_risks=frozenset([*policy.approved_risks, *approved_risks]),
                allowed_roots=policy.allowed_roots,
                max_file_size_mb=policy.max_file_size_mb,
                allow_unc_paths=policy.allow_unc_paths,
            )

        if self.run_store:
            self.run_store.save_run_start(trace.run_id, user_request, run_context)
        trace.emit("run.start", "Agent run started.", request=user_request, context=run_context)
        trace.emit("llm.plan.start", "Requesting plan from LLM.")
        plan = self.llm.plan(user_request, self.registry.list(), run_context)
        trace.emit(
            "llm.plan.end",
            "LLM plan received.",
            reasoning=plan.reasoning,
            tool_calls=[call.model_dump() for call in plan.tool_calls],
        )

        tool_results: list[ToolResult] = []
        runtime = ToolRuntime(registry=self.registry, policy=policy, trace=trace)
        for call in plan.tool_calls:
            arguments = dict(call.arguments)
            if data_path:
                arguments["path"] = data_path
            tool_results.append(runtime.run(call.name, arguments))

        if tool_results:
            trace.emit("llm.synthesis.start", "Requesting final synthesis from LLM.")
            final_answer = self.llm.synthesize(user_request, tool_results, run_context)
            trace.emit("llm.synthesis.end", "Final synthesis received.")
        else:
            final_answer = plan.final_answer or "No answer was produced."

        status = "completed" if not any(result.error for result in tool_results) else "completed_with_errors"
        trace.emit("run.end", "Agent run finished.", status=status)
        if self.run_store:
            self.run_store.save_events(trace.events)
            self.run_store.save_run_end(trace.run_id, final_answer, status=status)

        return AgentRun(
            run_id=trace.run_id,
            request=user_request,
            plan=plan,
            tool_results=tool_results,
            final_answer=final_answer,
            events=trace.events,
        )
