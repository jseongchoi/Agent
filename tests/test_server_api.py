from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from semicon_agent.server.api import create_app


DATA_PATH = Path(__file__).parents[1] / "examples" / "sample_wafer.csv"


def test_health_endpoint(tmp_path: Path) -> None:
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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

    assert response.status_code == 400
    assert "outside allowed server roots" in response.json()["detail"]


def test_bad_remote_open_model_endpoint_returns_400(tmp_path: Path) -> None:
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))

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


def test_index_renders_ui(tmp_path: Path) -> None:
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))

    response = client.get("/")

    assert response.status_code == 200
    assert "Semicon Agent" in response.text
    assert "/api/runs" in response.text
