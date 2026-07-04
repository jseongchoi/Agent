from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from semicon_agent.server.api import create_app


DATA_PATH = Path(__file__).parents[1] / "examples" / "sample_wafer.csv"


def test_health_endpoint(tmp_path: Path) -> None:
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_endpoint_reports_runtime_shape(tmp_path: Path) -> None:
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))

    response = client.get("/api/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["tool_count"] >= 5
    assert "yield_summary" in payload["tools"]
    assert payload["run_count"] == 0
    assert "session_db" not in payload


def test_status_endpoint_can_expose_debug_paths_when_enabled(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            session_db=tmp_path / "runs.sqlite",
            artifact_root=tmp_path / "artifacts",
            debug_status=True,
        )
    )

    response = client.get("/api/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_db"].endswith("runs.sqlite")
    assert payload["allowed_roots"]


def test_run_endpoint_persists_run_trace_and_artifact(tmp_path: Path) -> None:
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))

    response = client.post(
        "/api/runs",
        json={
            "request": "analyze yield",
            "data_path": str(DATA_PATH),
            "max_steps": 3,
            "stream": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"]
    assert payload["artifact"].endswith(".md")
    assert "Yield: 75.00%" in payload["final_answer"]

    runs = client.get("/api/runs").json()
    assert runs[0]["run_id"] == payload["run_id"]

    trace = client.get(f"/api/runs/{payload['run_id']}/trace").json()
    assert any(event["event_type"] == "run.end" for event in trace)

    artifact = client.get(f"/api/artifacts/{payload['artifact']}")
    assert artifact.status_code == 200
    assert "Yield: 75.00%" in artifact.text


def test_upload_then_run_with_artifact(tmp_path: Path) -> None:
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))
    content = DATA_PATH.read_bytes()

    upload = client.post("/api/artifacts", files={"file": ("sample.csv", content, "text/csv")})

    assert upload.status_code == 200
    artifact_name = upload.json()["name"]
    assert artifact_name.startswith("uploads/")

    run = client.post(
        "/api/runs",
        json={
            "request": "analyze yield",
            "data_artifact": artifact_name,
            "max_steps": 3,
        },
    )

    assert run.status_code == 200
    assert "Yield: 75.00%" in run.json()["final_answer"]


def test_upload_xlsx_then_run_with_artifact(tmp_path: Path) -> None:
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))
    data = tmp_path / "sample.xlsx"
    pd.DataFrame(
        [
            {"wafer_id": "W01", "is_pass": True, "param": 1.0},
            {"wafer_id": "W01", "is_pass": False, "param": 2.0},
            {"wafer_id": "W02", "is_pass": True, "param": 3.0},
        ]
    ).to_excel(data, index=False)

    upload = client.post(
        "/api/artifacts",
        files={"file": ("sample.xlsx", data.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert upload.status_code == 200
    run = client.post(
        "/api/runs",
        json={
            "request": "analyze yield",
            "data_artifact": upload.json()["name"],
            "max_steps": 3,
        },
    )

    assert run.status_code == 200
    assert "Yield: 66.67%" in run.json()["final_answer"]


def test_run_rejects_data_path_outside_allowed_roots(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            session_db=tmp_path / "runs.sqlite",
            artifact_root=tmp_path / "artifacts",
            allowed_roots=(tmp_path / "allowed",),
        )
    )

    response = client.post(
        "/api/runs",
        json={
            "request": "analyze yield",
            "data_path": str(DATA_PATH),
        },
    )

    assert response.status_code == 403
    assert "outside allowed server roots" in response.json()["detail"]


def test_bad_remote_open_model_endpoint_returns_400(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            session_db=tmp_path / "runs.sqlite",
            artifact_root=tmp_path / "artifacts",
            allow_client_llm_config=True,
        )
    )

    response = client.post(
        "/api/runs",
        json={
            "request": "analyze yield",
            "data_path": str(DATA_PATH),
            "llm": "open-model",
            "base_url": "http://example.com/v1",
        },
    )

    assert response.status_code == 400
    assert "Remote open-model endpoints" in response.json()["detail"]


def test_client_llm_config_is_rejected_by_default(tmp_path: Path) -> None:
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))

    response = client.post(
        "/api/runs",
        json={
            "request": "analyze yield",
            "data_path": str(DATA_PATH),
            "llm": "open-model",
            "base_url": "http://localhost:8000/v1",
        },
    )

    assert response.status_code == 403
    assert "Client LLM configuration is disabled" in response.json()["detail"]


def test_client_llm_config_is_rejected_even_for_mock_runs(tmp_path: Path) -> None:
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))

    response = client.post(
        "/api/runs",
        json={
            "request": "analyze yield",
            "data_path": str(DATA_PATH),
            "api_key": "client-secret",
        },
    )

    assert response.status_code == 403
    assert "Client LLM configuration is disabled" in response.json()["detail"]


def test_client_risk_approval_is_rejected_by_default(tmp_path: Path) -> None:
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))

    response = client.post(
        "/api/runs",
        json={
            "request": "analyze yield",
            "data_path": str(DATA_PATH),
            "approve_risks": ["external"],
        },
    )

    assert response.status_code == 403
    assert "Client risk approval is disabled" in response.json()["detail"]


def test_open_model_runtime_failure_returns_502(tmp_path: Path, monkeypatch) -> None:
    class FailingLLM:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def plan(self, user_request, tools, context):
            raise RuntimeError("open-model unavailable")

    monkeypatch.setattr("semicon_agent.server.api.OpenModelLLM", FailingLLM)
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))

    response = client.post(
        "/api/runs",
        json={
            "request": "analyze yield",
            "data_path": str(DATA_PATH),
            "llm": "open-model",
        },
    )

    assert response.status_code == 502
    assert "open-model unavailable" in response.json()["detail"]


def test_index_renders_ui(tmp_path: Path) -> None:
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))

    response = client.get("/")

    assert response.status_code == 200
    assert "Semicon Agent" in response.text
    assert "/api/runs" in response.text
