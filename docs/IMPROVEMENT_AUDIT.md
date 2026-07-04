# Semicon Agent Improvement Audit

This document records the empirical audit performed after core v4. It separates
items that were fixed immediately from items that remain as engineering backlog.

## Verification Matrix

The following checks were run against the repository:

| Check | Result |
| --- | --- |
| `python -m pip install -e ".[dev]"` | Passed |
| `python -m pip check` | Passed |
| `python -m pytest -p no:cacheprovider` | Passed, 47 tests |
| `python -m semicon_agent.self_check --data examples/sample_wafer.csv` | Passed |
| `semicon-agent-check --data examples/sample_wafer.csv` | Passed after editable reinstall |
| `semicon-agent "analyze yield and SPC" --data examples/sample_wafer.csv` | Passed |
| `semicon-agent --list-runs` | Passed |
| `semicon-agent-server --help` | Passed |
| Markdown local link check | Passed |
| `python -m compileall -q semicon_agent tests examples` | Passed |
| API TestClient audit: health/status/run/trace/artifact/job/security blocks | Passed |

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
- Serverless self-check suitable for smoke testing.
- Beginner and architecture documentation now cover setup, commands, code tour, and limitations.

## Remaining P0/P1 Backlog

These are the most important improvements before treating the project as a
production-like platform.

| Priority | Area | Work Needed | Reason |
| --- | --- | --- | --- |
| P0 | Durable API execution model | Replace in-memory jobs with a persistent queue/worker. | Current jobs are useful locally but disappear on process restart. |
| P0 | Auth boundary | Add authentication and role-based authorization before exposing the API beyond localhost. | Current API is suitable for local use, not shared deployment. |
| P0 | Upload hardening | Stream uploads to disk, sniff file signatures, enforce parser limits, and protect Excel parsing. | Current upload reads full content into memory and trusts extension. |
| P0 | Remote LLM redaction | Add per-tool result summaries and stricter outbound payload filtering. | Remote LLM calls should not receive full raw tool outputs by default. |
| P1 | Job operations | Add cancellation, retry, progress events, and timeout policy. | Current job API only supports create/list/get status. |
| P1 | True streaming | Implement provider streaming and SSE/WebSocket event delivery. | Current `stream` path is streaming-ready but returns one final JSON response. |
| P1 | Error taxonomy | Replace broad error strings with structured error codes and categories. | Better UI handling, retries, and user support. |
| P1 | Strong parser limits | Add parser timeout, cell limits, and content sniffing. | Row/column limits exist, but upload and parser hardening are still partial. |
| P1 | Tool result contracts | Define typed result models for major tools. | Reduces downstream assumptions and makes LLM summaries safer. |

## P2/P3 Backlog

| Priority | Area | Work Needed |
| --- | --- | --- |
| P2 | Provider ecosystem | Add Ollama, vLLM, LM Studio, OpenRouter adapters. |
| P2 | Workflow engine | Add graph executor with retryable nodes and resumable approvals. |
| P2 | Observability | Add trace dashboard or structured event export. |
| P2 | Project memory | Add previous-run retrieval and explicit memory policy. |
| P2 | Semiconductor tools | Add wafer map, bin pareto, lot trend, recipe comparison, and defect clustering tools. |
| P3 | Packaging | Add CI workflow, lint/format config, and release metadata. |
| P3 | UI | Replace simple inline HTML with a more maintainable frontend if the UI grows. |

## Recommended Next Sprint

The next practical sprint should focus on production shape, not more demo
analytics:

1. Replace in-memory jobs with a durable queue/worker.
2. Add compact/default API payloads and a debug flag for full trace payloads.
3. Add upload streaming, content sniffing, parser timeout, and stronger Excel protection.
4. Add a minimal auth boundary for non-local server use.
5. Add structured error codes and cancellation/retry controls.

Those five changes would move the framework closer to a robust agent platform
without over-investing in placeholder semiconductor analysis logic.
