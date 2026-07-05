from __future__ import annotations

import time
from pathlib import Path
from threading import Event

import pandas as pd
from fastapi.testclient import TestClient

from semicon_agent.server.api import create_app


DATA_PATH = Path(__file__).parents[1] / "examples" / "sample_wafer.csv"


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 5.0) -> dict[str, object]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in {"completed", "failed", "cancelled"}:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"Job did not finish within {timeout} seconds.")


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
    assert payload["job_counts"] == {"queued": 0, "running": 0, "completed": 0, "failed": 0, "cancelled": 0}
    assert "session_db" not in payload


def test_api_token_protects_api_routes(tmp_path: Path) -> None:
    client = TestClient(
        create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts", api_token="secret")
    )

    assert client.get("/health").status_code == 200

    blocked = client.get("/api/status")
    assert blocked.status_code == 401
    assert blocked.json()["error"]["code"] == "AUTH_REQUIRED"

    allowed = client.get("/api/status", headers={"Authorization": "Bearer secret"})
    assert allowed.status_code == 200


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
    assert payload["job_db"].endswith("jobs.sqlite")
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
    assert "events" not in payload
    assert "tool_results" not in payload
    assert payload["tool_result_count"] == 1

    runs = client.get("/api/runs").json()
    assert runs[0]["run_id"] == payload["run_id"]

    run_detail = client.get(f"/api/runs/{payload['run_id']}")
    assert run_detail.status_code == 200
    assert run_detail.json()["status"] == "completed"

    trace = client.get(f"/api/runs/{payload['run_id']}/trace").json()
    assert any(event["event_type"] == "run.end" for event in trace)

    spans = client.get(f"/api/runs/{payload['run_id']}/otel").json()
    assert spans[0]["trace_id"]
    assert any(span["name"] == "run.end" for span in spans)

    artifact = client.get(f"/api/artifacts/{payload['artifact']}")
    assert artifact.status_code == 200
    assert "Yield: 75.00%" in artifact.text


def test_run_endpoint_can_return_debug_payload(tmp_path: Path) -> None:
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))

    response = client.post(
        "/api/runs",
        json={
            "request": "analyze yield",
            "data_path": str(DATA_PATH),
            "max_steps": 3,
            "debug": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["events"]
    assert payload["tool_results"][0]["name"] == "yield_summary"


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


def test_invalid_upload_is_removed(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=artifacts))

    response = client.post(
        "/api/artifacts",
        files={"file": ("bad.xlsx", b"not a workbook", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )

    assert response.status_code == 400
    assert not list((artifacts / "uploads").glob("*"))


def test_job_endpoint_runs_agent_and_exposes_status(tmp_path: Path) -> None:
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))

    created = client.post(
        "/api/jobs",
        json={
            "request": "analyze yield",
            "data_path": str(DATA_PATH),
            "max_steps": 3,
        },
    )

    assert created.status_code == 202
    assert created.json()["status"] in {"queued", "running"}

    job = _wait_for_job(client, created.json()["job_id"])
    assert job["status"] == "completed"
    assert job["run_id"]
    assert "Yield: 75.00%" in job["result"]["final_answer"]

    listed = client.get("/api/jobs").json()
    assert listed[0]["job_id"] == job["job_id"]

    run_detail = client.get(f"/api/runs/{job['run_id']}")
    assert run_detail.status_code == 200
    assert run_detail.json()["status"] == "completed"


def test_job_metadata_survives_app_recreation(tmp_path: Path) -> None:
    session_db = tmp_path / "runs.sqlite"
    job_db = tmp_path / "jobs.sqlite"
    artifact_root = tmp_path / "artifacts"
    client = TestClient(create_app(session_db=session_db, job_db=job_db, artifact_root=artifact_root))

    created = client.post(
        "/api/jobs",
        json={
            "request": "analyze yield",
            "data_path": str(DATA_PATH),
            "max_steps": 3,
        },
    )
    completed = _wait_for_job(client, created.json()["job_id"])
    assert completed["status"] == "completed"

    restarted = TestClient(create_app(session_db=session_db, job_db=job_db, artifact_root=artifact_root))
    loaded = restarted.get(f"/api/jobs/{completed['job_id']}")

    assert loaded.status_code == 200
    assert loaded.json()["status"] == "completed"
    assert loaded.json()["run_id"] == completed["run_id"]


def test_job_endpoint_returns_failed_status_for_runtime_error(tmp_path: Path, monkeypatch) -> None:
    class FailingLLM:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def plan(self, user_request, tools, context):
            raise RuntimeError("job llm unavailable")

    monkeypatch.setattr("semicon_agent.server.api.OpenModelLLM", FailingLLM)
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))

    created = client.post(
        "/api/jobs",
        json={
            "request": "analyze yield",
            "data_path": str(DATA_PATH),
            "llm": "open-model",
        },
    )

    assert created.status_code == 202
    job = _wait_for_job(client, created.json()["job_id"])
    assert job["status"] == "failed"
    assert "job llm unavailable" in job["error"]


def test_job_endpoint_can_retry_failed_job(tmp_path: Path, monkeypatch) -> None:
    calls = {"count": 0}

    def flaky_execute(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("transient failure")
        return {"run_id": "retry-run", "final_answer": "retried", "artifact": "reports/retry.md"}

    monkeypatch.setattr("semicon_agent.server.api._execute_run_request", flaky_execute)
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))

    created = client.post(
        "/api/jobs",
        json={
            "request": "analyze yield",
            "data_path": str(DATA_PATH),
            "max_steps": 3,
        },
    )
    failed = _wait_for_job(client, created.json()["job_id"])
    assert failed["status"] == "failed"

    retried = client.post(f"/api/jobs/{failed['job_id']}/retry")
    assert retried.status_code == 202
    completed = _wait_for_job(client, retried.json()["job_id"])
    assert completed["status"] == "completed"
    assert completed["run_id"] == "retry-run"


def test_job_endpoint_can_cancel_queued_job(tmp_path: Path, monkeypatch) -> None:
    started = Event()
    release = Event()

    def slow_execute(*args, **kwargs):
        started.set()
        release.wait(timeout=5)
        return {"run_id": "slow-run", "final_answer": "done", "artifact": "reports/slow.md"}

    monkeypatch.setattr("semicon_agent.server.api._execute_run_request", slow_execute)
    client = TestClient(
        create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts", job_workers=1)
    )

    first = client.post("/api/jobs", json={"request": "analyze yield", "data_path": str(DATA_PATH)})
    assert first.status_code == 202
    assert started.wait(timeout=2)

    second = client.post("/api/jobs", json={"request": "analyze yield", "data_path": str(DATA_PATH)})
    cancelled = client.delete(f"/api/jobs/{second.json()['job_id']}")
    release.set()

    assert cancelled.status_code == 202
    assert cancelled.json()["status"] == "cancelled"


def test_missing_job_and_run_return_404(tmp_path: Path) -> None:
    client = TestClient(create_app(session_db=tmp_path / "runs.sqlite", artifact_root=tmp_path / "artifacts"))

    missing_job = client.get("/api/jobs/missing")
    assert missing_job.status_code == 404
    assert missing_job.json()["error"]["code"] == "JOB_NOT_FOUND"

    missing_run = client.get("/api/runs/missing")
    assert missing_run.status_code == 404
    assert missing_run.json()["error"]["code"] == "RUN_NOT_FOUND"


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
    assert "/api/jobs" in response.text
