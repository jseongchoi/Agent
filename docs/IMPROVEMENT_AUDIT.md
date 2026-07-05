# Semicon Agent Improvement Audit

This document records the empirical audit performed after core v7. It separates
items that were fixed immediately from items that remain as engineering backlog.

## Verification Matrix

The following checks were run against the repository:

| Check | Result |
| --- | --- |
| `python -m pip install -e ".[dev]"` | Passed |
| `python -m pip check` | Passed |
| `python -m pytest -p no:cacheprovider` | Passed, 58 tests |
| `python -m semicon_agent.self_check --data examples/sample_wafer.csv` | Passed |
| `python -m semicon_agent.eval` | Passed |
| `semicon-agent-check --data examples/sample_wafer.csv` | Passed after editable reinstall |
| `semicon-agent "analyze yield and SPC" --data examples/sample_wafer.csv` | Passed |
| `semicon-agent --list-runs` | Passed |
| `semicon-agent-server --help` | Passed |
| Markdown local link check | Passed |
| `python -m compileall -q semicon_agent tests examples` | Passed |
| API TestClient audit: health/status/run/trace/otel/artifact/job/auth/security blocks | Passed |

## Fixed During This Audit

| Area | Finding | Fix |
| --- | --- | --- |
| Packaging | `semicon-agent-check` was unavailable until editable reinstall. | Reinstalled locally and clarified that console scripts require install/reinstall in docs. |
| Excel support | Docs and upload allow `.xls`, but runtime dependencies did not include `xlrd`. | Added `xlrd>=2.0` to runtime dependencies. |
| Excel regression coverage | `.xlsx` file loading and upload-run flow were not directly tested. | Added `load_table` `.xlsx` test and API upload `.xlsx` run test. |
| Public API consistency | `ArtifactStore` was available at top-level package but not `semicon_agent.core`. | Exported `ArtifactStore` from `semicon_agent.core`. |
| API execution model | Long API work only had a synchronous `/api/runs` path. | Added in-memory `/api/jobs` with 202 creation and status polling. |
| Run status | There was no direct `GET /api/runs/{run_id}` endpoint. | Added run detail lookup. |
| Data size limits | Table loading did not enforce row/column limits. | Added row/column limits in `load_table` and regression tests. |
| API auth boundary | Local server had no optional authentication gate. | Added optional bearer token auth for `/api/*` via `SEMICON_AGENT_API_TOKEN` or `--api-token`. |
| Error taxonomy | API errors returned only broad strings. | Added structured `error.code/category/retryable` payloads while preserving `detail`. |
| Upload sniffing | Upload validation trusted extension too much. | Added text NUL checks, Excel signature checks, XLSX archive path/entry/size checks, and `.xlsx` macro-content rejection. |
| Direct parser guard | Direct `data_path` parsing could read oversized files. | Added file size limit before pandas parsing. |
| Job operations | Background jobs could not be cancelled or retried. | Added queued-job cancellation and failed/cancelled job retry endpoints. |
| Observability export | Trace events were only available as internal event JSON. | Added `/api/runs/{run_id}/otel` span-like JSON export. |
| Regression eval | There was no deterministic eval suite for agent behavior. | Added `semicon_agent.eval` and `semicon-agent-eval`. |
| CI | GitHub Actions workflow was missing. | Added matrix CI for pytest, self-check, and eval. |
| Durable job metadata | Job metadata disappeared when the API process restarted. | Added SQLite job metadata persistence and app-recreation regression coverage. |
| API payload size | Run/job results returned full plan/tool/event payloads by default. | Added compact default payloads and `debug: true` for details. |
| Parser hardening | Parser timeout and cell budget were missing. | Added parser timeout and cell budget to `load_table`. |
| Upload memory path | API upload read the whole file before saving. | Switched API upload to chunked writes with cleanup on validation failure. |

## Current Strengths

- Deterministic local development path through `MockLLM`.
- OpenAI-compatible `OpenModelLLM` adapter with local-first endpoint guard.
- Tool registry and schema validation.
- Data path boundary enforced through `ExecutionPolicy` and `ToolRuntime`.
- Risk-level policy and approval provider path.
- SQLite run/session persistence.
- Failure persistence for LLM planning/synthesis exceptions.
- Artifact store for uploads, reports, and self-check outputs.
- FastAPI API and simple local Web UI.
- In-memory background job API for long local runs.
- Optional bearer-token API boundary for local/shared test deployments.
- Structured API error payloads.
- Queued-job cancellation and failed-job retry.
- SQLite-backed job status/result metadata.
- Compact API result payloads with opt-in debug detail.
- Span-like trace export for observability integrations.
- Deterministic eval CLI for CI.
- Serverless self-check suitable for smoke testing.
- Beginner and architecture documentation now cover setup, commands, code tour, and limitations.

## Remaining P0/P1 Backlog

These are the most important improvements before treating the project as a
production-like platform.

| Priority | Area | Work Needed | Reason |
| --- | --- | --- | --- |
| P0 | Durable API execution model | Replace in-process execution with a persistent queue/worker that can resume queued jobs after restart. | Job metadata persists, but task execution is still in-process. |
| P0 | Auth boundary | Add role-based authorization, audit identity, and deployment-grade auth middleware. | Token auth exists, but it is not RBAC or enterprise identity. |
| P0 | Upload hardening | Add parser process isolation and deeper Excel protections. | Upload chunking, content sniffing, parser timeout, and cell budget exist, but parsing still happens in-process. |
| P0 | Remote LLM redaction | Add per-tool result summaries and stricter outbound payload filtering. | Remote LLM calls should not receive full raw tool outputs by default. |
| P1 | Job operations | Add running-job cooperative cancellation, progress events, and timeout policy. | Queued cancellation and retry exist; running jobs still finish normally. |
| P1 | True streaming | Implement provider streaming and SSE/WebSocket event delivery. | Current `stream` path is streaming-ready but returns one final JSON response. |
| P1 | Strong parser limits | Add process-level parser kill and per-format parser profiles. | Current timeout raises to caller but cannot forcibly stop a stuck parser thread. |
| P1 | Tool result contracts | Define typed result models for major tools. | Reduces downstream assumptions and makes LLM summaries safer. |

## P2/P3 Backlog

| Priority | Area | Work Needed |
| --- | --- | --- |
| P2 | Provider ecosystem | Add Ollama, vLLM, LM Studio, OpenRouter adapters. |
| P2 | Workflow engine | Add graph executor with retryable nodes and resumable approvals. |
| P2 | Observability | Add trace dashboard and OpenTelemetry exporter package integration. |
| P2 | Project memory | Add searchable previous-run retrieval and explicit memory policy. |
| P2 | Semiconductor tools | Add wafer map, bin pareto, lot trend, recipe comparison, and defect clustering tools. |
| P3 | Packaging | Add lint/format config, type check, and release metadata. |
| P3 | UI | Replace simple inline HTML with a more maintainable frontend if the UI grows. |

## Recommended Next Sprint

The next practical sprint should focus on production shape, not more demo
analytics:

1. Replace in-process jobs with a durable queue/worker.
2. Add process-isolated parsing and stronger Excel protection.
3. Add role-based auth and audit identity.
4. Add true SSE/WebSocket streaming and provider streaming.
5. Add remote LLM payload minimization.

Those five changes would move the framework closer to a robust agent platform
without over-investing in placeholder semiconductor analysis logic.
