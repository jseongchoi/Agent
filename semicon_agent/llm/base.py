from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from semicon_agent.models import AgentPlan, LLMStreamChunk, ToolResult
from semicon_agent.tools.base import ToolSpec


class BaseLLM(Protocol):
    def plan(
        self,
        user_request: str,
        tools: list[ToolSpec],
        context: dict[str, object],
    ) -> AgentPlan:
        """Return an agent plan with zero or more tool calls."""

    def synthesize(
        self,
        user_request: str,
        tool_results: list[ToolResult],
        context: dict[str, object],
    ) -> str:
        """Return the final user-facing answer."""


class StreamingLLM(BaseLLM, Protocol):
    def stream_synthesize(
        self,
        user_request: str,
        tool_results: list[ToolResult],
        context: dict[str, object],
    ) -> Iterator[LLMStreamChunk]:
        """Yield a final answer as stream chunks."""
