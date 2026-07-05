# 최신 에이전트 기준 TODO와 구현 내역

이 문서는 2026년 기준 최신 에이전트 프레임워크에서 중요하게 다루는 기능을 기준으로
`semicon-agent`에 무엇을 보강했는지 정리한다.

참고한 기준은 다음과 같다.

- OpenAI Agents SDK: orchestration, handoffs, guardrails, human review, state, observability
  - <https://developers.openai.com/api/docs/guides/agents>
  - <https://openai.github.io/openai-agents-python/tracing/>
  - <https://openai.github.io/openai-agents-python/guardrails/>
- Model Context Protocol: tools/resources/prompts를 표준 인터페이스로 연결
  - <https://modelcontextprotocol.io/docs/getting-started/intro>
- LangGraph/LangChain: durable execution, persistence, human-in-the-loop
  - <https://docs.langchain.com/oss/python/langgraph/overview>
  - <https://docs.langchain.com/oss/python/langgraph/persistence>
  - <https://docs.langchain.com/oss/python/langchain/human-in-the-loop>
- LlamaIndex workflows: workflow state, human input event, tool-driven agent 구성
  - <https://developers.llamaindex.ai/python/framework/understanding/agent/human_in_the_loop/>
- OWASP LLM Top 10: prompt injection, sensitive information disclosure, insecure plugin/tool design
  - <https://owasp.org/www-project-top-10-for-large-language-model-applications/>
- OpenTelemetry AI agent observability: GenAI/agent trace 표준화 방향
  - <https://opentelemetry.io/blog/2025/ai-agent-observability/>

## 핵심 방향

최신 에이전트의 경쟁력은 “모델이 똑똑하다”만으로 결정되지 않는다. 실제로는 다음
운영 기능이 중요하다.

| 축 | 의미 | 현재 처리 |
| --- | --- | --- |
| Tool interface | LLM이 직접 실행하지 않고 runtime이 검증 후 tool 실행 | `ToolRegistry`, `ToolRuntime` |
| Permission boundary | 파일/외부/API/위험 작업을 정책으로 제한 | `ExecutionPolicy`, approval provider |
| Human-in-the-loop | 위험 작업 전 승인/거절/수정 가능 | CLI approval provider |
| Persistence | run, event, artifact를 저장해 재현 가능하게 함 | SQLite run store, artifact store |
| Async execution | 긴 작업을 background job으로 실행 | `/api/jobs` |
| Job controls | 실패/대기/실행/재시작 작업을 제어 | cancel/retry/resume/progress 추가 |
| Observability | 실행 과정을 trace로 확인 | event trace, span-like export |
| Security | LLM/tool/API 경계를 기본 차단 | client LLM/risk 차단, token auth |
| Evals | 에이전트 동작을 자동 회귀 검증 | `semicon_agent.eval` |
| CI | 변경 때마다 테스트 자동 실행 | GitHub Actions |

## 이번에 구현한 TODO

| 상태 | TODO | 구현 위치 | 검증 |
| --- | --- | --- | --- |
| 완료 | Optional API bearer token | `semicon_agent/server/api.py`, `config.py`, `server/__main__.py` | `test_api_token_protects_api_routes` |
| 완료 | Structured API errors | `semicon_agent/core/errors.py`, `server/api.py` | missing job/run/auth 테스트 |
| 완료 | Upload content sniffing | `semicon_agent/core/artifacts.py` | artifact/upload tests |
| 완료 | Direct file size guard | `semicon_agent/tools/semiconductor.py` | file-size limit test |
| 완료 | Job cancellation | `semicon_agent/server/jobs.py`, `server/api.py` | queued cancellation test |
| 완료 | Job retry | `semicon_agent/server/jobs.py`, `server/api.py` | failed retry test |
| 완료 | Span-like trace export | `semicon_agent/core/observability.py`, `/api/runs/{run_id}/otel` | run API test |
| 완료 | Previous-run context option | `RunRequest.include_previous_runs` | covered through API model path |
| 완료 | Deterministic eval CLI | `semicon_agent/eval.py`, `pyproject.toml` | `tests/test_eval.py` |
| 완료 | GitHub Actions CI | `.github/workflows/test.yml` | workflow file added |
| 완료 | Durable job metadata | `semicon_agent/server/jobs.py` | app recreation test |
| 완료 | Compact API payload | `semicon_agent/server/api.py` | compact/debug response tests |
| 완료 | Parser timeout/cell budget | `semicon_agent/tools/semiconductor.py` | parser/cell limit tests |
| 완료 | Chunked upload write/cleanup | `semicon_agent/server/api.py`, `core/artifacts.py` | invalid upload cleanup test |
| 완료 | Role-based API tokens | `semicon_agent/server/auth.py`, `server/api.py` | read/write route tests |
| 완료 | Remote LLM payload minimization | `semicon_agent/llm/privacy.py`, `llm/open_model.py` | privacy/open-model tests |
| 완료 | Process-isolated parser mode | `semicon_agent/tools/table_parser.py`, `tools/semiconductor.py` | process parser success/timeout tests |
| 완료 | Resumable persisted jobs | `semicon_agent/server/jobs.py`, `server/api.py` | queued/running resume and persisted retry tests |
| 완료 | Running job cooperative cancellation | `core/cancellation.py`, `core/agent.py`, `server/jobs.py` | running cancel and cancelled-run persistence tests |

## 아직 남은 고우선순위 TODO

이 항목들은 “풀패키지 운영형”으로 가려면 계속 해야 한다.

| 우선순위 | TODO | 이유 |
| --- | --- | --- |
| P0 | External durable queue/worker | queued/running job payload 재개는 들어갔지만, 별도 worker process, 분산 큐, exactly-once 실행 보장은 없다. |
| P0 | Deployment auth | role token은 들어갔지만 사용자 ID, rotation, expiry, enterprise identity 연동은 없다. |
| P0 | Full upload streaming | API는 chunk write와 process parser mode를 지원하지만, Excel 검증은 여전히 로컬 파일 archive 전체를 검사한다. |
| P0 | Remote LLM policy controls | payload 요약은 들어갔지만 tool별 outbound allowlist와 tenant별 정책은 없다. |
| P1 | True SSE/WebSocket streaming | 현재 streaming-ready path는 있지만 HTTP 실시간 이벤트가 아니다. |
| P1 | Job timeout policy | running job 취소 요청은 cooperative하게 처리되지만, hard timeout 정책은 없다. |
| P1 | Durable human approval | approval 후 resume 가능한 checkpoint runtime이 필요하다. |
| P1 | Provider adapters | Ollama, vLLM, LM Studio, OpenRouter 등 provider별 adapter가 필요하다. |
| P1 | Tool result typed contracts | 주요 tool 결과를 Pydantic model로 고정하면 UI/LLM 요약 안정성이 좋아진다. |
| P2 | Semiconductor tool pack | wafer map, bin pareto, lot trend, recipe comparison, defect clustering 등이 필요하다. |

## 판단

현재 코드는 “반도체 데이터 분석 업무용 에이전트 프레임워크의 강한 프로토타입”이다.
기능 데모 수준을 넘어 agent runtime, 정책, trace, artifact, API, job metadata persistence,
queued/running job resume, running job cooperative cancellation, parser guard, eval, CI까지 들어갔다.

다만 “최고 수준 production agent platform”이라고 부르려면 durable worker execution, enterprise auth,
streaming transport, provider ecosystem, per-format parser sandbox policy, remote LLM policy controls가 더 필요하다.
