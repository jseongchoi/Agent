from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from semicon_agent.tools.base import RiskLevel, ToolSpec


PolicyAction = Literal["allow", "deny", "requires_approval"]


@dataclass(frozen=True)
class PolicyDecision:
    action: PolicyAction
    reason: str

    @property
    def allowed(self) -> bool:
        return self.action == "allow"


@dataclass(frozen=True)
class ExecutionPolicy:
    approved_risks: frozenset[RiskLevel] = frozenset({"safe", "read"})
    allowed_roots: tuple[Path, ...] = ()
    max_file_size_mb: int = 100
    allow_unc_paths: bool = False

    def evaluate_tool(self, tool: ToolSpec) -> PolicyDecision:
        if tool.risk_level not in self.approved_risks:
            if tool.requires_approval:
                return PolicyDecision(
                    "requires_approval",
                    f"Tool '{tool.name}' requires approval for risk '{tool.risk_level}'.",
                )
            return PolicyDecision(
                "deny",
                f"Tool '{tool.name}' risk '{tool.risk_level}' is not approved.",
            )
        return PolicyDecision("allow", f"Tool '{tool.name}' is allowed.")

    def resolve_data_path(self, raw_path: str) -> Path:
        if raw_path.startswith("~"):
            raise PermissionError("Home-directory paths are not allowed in tool arguments.")
        if raw_path.startswith("\\\\") and not self.allow_unc_paths:
            raise PermissionError("UNC/network paths are not allowed.")

        resolved = Path(raw_path).expanduser().resolve()
        roots = tuple(root.resolve() for root in self.allowed_roots)
        if roots and not any(_is_relative_to(resolved, root) for root in roots):
            root_list = ", ".join(str(root) for root in roots)
            raise PermissionError(f"Path is outside allowed roots: {resolved}. Allowed roots: {root_list}")
        if resolved.exists() and resolved.is_file():
            max_bytes = self.max_file_size_mb * 1024 * 1024
            if resolved.stat().st_size > max_bytes:
                raise PermissionError(f"File exceeds size limit of {self.max_file_size_mb} MB: {resolved}")
        return resolved

    def with_allowed_root(self, root: str | Path) -> ExecutionPolicy:
        resolved = Path(root).expanduser().resolve()
        roots = tuple(dict.fromkeys([*self.allowed_roots, resolved]))
        return ExecutionPolicy(
            approved_risks=self.approved_risks,
            allowed_roots=roots,
            max_file_size_mb=self.max_file_size_mb,
            allow_unc_paths=self.allow_unc_paths,
        )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
