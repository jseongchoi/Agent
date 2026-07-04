from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ErrorCategory = Literal["auth", "validation", "permission", "not_found", "conflict", "upstream", "runtime"]


@dataclass(frozen=True)
class ErrorInfo:
    code: str
    message: str
    category: ErrorCategory
    retryable: bool = False
    details: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "code": self.code,
            "message": self.message,
            "category": self.category,
            "retryable": self.retryable,
        }
        if self.details:
            payload["details"] = self.details
        return payload


class AgentAPIError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        category: ErrorCategory,
        retryable: bool = False,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.info = ErrorInfo(
            code=code,
            message=message,
            category=category,
            retryable=retryable,
            details=details or {},
        )
