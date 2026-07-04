from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentPlan(BaseModel):
    reasoning: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    final_answer: str | None = None


class ToolResult(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    output: Any = None
    error: str | None = None


class LLMStreamChunk(BaseModel):
    content: str = ""
    done: bool = False
    event: str = "message"
