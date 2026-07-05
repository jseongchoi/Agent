from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Literal

from fastapi import Request

from semicon_agent.core.errors import AgentAPIError


Role = Literal["read", "write", "admin"]
ROLE_LEVELS: dict[Role, int] = {"read": 1, "write": 2, "admin": 3}


@dataclass(frozen=True)
class AuthPolicy:
    tokens: dict[str, Role]

    @classmethod
    def from_config(cls, api_token: str | None = None, api_tokens: dict[str, Role] | None = None) -> AuthPolicy:
        tokens: dict[str, Role] = dict(api_tokens or {})
        if api_token:
            tokens[api_token] = "admin"
        return cls(tokens=tokens)

    @property
    def enabled(self) -> bool:
        return bool(self.tokens)

    def require(self, request: Request, role: Role) -> None:
        if not self.enabled:
            return
        authorization = request.headers.get("authorization", "")
        prefix = "Bearer "
        if not authorization.startswith(prefix):
            raise AgentAPIError(401, "AUTH_REQUIRED", "A valid bearer token is required.", "auth")
        token = authorization[len(prefix) :]
        actual = self._role_for_token(token)
        if actual is None:
            raise AgentAPIError(401, "AUTH_REQUIRED", "A valid bearer token is required.", "auth")
        if ROLE_LEVELS[actual] < ROLE_LEVELS[role]:
            raise AgentAPIError(403, "AUTH_FORBIDDEN", f"Role '{role}' is required for this API route.", "auth")

    def _role_for_token(self, token: str) -> Role | None:
        for expected, role in self.tokens.items():
            if secrets.compare_digest(token, expected):
                return role
        return None


def parse_api_tokens(value: str | None) -> dict[str, Role]:
    tokens: dict[str, Role] = {}
    if not value:
        return tokens
    for raw_entry in value.split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        try:
            role, token = entry.split(":", 1)
        except ValueError as exc:
            raise ValueError("API token entries must use role:token format.") from exc
        normalized = role.strip().lower()
        if normalized not in ROLE_LEVELS:
            raise ValueError("API token role must be read, write, or admin.")
        token = token.strip()
        if not token:
            raise ValueError("API token cannot be empty.")
        tokens[token] = normalized  # type: ignore[assignment]
    return tokens
