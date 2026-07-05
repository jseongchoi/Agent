from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


class AgentCancelledError(RuntimeError):
    pass


@dataclass(frozen=True)
class CancellationToken:
    is_cancelled: Callable[[], bool]
    reason: str = "Agent run was cancelled."

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            raise AgentCancelledError(self.reason)
