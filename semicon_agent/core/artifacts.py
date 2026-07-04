from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any


class ArtifactStore:
    def __init__(self, root: str | Path = ".semicon_agent/artifacts") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_text(self, name: str, content: str) -> str:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return _artifact_name(path, self.root)

    def save_bytes(self, name: str, content: bytes) -> str:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return _artifact_name(path, self.root)

    def save_upload(self, original_name: str, content: bytes) -> str:
        suffix = Path(original_name).suffix.lower()
        if suffix not in {".csv", ".tsv", ".txt", ".xlsx", ".xls"}:
            raise ValueError(f"Unsupported upload type: {suffix}")
        return self.save_bytes(f"uploads/{uuid.uuid4().hex}{suffix}", content)

    def save_json(self, name: str, payload: Any) -> str:
        content = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        return self.save_text(name, content)

    def read_text(self, name: str) -> str:
        return self._path(name).read_text(encoding="utf-8")

    def path_for(self, name: str) -> Path:
        path = self._path(name)
        if not path.exists():
            raise FileNotFoundError(name)
        return path

    def list_artifacts(self) -> list[dict[str, object]]:
        artifacts = []
        for path in sorted(self.root.rglob("*")):
            if path.is_file():
                artifacts.append(
                    {
                        "name": _artifact_name(path, self.root),
                        "kind": _artifact_kind(path, self.root),
                        "size": path.stat().st_size,
                        "modified_at": path.stat().st_mtime,
                    }
                )
        return artifacts

    def _path(self, name: str) -> Path:
        safe_parts = [_safe_name(part) for part in Path(name).parts if part not in {"", ".", "/"}]
        if not safe_parts:
            raise ValueError("Artifact name cannot be empty.")
        path = self.root.joinpath(*safe_parts).resolve()
        root = self.root.resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError("Artifact path escapes artifact root.") from exc
        return path


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    if not cleaned:
        raise ValueError("Artifact name cannot be empty.")
    return cleaned[:160]


def _artifact_name(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _artifact_kind(path: Path, root: Path) -> str:
    parts = path.resolve().relative_to(root.resolve()).parts
    if parts and parts[0] == "uploads":
        return "upload"
    if parts and parts[0] == "reports":
        return "report"
    return "artifact"
