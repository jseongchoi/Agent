# Semicon Agent

Python-first agent framework for semiconductor data analysis.

The framework keeps the LLM layer replaceable. It ships with a deterministic
`MockLLM` for local tests, and an OpenAI-compatible `OpenModelLLM` adapter for
future open-model APIs.

## Architecture

1. LLM gateway: `MockLLM` now, `OpenModelLLM` later.
2. Agent core: plan tool calls, execute tools, trace events, persist run history.
3. Tool runtime: validate arguments, enforce path boundaries, apply permission policy.
4. Orchestration loop: re-plan across bounded plan/act steps.
5. Approval layer: require human or programmatic approval for risky tools.
6. Streaming-ready LLM interface: expose synthesis as stream chunks.
7. Tool registry: expose Python demo functions with JSON-like schemas.
8. Semiconductor tools: lightweight placeholders for profile, yield, SPC/Cpk, anomaly, correlation, report.
9. CLI: run analysis, inspect sessions, and view traces from the terminal.
10. API/UI layer: FastAPI endpoints, local web UI, uploads, report artifacts.
11. Configuration: shared env-driven settings for CLI/server defaults.
12. Self-check: serverless end-to-end health check.

## Core Features

- Tool argument validation
- Workspace/data path policy
- Tool risk metadata and approval policy
- SQLite run/session store
- Redacted trace events
- Multi-step orchestration with `--max-steps`
- Interactive approval with `--interactive-approval`
- Streaming-ready synthesis with `--stream`
- Local mock LLM for deterministic tests
- OpenAI-compatible open-model adapter with remote endpoint safety checks
- Shared configuration via `SEMICON_AGENT_*` and `OPEN_MODEL_*` environment variables
- Serverless self-check command for CI or local validation

## Install

```powershell
python -m pip install -e ".[dev]"
```

## Quick Start

```powershell
python -m semicon_agent "analyze yield and SPC" --data examples/sample_wafer.csv
```

Run a serverless end-to-end self-check:

```powershell
python -m semicon_agent.self_check --data examples/sample_wafer.csv
# or, after editable install:
semicon-agent-check --data examples/sample_wafer.csv
```

Recommended reading order:

1. [`docs/BEGINNER_GUIDE.md`](docs/BEGINNER_GUIDE.md): first-time setup, concepts, commands, code tour, troubleshooting.
2. [`docs/AGENT_GUIDE.md`](docs/AGENT_GUIDE.md): deeper architecture, coding-agent internals, extension roadmap.

For a full report:

```powershell
python -m semicon_agent "create an overall semiconductor data report" --data examples/sample_wafer.csv
```

For a future OpenAI-compatible open-model API:

```powershell
$env:OPEN_MODEL_API_KEY="..."
python -m semicon_agent "analyze yield" --data examples/sample_wafer.csv --llm open-model --base-url http://localhost:8000/v1 --model my-open-model
```

Non-local open-model endpoints require HTTPS and `--allow-remote-llm`.

The API endpoint is expected to support `POST /chat/completions`.

List persisted runs:

```powershell
python -m semicon_agent --list-runs
```

Show trace events:

```powershell
python -m semicon_agent --show-trace <run_id>
```

Run with bounded re-planning and streaming synthesis:

```powershell
python -m semicon_agent "analyze yield" --data examples/sample_wafer.csv --max-steps 3 --stream
```

Prompt for tools that require approval:

```powershell
python -m semicon_agent "run approved task" --interactive-approval
```

Run the local API server and web UI:

```powershell
python -m semicon_agent.server --host 127.0.0.1 --port 8008 --allow-root examples
```

Then open `http://127.0.0.1:8008`.

Server API defaults are intentionally local-first:

- Client-provided LLM `base_url`, `api_key`, and `allow_remote_llm` are rejected unless the server starts with `--allow-client-llm-config`.
- Client-provided risk approvals are rejected unless the server starts with `--allow-client-risk-approval`.
- Detailed path status is hidden unless the server starts with `--debug-status`.

To run the server with a server-side open-model profile:

```powershell
$env:OPEN_MODEL_BASE_URL="http://localhost:8000/v1"
$env:OPEN_MODEL_NAME="my-open-model"
python -m semicon_agent.server --default-llm open-model
```

Primary API endpoints:

- `GET /health`
- `GET /api/status`
- `GET /`
- `POST /api/artifacts`
- `GET /api/artifacts`
- `GET /api/artifacts/{name}`
- `POST /api/runs`
- `GET /api/runs`
- `GET /api/runs/{run_id}/trace`

The semiconductor analysis tools are intentionally lightweight demo tools. The
main point is to validate agent planning, tool routing, execution, and later LLM
replacement. Replace `semicon_agent/tools/semiconductor.py` with production
analysis logic only when you need real data-science behavior.

Input data expectations:

- Supported files: `.csv`, `.tsv`, `.txt`, `.xlsx`, `.xls`
- Common role columns: `lot_id`, `wafer_id`, `hard_bin`, `soft_bin`, `is_pass`, `pass`, `result`, `status`
- If no pass/status column exists, `hard_bin == 1` or `soft_bin == 1` is treated as pass.
- Numeric columns that are not obvious IDs/bins are treated as measurement columns.

Useful environment variables:

- `SEMICON_AGENT_SESSION_DB`
- `SEMICON_AGENT_ARTIFACT_ROOT`
- `SEMICON_AGENT_ALLOWED_ROOTS`
- `SEMICON_AGENT_MAX_STEPS`
- `SEMICON_AGENT_ALLOW_REMOTE_LLM`
- `OPEN_MODEL_BASE_URL`
- `OPEN_MODEL_NAME`
- `OPEN_MODEL_API_KEY`

## Test

```powershell
python -m pytest -p no:cacheprovider
```
