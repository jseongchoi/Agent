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

## Quick Start

```powershell
python -m semicon_agent "analyze yield and SPC" --data examples/sample_wafer.csv
```

For the full architecture and extension guide, see
[`docs/AGENT_GUIDE.md`](docs/AGENT_GUIDE.md).

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

The semiconductor analysis tools are intentionally lightweight demo tools. The
main point is to validate agent planning, tool routing, execution, and later LLM
replacement. Replace `semicon_agent/tools/semiconductor.py` with production
analysis logic only when you need real data-science behavior.

## Test

```powershell
python -m pytest
```
