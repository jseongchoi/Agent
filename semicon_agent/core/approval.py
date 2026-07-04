from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ApprovalRequest:
    tool_name: str
    risk_level: str
    reason: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ApprovalResult:
    approved: bool
    reason: str


class ApprovalProvider(Protocol):
    def request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        """Return whether a pending tool call should be approved."""


class DenyApprovalProvider:
    def request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        return ApprovalResult(False, "Tool requires approval, but no approval provider approved it.")


class AutoApprovalProvider:
    def request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        return ApprovalResult(True, "Approved automatically.")


class ConsoleApprovalProvider:
    def request_approval(self, request: ApprovalRequest) -> ApprovalResult:
        print(f"Tool approval required: {request.tool_name}")
        print(f"Risk: {request.risk_level}")
        print(f"Reason: {request.reason}")
        answer = input("Approve this tool call? [y/N] ").strip().lower()
        if answer in {"y", "yes"}:
            return ApprovalResult(True, "Approved by user.")
        return ApprovalResult(False, "Denied by user.")
