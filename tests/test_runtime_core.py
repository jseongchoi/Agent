from __future__ import annotations

from pathlib import Path

import pytest

from semicon_agent.core.agent import SemiconductorAgent
from semicon_agent.core.policy import ExecutionPolicy
from semicon_agent.core.session import SQLiteRunStore
from semicon_agent.llm.open_model import OpenModelLLM
from semicon_agent.models import AgentPlan, ToolCall, ToolResult
from semicon_agent.tools.base import ToolSpec
from semicon_agent.tools.registry import ToolRegistry
from semicon_agent.tools.validation import ToolValidationError, validate_arguments


DATA_PATH = Path(__file__).parents[1] / "examples" / "sample_wafer.csv"


class StaticLLM:
    def __init__(self, plan: AgentPlan) -> None:
        self._plan = plan

    def plan(self, user_request: str, tools: list[ToolSpec], context: dict[str, object]) -> AgentPlan:
        return self._plan

    def synthesize(
        self,
        user_request: str,
        tool_results: list[ToolResult],
        context: dict[str, object],
    ) -> str:
        errors = [result.error for result in tool_results if result.error]
        if errors:
            return "ERROR: " + "; ".join(errors)
        return "OK"


def test_argument_validation_rejects_unknown_and_out_of_bounds_args() -> None:
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "max_examples": {"type": "integer", "default": 10, "minimum": 1, "maximum": 100},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    assert validate_arguments(schema, {"path": "data.csv"})["max_examples"] == 10
    with pytest.raises(ToolValidationError):
        validate_arguments(schema, {"path": "data.csv", "extra": True})
    with pytest.raises(ToolValidationError):
        validate_arguments(schema, {"path": "data.csv", "max_examples": 1000})


def test_agent_locks_tool_path_to_runtime_data_path() -> None:
    plan = AgentPlan(
        tool_calls=[
            ToolCall(
                name="dataset_profile",
                arguments={"path": "C:/Windows/System32/drivers/etc/hosts"},
            )
        ]
    )
    agent = SemiconductorAgent(llm=StaticLLM(plan))

    run = agent.run("profile data", data_path=str(DATA_PATH))

    assert run.tool_results[0].error is None
    assert Path(run.tool_results[0].arguments["path"]).resolve() == DATA_PATH.resolve()


def test_path_policy_rejects_paths_outside_allowed_roots(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.csv"
    outside.write_text("a,b\n1,2\n", encoding="utf-8")
    policy = ExecutionPolicy(allowed_roots=(tmp_path,))
    plan = AgentPlan(tool_calls=[ToolCall(name="dataset_profile", arguments={"path": str(outside)})])
    agent = SemiconductorAgent(llm=StaticLLM(plan), policy=policy)

    run = agent.run("profile data")

    assert "outside allowed roots" in str(run.tool_results[0].error)


def test_permission_policy_blocks_unapproved_destructive_tool() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="dangerous_delete",
            description="Fake destructive tool for policy tests.",
            parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            handler=lambda: {"deleted": True},
            risk_level="destructive",
            requires_approval=True,
        )
    )
    plan = AgentPlan(tool_calls=[ToolCall(name="dangerous_delete")])
    agent = SemiconductorAgent(llm=StaticLLM(plan), registry=registry)

    blocked = agent.run("delete")
    approved = agent.run("delete", approved_risks={"destructive"})

    assert "requires approval" in str(blocked.tool_results[0].error)
    assert approved.tool_results[0].output == {"deleted": True}


def test_sqlite_run_store_persists_runs_and_events(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    agent = SemiconductorAgent(llm=StaticLLM(AgentPlan(tool_calls=[ToolCall(name="yield_summary")])), run_store=store)

    run = agent.run("yield", data_path=str(DATA_PATH))
    runs = store.list_runs()
    events = store.get_events(run.run_id)

    assert runs[0]["run_id"] == run.run_id
    assert any(event["event_type"] == "tool.start" for event in events)
    assert any(event["event_type"] == "run.end" for event in events)


def test_open_model_endpoint_policy() -> None:
    OpenModelLLM(base_url="http://localhost:8000/v1", model="demo")

    with pytest.raises(ValueError):
        OpenModelLLM(base_url="http://example.com/v1", model="demo")
    with pytest.raises(ValueError):
        OpenModelLLM(base_url="http://example.com/v1", model="demo", allow_remote=True)

    OpenModelLLM(base_url="https://example.com/v1", model="demo", allow_remote=True)
