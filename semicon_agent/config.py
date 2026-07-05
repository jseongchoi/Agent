from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_roots(name: str) -> tuple[Path, ...]:
    value = os.getenv(name, "")
    if not value.strip():
        return ()
    return tuple(Path(part).expanduser() for part in value.split(os.pathsep) if part.strip())


@dataclass(frozen=True)
class AgentSettings:
    session_db: Path = Path(".semicon_agent/runs.sqlite")
    job_db: Path = Path(".semicon_agent/jobs.sqlite")
    artifact_root: Path = Path(".semicon_agent/artifacts")
    api_token: str | None = None
    open_model_base_url: str = "http://localhost:8000/v1"
    open_model_name: str = "open-model"
    open_model_api_key: str | None = None
    allow_remote_llm: bool = False
    max_steps: int = 3
    allowed_roots: tuple[Path, ...] = field(default_factory=lambda: (Path.cwd(),))

    @classmethod
    def from_env(cls, cwd: str | Path | None = None) -> AgentSettings:
        base_cwd = Path(cwd).expanduser().resolve() if cwd is not None else Path.cwd()
        allowed_roots = (base_cwd, *_env_roots("SEMICON_AGENT_ALLOWED_ROOTS"))
        return cls(
            session_db=Path(os.getenv("SEMICON_AGENT_SESSION_DB", ".semicon_agent/runs.sqlite")),
            job_db=Path(os.getenv("SEMICON_AGENT_JOB_DB", ".semicon_agent/jobs.sqlite")),
            artifact_root=Path(os.getenv("SEMICON_AGENT_ARTIFACT_ROOT", ".semicon_agent/artifacts")),
            api_token=os.getenv("SEMICON_AGENT_API_TOKEN"),
            open_model_base_url=os.getenv("OPEN_MODEL_BASE_URL", "http://localhost:8000/v1"),
            open_model_name=os.getenv("OPEN_MODEL_NAME", "open-model"),
            open_model_api_key=os.getenv("OPEN_MODEL_API_KEY"),
            allow_remote_llm=_env_bool("SEMICON_AGENT_ALLOW_REMOTE_LLM", False),
            max_steps=int(os.getenv("SEMICON_AGENT_MAX_STEPS", "3")),
            allowed_roots=allowed_roots,
        )

    def resolved_allowed_roots(
        self,
        extra_roots: tuple[str | Path, ...] = (),
        include_artifact_root: bool = False,
    ) -> tuple[Path, ...]:
        roots: list[Path] = [*self.allowed_roots, *[Path(root) for root in extra_roots]]
        if include_artifact_root:
            roots.append(self.artifact_root)
        resolved = [root.expanduser().resolve() for root in roots]
        return tuple(dict.fromkeys(resolved))


def validate_max_steps(value: int, upper_bound: int = 20) -> int:
    if value < 1 or value > upper_bound:
        raise ValueError(f"max_steps must be between 1 and {upper_bound}.")
    return value
