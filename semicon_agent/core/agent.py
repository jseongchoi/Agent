from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from semicon_agent.core.approval import ApprovalProvider
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
    plans: list[AgentPlan]
    tool_results: list[ToolResult]
    final_answer: str
    events: list[RunEvent]
    step_count: int
    stop_reason: str


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
        approval_provider: ApprovalProvider | None = None,
        max_steps: int = 1,
        stream: bool = False,
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
        trace.emit("run.start", "Agent run started.", request=user_request, context=run_context, max_steps=max_steps)
        plans: list[AgentPlan] = []
        tool_results: list[ToolResult] = []
        stop_reason = "max_steps"
        seen_tool_batches: set[tuple[tuple[str, str], ...]] = set()
        runtime = ToolRuntime(
            registry=self.registry,
            policy=policy,
            trace=trace,
            approval_provider=approval_provider,
        )
        for step_index in range(max_steps):
            step_context = {
                **run_context,
                "step_index": step_index,
                "completed_tools": [result.name for result in tool_results if not result.error],
                "tool_results": [result.model_dump() for result in tool_results],
            }
            trace.emit("llm.plan.start", "Requesting plan from LLM.", step_index=step_index)
            plan = self.llm.plan(user_request, self.registry.list(), step_context)
            plans.append(plan)
            trace.emit(
                "llm.plan.end",
                "LLM plan received.",
                step_index=step_index,
                reasoning=plan.reasoning,
                tool_calls=[call.model_dump() for call in plan.tool_calls],
                final_answer=plan.final_answer,
            )

            if not plan.tool_calls:
                stop_reason = "final_answer" if plan.final_answer else "no_tool_calls"
                break

            tool_batch = tuple((call.name, repr(sorted(call.arguments.items()))) for call in plan.tool_calls)
            if tool_batch in seen_tool_batches:
                stop_reason = "repeated_tool_calls"
                trace.emit("run.stop", "Stopping because the same tool call batch repeated.", step_index=step_index)
                break
            seen_tool_batches.add(tool_batch)

            step_results: list[ToolResult] = []
            for call in plan.tool_calls:
                arguments = dict(call.arguments)
                if data_path:
                    arguments["path"] = data_path
                step_results.append(runtime.run(call.name, arguments))
            tool_results.extend(step_results)

            if any(result.error for result in step_results):
                stop_reason = "tool_error"
                break

        if tool_results:
            trace.emit("llm.synthesis.start", "Requesting final synthesis from LLM.")
            if stream:
                chunks = []
                stream_synthesize = getattr(self.llm, "stream_synthesize", None)
                if stream_synthesize is None:
                    chunks.append(self.llm.synthesize(user_request, tool_results, run_context))
                else:
                    iterator = stream_synthesize(user_request, tool_results, run_context)
                    for chunk in iterator:
                        trace.emit("llm.stream.chunk", "Received synthesis stream chunk.", event=chunk.event, done=chunk.done)
                        chunks.append(chunk.content)
                final_answer = "".join(chunks)
            else:
                final_answer = self.llm.synthesize(user_request, tool_results, run_context)
            trace.emit("llm.synthesis.end", "Final synthesis received.")
        else:
            plan = plans[-1] if plans else AgentPlan()
            final_answer = plan.final_answer or "No answer was produced."

        status = "completed" if not any(result.error for result in tool_results) else "completed_with_errors"
        latest_plan = plans[-1] if plans else AgentPlan()
        trace.emit("run.end", "Agent run finished.", status=status, stop_reason=stop_reason)
        if self.run_store:
            self.run_store.save_events(trace.events)
            self.run_store.save_run_end(trace.run_id, final_answer, status=status)

        return AgentRun(
            run_id=trace.run_id,
            request=user_request,
            plan=latest_plan,
            plans=plans,
            tool_results=tool_results,
            final_answer=final_answer,
            events=trace.events,
            step_count=len(plans),
            stop_reason=stop_reason,
        )
