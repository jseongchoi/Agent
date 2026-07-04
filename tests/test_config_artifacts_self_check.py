from __future__ import annotations

from pathlib import Path

import pytest

from semicon_agent.config import AgentSettings
from semicon_agent.core.artifacts import ArtifactStore
from semicon_agent.self_check import run_self_check


DATA_PATH = Path(__file__).parents[1] / "examples" / "sample_wafer.csv"


def test_settings_reads_environment_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    extra = tmp_path / "extra"
    monkeypatch.setenv("SEMICON_AGENT_ALLOWED_ROOTS", str(extra))
    monkeypatch.setenv("SEMICON_AGENT_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("SEMICON_AGENT_API_TOKEN", "test-token")

    settings = AgentSettings.from_env(cwd=tmp_path / "cwd")
    roots = settings.resolved_allowed_roots(include_artifact_root=True)

    assert (tmp_path / "cwd").resolve() in roots
    assert extra.resolve() in roots
    assert (tmp_path / "artifacts").resolve() in roots
    assert settings.api_token == "test-token"


def test_artifact_store_rejects_escape_and_unsupported_upload(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")

    with pytest.raises(ValueError):
        store.save_text("../escape.md", "nope")
    with pytest.raises(ValueError):
        store.save_upload("payload.exe", b"nope")


def test_artifact_store_sniffs_upload_content(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")

    with pytest.raises(ValueError, match="NUL"):
        store.save_upload("payload.csv", b"a,b\n1,\x00\n")
    with pytest.raises(ValueError, match="ZIP workbook"):
        store.save_upload("payload.xlsx", b"not a workbook")
    with pytest.raises(ValueError, match="OLE workbook"):
        store.save_upload("payload.xls", b"not a workbook")


def test_serverless_self_check_runs_end_to_end(tmp_path: Path) -> None:
    payload = run_self_check(
        data_path=DATA_PATH,
        session_db=tmp_path / "self_check.sqlite",
        artifact_root=tmp_path / "artifacts",
    )

    assert payload["ok"] is True
    assert payload["tool_count"] == 1
    assert payload["report_artifact"].startswith("self_checks/")
    assert (tmp_path / "artifacts" / str(payload["report_artifact"])).exists()
