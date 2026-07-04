from __future__ import annotations

from pathlib import Path
import secrets
from typing import Literal

from fastapi import FastAPI, File, Request, UploadFile
from fastapi import status as http_status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from semicon_agent.config import validate_max_steps
from semicon_agent.core.agent import AgentRun, SemiconductorAgent
from semicon_agent.core.artifacts import ArtifactStore
from semicon_agent.core.errors import AgentAPIError
from semicon_agent.core.observability import export_events_as_spans
from semicon_agent.core.policy import ExecutionPolicy, RiskLevel
from semicon_agent.core.session import SQLiteRunStore
from semicon_agent.core.trace import redact
from semicon_agent.llm.mock import MockLLM
from semicon_agent.llm.open_model import OpenModelLLM
from semicon_agent.server.jobs import InMemoryJobStore
from semicon_agent.tools.registry import build_default_registry


class RunRequest(BaseModel):
    request: str = Field(min_length=1)
    data_path: str | None = None
    data_artifact: str | None = None
    llm: Literal["mock", "open-model"] | None = None
    base_url: str = "http://localhost:8000/v1"
    model: str = "open-model"
    api_key: str | None = None
    allow_remote_llm: bool = False
    max_steps: int = Field(default=3, ge=1, le=20)
    stream: bool = False
    approve_risks: list[RiskLevel] = Field(default_factory=list)
    include_previous_runs: int = Field(default=0, ge=0, le=5)


def create_app(
    session_db: str | Path = ".semicon_agent/runs.sqlite",
    artifact_root: str | Path = ".semicon_agent/artifacts",
    allowed_roots: tuple[str | Path, ...] | None = None,
    default_llm: Literal["mock", "open-model"] = "mock",
    open_model_base_url: str = "http://localhost:8000/v1",
    open_model_name: str = "open-model",
    open_model_api_key: str | None = None,
    allow_remote_llm: bool = False,
    allow_client_llm_config: bool = False,
    allow_client_risk_approval: bool = False,
    debug_status: bool = False,
    api_token: str | None = None,
    job_workers: int = 2,
) -> FastAPI:
    app = FastAPI(title="Semicon Agent", version="0.1.0")
    run_store = SQLiteRunStore(session_db)
    artifact_store = ArtifactStore(artifact_root)
    job_store = InMemoryJobStore(max_workers=job_workers)
    app.add_event_handler("shutdown", job_store.shutdown)
    server_allowed_roots = _server_allowed_roots(allowed_roots, artifact_store.root)
    registry = build_default_registry()

    @app.exception_handler(AgentAPIError)
    def agent_api_error_handler(_request: Request, exc: AgentAPIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.info.message, "error": exc.info.to_dict()},
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/status")
    def status(http_request: Request) -> dict[str, object]:
        _require_api_token(http_request, api_token)
        payload = {
            "status": "ok",
            "version": app.version,
            "tool_count": len(registry.list()),
            "tools": [tool.name for tool in registry.list()],
            "artifact_count": len(artifact_store.list_artifacts()),
            "run_count": run_store.count_runs(),
            "job_counts": job_store.counts(),
            "default_llm": default_llm,
        }
        if debug_status:
            payload.update(
                {
                    "session_db": str(Path(session_db).expanduser().resolve()),
                    "artifact_root": str(artifact_store.root.resolve()),
                    "allowed_roots": [str(root) for root in server_allowed_roots],
                }
            )
        return payload

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _index_html()

    @app.post("/api/runs")
    def create_run(request: RunRequest, http_request: Request) -> dict[str, object]:
        _require_api_token(http_request, api_token)
        llm, policy, data_path = _prepare_run_request(
            request,
            artifact_store=artifact_store,
            server_allowed_roots=server_allowed_roots,
            default_llm=default_llm,
            open_model_base_url=open_model_base_url,
            open_model_name=open_model_name,
            open_model_api_key=open_model_api_key,
            allow_remote_llm=allow_remote_llm,
            allow_client_llm_config=allow_client_llm_config,
            allow_client_risk_approval=allow_client_risk_approval,
        )
        try:
            return _execute_run_request(
                request,
                llm=llm,
                policy=policy,
                data_path=data_path,
                run_store=run_store,
                artifact_store=artifact_store,
            )
        except RuntimeError as exc:
            raise AgentAPIError(502, "LLM_UPSTREAM_ERROR", str(exc), "upstream", retryable=True) from exc

    @app.post("/api/jobs", status_code=http_status.HTTP_202_ACCEPTED)
    def create_job(request: RunRequest, http_request: Request) -> dict[str, object]:
        _require_api_token(http_request, api_token)
        llm, policy, data_path = _prepare_run_request(
            request,
            artifact_store=artifact_store,
            server_allowed_roots=server_allowed_roots,
            default_llm=default_llm,
            open_model_base_url=open_model_base_url,
            open_model_name=open_model_name,
            open_model_api_key=open_model_api_key,
            allow_remote_llm=allow_remote_llm,
            allow_client_llm_config=allow_client_llm_config,
            allow_client_risk_approval=allow_client_risk_approval,
        )
        job = job_store.submit(
            lambda: _execute_run_request(
                request,
                llm=llm,
                policy=policy,
                data_path=data_path,
                run_store=run_store,
                artifact_store=artifact_store,
            )
        )
        return job.to_dict()

    @app.get("/api/jobs")
    def list_jobs(http_request: Request, limit: int = 20) -> list[dict[str, object]]:
        _require_api_token(http_request, api_token)
        return [job.to_dict() for job in job_store.list(limit=limit)]

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str, http_request: Request) -> dict[str, object]:
        _require_api_token(http_request, api_token)
        job = job_store.get(job_id)
        if job is None:
            raise AgentAPIError(404, "JOB_NOT_FOUND", "Job not found.", "not_found")
        return job.to_dict()

    @app.delete("/api/jobs/{job_id}", status_code=http_status.HTTP_202_ACCEPTED)
    def cancel_job(job_id: str, http_request: Request) -> dict[str, object]:
        _require_api_token(http_request, api_token)
        cancelled = job_store.cancel(job_id)
        if cancelled is None:
            raise AgentAPIError(404, "JOB_NOT_FOUND", "Job not found.", "not_found")
        if not cancelled:
            raise AgentAPIError(409, "JOB_NOT_CANCELLABLE", "Job cannot be cancelled in its current state.", "conflict")
        job = job_store.get(job_id)
        return job.to_dict() if job else {"job_id": job_id, "status": "cancelled"}

    @app.post("/api/jobs/{job_id}/retry", status_code=http_status.HTTP_202_ACCEPTED)
    def retry_job(job_id: str, http_request: Request) -> dict[str, object]:
        _require_api_token(http_request, api_token)
        try:
            job = job_store.retry(job_id)
        except ValueError as exc:
            raise AgentAPIError(409, "JOB_NOT_RETRYABLE", str(exc), "conflict") from exc
        if job is None:
            raise AgentAPIError(404, "JOB_NOT_FOUND", "Job not found.", "not_found")
        return job.to_dict()

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, http_request: Request) -> dict[str, object]:
        _require_api_token(http_request, api_token)
        run = run_store.get_run(run_id)
        if run is None:
            raise AgentAPIError(404, "RUN_NOT_FOUND", "Run not found.", "not_found")
        return run

    @app.get("/api/runs")
    def list_runs(http_request: Request, limit: int = 20) -> list[dict[str, object]]:
        _require_api_token(http_request, api_token)
        return run_store.list_runs(limit=limit)

    @app.get("/api/runs/{run_id}/trace")
    def get_trace(run_id: str, http_request: Request) -> list[dict[str, object]]:
        _require_api_token(http_request, api_token)
        events = run_store.get_events(run_id)
        if not events:
            raise AgentAPIError(404, "RUN_TRACE_NOT_FOUND", "Run trace not found.", "not_found")
        return events

    @app.get("/api/runs/{run_id}/otel")
    def get_trace_spans(run_id: str, http_request: Request) -> list[dict[str, object]]:
        _require_api_token(http_request, api_token)
        events = run_store.get_events(run_id)
        if not events:
            raise AgentAPIError(404, "RUN_TRACE_NOT_FOUND", "Run trace not found.", "not_found")
        return export_events_as_spans(events)

    @app.get("/api/artifacts")
    def list_artifacts(http_request: Request) -> list[dict[str, object]]:
        _require_api_token(http_request, api_token)
        return artifact_store.list_artifacts()

    @app.post("/api/artifacts")
    async def upload_artifact(http_request: Request, file: UploadFile = File(...)) -> dict[str, object]:
        _require_api_token(http_request, api_token)
        content = await file.read()
        if len(content) > 100 * 1024 * 1024:
            raise AgentAPIError(413, "UPLOAD_TOO_LARGE", "Upload exceeds 100 MB limit.", "validation")
        try:
            name = artifact_store.save_upload(file.filename or "upload", content)
        except ValueError as exc:
            raise AgentAPIError(400, "INVALID_UPLOAD", str(exc), "validation") from exc
        return {"name": name, "original_name": file.filename, "size": len(content)}

    @app.get("/api/artifacts/{name:path}")
    def get_artifact(name: str, http_request: Request) -> FileResponse:
        _require_api_token(http_request, api_token)
        try:
            path = artifact_store.path_for(name)
            return FileResponse(path)
        except FileNotFoundError as exc:
            raise AgentAPIError(404, "ARTIFACT_NOT_FOUND", "Artifact not found.", "not_found") from exc
        except ValueError as exc:
            raise AgentAPIError(400, "INVALID_ARTIFACT_NAME", str(exc), "validation") from exc

    return app


def _prepare_run_request(
    request: RunRequest,
    artifact_store: ArtifactStore,
    server_allowed_roots: tuple[Path, ...],
    default_llm: Literal["mock", "open-model"],
    open_model_base_url: str,
    open_model_name: str,
    open_model_api_key: str | None,
    allow_remote_llm: bool,
    allow_client_llm_config: bool,
    allow_client_risk_approval: bool,
):
    try:
        validate_max_steps(request.max_steps)
        data_path = _resolve_run_data_path(request, artifact_store, server_allowed_roots)
        llm = _build_llm(
            request,
            default_llm=default_llm,
            open_model_base_url=open_model_base_url,
            open_model_name=open_model_name,
            open_model_api_key=open_model_api_key,
            allow_remote_llm=allow_remote_llm,
            allow_client_llm_config=allow_client_llm_config,
        )
        policy = _build_policy(request, server_allowed_roots, allow_client_risk_approval=allow_client_risk_approval)
    except (ValueError, PermissionError, FileNotFoundError) as exc:
        if isinstance(exc, PermissionError):
            raise AgentAPIError(403, "PERMISSION_DENIED", str(exc), "permission") from exc
        if isinstance(exc, FileNotFoundError):
            raise AgentAPIError(404, "DATA_FILE_NOT_FOUND", str(exc), "not_found") from exc
        raise AgentAPIError(400, "INVALID_REQUEST", str(exc), "validation") from exc
    return llm, policy, data_path


def _execute_run_request(
    request: RunRequest,
    llm,
    policy: ExecutionPolicy,
    data_path: Path | None,
    run_store: SQLiteRunStore,
    artifact_store: ArtifactStore,
) -> dict[str, object]:
    agent = SemiconductorAgent(llm=llm, policy=policy, run_store=run_store)
    previous_runs = run_store.list_runs(limit=request.include_previous_runs) if request.include_previous_runs else []
    run = agent.run(
        request.request,
        data_path=str(data_path) if data_path else None,
        approved_risks=set(request.approve_risks),
        max_steps=request.max_steps,
        stream=request.stream,
        previous_runs=previous_runs,
    )
    artifact_name = artifact_store.save_text(f"reports/{run.run_id}.md", run.final_answer)
    payload = _run_payload(run)
    payload["artifact"] = artifact_name
    return payload


def _build_llm(
    request: RunRequest,
    default_llm: Literal["mock", "open-model"],
    open_model_base_url: str,
    open_model_name: str,
    open_model_api_key: str | None,
    allow_remote_llm: bool,
    allow_client_llm_config: bool,
):
    llm_name = request.llm or default_llm
    client_fields = {"base_url", "model", "api_key", "allow_remote_llm"} & request.model_fields_set
    if client_fields and not allow_client_llm_config:
        raise PermissionError("Client LLM configuration is disabled on this server.")
    if llm_name == "open-model":
        base_url = request.base_url if allow_client_llm_config else open_model_base_url
        model = request.model if allow_client_llm_config else open_model_name
        api_key = request.api_key if allow_client_llm_config else open_model_api_key
        allow_remote = request.allow_remote_llm if allow_client_llm_config else allow_remote_llm
        return OpenModelLLM(
            base_url=base_url,
            model=model,
            api_key=api_key,
            allow_remote=allow_remote,
        )
    return MockLLM()


def _build_policy(
    request: RunRequest,
    allowed_roots: tuple[Path, ...],
    allow_client_risk_approval: bool,
) -> ExecutionPolicy:
    if request.approve_risks and not allow_client_risk_approval:
        raise PermissionError("Client risk approval is disabled on this server.")
    roots = list(allowed_roots)
    approved = {"safe", "read", *(request.approve_risks if allow_client_risk_approval else [])}
    return ExecutionPolicy(approved_risks=frozenset(approved), allowed_roots=tuple(roots))


def _server_allowed_roots(allowed_roots: tuple[str | Path, ...] | None, artifact_root: Path) -> tuple[Path, ...]:
    base_roots = allowed_roots if allowed_roots is not None else (Path.cwd(),)
    roots = [Path(root).expanduser().resolve() for root in base_roots]
    roots.append(artifact_root.expanduser().resolve())
    return tuple(dict.fromkeys(roots))


def _resolve_run_data_path(
    request: RunRequest,
    artifact_store: ArtifactStore,
    allowed_roots: tuple[Path, ...],
) -> Path | None:
    if request.data_artifact and request.data_path:
        raise ValueError("Use either data_artifact or data_path, not both.")
    if request.data_artifact:
        return artifact_store.path_for(request.data_artifact)
    if not request.data_path:
        return None
    path = Path(request.data_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    if not any(_is_relative_to(path, root) for root in allowed_roots):
        raise PermissionError(f"data_path is outside allowed server roots: {path}")
    return path


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _require_api_token(request: Request, api_token: str | None) -> None:
    if not api_token:
        return
    authorization = request.headers.get("authorization", "")
    expected = f"Bearer {api_token}"
    if not secrets.compare_digest(authorization, expected):
        raise AgentAPIError(401, "AUTH_REQUIRED", "A valid bearer token is required.", "auth")


def _run_payload(run: AgentRun) -> dict[str, object]:
    return redact(
        {
            "run_id": run.run_id,
            "request": run.request,
            "plan": run.plan.model_dump(),
            "plans": [plan.model_dump() for plan in run.plans],
            "tool_results": [result.model_dump() for result in run.tool_results],
            "final_answer": run.final_answer,
            "step_count": run.step_count,
            "stop_reason": run.stop_reason,
            "events": [event.to_dict() for event in run.events],
        }
    )


def _index_html() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Semicon Agent</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; background: #f6f7f9; color: #15171a; }
    main { max-width: 1120px; margin: 0 auto; padding: 24px; }
    header { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 18px; }
    h1 { font-size: 24px; margin: 0; }
    .grid { display: grid; grid-template-columns: 360px 1fr; gap: 16px; align-items: start; }
    section { background: #fff; border: 1px solid #d9dde3; border-radius: 8px; padding: 16px; }
    label { display: block; font-size: 12px; font-weight: 650; margin: 12px 0 6px; }
    input, textarea, select { width: 100%; box-sizing: border-box; border: 1px solid #c6ccd4; border-radius: 6px; padding: 9px; font: inherit; }
    textarea { min-height: 96px; resize: vertical; }
    button { border: 0; border-radius: 6px; background: #1769e0; color: white; font-weight: 700; padding: 10px 12px; cursor: pointer; margin-top: 12px; }
    button:disabled { opacity: .55; cursor: default; }
    pre { white-space: pre-wrap; word-break: break-word; background: #101418; color: #f4f7fb; padding: 14px; border-radius: 8px; min-height: 280px; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .muted { color: #5b6472; font-size: 13px; }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Semicon Agent</h1>
      <span class="muted">Local agent runtime</span>
    </header>
    <div class="grid">
      <section>
        <label for="request">Request</label>
        <textarea id="request">create an overall report</textarea>
        <label for="data">Data path</label>
        <input id="data" value="examples/sample_wafer.csv" />
        <label for="token">API token</label>
        <input id="token" type="password" autocomplete="off" />
        <label for="file">Upload dataset</label>
        <input id="file" type="file" />
        <div class="row">
          <div>
            <label for="maxSteps">Max steps</label>
            <input id="maxSteps" type="number" min="1" max="20" value="3" />
          </div>
          <div>
            <label for="mode">Mode</label>
            <select id="mode"><option value="job">job</option><option value="sync">sync</option></select>
          </div>
        </div>
        <label for="stream">Stream path</label>
        <select id="stream"><option value="false">off</option><option value="true">on</option></select>
        <button id="run">Run Agent</button>
      </section>
      <section>
        <div class="muted" id="status">Idle</div>
        <pre id="output"></pre>
      </section>
    </div>
  </main>
  <script>
    const runButton = document.getElementById("run");
    const statusEl = document.getElementById("status");
    const outputEl = document.getElementById("output");
    runButton.addEventListener("click", async () => {
      runButton.disabled = true;
      statusEl.textContent = "Running";
      outputEl.textContent = "";
      try {
        let dataArtifact = null;
        const file = document.getElementById("file").files[0];
        if (file) {
          const form = new FormData();
          form.append("file", file);
          const upload = await fetch("/api/artifacts", { method: "POST", headers: apiHeaders(false), body: form });
          const uploaded = await upload.json();
          if (!upload.ok) throw new Error(JSON.stringify(uploaded));
          dataArtifact = uploaded.name;
        }
        const body = {
          request: document.getElementById("request").value,
          data_path: dataArtifact ? null : document.getElementById("data").value,
          data_artifact: dataArtifact,
          max_steps: Number(document.getElementById("maxSteps").value),
          stream: document.getElementById("stream").value === "true"
        };
        const mode = document.getElementById("mode").value;
        const response = await fetch(mode === "job" ? "/api/jobs" : "/api/runs", {
          method: "POST",
          headers: apiHeaders(true),
          body: JSON.stringify(body)
        });
        let payload = await response.json();
        if (!response.ok) throw new Error(JSON.stringify(payload));
        if (mode === "job") {
          statusEl.textContent = `Queued: ${payload.job_id}`;
          payload = await pollJob(payload.job_id);
          if (payload.status === "failed") throw new Error(payload.error || "Job failed");
          payload = payload.result;
        }
        statusEl.textContent = `Completed: ${payload.run_id}`;
        outputEl.textContent = payload.final_answer + "\\n\\nArtifact: " + payload.artifact;
      } catch (error) {
        statusEl.textContent = "Error";
        outputEl.textContent = String(error);
      } finally {
        runButton.disabled = false;
      }
    });
    async function pollJob(jobId) {
      for (let attempt = 0; attempt < 300; attempt += 1) {
        const response = await fetch(`/api/jobs/${jobId}`, { headers: apiHeaders(false) });
        const payload = await response.json();
        if (!response.ok) throw new Error(JSON.stringify(payload));
        statusEl.textContent = `Job ${payload.status}: ${jobId}`;
        if (payload.status === "completed" || payload.status === "failed") return payload;
        await new Promise(resolve => setTimeout(resolve, 500));
      }
      throw new Error("Job timed out");
    }
    function apiHeaders(json) {
      const headers = {};
      if (json) headers["Content-Type"] = "application/json";
      const token = document.getElementById("token").value;
      if (token) headers["Authorization"] = `Bearer ${token}`;
      return headers;
    }
  </script>
</body>
</html>
"""
