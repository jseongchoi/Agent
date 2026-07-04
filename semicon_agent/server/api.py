from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from semicon_agent.core.agent import AgentRun, SemiconductorAgent
from semicon_agent.core.artifacts import ArtifactStore
from semicon_agent.core.policy import ExecutionPolicy, RiskLevel
from semicon_agent.core.session import SQLiteRunStore
from semicon_agent.core.trace import redact
from semicon_agent.llm.mock import MockLLM
from semicon_agent.llm.open_model import OpenModelLLM


class RunRequest(BaseModel):
    request: str = Field(min_length=1)
    data_path: str | None = None
    data_artifact: str | None = None
    llm: Literal["mock", "open-model"] = "mock"
    base_url: str = "http://localhost:8000/v1"
    model: str = "open-model"
    api_key: str | None = None
    allow_remote_llm: bool = False
    max_steps: int = Field(default=3, ge=1, le=20)
    stream: bool = False
    approve_risks: list[RiskLevel] = Field(default_factory=list)


def create_app(
    session_db: str | Path = ".semicon_agent/runs.sqlite",
    artifact_root: str | Path = ".semicon_agent/artifacts",
    allowed_roots: tuple[str | Path, ...] | None = None,
) -> FastAPI:
    app = FastAPI(title="Semicon Agent", version="0.1.0")
    run_store = SQLiteRunStore(session_db)
    artifact_store = ArtifactStore(artifact_root)
    server_allowed_roots = tuple(Path(root).expanduser().resolve() for root in (allowed_roots or (Path.cwd(), artifact_store.root)))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _index_html()

    @app.post("/api/runs")
    def create_run(request: RunRequest) -> dict[str, object]:
        try:
            data_path = _resolve_run_data_path(request, artifact_store, server_allowed_roots)
            llm = _build_llm(request)
        except (ValueError, PermissionError, FileNotFoundError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        policy = _build_policy(request, server_allowed_roots)
        agent = SemiconductorAgent(llm=llm, policy=policy, run_store=run_store)
        run = agent.run(
            request.request,
            data_path=str(data_path) if data_path else None,
            approved_risks=set(request.approve_risks),
            max_steps=request.max_steps,
            stream=request.stream,
        )
        artifact_name = artifact_store.save_text(f"reports/{run.run_id}.md", run.final_answer)
        payload = _run_payload(run)
        payload["artifact"] = artifact_name
        return payload

    @app.get("/api/runs")
    def list_runs(limit: int = 20) -> list[dict[str, object]]:
        return run_store.list_runs(limit=limit)

    @app.get("/api/runs/{run_id}/trace")
    def get_trace(run_id: str) -> list[dict[str, object]]:
        events = run_store.get_events(run_id)
        if not events:
            raise HTTPException(status_code=404, detail="Run trace not found.")
        return events

    @app.get("/api/artifacts")
    def list_artifacts() -> list[dict[str, object]]:
        return artifact_store.list_artifacts()

    @app.post("/api/artifacts")
    async def upload_artifact(file: UploadFile = File(...)) -> dict[str, object]:
        content = await file.read()
        if len(content) > 100 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Upload exceeds 100 MB limit.")
        try:
            name = artifact_store.save_upload(file.filename or "upload", content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"name": name, "original_name": file.filename, "size": len(content)}

    @app.get("/api/artifacts/{name:path}")
    def get_artifact(name: str) -> FileResponse:
        try:
            path = artifact_store.path_for(name)
            return FileResponse(path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Artifact not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


def _build_llm(request: RunRequest):
    if request.llm == "open-model":
        return OpenModelLLM(
            base_url=request.base_url,
            model=request.model,
            api_key=request.api_key,
            allow_remote=request.allow_remote_llm,
        )
    return MockLLM()


def _build_policy(request: RunRequest, allowed_roots: tuple[Path, ...]) -> ExecutionPolicy:
    roots = list(allowed_roots)
    approved = {"safe", "read", *request.approve_risks}
    return ExecutionPolicy(approved_risks=frozenset(approved), allowed_roots=tuple(roots))


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
        <label for="file">Upload dataset</label>
        <input id="file" type="file" />
        <div class="row">
          <div>
            <label for="maxSteps">Max steps</label>
            <input id="maxSteps" type="number" min="1" max="20" value="3" />
          </div>
          <div>
            <label for="stream">Stream path</label>
            <select id="stream"><option value="false">off</option><option value="true">on</option></select>
          </div>
        </div>
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
          const upload = await fetch("/api/artifacts", { method: "POST", body: form });
          const uploaded = await upload.json();
          if (!upload.ok) throw new Error(JSON.stringify(uploaded));
          dataArtifact = uploaded.name;
        }
        const response = await fetch("/api/runs", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            request: document.getElementById("request").value,
            data_path: dataArtifact ? null : document.getElementById("data").value,
            data_artifact: dataArtifact,
            max_steps: Number(document.getElementById("maxSteps").value),
            stream: document.getElementById("stream").value === "true"
          })
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(JSON.stringify(payload));
        statusEl.textContent = `Completed: ${payload.run_id}`;
        outputEl.textContent = payload.final_answer + "\\n\\nArtifact: " + payload.artifact;
      } catch (error) {
        statusEl.textContent = "Error";
        outputEl.textContent = String(error);
      } finally {
        runButton.disabled = false;
      }
    });
  </script>
</body>
</html>
"""
