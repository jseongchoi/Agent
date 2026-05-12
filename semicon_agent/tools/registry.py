from __future__ import annotations

from semicon_agent.tools.base import ToolSpec
from semicon_agent.tools.semiconductor import build_semiconductor_tools


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def list(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc

    def run(self, name: str, arguments: dict[str, object]) -> object:
        return self.get(name).run(dict(arguments))


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in build_semiconductor_tools():
        registry.register(tool)
    return registry
