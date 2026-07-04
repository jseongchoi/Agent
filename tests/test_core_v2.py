from __future__ import annotations

from pathlib import Path

from semicon_agent.core.agent import SemiconductorAgent
from semicon_agent.core.approval import ApprovalRequest, ApprovalResult
from semicon_agent.models import AgentPlan, LLMStreamChunk, ToolCall, ToolResult
from semicon_agent.tools.base import ToolSpec
from semicon_agent.tools.registry import ToolRegistry


DATA_PATH = Path(__file__).parents[1] / "examples" / "sample_wafer.csv"


class SequenceLLM:
    def __init__(self, plans: list[AgentPlan]) -> None:
        self.plans = plans
        self.plan_calls = 0
        self.used_stream = False

    def plan(self, user_request: str, tools: list[ToolSpec], context: dict[str, object]) -> AgentPlan:
        index = min(self.plan_calls, len(self.plans) - 1)
        self.plan_calls += 1
        return self.plans[index]

    def synthesize(
        self,
        user_request: str,
        tool_results: list[ToolResult],
        context: dict[str, object],
    ) -> str:
        return "normal synthesis"

    def stream_synthesize(
        self,
        user_request: str,
        tool_results: list[ToolResult],
        context: dict[str, object],
    ):
        self.used_stream = True
        yield LLMStreamChunk(content="stream ")
        yield LLMStreamChunk(content="synthesis")
        yield LLMStreamChunk(done=True, event="done")


class ApproveAll:
    def request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        return ApprovalResult(True, "test approval")


def test_multi_step_orchestration_replans_until_final_answer() -> None:
    llm = SequenceLLM(
        [
            AgentPlan(tool_calls=[ToolCall(name="yield_summary")]),
            AgentPlan(final_answer="done"),
        ]
    )
    agent = SemiconductorAgent(llm=llm)

    run = agent.run("analyze yield", data_path=str(DATA_PATH), max_steps=3)

    assert llm.plan_calls == 2
    assert run.step_count == 2
    assert run.stop_reason == "final_answer"
    assert [result.name for result in run.tool_results] == ["yield_summary"]


def test_default_run_executes_static_plan_once() -> None:
    llm = SequenceLLM([AgentPlan(tool_calls=[ToolCall(name="yield_summary")])])
    agent = SemiconductorAgent(llm=llm)

    run = agent.run("analyze yield", data_path=str(DATA_PATH))

    assert llm.plan_calls == 1
    assert run.step_count == 1
    assert run.stop_reason == "max_steps"
    assert [result.name for result in run.tool_results] == ["yield_summary"]


def test_multi_step_stops_on_repeated_tool_calls() -> None:
    llm = SequenceLLM(
        [
            AgentPlan(tool_calls=[ToolCall(name="yield_summary")]),
            AgentPlan(tool_calls=[ToolCall(name="yield_summary")]),
        ]
    )
    agent = SemiconductorAgent(llm=llm)

    run = agent.run("analyze yield", data_path=str(DATA_PATH), max_steps=3)

    assert run.step_count == 2
    assert run.stop_reason == "repeated_tool_calls"
    assert [result.name for result in run.tool_results] == ["yield_summary"]


def test_streaming_synthesis_path_is_used() -> None:
    llm = SequenceLLM(
        [
            AgentPlan(tool_calls=[ToolCall(name="yield_summary")]),
            AgentPlan(final_answer="done"),
        ]
    )
    agent = SemiconductorAgent(llm=llm)

    run = agent.run("analyze yield", data_path=str(DATA_PATH), stream=True)

    assert llm.used_stream is True
    assert run.final_answer == "stream synthesis"
    assert any(event.event_type == "llm.stream.chunk" for event in run.events)


def test_approval_provider_can_approve_required_tool() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="external_export",
            description="Fake external tool for approval tests.",
            parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            handler=lambda: {"sent": True},
            risk_level="external",
            requires_approval=True,
        )
    )
    llm = SequenceLLM([AgentPlan(tool_calls=[ToolCall(name="external_export")]), AgentPlan(final_answer="done")])
    agent = SemiconductorAgent(llm=llm, registry=registry)

    run = agent.run("export", approval_provider=ApproveAll())

    assert run.tool_results[0].output == {"sent": True}
    assert any(event.event_type == "tool.approval_result" for event in run.events)
