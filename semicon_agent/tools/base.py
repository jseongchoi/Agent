from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal


RiskLevel = Literal["safe", "read", "write", "external", "destructive"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    risk_level: RiskLevel = "safe"
    effects: tuple[str, ...] = ()
    requires_approval: bool = False
    data_access: tuple[str, ...] = ()
    path_fields: tuple[str, ...] = ("path",)

    def run(self, arguments: dict[str, Any]) -> Any:
        return self.handler(**arguments)
