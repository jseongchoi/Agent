from __future__ import annotations

import io
import json
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any


TEXT_UPLOAD_SUFFIXES = {".csv", ".tsv", ".txt"}
EXCEL_UPLOAD_SUFFIXES = {".xlsx", ".xls"}
SUPPORTED_UPLOAD_SUFFIXES = TEXT_UPLOAD_SUFFIXES | EXCEL_UPLOAD_SUFFIXES
MAX_XLSX_ENTRIES = 1_000
MAX_XLSX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


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
        if suffix not in SUPPORTED_UPLOAD_SUFFIXES:
            raise ValueError(f"Unsupported upload type: {suffix}")
        _validate_upload_content(suffix, content)
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


def _validate_upload_content(suffix: str, content: bytes) -> None:
    if not content:
        raise ValueError("Upload cannot be empty.")
    if suffix in TEXT_UPLOAD_SUFFIXES:
        if b"\x00" in content[:8192]:
            raise ValueError("Text upload contains NUL bytes.")
        return
    if suffix == ".xlsx":
        _validate_xlsx_content(content)
        return
    if suffix == ".xls":
        if not content.startswith(OLE2_MAGIC):
            raise ValueError("XLS upload does not look like an OLE workbook.")
        return


def _validate_xlsx_content(content: bytes) -> None:
    if not content.startswith(b"PK"):
        raise ValueError("XLSX upload does not look like a ZIP workbook.")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as workbook:
            entries = workbook.infolist()
            if len(entries) > MAX_XLSX_ENTRIES:
                raise ValueError(f"XLSX upload exceeds archive entry limit of {MAX_XLSX_ENTRIES}.")
            total_size = 0
            for entry in entries:
                total_size += entry.file_size
                _validate_zip_entry(entry.filename)
                if entry.filename.lower().endswith("vbaproject.bin"):
                    raise ValueError("Macro-enabled workbook content is not allowed for .xlsx uploads.")
                if total_size > MAX_XLSX_UNCOMPRESSED_BYTES:
                    raise ValueError("XLSX upload expands beyond the uncompressed size limit.")
    except zipfile.BadZipFile as exc:
        raise ValueError("XLSX upload is not a valid ZIP workbook.") from exc


def _validate_zip_entry(name: str) -> None:
    normalized = name.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    if normalized.startswith("/") or ".." in parts:
        raise ValueError("XLSX upload contains an unsafe archive path.")
